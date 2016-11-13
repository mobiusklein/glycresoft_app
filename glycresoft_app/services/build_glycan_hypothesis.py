from flask import Response, g, request, render_template
from werkzeug import secure_filename

from .form_cleaners import remove_empty_rows, intify
from .service_module import register_service

try:
    from StringIO import StringIO
except:
    from io import StringIO

from glycresoft_app.task.combinatorial_glycan_hypothesis import BuildCombinatorialGlycanHypothesis
from glycresoft_app.task.text_file_glycan_hypothesis import BuildTextFileGlycanHypothesis


app = make_glycan_hypothesis = register_service("make_glycan_hypothesis", __name__)


@app.route("/glycan_search_space")
def build_naive_glycan_search():
    return render_template("glycan_search_space.templ")


def _serialize_rules_to_buffer(rules, constraints, header_comment=""):
    lines = [';%s' % header_comment]
    for symbol, low, high in rules:
        lines.append(" ".join(map(str, [symbol, low, high])))
    lines.append("")
    for lhs, op, rhs in constraints:
        lines.append(" ".join(map(str, (lhs, op, rhs))))
    return StringIO('\n'.join(lines))


def is_text_file_present(file_storage):
    if file_storage.filename == "":
        return False
    return True


@app.route("/glycan_search_space", methods=["POST"])
def build_naive_glycan_search_process():
    data = request.values
    custom_reduction_type = data.get("custom_reduction_type")
    custom_derivatization_type = data.get("custom_derivatization_type")

    has_custom_reduction = custom_reduction_type != ""
    has_custom_derivatization = custom_derivatization_type != ""

    reduction_type = data.get("reduction_type")
    derivatization_type = data.get("derivatization_type")

    hypothesis_name = data.get("hypothesis_name", "")
    if hypothesis_name.strip() == "":
        hypothesis_name = None

    if reduction_type in ("", "native"):
        reduction_type = None
    if derivatization_type in ("", "native"):
        derivatization_type = None

    comb_monosaccharide_name = data.getlist('monosaccharide_name')[:-1]
    comb_lower_bound = map(intify, data.getlist('monosaccharide_lower_bound')[:-1])
    comb_upper_bound = map(intify, data.getlist('monosaccharide_upper_bound')[:-1])

    comb_monosaccharide_name, comb_lower_bound, comb_upper_bound = remove_empty_rows(
        comb_monosaccharide_name, comb_lower_bound, comb_upper_bound)

    include_human_n_glycan = data.get("glycomedb-human-n-glycan")
    include_human_o_glycan = data.get("glycomedb-human-o-glycan")
    include_mammalian_n_glycan = data.get("glycomedb-mammlian-n-glycan")
    include_mammalian_o_glycan = data.get("glycomedb-mammlian-o-glycan")

    constraint_lhs = data.getlist("left_hand_side")[:-1]
    constraint_op = data.getlist("operator")[:-1]
    constraint_rhs = data.getlist("right_hand_side")[:-1]

    glycan_list_file = request.files["glycan-list-file"]

    if is_text_file_present(glycan_list_file):
        secure_glycan_list_file = g.manager.get_temp_path(secure_filename(glycan_list_file.filename))
        glycan_list_file.save(secure_glycan_list_file)
        task = BuildTextFileGlycanHypothesis(
            secure_glycan_list_file,
            g.manager.connection_bridge,
            reduction=custom_reduction_type if has_custom_reduction else reduction_type,
            derivatization=custom_derivatization_type if has_custom_derivatization else derivatization_type,
            name=hypothesis_name,
            callback=lambda: 0)
        g.manager.add_task(task)
    else:
        constraints = zip(*remove_empty_rows(constraint_lhs, constraint_op, constraint_rhs))
        rules = zip(comb_monosaccharide_name, comb_lower_bound, comb_upper_bound)
        # File-like object to pass to the task in place of a path to a rules file
        rules_buffer = _serialize_rules_to_buffer(rules, constraints, "generated")

        task = BuildCombinatorialGlycanHypothesis(
            rules_buffer, g.manager.connection_bridge,
            reduction=custom_reduction_type if has_custom_reduction else reduction_type,
            derivatization=custom_derivatization_type if has_custom_derivatization else derivatization_type,
            name=hypothesis_name,
            callback=lambda: 0
        )
        g.manager.add_task(task)

    return Response("Task Scheduled")
