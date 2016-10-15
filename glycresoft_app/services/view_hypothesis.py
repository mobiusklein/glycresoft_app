import logging
from flask import request, g, render_template, Response, Blueprint, jsonify

from glycan_profiling.serialize import (
    GlycanHypothesis, GlycopeptideHypothesis, Protein,
    GlycanComposition)
from glycresoft_app.utils.pagination import paginate
from glycresoft_app.utils.state_transfer import request_arguments_and_context

from .service_module import register_service


app = view_hypothesis = register_service("view_hypothesis", __name__)


def _locate_hypothesis(uuid):
    hypothesis = g.manager.session.query(GlycanHypothesis).filter(
        GlycanHypothesis.uuid == uuid).first()
    if hypothesis is not None:
        return hypothesis
    hypothesis = g.manager.session.query(GlycopeptideHypothesis).filter(
        GlycopeptideHypothesis.uuid == uuid).first()
    if hypothesis is not None:
        return hypothesis
    else:
        return None


@app.route("/view_hypothesis/<uuid>", methods=["POST"])
def view_hypothesis_dispatch(uuid):
    try:
        arguments, state = request_arguments_and_context(request)
        # params = arguments['params']
        # uuid = params['uuid']
        hypothesis = _locate_hypothesis(uuid)
        if isinstance(hypothesis, GlycanHypothesis):
            return handle_glycan_hypothesis(hypothesis)
        return Response("<h2>%s</h2>" % hypothesis.name)
    except Exception, e:
        logging.exception("An exception occurred for %r",
                          request.get_json(), exc_info=e)
    return Response("<h2>No display method is implemented for %s </h2>" % request.get_json())


def handle_glycan_hypothesis(hypothesis):
    return render_template("view_glycan_hypothesis/container.templ", hypothesis=hypothesis)


@app.route("/view_glycan_composition_hypothesis/<int:id>/", methods=["POST"])
def view_glycan_composition_hypothesis(id):
    # state = request.get_json()
    # settings = state['settings']
    # context = state['context']
    hypothesis = g.db.query(GlycanHypothesis).get(id)
    return render_template("view_glycan_hypothesis/container.templ", hypothesis=hypothesis)


@app.route("/view_glycan_composition_hypothesis/<int:id>/<int:page>", methods=["POST"])
def view_glycan_composition_hypothesis_table(id, page=1):
    # state = request.get_json()
    # settings = state['settings']
    # context = state['context']
    # hypothesis = g.db.query(GlycanHypothesis).get(id)

    page_size = 50

    def filter_context(q):
        return q.filter_by(
            hypothesis_id=id)
    paginator = paginate(filter_context(g.db.query(GlycanComposition).filter(
        GlycanComposition.hypothesis_id == id)), page, page_size)
    return render_template(
        "view_glycan_hypothesis/display_table.templ",
        paginator=paginator, base_index=(page - 1) * page_size)
