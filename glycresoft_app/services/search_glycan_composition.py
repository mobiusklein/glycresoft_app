import re
from flask import Response, g, request, render_template
from werkzeug import secure_filename

from glycan_profiling.models import GeneralScorer, ms1_model_features


from .form_cleaners import remove_empty_rows, intify, make_unique_name, touch_file
from .service_module import register_service

from ..task.analyze_glycan_composition_data import AnalyzeGlycanCompositionTask


app = search_glycan_composition = register_service("search_glycan_composition", __name__)


@app.route("/search_glycan_composition/run_search")
def run_search():
    print("Model Features", ms1_model_features)
    return render_template(
        "glycan_search/run_search.templ", manager=g.manager,
        extra_features=ms1_model_features)


@app.route("/search_glycan_composition/run_search", methods=["POST"])
def run_search_post():
    data = request.values
    mass_shift_data = list(zip(data.getlist('mass_shift_name'),
                               data.getlist('mass_shift_max_count')))
    mass_shift_data = mass_shift_data[:-1]
    mass_shift_data = [(a, int(b)) for a, b in mass_shift_data]

    matching_tolerance = float(data.get("mass-matching-tolerance", 10))
    if matching_tolerance > 1e-4:
        matching_tolerance *= 1e-6

    grouping_tolerance = float(data.get("peak-grouping-tolerance", 15))
    if grouping_tolerance > 1e-4:
        grouping_tolerance *= 1e-6

    hypothesis_uuid = (data.get("hypothesis_choice"))
    hypothesis_record = g.manager.hypothesis_manager.get(hypothesis_uuid)

    sample_records = list(map(g.manager.sample_manager.get, data.getlist("samples")))

    minimum_mass = float(data.get("minimum-mass", 500.))
    extra_model_features = data.getlist("model-features")
    extra_model_features = [ms1_model_features[feat] for feat in extra_model_features]

    hypothesis_name = hypothesis_record.name
    for sample_record in sample_records:
        sample_name = sample_record.name
        job_number = g.manager.get_next_job_number()
        name_prefix = "%s at %s (%d)" % (hypothesis_name, sample_name, job_number)
        cleaned_prefix = re.sub(r"[\s\(\)]", "_", name_prefix)
        name_template = g.manager.get_results_path(
            secure_filename(cleaned_prefix) + "_%s.analysis.db")
        storage_path = make_unique_name(name_template)

        scoring_model = GeneralScorer.clone()
        for feat in extra_model_features:
            scoring_model.add_feature(feat)

        task = AnalyzeGlycanCompositionTask(
            hypothesis_record.path, sample_record.path, hypothesis_record.id,
            storage_path, name_prefix, mass_shift_data, grouping_tolerance,
            matching_tolerance, scoring_model=scoring_model,
            minimum_mass=minimum_mass,
            callback=lambda: 0,
            job_name_part=job_number)
        g.add_task(task)

    return Response("Tasks Scheduled")
