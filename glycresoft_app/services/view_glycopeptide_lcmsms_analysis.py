import os
from weakref import WeakValueDictionary
from collections import OrderedDict

from flask import Response, g, request, render_template, jsonify, current_app

from .collection_view import CollectionViewBase
from .service_module import register_service

from threading import RLock
from glycresoft_app.utils.state_transfer import request_arguments_and_context, FilterSpecificationSet
from glycresoft_app.utils.pagination import SequencePagination
from glycresoft_app.task.task_process import Message
from glycresoft_app import report


from glycan_profiling.tandem.ref import SpectrumReference
from glycan_profiling.serialize import (
    Analysis, Protein, Glycopeptide, GlycanCombination,
    IdentifiedGlycopeptide, func,
    MSScan, GlycopeptideSpectrumSolutionSet)

from glycan_profiling.tandem.glycopeptide.scoring import CoverageWeightedBinomialScorer

from glycan_profiling.tandem.glycopeptide.identified_structure import IdentifiedGlycoprotein

from glycan_profiling.serialize.hypothesis.glycan import GlycanCombinationGlycanComposition


from glycan_profiling.database.glycan_composition_filter import (
    GlycanCompositionFilter, InclusionFilter)

from glycan_profiling.plotting.chromatogram_artist import ChromatogramArtist
from glycan_profiling.plotting.summaries import (
    SmoothingChromatogramArtist,
    figax)


from glycan_profiling.tandem.glycopeptide import chromatogram_graph


from glycan_profiling.output import (
    GlycopeptideLCMSMSAnalysisCSVSerializer,
    GlycopeptideSpectrumMatchAnalysisCSVSerializer,
    MzIdentMLSerializer)

from glycan_profiling.plotting.plot_glycoforms import plot_glycoforms_svg
from glycan_profiling.plotting.sequence_fragment_logo import glycopeptide_match_logo

from glycan_profiling.plotting.entity_bar_chart import (
    AggregatedAbundanceArtist, BundledGlycanComposition)

from glycan_profiling.task import log_handle

from ms_deisotope.output.mzml import ProcessedMzMLDeserializer

app = view_glycopeptide_lcmsms_analysis = register_service("view_glycopeptide_lcmsms_analysis", __name__)


VIEW_CACHE = dict()


class GlycopeptideSnapShot(object):
    def __init__(self, protein_id, score_threshold, glycan_filters, members):
        self.protein_id = protein_id
        self.score_threshold = score_threshold
        self.glycan_filters = glycan_filters
        self.members = sorted(members, key=lambda x: x.ms2_score, reverse=True)
        self.member_id_map = {m.id: m for m in members}
        self.figure_axes = {}
        self._glycoprotein = None

    def get_glycoprotein(self, session):
        if self._glycoprotein is None:
            protein = session.query(Protein).get(self.protein_id)
            self._glycoprotein = IdentifiedGlycoprotein(protein, self.members)
        return self._glycoprotein

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

    def paginate(self, page, per_page=50):
        return SequencePagination.paginate(self.members, page, per_page)

    def __getitem__(self, i):
        return self.member_id_map[i]

    def plot_glycoforms(self, session):
        try:
            svg = self.figure_axes['plot_glycoforms']
            return svg
        except KeyError:
            protein = session.query(Protein).get(self.protein_id)
            ax = figax()
            svg = plot_glycoforms_svg(protein, self.members, ax=ax)
            self.figure_axes['plot_glycoforms'] = svg
            return svg

    def site_specific_glycosylation(self, session):
        try:
            axes = self.figure_axes['site_specific_glycosylation']
            return axes
        except KeyError:
            glycoprot = self.get_glycoprotein(session)
            axes = OrderedDict()
            for site in sorted(glycoprot.glycosylation_sites):
                spanning_site = glycoprot.site_map[site]
                if len(spanning_site) == 0:
                    continue
                bundle = BundledGlycanComposition.aggregate(spanning_site)
                ax = figax()
                AggregatedAbundanceArtist(bundle, ax=ax).draw()
                axes[site] = ax
            return axes


