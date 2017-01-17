from multiprocessing import cpu_count
from werkzeug import secure_filename
from flask import Response, g, request, render_template, redirect, abort, current_app
from .service_module import register_service

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


app = sample_management = register_service("sample_management", __name__)


@sample_management.route("/add_sample", methods=["POST"])
def post_add_sample():
    """Handle an uploaded sample file

    Returns
    -------
    TYPE : Description
    """
    sample_name = request.values['sample-name']
    if sample_name == "":
        sample_name = request.files['observed-ions-file'].filename
    if sample_name == "":
        current_app.logger.info("No sample name could be extracted. %r", request.values)
        return abort(400)
    secure_name = secure_filename(sample_name)
    path = g.manager.get_temp_path(secure_name)
    request.files['observed-ions-file'].save(path)
    # dest = g.manager.get_sample_path(sample_name)

    # Construct the task with a callback to add the processed sample
    # to the set of project samples

    start_time = float(request.values['start-time'])
    end_time = float(request.values['end-time'])

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

    n_workers = 5
    if cpu_count() < n_workers:
        n_workers = cpu_count()

    task = PreprocessMSTask(
        path, g.manager.connection_bridge,
        averagine, start_time, end_time, maximum_charge_state,
        sample_name, msn_averagine, ms1_score_threshold,
        msn_score_threshold, missed_peaks, n_processes=n_workers, callback=lambda: 0)

    g.manager.add_task(task)
    return Response("Task Scheduled")


@sample_management.route("/add_sample")
def add_sample():
    return render_template("add_sample_form.templ")


@app.route("/view_sample/<int:sample_run_id>")
def view_sample(sample_run_id):
    d = DatabaseScanDeserializer(g.manager.connection_bridge, sample_run_id=sample_run_id)
    scan_levels = dict(
        d.query(MSScan.ms_level, func.count(MSScan.scan_id)).filter(
        MSScan.sample_run_id == sample_run_id).group_by(MSScan.ms_level))
    chromatograms = draw_raw_chromatograms(sample_run_id)
    return render_template(
        "view_sample_run/overview.templ", sample_run=d.sample_run, scan_levels=scan_levels,
        chromatograms=chromatograms)


@sample_management.route("/draw_raw_chromatograms/<int:sample_run_id>")
def draw_raw_chromatograms(sample_run_id):
    d = DatabaseScanDeserializer(g.manager.connection_bridge, sample_run_id=sample_run_id)
    average_abundance = d.query(func.sum(DeconvolutedPeak.intensity) / func.count(DeconvolutedPeak.id)).join(MSScan).filter(
        MSScan.sample_run_id == sample_run_id, MSScan.ms_level == 1).scalar()
    ex = ChromatogramExtractor(d, minimum_intensity=float(average_abundance) * 8., minimum_mass=1000)
    chroma = ex.run()
    ax = figax()

    window_width = 0.01
    windows = [DeconvolutedPeak.neutral_mass.between(i.mass() - window_width, i.mass() + window_width)
               for i in standard_oxonium_ions]
    union = windows[0]
    for i in windows[1:]:
        union |= i

    oxonium_ions_q = d.query(MSScan.scan_time, func.sum(DeconvolutedPeak.intensity)).join(DeconvolutedPeak).filter(
        MSScan.sample_run_id == sample_run_id,
        MSScan.ms_level == 2,
        union).group_by(MSScan.scan_time).all()

    a = SmoothingChromatogramArtist([ex.total_ion_chromatogram], ax=ax, colorizer=lambda *a, **k: 'lightblue')
    a.draw(label_function=lambda *a, **kw: "")
    rt, intens = ex.total_ion_chromatogram.as_arrays()
    a.draw_generic_chromatogram(
        "TIC", rt, intens, 'lightblue')
    a.ax.set_ylim(0, max(intens) * 1.1)

    if oxonium_ions_q:
        oxonium_axis = ax.twinx()
        stub = SimpleChromatogram(ex.total_ion_chromatogram.time_converter)
        for key in ex.total_ion_chromatogram:
            stub[key] = 0
        oxonium_artist = SmoothingChromatogramArtist([stub], ax=oxonium_axis).draw(label_function=lambda *a, **kw: "")
        rt, intens = zip(*oxonium_ions_q)
        oxonium_axis.set_ylim(0, max(intens) * 1.1)
        oxonium_axis.yaxis.tick_right()
        oxonium_axis.axes.spines['right'].set_visible(True)
        oxonium_axis.set_ylabel("Oxonium Abundance", fontsize=18)
        oxonium_artist.draw_generic_chromatogram(
            "Oxonium Ions", rt, intens, 'green')

    fig = a.ax.get_figure()
    fig.set_figwidth(10)
    return svg_plot(ax, patchless=True, bbox_inches='tight')
