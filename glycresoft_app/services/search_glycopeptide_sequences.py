from flask import Response, g, request, render_template

from .form_cleaners import remove_empty_rows, intify
from .service_module import register_service

from ..task.analyze_glycopeptide_sequence_data import AnalyzeGlycopeptideSequenceTask

app = search_glycopeptide_sequences = register_service("search_glycopeptide_sequences", __name__)


@app.route("/search_glycopeptide_sequences/run_search")
def run_search():
    return render_template(
        "glycopeptide_search/run_search.templ",
        manager=g.manager)


@app.route("/search_glycopeptide_sequences/run_search", methods=["POST"])
def run_search_post():
    data = request.values
    matching_tolerance = float(data.get("mass-matching-tolerance", 10))
    if matching_tolerance > 1e-4:
        matching_tolerance *= 1e-6

    grouping_tolerance = float(data.get("peak-grouping-tolerance", 15))
    if grouping_tolerance > 1e-4:
        grouping_tolerance *= 1e-6

    ms2_matching_tolerance = float(data.get("ms2-tolerance", 20))
    if ms2_matching_tolerance > 1e-4:
        ms2_matching_tolerance *= 1e-6

    psm_fdr_threshold = float(data.get("q-value-threshold", 0.05))

    hypothesis_id = int(data.get("hypothesis_choice"))
    sample_ids = list(map(int, data.getlist("samples")))
    for sample_id in sample_ids:
        task = AnalyzeGlycopeptideSequenceTask(
            g.manager.connection_bridge, sample_id, hypothesis_id,
            None, grouping_error_tolerance=grouping_tolerance, mass_error_tolerance=matching_tolerance,
            msn_mass_error_tolerance=ms2_matching_tolerance, psm_fdr_threshold=psm_fdr_threshold,
            job_name_part=g.manager.get_next_job_number())
        g.manager.add_task(task)
    return Response("Tasks Scheduled")