class GlycopeptideAnalysisView(CollectionViewBase):
    def __init__(self, storage_record, analysis_id):
        CollectionViewBase.__init__(self, storage_record)
        self.analysis_id = analysis_id

        self.protein_index = None
        self.glycan_composition_filter = None
        self.monosaccharide_bounds = FilterSpecificationSet()
        self.score_threshold = 50
        self.analysis = None
        self.hypothesis = None

        self.parameters = None

        self._peak_loader = None
        self._snapshots_lock = RLock()
        self._snapshots = dict()

        self._converted_cache = WeakValueDictionary()

        with self:
            self._resolve_sources()
            self._build_protein_index()
            self._build_glycan_filter()

    @property
    def peak_loader(self):
        if self._peak_loader is None:
            try:
                if os.path.exists(self.analysis.parameters['sample_path']):
                    self._peak_loader = ProcessedMzMLDeserializer(self.analysis.parameters['sample_path'])
                elif os.path.exists(
                        os.path.join(
                            g.manager.base_path, self.analysis.parameters['sample_path'])):
                    self._peak_loader = ProcessedMzMLDeserializer(
                        os.path.join(
                            g.manager.base_path, self.analysis.parameters['sample_path']))
                else:
                    raise IOError("Could not locate file")
            except KeyError:
                pass
            except AttributeError:
                pass
        return self._peak_loader

    def _snapshot_size(self):
        return sum(map(len, self._snapshots.values()))

    def _snapshot_upkeep(self, max_size=5e2):
        if self._snapshot_size() > max_size:
            pass
            # TODO switch from using a plain dict to using
            # something connected to an LRU cache

    def search_by_scan(self, scan_id):
        case = self.session.query(GlycopeptideSpectrumSolutionSet).join(MSScan).filter(
            MSScan.scan_id == scan_id,
            GlycopeptideSpectrumSolutionSet.analysis_id == self.analysis_id).first()
        if case is None:
            return jsonify(status="No Match", solutions=[])
        else:
            case = case.convert()
            solutions = []
            for member in case:
                solutions.append(dict(score=member.score, target=str(member.target), id=member.target.id))
            return jsonify(status='Match', solutions=solutions)

    def _resolve_sources(self):
        self.analysis = self.session.query(Analysis).get(self.analysis_id)
        self.hypothesis = self.analysis.hypothesis
        self.parameters = self.analysis.parameters

    def _build_protein_index(self):
        theoretical_counts = self.session.query(Protein.name, Protein.id, func.count(Glycopeptide.id)).join(
            Glycopeptide).group_by(Protein.id).filter(
            Protein.hypothesis_id == self.hypothesis.id).all()
        matched_counts = self.session.query(Protein.name, Protein.id, func.count(IdentifiedGlycopeptide.id)).join(
            Glycopeptide).join(
            IdentifiedGlycopeptide, IdentifiedGlycopeptide.structure_id == Glycopeptide.id).group_by(
            Protein.id).filter(
            IdentifiedGlycopeptide.ms2_score > self.score_threshold,
            IdentifiedGlycopeptide.analysis_id == self.analysis_id).all()
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
            entry['identified_glycopeptide_count'] = glycopeptide_count
            listing.append(entry)
        self.protein_index = sorted(listing, key=lambda x: x["identified_glycopeptide_count"], reverse=True)
        for protein_entry in self.protein_index:
            protein_entry['protein'] = self.session.query(Protein).get(protein_entry["protein_id"])
        return self.protein_index

    def _build_glycan_filter(self):
        self.glycan_composition_filter = GlycanCompositionFilter(self.hypothesis.glycan_hypothesis.glycans.all())

    def filter_glycan_combinations(self):
        if len(self.monosaccharide_bounds) == 0:
            ids = self.session.query(GlycanCombination.id).filter(
                GlycanCombination.hypothesis_id == self.hypothesis.id).all()
            return [i[0] for i in ids]

        query = self.monosaccharide_bounds.to_filter_query(self.glycan_composition_filter)
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
        return frozenset(keepers)

    def get_items_for_display(self, protein_id):
        with self._snapshots_lock:
            if protein_id in self._snapshots:
                snapshot = self._snapshots[protein_id]
                if not snapshot.is_valid(self.score_threshold, self.monosaccharide_bounds):
                    log_handle.log("Previous Snapshot Invalid, Rebuilding")
                    snapshot = self._build_protein_snap_shot(protein_id)
            else:
                log_handle.log("New Protein, Building Snapshot")
                snapshot = self._build_protein_snap_shot(protein_id)
            self._snapshots[protein_id] = snapshot
        return snapshot

    def get_glycopeptide(self, glycopeptide_id):
        return self.convert_glycopeptide(self.session.query(IdentifiedGlycopeptide).get(glycopeptide_id))

    def convert_glycopeptide(self, identified_glycopeptide):
        if identified_glycopeptide.id in self._converted_cache:
            return self._converted_cache[identified_glycopeptide.id]
        else:
            inst = identified_glycopeptide.convert()
            self._converted_cache[identified_glycopeptide.id] = inst
            return inst

    def _build_protein_snap_shot(self, protein_id):
        log_handle.log("Loading Glycopeptides")
        gps = self.session.query(
            IdentifiedGlycopeptide,
            Glycopeptide.glycan_combination_id).join(IdentifiedGlycopeptide.structure).filter(
            IdentifiedGlycopeptide.analysis_id == self.analysis_id,
            Glycopeptide.protein_id == protein_id,
            IdentifiedGlycopeptide.ms2_score > self.score_threshold).all()

        log_handle.log("Retrieving Valid Glycan Combinations")
        valid_glycan_combinations = self.filter_glycan_combinations()

        log_handle.log("Filtering Glycopeptides by Glycans")
        keepers = []
        for gp, glycan_combination_id in gps:
            if glycan_combination_id in valid_glycan_combinations:
                keepers.append(gp)

        log_handle.log("Converting Kept Glycopeptides")
        keepers = [self.convert_glycopeptide(gp) for gp in keepers]

        log_handle.log("Snapshot Complete")
        snapshot = GlycopeptideSnapShot(protein_id, self.score_threshold, self.monosaccharide_bounds, keepers)
        return snapshot

    def update_connection(self):
        pass

    def update_threshold(self, score_threshold, monosaccharide_bounds):
        last_threshold = self.score_threshold
        self.score_threshold = score_threshold
        if last_threshold != score_threshold:
            log_handle.log("Reindexing Proteins")
            self._build_protein_index()
        self.monosaccharide_bounds = monosaccharide_bounds

    def paginate(self, protein_id, page, per_page=25):
        return self.get_items_for_display(protein_id).paginate(page, per_page)


