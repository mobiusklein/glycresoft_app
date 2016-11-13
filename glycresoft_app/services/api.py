from uuid import uuid4
from flask import Blueprint, g, jsonify

from glycresoft_app.utils import json_serializer
from glycan_profiling.serialize import IdentifiedGlycopeptide
from glycan_profiling.plotting import colors

from .service_module import register_service
from .view_hypothesis import _locate_hypothesis

# ----------------------------------------
#           JSON Data API Calls
# ----------------------------------------

api = register_service("api", __name__)


@api.route("/api/identified_glycopeptide/<int:id>")
def get_glycopeptide_match_api(id):
    gpm = g.db.query(IdentifiedGlycopeptide).get(id)
    if gpm:
        gpm = gpm
    return jsonify(**{
        "id": gpm.id, "glycopeptide": str(gpm.structure.glycopeptide_sequence), "ms2_score": gpm.ms2_score,
        "ms1_score": gpm.ms1_score
    })


@api.route("/api/tasks")
def api_tasks():
    return jsonify(**{t.id: t.to_json() for t in g.manager.tasks.values()})


@api.route("/api/colors")
def api_colors():
    return jsonify(**colors.color_dict())


@api.route("/api/samples")
def api_samples():
    samples = g.manager.samples()
    d = {
        str(h.name): h.to_json() for h in samples
    }
    return jsonify(**d)


@api.route("/api/hypotheses")
def api_hypotheses():
    d = {}
    for hypothesis in g.manager.glycan_hypotheses():
        dump = hypothesis.to_json()
        d[hypothesis.uuid] = dump
    for hypothesis in g.manager.glycopeptide_hypotheses():
        dump = hypothesis.to_json()
        d[hypothesis.uuid] = dump
    return jsonify(**d)


@api.route("/api/hypotheses/<uuid>")
def get_hypothesis(uuid):
    hypothesis = _locate_hypothesis(uuid)
    return jsonify(hypothesis=hypothesis.to_json())


@api.route("/api/analyses")
def api_analyses():
    d = {}
    for analysis in g.manager.analyses():
        dump = analysis.to_json()
        d[analysis.uuid] = dump
    return jsonify(**d)
