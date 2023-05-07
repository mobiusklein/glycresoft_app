import re
import json
from typing import Union
from flask import Response, g, request, render_template, current_app

try:
    from werkzeug import secure_filename
except ImportError:
    from werkzeug.utils import secure_filename

from glycan_profiling.cli.validators import validate_glycopeptide_tandem_scoring_function

from .form_cleaners import remove_empty_rows, make_unique_name, float_or, try_int, float_or_infinity
from .service_module import register_service

from ..task.analyze_glycopeptide_sequence_data import AnalyzeGlycopeptideSequenceTask, GlycopeptideSearchStrategyEnum

app = search_glycopeptide_sequences = register_service("search_glycopeptide_sequences", __name__)


@app.route("/search_glycopeptide_sequences/run_search")
def run_search():
    return render_template(
        "glycopeptide_search/run_search.templ",
        manager=g.manager)


@app.route("/search_glycopeptide_sequences/run_search", methods=["POST"])
def run_search_post():
    data = request.values
    matching_tolerance = float(data.get("ms1-tolerance", 10))
    if matching_tolerance > 1e-4:
        matching_tolerance *= 1e-6

    grouping_tolerance = float(data.get("peak-grouping-tolerance", 15))
    if grouping_tolerance > 1e-4:
        grouping_tolerance *= 1e-6

    ms2_matching_tolerance = float(data.get("ms2-tolerance", 20))
    if ms2_matching_tolerance > 1e-4:
        ms2_matching_tolerance *= 1e-6

    psm_fdr_threshold = float(data.get("q-value-threshold", 0.05))

    minimum_search_mass = float_or(
        data.get("minimum-search-mass", 1000.0), 1000.0)
    maximum_search_mass = float_or_infinity(
        data.get("maximum-search-mass", float('inf')))

    use_peptide_mass_filter = data.get("peptide-mass-filter")
    if use_peptide_mass_filter == 'on':
        use_peptide_mass_filter = True
    else:
        use_peptide_mass_filter = False

    permute_decoy_glycan_fragments = data.get("permute-decoy-glycan-fragments")
    if permute_decoy_glycan_fragments == 'on':
        permute_decoy_glycan_fragments = True
    else:
        permute_decoy_glycan_fragments = False

    include_rare_signature_ions = data.get("include-rare-signature-ions")
    if include_rare_signature_ions == 'on':
        include_rare_signature_ions = True
    else:
        include_rare_signature_ions = False

    model_retention_time = data.get("model-retention-time")
    if model_retention_time == 'on':
        model_retention_time = True
    else:
        model_retention_time = False

    msn_scoring_model_name = data.get("msn-scoring-model")
    tandem_scoring_model, msn_scoring_options = validate_glycopeptide_tandem_scoring_function(None, msn_scoring_model_name)
    if msn_scoring_options:
        current_app.logger.warning("Requested scoring model %s has unused options %s", msn_scoring_model_name, msn_scoring_options)

    hypothesis_uuid = (data.get("hypothesis_choice"))
    hypothesis_record = g.manager.hypothesis_manager.get(hypothesis_uuid)
    hypothesis_name = hypothesis_record.name

    decoy_hypothesis_record = hypothesis_record.decoy_hypothesis
    decoy_hypothesis_path = None
    decoy_hypothesis_id = None
    if decoy_hypothesis_record is not None:
        decoy_hypothesis_path = decoy_hypothesis_record.path
        decoy_hypothesis_id = decoy_hypothesis_record.id

    search_strategy = GlycopeptideSearchStrategyEnum.classic
    if decoy_hypothesis_record and not hypothesis_record.is_full_crossproduct:
        search_strategy = GlycopeptideSearchStrategyEnum.multipart
    elif decoy_hypothesis_record:
        search_strategy = GlycopeptideSearchStrategyEnum.classic_comparison

    sample_records = list(map(g.manager.sample_manager.get, data.getlist("samples")))

    minimum_oxonium_threshold = float(data.get("minimum-oxonium-threshold", 0.05))
    workload_size = int(data.get("batch-size", 1000))

    mass_shift_data = list(zip(data.getlist('mass_shift_name'),
                               data.getlist('mass_shift_max_count')))
    mass_shift_data = mass_shift_data[:-1]
    mass_shift_data = [(a, try_int(b)) for a, b in mass_shift_data if a and b]

    for sample_record in sample_records:
        sample_name = sample_record.name
        job_number = g.manager.get_next_job_number()
        name_prefix = "%s at %s (%d)" % (hypothesis_name, sample_name, job_number)
        cleaned_prefix = re.sub(r"[\s\(\)]", "_", name_prefix)
        name_template = g.manager.get_results_path(
            secure_filename(cleaned_prefix) + "_%s.analysis.db")
        storage_path = make_unique_name(name_template)

        task = AnalyzeGlycopeptideSequenceTask(
            hypothesis_record.path, sample_record.path, hypothesis_record.id,
            storage_path, name_prefix,
            grouping_error_tolerance=grouping_tolerance,
            mass_error_tolerance=matching_tolerance,
            msn_mass_error_tolerance=ms2_matching_tolerance,
            psm_fdr_threshold=psm_fdr_threshold,
            minimum_oxonium_threshold=minimum_oxonium_threshold,
            workload_size=workload_size,
            use_peptide_mass_filter=use_peptide_mass_filter,
            mass_shifts=mass_shift_data,
            permute_decoy_glycan_fragments=permute_decoy_glycan_fragments,
            job_name_part=job_number,
            include_rare_signature_ions=include_rare_signature_ions,
            model_retention_time=model_retention_time,
            search_strategy=search_strategy,
            decoy_database_connection=decoy_hypothesis_path,
            decoy_hypothesis_id=decoy_hypothesis_id,
            tandem_scoring_model=tandem_scoring_model,
            search_mass_range=(minimum_search_mass, maximum_search_mass)
        )
        g.add_task(task)
    return Response("Tasks Scheduled")