def get_view(analysis_uuid):
    if analysis_uuid in VIEW_CACHE:
        view = VIEW_CACHE[analysis_uuid]
        view.update_connection()
    else:
        record = g.manager.analysis_manager.get(analysis_uuid)
        view = GlycopeptideAnalysisView(record, record.id)
        VIEW_CACHE[analysis_uuid] = view
    return view


@app.route("/view_glycopeptide_lcmsms_analysis/<analysis_uuid>")
def index(analysis_uuid):
    view = get_view(analysis_uuid)
    with view:
        args, state = request_arguments_and_context()
        log_handle.log("Loading Index")
        log_handle.log("%s" % state.monosaccharide_filters)
        view.update_threshold(state.settings['minimum_ms2_score'], state.monosaccharide_filters)
        return render_template(
            "view_glycopeptide_search/overview.templ", analysis=view.analysis,
            protein_table=view.protein_index)


@app.route("/view_glycopeptide_lcmsms_analysis/<analysis_uuid>/<int:protein_id>/overview", methods=['POST'])
def protein_view(analysis_uuid, protein_id):
    view = get_view(analysis_uuid)
    with view:
        args, state = request_arguments_and_context()
        log_handle.log("%s" % state.monosaccharide_filters)
        view.update_threshold(state.settings['minimum_ms2_score'], state.monosaccharide_filters)
        snapshot = view.get_items_for_display(protein_id)
        glycoprotein = snapshot.get_glycoprotein(view.session)
        return render_template(
            "view_glycopeptide_search/components/protein_view.templ",
            glycoprotein=glycoprotein)


@app.route("/view_glycopeptide_lcmsms_analysis/<analysis_uuid>/<int:protein_id>/page/<int:page>", methods=['POST'])
def page(analysis_uuid, protein_id, page):
    view = get_view(analysis_uuid)
    with view:
        snapshot = view.get_items_for_display(protein_id)
        paginator = snapshot.paginate(page, 25)
        return render_template(
            "view_glycopeptide_search/components/glycopeptide_match_table.templ", paginator=paginator)


