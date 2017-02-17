import re
import os

from uuid import uuid4
from multiprocessing import cpu_count

import numpy as np

from werkzeug import secure_filename
from flask import Response, g, request, render_template, redirect, abort, current_app
from .service_module import register_service
from .form_cleaners import make_unique_name, touch_file
from .collection_view import ViewCache

from glycresoft_app.utils.state_transfer import request_arguments_and_context
from glycresoft_app.task.preprocess_mzml import PreprocessMSTask
from glycresoft_app.report import svg_plot

from glycan_profiling.serialize import (
    DatabaseBoundOperation, DatabaseScanDeserializer,
    MSScan, SampleRun, DeconvolutedPeak, func)

from glycan_profiling.plotting import AbundantLabeler, SmoothingChromatogramArtist, figax
from glycan_profiling.trace import ChromatogramExtractor
from glycan_profiling.chromatogram_tree import SimpleChromatogram
from glycan_profiling.tandem.spectrum_matcher_base import standard_oxonium_ions

from ms_deisotope.output.mzml import ProcessedMzMLDeserializer


app = sample_management = register_service("sample_management", __name__)


VIEW_CACHE = ViewCache()


class SampleView(object):
    def __init__(self, record):
        self.record = record
        self.reader = ProcessedMzMLDeserializer(record.path)
        self.scan_levels = {
            1: len(self.reader.extended_index.ms1_ids),
            "N": len(self.reader.extended_index.msn_ids)
        }
        self.abundance_threshold = None
        self.chromatograms = None
        self.total_ion_chromatogram = None
        self.oxonium_ion_chromatogram = None
        self.chromatogram_artist = None
        self.oxonium_ion_artist = None

    def _estimate_threshold(self):
        acc = []
        for scan_id in self.reader.extended_index.ms1_ids:
            header = self.reader.get_scan_header_by_id(scan_id)
            acc.extend(header.arrays[1])

        self.abundance_threshold = np.percentile(acc, 90)

    def build_oxonium_ion_chromatogram(self):
        window_width = 0.01
        ox_time = []
        ox_current = []
        for scan_id in self.reader.extended_index.msn_ids:
            scan = self.reader.get_scan_header_by_id(scan_id)
            mz, intens = scan.arrays
            total = 0
            for ion in standard_oxonium_ions:
                coords = sweep(mz, ion.mass() + 1.007, window_width)
                total += intens[coords].sum()
            ox_time.append(scan.scan_time)
            ox_current.append(total)
        self.oxonium_ion_chromatogram = list(
            map(np.array, (
                ox_time,
                ox_current)))

    def draw_chromatograms(self):
        if self.chromatograms is None:
            self.build_chromatograms()
        ax = figax()
        a = SmoothingChromatogramArtist(
            list(self.chromatograms) + [
                self.total_ion_chromatogram
            ], ax=ax, colorizer=lambda *a, **k: 'lightblue')
        a.draw(label_function=lambda *a, **kw: "")
        rt, intens = self.total_ion_chromatogram.as_arrays()
        a.draw_generic_chromatogram(
            "TIC", rt, intens, 'lightblue')
        a.ax.set_ylim(0, max(intens) * 1.1)
        chromatogram_artist = a

        # if self.reader.extended_index.msn_ids:
        #     oxonium_axis = ax.twinx()
        #     stub = SimpleChromatogram(
        #         self.total_ion_chromatogram.time_converter)
        #     for key in self.total_ion_chromatogram:
        #         stub[key] = 0
        #     oxonium_ion_artist = SmoothingChromatogramArtist(
        #         [stub],
        #         ax=oxonium_axis).draw(
        #         label_function=lambda *a, **kw: "")
        #     rt, intens = self.oxonium_ion_chromatogram
        #     oxonium_axis.set_ylim(0, max(intens) * 1.1)
        #     oxonium_axis.yaxis.tick_right()
        #     oxonium_axis.axes.spines['right'].set_visible(True)
        #     oxonium_axis.set_ylabel("Oxonium Abundance", fontsize=18)
        #     oxonium_ion_artist.draw_generic_chromatogram(
        #         "Oxonium Ions", rt, intens, 'green')
        fig = chromatogram_artist.ax.get_figure()
        fig.set_figwidth(10)
        fig.set_figheight(5)
        return svg_plot(ax, patchless=True, bbox_inches='tight')

    def build_chromatograms(self):
        if self.abundance_threshold is None:
            self._estimate_threshold()
        ex = ChromatogramExtractor(
            self.reader, minimum_intensity=self.abundance_threshold,
            minimum_mass=1000)
        self.chromatograms = ex.run()
        self.total_ion_chromatogram = ex.total_ion_chromatogram

        if self.reader.extended_index.msn_ids:
            self.build_oxonium_ion_chromatogram()


def get_view(uuid):
    try:
        view = VIEW_CACHE[uuid]
        return view
    except KeyError:
        record = g.manager.sample_manager.get(uuid)
        VIEW_CACHE[uuid] = SampleView(record)
        return VIEW_CACHE[uuid]


