import logging
from flask import request, g, render_template, Response, Blueprint, jsonify

from glycan_profiling.serialize import (
    GlycanHypothesis, GlycopeptideHypothesis, Protein,
    GlycanComposition, Glycopeptide, func)
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
        arguments, state = request_arguments_and_context()
        hypothesis = _locate_hypothesis(uuid)
        if isinstance(hypothesis, GlycanHypothesis):
            return handle_glycan_hypothesis(hypothesis)
        elif isinstance(hypothesis, GlycopeptideHypothesis):
            return handle_glycopeptide_hypothesis(hypothesis)
        return Response("<h2>%s</h2>" % hypothesis.name)
    except Exception, e:
        logging.exception("An exception occurred for %r",
                          request.get_json(), exc_info=e)
    return Response("<h2>No display method is implemented for %s </h2>" % request.get_json())


@app.route("/view_hypothesis/<uuid>/mass_search", methods=["POST"])
def mass_search_dispatch(uuid):
    try:
        arguments, state = request_arguments_and_context()
        hypothesis = _locate_hypothesis(uuid)
        if isinstance(hypothesis, GlycanHypothesis):
            return search_glycan_hypothesis(hypothesis.id, arguments['mass'], arguments['tolerance'])
        elif isinstance(hypothesis, GlycopeptideHypothesis):
            return search_glycopeptide_hypothesis(hypothesis.id, arguments['mass'], arguments['tolerance'])
        return jsonify(*[])
    except Exception, e:
        logging.exception("An exception occurred for %r",
                          request.get_json(), exc_info=e)
        return jsonify(*[])


def handle_glycan_hypothesis(hypothesis):
    return render_template("view_glycan_hypothesis/container.templ", hypothesis=hypothesis)


@app.route("/view_glycan_composition_hypothesis/<int:id>/", methods=["POST"])
def view_glycan_composition_hypothesis(id):
    hypothesis = g.db.query(GlycanHypothesis).get(id)
    return render_template("view_glycan_hypothesis/container.templ", hypothesis=hypothesis)


@app.route("/view_glycan_composition_hypothesis/<int:id>/<int:page>", methods=["POST"])
def view_glycan_composition_hypothesis_table(id, page=1):
    page_size = 50

    def filter_context(q):
        return q.filter_by(
            hypothesis_id=id)
    paginator = paginate(filter_context(g.db.query(GlycanComposition).filter(
        GlycanComposition.hypothesis_id == id)), page, page_size)
    return render_template(
        "view_glycan_hypothesis/display_table.templ",
        paginator=paginator, base_index=(page - 1) * page_size)


def protein_index(session, hypothesis_id):
    theoretical_counts = session.query(Protein.name, Protein.id, func.count(Glycopeptide.id)).join(
        Glycopeptide).group_by(Protein.id).filter(
        Protein.hypothesis_id == hypothesis_id).all()

    listing = []
    for protein_name, protein_id, glycopeptide_count in theoretical_counts:
        entry = {
            "protein_name": protein_name,
            "protein_id": protein_id,
            "theoretical_count": glycopeptide_count
        }
        listing.append(entry)
    protein_index = sorted(listing, key=lambda x: x["protein_name"])
    for protein_entry in protein_index:
        protein_entry['protein'] = session.query(Protein).get(protein_entry["protein_id"])
    return protein_index


def handle_glycopeptide_hypothesis(hypothesis):
    protein_table = protein_index(g.manager.session, hypothesis.id)
    return render_template("view_glycopeptide_hypothesis/container.templ",
                           hypothesis=hypothesis, protein_table=protein_table)


@app.route("/view_glycopeptide_hypothesis/<int:hypothesis_id>/<int:protein_id>/view", methods=['POST'])
def view_protein(hypothesis_id, protein_id):
    session = g.manager.session
    protein = session.query(Protein).get(protein_id)
    return render_template("view_glycopeptide_hypothesis/components/protein_view.templ", protein=protein)


@app.route("/view_glycopeptide_hypothesis/<int:hypothesis_id>/<int:protein_id>/page/<int:page>", methods=['POST'])
def paginate_theoretical_glycopeptides(hypothesis_id, protein_id, page, per_page=50):
    session = g.manager.session
    paginator = paginate(session.query(Glycopeptide).filter(
        Glycopeptide.protein_id == protein_id), page, per_page)
    base_index = (page - 1) * per_page
    return render_template(
        "view_glycopeptide_hypothesis/components/display_table.templ",
        paginator=paginator, base_index=base_index)


def search_glycopeptide_hypothesis(hypothesis_id, mass, ppm_tolerance):
    session = g.manager.session
    lo = mass - (mass * ppm_tolerance)
    hi = mass + (mass * ppm_tolerance)
    hits = session.query(Glycopeptide).filter(
        Glycopeptide.hypothesis_id == hypothesis_id,
        Glycopeptide.calculated_mass.between(lo, hi)).all()
    converted = [
        {"string": hit.glycopeptide_sequence, "mass": hit.calculated_mass,
         "error": (mass - hit.calculated_mass) / hit.calculated_mass} for hit in hits
    ]
    if len(converted) == 1:
        return jsonify(converted)
    return jsonify(*converted)


def search_glycan_hypothesis(hypothesis_id, mass, ppm_tolerance):
    session = g.manager.session
    lo = mass - (mass * ppm_tolerance)
    hi = mass + (mass * ppm_tolerance)
    hits = session.query(GlycanComposition).filter(
        GlycanComposition.hypothesis_id == hypothesis_id,
        GlycanComposition.calculated_mass.between(lo, hi)).all()
    print(lo, hi)
    print(hits)
    converted = [
        {"string": hit.composition, "mass": hit.calculated_mass,
         "error": (mass - hit.calculated_mass) / hit.calculated_mass} for hit in hits
    ]
    if len(converted) == 1:
        return jsonify(converted)
    else:
        return jsonify(*converted)
