from flask import Response, g, request, render_template
from .service_module import register_service

from ..utils.state_transfer import request_arguments_and_context

from glycan_profiling.serialize import (
    Analysis, Protein, Glycopeptide, GlycanCombination,
    GlycopeptideHypothesis, IdentifiedGlycopeptide, func)
from glycan_profiling.serialize.hypothesis.glycan import GlycanCombinationGlycanComposition

from glycan_profiling.database.glycan_composition_filter import (
    GlycanCompositionFilter, InclusionFilter)

app = view_glycopeptide_lcmsms_analysis = register_service("view_glycopeptide_lcmsms_analysis", __name__)


VIEW_CACHE = dict()


class GlycopeptideSnapShot(object):
    def __init__(self, protein_id, score_threshold, glycan_filters, members):
        self.protein_id = protein_id
        self.score_threshold = score_threshold
        self.glycan_filters = glycan_filters
        self.members = members

    def is_valid(self, score_threshold, glycan_filters):
        if self.score_threshold != score_threshold:
            return False
        if self.glycan_filters != glycan_filters:
            return False
        return True

    def __iter__(self):
        return iter(self.members)

    def __len__(self):
        return len(self.members)

    def __getitem__(self, i):
        return self.members[i]


class AnalysisView(object):
    def __init__(self, session, analysis_id):
        self.analysis_id = analysis_id
        self.session = session
        self.protein_index = None
        self.glycan_composition_filter = None
        self.monosaccharide_bounds = []
        self.score_threshold = 50
        self.analysis = None
        self.hypothesis = None

        self._resolve_sources()
        self._build_protein_index()
        self._build_glycan_filter()

        self._snapshots = dict()

    def _resolve_sources(self):
        self.analysis = self.session.query(Analysis).get(self.analysis_id)
        self.hypothesis = self.analysis.hypothesis

    def _build_protein_index(self):
        theoretical_counts = self.session.query(Protein.name, Protein.id, func.count(Glycopeptide.id)).join(
            Glycopeptide).group_by(Protein.id).filter(
            Protein.hypothesis_id == self.hypothesis.id).all()
        matched_counts = self.session.query(Protein.name, Protein.id, func.count(IdentifiedGlycopeptide.id)).join(
            Glycopeptide).join(
            IdentifiedGlycopeptide, IdentifiedGlycopeptide.structure_id == Glycopeptide.id).group_by(
            Protein.id).filter(IdentifiedGlycopeptide.ms2_score > self.score_threshold).all()
        listing = []
        index = {}
        for protein_name, protein_id, glycopeptide_count in theoretical_counts:
            index[protein_id] = {
                "protein_name": protein_name,
                "protein_id": protein_id,
                "theoretical_count": glycopeptide_count
            }
        for protein_name, protein_id, glycopeptide_count in matched_counts:
            entry = index[protein_id]
            entry['match_count'] = glycopeptide_count
            listing.append(entry)
        self.protein_index = sorted(listing, key=lambda x: x["identified_glycopeptide_count"])
        for protein_entry in self.protein_index:
            protein_entry['protein'] = self.session.query(Protein).get(protein_entry["protein_id"])
        return self.protein_index

    def _build_glycan_filter(self):
        self.glycan_composition_filter = GlycanCompositionFilter(self.hypothesis.glycan_hypothesis.glycans)

    def filter_glycan_combinations(self):
        if len(self.monosaccharide_bounds) == 0:
            ids = self.session.query(GlycanCombination.id).filter(
                GlycanCombination.hypothesis_id == self.hypothesis.id).all()
            return [i[0] for i in ids]
        query = self.glycan_composition_filter.query(*self.monosaccharide_bounds[0])
        for bound in self.monosaccharide_bounds[1:]:
            query.add(*bound)
        inclusion_filter = InclusionFilter(query)

        keepers = []
        last_combination_id = None
        keep = True
        for rel in self.session.query(GlycanCombinationGlycanComposition).join(GlycanCombination).filter(
                GlycanCombination.hypothesis_id == self.hypothesis.id).order_by(
                GlycanCombinationGlycanComposition.c.combination_id).all():
            if rel.combination_id != last_combination_id:
                if last_combination_id is not None and keep:
                    keepers.append(last_combination_id)
                last_combination_id = rel.combination_id
                keep = True
            if rel.glycan_id not in inclusion_filter:
                keep = False
        if keep:
            keepers.append(last_combination_id)
        return keepers

    def get_identified_glycopeptides_to_display(self, protein_id):
        gps = self._identified_glycopeptides_for_protein(protein_id)
        return gps

    def _identified_glycopeptides_for_protein(self, protein_id):
        if protein_id in self._snapshots:
            snapshot = self._snapshots[protein_id]
            if snapshot.is_valid(self.score_threshold, self.monosaccharide_bounds):
                return snapshot
        gps = self.session.query(IdentifiedGlycopeptide).join(IdentifiedGlycopeptide.structure).filter(
            IdentifiedGlycopeptide.analysis_id == self.analysis_id,
            Glycopeptide.protein_id == protein_id,
            IdentifiedGlycopeptide.ms2_score > self.score_threshold).all()

        valid_glycan_combinations = self.filter_glycan_combinations()

        keepers = []
        for gp in gps:
            if gp.structure.glycan_combination_id in valid_glycan_combinations:
                keepers.append(gp)

        snapshot = GlycopeptideSnapShot(protein_id, self.score_threshold, tuple(self.monosaccharide_bounds), keepers)
        self._snapshots[protein_id] = snapshot
        return snapshot


def get_view(analysis_id):
    if analysis_id in VIEW_CACHE:
        view = VIEW_CACHE[analysis_id]
    else:
        view = AnalysisView(g.manager.session, analysis_id)
        VIEW_CACHE[analysis_id] = view
    return view


@app.route("/view_glycopeptide_lcmsms_analysis/<int:analysis_id>")
def index(analysis_id):
    view = get_view(analysis_id)