@app.route("/view_glycopeptide_lcmsms_analysis/<analysis_uuid>/<int:protein_id>/plot_glycoforms", methods=['POST'])
def plot_glycoforms(analysis_uuid, protein_id):
    view = get_view(analysis_uuid)
    with view:
        snapshot = view.get_items_for_display(protein_id)
        svg = snapshot.plot_glycoforms(view.session)
        return svg


@app.route("/view_glycopeptide_lcmsms_analysis/<analysis_uuid>/<int:protein_id>/site_specific_glycosylation",
           methods=['POST'])
def site_specific_glycosylation(analysis_uuid, protein_id):
    view = get_view(analysis_uuid)
    with view:
        snapshot = view.get_items_for_display(protein_id)
        axes_map = snapshot.site_specific_glycosylation(view.session)
        glycoprotein = snapshot.get_glycoprotein(view.session)
        return render_template(
            "/view_glycopeptide_search/components/site_specific_glycosylation.templ",
            axes_map=axes_map, glycoprotein=glycoprotein)


@app.route("/view_glycopeptide_lcmsms_analysis/<analysis_uuid>/search_by_scan/<scan_id>")
def search_by_scan(analysis_uuid, scan_id):
    view = get_view(analysis_uuid)
    with view:
        return view.search_by_scan(scan_id)


@app.route(
    "/view_glycopeptide_lcmsms_analysis/<analysis_uuid>/<int:protein_id>/details_for/<int:glycopeptide_id>",
    methods=['POST'])
def glycopeptide_detail(analysis_uuid, protein_id, glycopeptide_id):
    view = get_view(analysis_uuid)
    with view:
        snapshot = view.get_items_for_display(protein_id)
        session = view.session
        try:
            gp = snapshot[glycopeptide_id]
        except:
            gp = view.get_glycopeptide(glycopeptide_id)

        matched_scans = []
        for solution_set in gp.spectrum_matches:
            psm = solution_set[0]
            if isinstance(psm.scan, SpectrumReference):
                scan = session.query(MSScan).filter(
                    MSScan.scan_id == psm.scan.id,
                    MSScan.sample_run_id == view.analysis.sample_run_id).first().convert()
            else:
                scan = psm.scan
            matched_scans.append(scan)

        spectrum_match_ref = max(gp.spectrum_matches, key=lambda x: x.score)
        scan = view.peak_loader.get_scan_by_id(spectrum_match_ref.scan.id)

        match = CoverageWeightedBinomialScorer.evaluate(
            scan, gp.structure,
            error_tolerance=view.analysis.parameters["fragment_error_tolerance"])

        max_peak = max([p.intensity for p in match.spectrum])

        ax = figax()
        art = SmoothingChromatogramArtist([gp], ax=ax, colorizer=lambda *a, **k: 'green').draw(
            label_function=lambda *a, **k: "", legend=False)
        lo, hi = ax.get_xlim()
        lo -= 0.5
        hi += 0.5
        yl = ax.get_ylabel()
        ax.set_ylabel(yl, fontsize=16)
        ax.set_xlabel(ax.get_xlabel(), fontsize=16)
        ax.set_xlim(lo, hi)
        ax.get_xaxis().get_major_formatter().set_useOffset(False)
        labels = [tl for tl in ax.get_xticklabels()]
        for label in labels:
            label.set(fontsize=12)
        for label in ax.get_yticklabels():
            label.set(fontsize=12)

        spectrum_plot = match.annotate(ax=figax(), pretty=True)
        spectrum_plot.set_title("%s\n" % (scan.id,), fontsize=18)
        spectrum_plot.set_ylabel(spectrum_plot.get_ylabel(), fontsize=16)
        spectrum_plot.set_xlabel(spectrum_plot.get_xlabel(), fontsize=16)

        sequence_logo_plot = glycopeptide_match_logo(match, ax=figax())

        return render_template(
            "/view_glycopeptide_search/components/glycopeptide_detail.templ",
            glycopeptide=gp,
            match=match,
            chromatogram_plot=report.svg_plot(ax, bbox_inches='tight', height=3, width=7, patchless=True),
            spectrum_plot=report.svg_plot(spectrum_plot, bbox_inches='tight', height=3, width=10, patchless=True),
            sequence_logo_plot=report.svg_plot(sequence_logo_plot, bbox_inches='tight', height=2, width=7, patchless=True),
            matched_scans=matched_scans,
            max_peak=max_peak,
        )


