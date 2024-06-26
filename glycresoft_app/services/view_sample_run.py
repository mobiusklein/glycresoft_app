import numpy as np
from flask import Response, g, request, render_template, redirect, abort, current_app, jsonify
from glycresoft_app.application_manager import ApplicationManager
from glycresoft_app.project.sample import SampleRunRecord

from glycresoft_app.task.task_process import Message

from glycresoft.plotting import (
    AbundantLabeler, SmoothingChromatogramArtist, figax)
from glycresoft.plotting.lcms_map import LCMSMapArtist

from glycresoft.trace import ChromatogramExtractor
from glycresoft.chromatogram_tree import SimpleChromatogram
from glycresoft.tandem.oxonium_ions import standard_oxonium_ions

from glycresoft.output import SimpleChromatogramCSVSerializer

import ms_deisotope
from ms_deisotope.output.mzml import ProcessedMzMLDeserializer

from glycresoft_app.report import png_plot

from .collection_view import ViewCache, SimpleViewBase
from .service_module import register_service
from .file_exports import safepath

app = view_sample_run = register_service("view_sample_run", __name__)


VIEW_CACHE = ViewCache()


class SampleView(SimpleViewBase):
    record: SampleRunRecord

    def __init__(self, record, minimum_mass=None, abundance_threshold=None):
        SimpleViewBase.__init__(self)
        self.record = record
        self.reader = ProcessedMzMLDeserializer(record.path)
        self.scan_levels = {
            "1": len(self.reader.extended_index.ms1_ids),
            "N": len(self.reader.extended_index.msn_ids)
        }
        self.minimum_mass = minimum_mass
        self.abundance_threshold = abundance_threshold
        self._chromatograms = None
        self.chromatograms = None
        self.total_ion_chromatogram = None
        self.oxonium_ion_chromatogram = None
        self.chromatogram_artist = None
        self.oxonium_ion_artist = None

    @property
    def chromatograms(self):
        if self._chromatograms is None:
            self.build_chromatograms()
        return self._chromatograms

    @chromatograms.setter
    def chromatograms(self, value):
        self._chromatograms = value

    def _estimate_threshold(self):
        intensity_accumulator = []
        mz_accumulator = []
        charge_accumulator = []
        if not self.reader.extended_index.ms1_ids:
            self.mass_array = np.array([])
            self.charge_array = np.array([])
            self.intensity_array = np.array([])
            self.abundance_threshold = 0
            self.minimum_mass = 0
            return
        for scan_id in self.reader.extended_index.ms1_ids:
            header = self.reader.get_scan_header_by_id(scan_id)
            intensity_accumulator.extend(header.arrays.intensity)
            mz_accumulator.extend(header.arrays.mz)
            try:
                charge_accumulator.extend(header['charge array'])
            except Exception:
                charge_accumulator.extend(
                    np.ones_like(header.arrays.mz) * header.polarity)

        mass_array = ms_deisotope.neutral_mass(
            np.array(mz_accumulator),
            np.array(charge_accumulator))
        self.mass_array = mass_array
        self.charge_array = np.array(charge_accumulator, dtype=int)
        self.intensity_array = np.array(intensity_accumulator)
        if self.abundance_threshold is None and intensity_accumulator:
            self.abundance_threshold = np.percentile(intensity_accumulator, 90)
        if self.minimum_mass is None and len(mass_array):
            counts, bins = np.histogram(self.mass_array)
            self.minimum_mass = np.average(bins[:-1], weights=counts)

    def build_oxonium_ion_chromatogram(self):
        window_width = 0.01
        ox_time = []
        ox_current = []
        for scan_id in self.reader.extended_index.msn_ids:
            try:
                scan = self.reader.get_scan_header_by_id(scan_id)
            except AttributeError:
                print("Unable to resolve scan id %r" % scan_id)
                break
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
        chromatograms = list(self.chromatograms)
        if len(chromatograms):
            chromatograms.append(self.total_ion_chromatogram)
            chromatograms = [chrom for chrom in chromatograms if len(chrom) > 0]
            a = SmoothingChromatogramArtist(
                chromatograms, ax=ax, colorizer=lambda *a, **k: 'lightblue')
            a.draw(label_function=lambda *a, **kw: "")
            rt, intens = self.total_ion_chromatogram.as_arrays()
            a.draw_generic_chromatogram(
                "TIC", rt, intens, 'lightblue')
            a.ax.set_ylim(0, max(intens) * 1.1)
            chromatogram_artist = a
            fig = chromatogram_artist.ax.get_figure()
            fig.set_figwidth(10)
            fig.set_figheight(5)
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
        else:
            ax.text(0.5, 0.5, "No chromatograms extracted", ha='center', fontsize=16)
            ax.axis('off')
        return png_plot(ax, patchless=True, bbox_inches='tight', width=12, height=8)

    def build_chromatograms(self):
        if self.abundance_threshold is None:
            self._estimate_threshold()
        manager: ApplicationManager = g.manager
        manager.add_message(Message(f"Extracting chromatograms for {self.record.name}", "update"))
        ex = ChromatogramExtractor(
            self.reader, minimum_intensity=self.abundance_threshold,
            minimum_mass=self.minimum_mass)
        self.chromatograms = ex.run()
        self.total_ion_chromatogram = ex.total_ion_chromatogram

        if self.reader.extended_index.msn_ids:
            self.build_oxonium_ion_chromatogram()

    def draw_lcms_map(self):
        if self.abundance_threshold is None:
            self._estimate_threshold()
        ax = figax()
        artist = LCMSMapArtist.from_peak_loader(self.reader, threshold=self.abundance_threshold / 2., ax=ax)
        artist.draw()
        return png_plot(ax, patchless=True, bbox_inches='tight', width=10, height=10)


def get_view(uuid):
    try:
        view = VIEW_CACHE[uuid]
        return view
    except KeyError:
        record = g.manager.sample_manager.get(uuid)
        VIEW_CACHE[uuid] = SampleView(record)
        return VIEW_CACHE[uuid]


@app.route("/view_sample/<sample_run_uuid>")
def view_sample(sample_run_uuid):
    view = get_view(sample_run_uuid)
    return render_template(
        "view_sample_run/overview.templ",
        sample_run=view.record,
        scan_levels=view.scan_levels,
        chromatograms=view.draw_chromatograms())


@app.route("/view_sample/<sample_run_uuid>/to-csv")
def to_csv(sample_run_uuid):
    file_name = _export_csv(sample_run_uuid)[0]
    return jsonify(filename=file_name)


def _export_csv(sample_run_uuid):
    view = get_view(sample_run_uuid)
    with view:
        g.add_message(Message("Building Chromatogram CSV Export", "update"))

        file_name = "%s-chromatograms.csv" % (view.record.name)
        path = safepath(g.manager.get_temp_path(file_name))

        SimpleChromatogramCSVSerializer(
            open(path, 'wb'), view.chromatograms).start()
    return [file_name]


@app.route("/view_sample/<sample_run_uuid>/chromatogram_table")
def chromatogram_table(sample_run_uuid):
    view = get_view(sample_run_uuid)
    return render_template(
        "view_sample_run/chromatogram_table.templ",
        chromatogram_collection=view.chromatograms)


def binsearch(array, value, tol=0.1):
    lo = 0
    hi = len(array)
    while hi != lo:
        mid = (hi + lo) // 2
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

    ex = ChromatogramExtractor(
        reader, minimum_intensity=threshold, minimum_mass=300)
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
    return png_plot(ax, patchless=True, bbox_inches='tight')
