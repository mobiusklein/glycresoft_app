from flask import g, jsonify, current_app, request


# from glycresoft_app.utils import json_serializer
from glycan_profiling.plotting import colors
from glycan_profiling.chromatogram_tree import mass_shift
from glycan_profiling import symbolic_expression
from glypy.composition import formula
from glypy.structure.glycan_composition import from_iupac_lite, IUPACError
from glycopeptidepy.structure.modification import ModificationTable, ModificationCategory

from .service_module import register_service
from .view_hypothesis import _locate_hypothesis


api = register_service("api", __name__)


@api.route("/api/tasks")
def api_tasks():
    return jsonify(**{t.id: t.to_json() for t in g.manager.tasks().values()})


@api.route("/api/colors")
def api_colors():
    return jsonify(**colors.color_dict())


@api.route("/api/samples")
def api_samples():
    samples = g.manager.samples(g.user)
    d = {}
    for h in samples:
        try:
            d[str(h.name)] = h.to_json()
        except Exception:
            current_app.logger.exception("Error occurred in api_samples", exc_info=True)
    return jsonify(**d)


@api.route("/api/hypotheses")
def api_hypotheses():
    d = {}
    for hypothesis in g.manager.glycan_hypotheses(g.user):
        try:
            dump = hypothesis.to_json()
            d[hypothesis.uuid] = dump
        except Exception:
            current_app.logger.exception("Error occurred in api_hypotheses", exc_info=True)
    for hypothesis in g.manager.glycopeptide_hypotheses(g.user):
        try:
            dump = hypothesis.to_json()
            d[hypothesis.uuid] = dump
        except Exception:
            current_app.logger.exception("Error occurred in api_hypotheses", exc_info=True)
    return jsonify(**d)


@api.route("/api/hypotheses/<uuid>")
def get_hypothesis(uuid):
    hypothesis = _locate_hypothesis(uuid)
    d = {}
    if hypothesis is not None:
        d = hypothesis.to_json()
    return jsonify(hypothesis=d)


@api.route("/api/analyses")
def api_analyses():
    d = {}
    for analysis in g.manager.analyses(g.user):
        try:
            dump = analysis.to_json()
            d[analysis.uuid] = dump
        except Exception:
            current_app.logger.exception("Error occurred in api_analyses for %r", analysis, exc_info=True)
    return jsonify(**d)


@api.route("/api/modifications")
def modifications():
    d = {}
    mt = ModificationTable()
    d['definitions'] = [
        (rule.name, formula(rule.composition if rule.composition else {}), rule.mass) for rule in mt.rules()
    ]
    d['specificities'] = set()
    for rule in mt.rules():
        if (ModificationCategory.substitution in rule.categories or
            ModificationCategory.glycosylation in rule.categories or
                ModificationCategory.other_glycosylation in rule.categories):
            continue
        d['specificities'].update(rule.as_spec_strings())
    d['specificities'] = tuple(d['specificities'])
    return jsonify(**d)


@api.route("/api/validate-iupac", methods=["POST"])
def api_validate_iupac():
    payload = str(request.values.get("target_string")).strip()
    if payload == "":
        return jsonify(valid=False, message="empty name", query=payload)
    try:
        residue = from_iupac_lite(payload)
        return jsonify(valid=True, message=str(residue), query=payload)
    except IUPACError as e:
        return jsonify(valid=False, message=str(e), query=payload)


@api.route("/api/mass-shift")
def mass_shifts():
    d = {}
    d.update(mass_shift.mass_shift_index)
    return jsonify(**d)


@api.route("/api/parse-expression", methods=["POST"])
def api_parse_symbolic_expression():
    payloads = request.values.getlist("expressions[]")
    symbols = []
    for payload in payloads:
        payload = str(payload).strip()
        expr = symbolic_expression.parse_expression(payload)
        expr_symbols = []
        for sym in expr.get_symbols():
            sym = str(sym)
            # use IUPAClite to normalize symbols
            try:
                sym = str(from_iupac_lite(sym))
            except IUPACError:
                pass
            expr_symbols.append(sym)
        symbols.append(expr_symbols)
    return jsonify(symbols=symbols)