def _export_csv(analysis_uuid):
    view = get_view(analysis_uuid)
    with view:
        g.manager.add_message(Message("Building CSV Export", "update"))
        protein_name_resolver = {entry['protein_id']: entry['protein_name'] for entry in view.protein_index}

        file_name = "%s-glycopeptides.csv" % (view.analysis.name)
        path = g.manager.get_temp_path(file_name)

        gen = (
            gp for protein_id in protein_name_resolver for gp in
            view.get_items_for_display(protein_id).members)

        GlycopeptideLCMSMSAnalysisCSVSerializer(
            open(path, 'wb'), gen,
            protein_name_resolver).start()
    return file_name


def _export_spectrum_match_csv(analysis_uuid):
    view = get_view(analysis_uuid)
    with view:
        g.manager.add_message(Message("Building CSV Export", "update"))
        protein_name_resolver = {entry['protein_id']: entry['protein_name'] for entry in view.protein_index}

        file_name = "%s-glycopeptide-spectrum-matches.csv" % (view.analysis.name)
        path = g.manager.get_temp_path(file_name)

        gen = (
            sm for protein_id in protein_name_resolver for gp in
            view.get_items_for_display(protein_id).members
            for ss in gp.spectrum_matches
            for sm in ss
            if sm.target.protein_relation.protein_id in protein_name_resolver)
        GlycopeptideSpectrumMatchAnalysisCSVSerializer(
            open(path, 'wb'), gen, protein_name_resolver).start()
    return file_name


def _export_mzid(analysis_uuid):
    view = get_view(analysis_uuid)
    with view:
        g.manager.add_message(Message("Building mzIdentML Export", "update"))
        protein_name_resolver = {entry['protein_id']: entry['protein_name'] for entry in view.protein_index}
        file_name = "%s.mzid" % (view.analysis.name,)
        path = g.manager.get_temp_path(file_name)
        glycopeptides = [
            gp for protein_id in protein_name_resolver for gp in
            view.get_items_for_display(protein_id).members
        ]
        MzIdentMLSerializer(
            open(path, 'wb'), glycopeptides, view.analysis, view.connection).start()
    return file_name


@app.route("/view_glycopeptide_lcmsms_analysis/<analysis_uuid>/to-csv")
def to_csv(analysis_uuid):
    file_name = _export_csv(analysis_uuid)
    return jsonify(filename=file_name)


@app.route("/view_glycopeptide_lcmsms_analysis/<analysis_uuid>/<int:protein_id>/chromatogram_group", methods=["POST"])
def chromatogram_group_plot(analysis_uuid, protein_id):
    view = get_view(analysis_uuid)
    with view:
        snapshot = view.get_items_for_display(protein_id)
        graph = chromatogram_graph.GlycopeptideChromatogramGraph([
            gp.chromatogram for gp in snapshot
        ])
        graph.build()
        bunch = graph.sequence_map[request.values['backbone']]
        chroma = [node.chromatogram for node in bunch]
        ax = figax()
        SmoothingChromatogramArtist(
            chroma, ax=ax, colorizer=lambda *a, **k: 'green').draw(
            legend=False)
    return Response(report.svg_plot(ax, bbox_inches='tight', height=5, width=12, patchless=True))


serialization_formats = {
    "glycopeptides (csv)": _export_csv,
    "glycopeptide spectrum matches (csv)": _export_spectrum_match_csv,
    "mzIdentML (mzid 1.1.0)": _export_mzid
}


@app.route("/view_glycopeptide_lcmsms_analysis/<analysis_uuid>/export")
def export_menu(analysis_uuid):
    options = [
        "glycopeptides (csv)",
        "glycopeptide spectrum matches (csv)",
        "mzIdentML (mzid 1.1.0)"
    ]
    return render_template(
        "/view_glycopeptide_search/components/export_formats.templ",
        analysis_id=analysis_uuid, export_type_list=options)


@app.route("/view_glycopeptide_lcmsms_analysis/<analysis_uuid>/export", methods=["POST"])
def export_data(analysis_uuid):
    file_names = []
    for format_key in request.values:
        if format_key in serialization_formats:
            work_task = serialization_formats[format_key]
            file_names.append(
                work_task(analysis_uuid))
    return jsonify(status='success', filenames=file_names)