@sample_management.route("/add_sample", methods=["POST"])
def post_add_sample():
    """Handle an uploaded sample file

    Returns
    -------
    Response
    """
    sample_name = request.values['sample-name']
    if sample_name == "":
        sample_name = request.files['observed-ions-file'].filename
    if sample_name == "":
        current_app.logger.info("No sample name could be extracted. %r", request.values)
        return abort(400)

    sample_name = g.manager.make_unique_sample_name(
        sample_name)

    secure_name = secure_filename(sample_name)
    path = g.manager.get_temp_path(secure_name)
    request.files['observed-ions-file'].save(path)
    storage_path = g.manager.get_sample_path(
        re.sub(r"[\s\(\)]", "_", secure_name) + '-%s.mzML')

    storage_path = make_unique_name(storage_path)
    touch_file(storage_path)

    # Construct the task with a callback to add the processed sample
    # to the set of project samples

    start_time = float(request.values['start-time'])
    end_time = float(request.values['end-time'])

    extract_only_tandem_envelopes = bool(request.values.get("msms-features-only", False))

    prefab_averagine = request.values['ms1-averagine']
    prefab_msn_averagine = request.values['msn-averagine']

    custom_ms1_averagine_formula = request.values['ms1-averagine-custom']
    custom_msn_averagine_formula = request.values['msn-averagine-custom']

    if custom_ms1_averagine_formula:
        averagine = custom_ms1_averagine_formula
    else:
        averagine = prefab_averagine

    if custom_msn_averagine_formula:
        msn_averagine = custom_msn_averagine_formula
    else:
        msn_averagine = prefab_msn_averagine

    ms1_score_threshold = float(request.values['ms1-minimum-isotopic-score'])
    msn_score_threshold = float(request.values['msn-minimum-isotopic-score'])

    missed_peaks = int(request.values['missed-peaks'])
    maximum_charge_state = int(request.values['maximum-charge-state'])

    ms1_background_reduction = float(request.values.get(
        'ms1-background-reduction', 5.))

    n_workers = g.manager.configuration.get("preprocessor_worker_count", 6)
    if cpu_count() < n_workers:
        n_workers = cpu_count()

    task = PreprocessMSTask(
        path, g.manager.connection_bridge,
        averagine, start_time, end_time, maximum_charge_state,
        sample_name, msn_averagine, ms1_score_threshold,
        msn_score_threshold, missed_peaks, n_processes=n_workers,
        storage_path=storage_path, extract_only_tandem_envelopes=extract_only_tandem_envelopes,
        ms1_background_reduction=ms1_background_reduction,
        callback=lambda: 0)

    g.add_task(task)
    return Response("Task Scheduled")


@sample_management.route("/add_sample")
def add_sample():
    return render_template("add_sample_form.templ")


@app.route("/view_sample/<sample_run_uuid>")
def view_sample(sample_run_uuid):
    view = get_view(sample_run_uuid)
    return render_template(
        "view_sample_run/overview.templ",
        sample_run=view.record,
        scan_levels=view.scan_levels,
        chromatograms=view.draw_chromatograms())


@sample_management.route("/draw_raw_chromatograms/<sample_run_uuid>")
def draw_raw_chromatograms(sample_run_uuid):
    pass


def binsearch(array, value, tol=0.1):
    lo = 0
    hi = len(array)
    while hi != lo:
        mid = (hi + lo) / 2
        point = array[mid]
        if abs(value - point) < tol:
            return mid
        elif hi - lo == 1:
            return mid
        elif point > value:
            hi = mid
        else:
            lo = mid
    raise ValueError()


def sweep(array, value, tol):
    ix = binsearch(array, value, tol)
    start = ix
    while array[start] > (value - tol) and start > 0:
        start -= 1
    end = ix
    while array[end] < (value + tol) and end < (len(array) - 1):
        end += 1
    return slice(start, end)


def render_chromatograms(reader):
    acc = []
    for scan_id in reader.extended_index.ms1_ids:
        header = reader.get_scan_header_by_id(scan_id)
        acc.extend(header.arrays[1])

    threshold = np.percentile(acc, 90)

    ex = ChromatogramExtractor(reader, minimum_intensity=threshold, minimum_mass=1000)
    chroma = ex.run()

    window_width = 0.01

    ax = figax()
    a = SmoothingChromatogramArtist(
        list(chroma) + [
            ex.total_ion_chromatogram
        ], ax=ax, colorizer=lambda *a, **k: 'lightblue')
    a.draw(label_function=lambda *a, **kw: "")
    rt, intens = ex.total_ion_chromatogram.as_arrays()
    a.draw_generic_chromatogram(
        "TIC", rt, intens, 'lightblue')
    a.ax.set_ylim(0, max(intens) * 1.1)

    if reader.extended_index.msn_ids:
        ox_time = []
        ox_current = []
        for scan_id in reader.extended_index.msn_ids:
            scan = reader.get_scan_header_by_id(scan_id)
            mz, intens = scan.arrays
            total = 0
            for ion in standard_oxonium_ions:
                coords = sweep(mz, ion.mass() + 1.007, window_width)
                total += intens[coords].sum()
            ox_time.append(scan.scan_time)
            ox_current.append(total)
        oxonium_axis = ax.twinx()
        stub = SimpleChromatogram(ex.total_ion_chromatogram.time_converter)
        for key in ex.total_ion_chromatogram:
            stub[key] = 0
        oxonium_artist = SmoothingChromatogramArtist([stub], ax=oxonium_axis).draw(label_function=lambda *a, **kw: "")
        rt, intens = ox_time, ox_current
        oxonium_axis.set_ylim(0, max(intens) * 1.1)
        oxonium_axis.yaxis.tick_right()
        oxonium_axis.axes.spines['right'].set_visible(True)
        oxonium_axis.set_ylabel("Oxonium Abundance", fontsize=18)
        oxonium_artist.draw_generic_chromatogram(
            "Oxonium Ions", rt, intens, 'green')

    fig = a.ax.get_figure()
    fig.set_figwidth(10)
    return svg_plot(ax, patchless=True, bbox_inches='tight')
