import os

from weakref import WeakValueDictionary
from collections import OrderedDict
from threading import RLock

from sqlalchemy.orm import object_session

from flask import Response, g, request, render_template, jsonify, abort, current_app

from glycopeptidepy import PeptideSequence
from glycopeptidepy.utils.collectiontools import groupby
from glycresoft_app.application_manager import ApplicationManager
from glycresoft_app.project.project import Project

from glycresoft_app.utils.state_transfer import request_arguments_and_context, FilterSpecificationSet
from glycresoft_app.utils.pagination import SequencePagination
from glycresoft_app.task.task_process import Message
from glycresoft_app import report


from glycresoft.tandem.ref import SpectrumReference
from glycresoft.serialize import (
    Analysis, Protein, Glycopeptide, GlycanCombination,
    IdentifiedGlycopeptide, func, AnalysisDeserializer,
    MSScan, GlycopeptideSpectrumSolutionSet)

from glycresoft.profiler import GlycopeptideSearchStrategy

from glycresoft.tandem.glycopeptide.identified_structure import IdentifiedGlycoprotein
from glycresoft.tandem.target_decoy import TargetDecoyAnalyzer, GroupwiseTargetDecoyAnalyzer
from glycresoft.tandem.glycopeptide.dynamic_generation.multipart_fdr import GlycopeptideFDREstimator

from glycresoft.serialize.hypothesis.glycan import GlycanCombinationGlycanComposition


from glycresoft.database.glycan_composition_filter import (
    GlycanCompositionFilter, InclusionFilter)

from glycresoft.plotting.summaries import (
    SmoothingChromatogramArtist,
    figax)


from glycresoft.output import (
    GlycopeptideLCMSMSAnalysisCSVSerializer,
    GlycopeptideSpectrumMatchAnalysisCSVSerializer,
    MultiScoreGlycopeptideLCMSMSAnalysisCSVSerializer,
    MultiScoreGlycopeptideSpectrumMatchAnalysisCSVSerializer,
    MzIdentMLSerializer,
    ImportableGlycanHypothesisCSVSerializer,
    SpectrumAnnotatorExport,
    GlycopeptideDatabaseSearchReportCreator
)


from glycresoft.plotting.spectral_annotation import TidySpectrumMatchAnnotator
from glycresoft.plotting.plot_glycoforms import GlycoformLayout
from glycresoft.plotting.sequence_fragment_logo import glycopeptide_match_logo

from glycresoft.plotting.entity_bar_chart import (
    AggregatedAbundanceArtist, BundledGlycanComposition)

from glycresoft.task import log_handle

from ms_deisotope.data_source.scan import ProcessedScan
from ms_deisotope.output import ProcessedMSFileLoader

from glycresoft_app.task.glycopeptide_exports import (
    AnnotatedSpectraExport,
    ExportJob,
    ExportState,
    GlycopeptideCSVExport,
    GlycopeptideGlycansCSVExport,
    GlycopeptideSpectrumMatchCSVExport,
    HTMLReportExport,
)

from .collection_view import CollectionViewBase, ViewCache, SnapshotBase
from .service_module import register_service
from .file_exports import safepath



app = view_glycopeptide_lcmsms_analysis = register_service("view_glycopeptide_lcmsms_analysis", __name__)


VIEW_CACHE = ViewCache()


class GlycopeptideSnapShot(SnapshotBase):
    def __init__(self, protein_id, score_threshold, glycan_filters, members):
        SnapshotBase.__init__(self)
        self.protein_id = protein_id
        self.score_threshold = score_threshold
        self.glycan_filters = glycan_filters
        self.members = sorted(members, key=lambda x: x.ms2_score, reverse=True)
        self.member_id_map = {m.id: m for m in members}
        self.figure_axes = {}
        self._glycoprotein = None

    def _update_bindings(self, session):
        super(GlycopeptideSnapShot, self)._update_bindings(session)
        for obj in self.members:
            self._detatch_object(obj)
            session.add(obj)

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
            layout = GlycoformLayout(protein, self.members, ax=ax)
            layout.draw()
            svg = layout.to_svg(scale=2.0)
            self.figure_axes['plot_glycoforms'] = svg
            return svg

    def site_specific_glycosylation(self, session):
        try:
            axes = self.figure_axes['site_specific_glycosylation']
            return axes
        except KeyError:
            glycoprot = self.get_glycoprotein(session)
            axes = OrderedDict()
            for glycotype in glycoprot.glycosylation_types:
                for site in sorted(glycoprot.glycosylation_sites_for(glycotype)):
                    spanning_site = glycoprot.site_map[glycotype][site]
                    if len(spanning_site) == 0:
                        continue
                    bundle = BundledGlycanComposition.aggregate(spanning_site)
                    if len(bundle) == 0:
                        continue
                    ax = figax()
                    AggregatedAbundanceArtist(bundle, ax=ax).draw()
                    axes[(glycotype, site)] = ax
            return axes


class GlycopeptideAnalysisView(CollectionViewBase):
    _retention_time_model = None
    _fdr_estimator = None
    _is_multiscore = None

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

        self.retention_time_model = None
        self.fdr_estimator = None

        self._peak_loader = None
        self._snapshots_lock = RLock()
        self._snapshots = dict()

        self._converted_cache = WeakValueDictionary()

        with self:
            self._resolve_sources()
            self._build_protein_index()
            self._build_glycan_filter()

    @property
    def is_multiscore(self):
        if self._is_multiscore is None and self.parameters:
            self._is_multiscore = self.parameters.get('search_strategy') == GlycopeptideSearchStrategy.multipart_target_decoy_competition
        return self._is_multiscore

    @property
    def retention_time_model(self):
        if self._retention_time_model is None and self.parameters:
            self._retention_time_model = self.parameters.get("retention_time_model")
        return self._retention_time_model

    @retention_time_model.setter
    def retention_time_model(self, value):
        self._retention_time_model = value

    @property
    def fdr_estimator(self):
        if self._fdr_estimator is None and self.parameters:
            self._fdr_estimator = self.parameters.get(
                "fdr_estimator")
        return self._fdr_estimator

    @fdr_estimator.setter
    def fdr_estimator(self, value):
        self._fdr_estimator = value

    @property
    def peak_loader(self):
        if self._peak_loader is None:
            try:
                manager: ApplicationManager = g.manager
                manager.add_message(Message(f"Loading MS data for {self.analysis.name!r}", type="update", user=g.user))
                by_name = manager.sample_manager.find(name=self.analysis.parameters['sample_name'])
                if os.path.exists(self.analysis.parameters['sample_path']):
                    log_handle.log("Reading spectra from %r" % self.analysis.parameters['sample_path'])
                    self._peak_loader = ProcessedMSFileLoader(self.analysis.parameters['sample_path'])
                elif os.path.exists(
                        os.path.join(
                            g.manager.base_path, self.analysis.parameters['sample_path'])):
                    log_handle.log("Reading spectra from %r" % os.path.join(
                        g.manager.base_path, self.analysis.parameters['sample_path']))
                    self._peak_loader = ProcessedMSFileLoader(
                        os.path.join(
                            g.manager.base_path, self.analysis.parameters['sample_path']))
                elif by_name:
                    log_handle.log("Reading spectra from %r" % by_name[0].path)
                    self._peak_loader = ProcessedMSFileLoader(by_name[0].path)
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

    def _compare_sequence_to_spectrum(self, sequence, scan_id, **kwargs):
        scan = self.peak_loader.get_scan_by_id(scan_id)
        target = PeptideSequence(sequence)
        match = self.match_spectrum(scan, target)
        return match

    def search_by_scan(self, scan_id):
        case = self.session.query(GlycopeptideSpectrumSolutionSet).join(MSScan).filter(
            MSScan.scan_id == scan_id,
            GlycopeptideSpectrumSolutionSet.analysis_id == self.analysis_id).first()
        if case is None:
            return []
        else:
            case = case.convert()
            # solutions = []
            # for member in case:
            #     solutions.append(dict(score=member.score, target=str(member.target), id=member.target.id))
            # return jsonify(status='Match', solutions=solutions)
            return case

    def _resolve_sources(self):
        log_handle.log("Resolving Analysis (analysis_id=%r)" % (self.analysis_id,))
        self.analysis = self.session.query(Analysis).get(self.analysis_id)
        self.hypothesis = self.analysis.hypothesis
        self.parameters = self.analysis.parameters

    def _build_protein_index(self):
        theoretical_counts = self.session.query(Protein.name, Protein.id, func.count(Glycopeptide.id)).join(
            Glycopeptide).group_by(Protein.id).filter(
            Protein.hypothesis_id == self.hypothesis.id).all()
        matched_counts = self.session.query(Protein.name, Protein.id, func.count(IdentifiedGlycopeptide.id)).join(
            Protein.glycopeptides).join(
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

        # log_handle.log("Converting Kept Glycopeptides")
        # keepers = [self.convert_glycopeptide(gp) for gp in keepers]

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
        return self.get_items_for_display(
            protein_id).paginate(page, per_page)

    def match_spectrum(self, scan: ProcessedScan, structure: PeptideSequence):
        scoring_model = self.parameters['tandem_scoring_model']
        error_tolerance = self.parameters['fragment_error_tolerance']
        extra_msn_evaluation_kwargs = self.parameters.get(
            'extra_evaluation_kwargs', {}).copy()
        extra_msn_evaluation_kwargs['error_tolerance'] = error_tolerance
        extra_msn_evaluation_kwargs['extended_glycan_search'] = self.parameters.get(
            'extended_glycan_search', False)
        extra_msn_evaluation_kwargs['rare_signatures'] = self.parameters.get(
            'rare_signatures', False)
        extra_msn_evaluation_kwargs['fragile_fucose'] = self.parameters.get(
            'fragile_fucose', False)
        match = scoring_model.evaluate(scan, structure, **extra_msn_evaluation_kwargs)
        return match


def get_view(analysis_uuid):
    if analysis_uuid in VIEW_CACHE:
        view = VIEW_CACHE[analysis_uuid]
        view.update_connection()
    else:
        try:
            record = g.manager.analysis_manager.get(analysis_uuid)
        except KeyError:
            return abort(404)
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
        has_fdr = view.fdr_estimator is not None
        has_retention_time_model = view.retention_time_model is not None
        return render_template(
            "view_glycopeptide_search/overview.templ", analysis=view.analysis,
            protein_table=view.protein_index,
            has_fdr=has_fdr,
            has_retention_time_model=has_retention_time_model)


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
        with snapshot.bind(view.session):
            paginator = snapshot.paginate(page, 25)
            return render_template(
                "view_glycopeptide_search/components/glycopeptide_match_table.templ", paginator=paginator)


@app.route("/view_glycopeptide_lcmsms_analysis/<analysis_uuid>/<int:protein_id>/plot_glycoforms", methods=['POST'])
def plot_glycoforms(analysis_uuid, protein_id):
    view = get_view(analysis_uuid)
    with view:
        snapshot = view.get_items_for_display(protein_id)
        with snapshot.bind(view.session):
            svg = snapshot.plot_glycoforms(view.session)
            return svg


@app.route("/view_glycopeptide_lcmsms_analysis/<analysis_uuid>/<int:protein_id>/site_specific_glycosylation",
           methods=['POST'])
def site_specific_glycosylation(analysis_uuid, protein_id):
    view = get_view(analysis_uuid)
    with view:
        snapshot = view.get_items_for_display(protein_id)
        with snapshot.bind(view.session):
            axes_map = snapshot.site_specific_glycosylation(view.session)
            glycoprotein = snapshot.get_glycoprotein(view.session)
            return render_template(
                "/view_glycopeptide_search/components/site_specific_glycosylation.templ",
                axes_map=axes_map, glycoprotein=glycoprotein)


@app.route("/view_glycopeptide_lcmsms_analysis/<analysis_uuid>/plot_fdr", methods=['GET'])
def plot_fdr(analysis_uuid):
    view = get_view(analysis_uuid)
    figures = []
    with view:
        fdr_estimator = view.fdr_estimator
        if isinstance(fdr_estimator, (GroupwiseTargetDecoyAnalyzer, TargetDecoyAnalyzer)):
            ax = figax()
            fdr_estimator.plot(ax=ax)
            figures = [
                {
                    "title": "Total FDR",
                    "format": "svg",
                    "figure": report.svg_plot(ax.figure)
                }
            ]
        if isinstance(fdr_estimator, GlycopeptideFDREstimator):
            ax = figax()
            fdr_estimator.glycan_fdr.plot(ax=ax)
            ax.set_title("Glycan FDR", size=16)
            ax.figure.tight_layout()
            figures = [
                {
                    "title": "Glycan FDR",
                    "format": "svg",
                    "figure": report.svg_plot(ax.figure)
                }
            ]
            ax = figax()
            fdr_estimator.peptide_fdr.plot(ax=ax)
            ax.set_title("Peptide FDR", size=16)
            ax.figure.tight_layout()
            figures.append({
                "title": "Peptide FDR",
                "format": "svg",
                "figure": report.svg_plot(ax.figure)
            })
    return jsonify(figures=figures)


@app.route("/view_glycopeptide_lcmsms_analysis/<analysis_uuid>/plot_retention_time_model", methods=['GET'])
def plot_retention_time_model(analysis_uuid):
    view = get_view(analysis_uuid)
    figures = []
    with view:
        retention_time_model = view.retention_time_model
        if retention_time_model is not None:
            ax = figax()
            retention_time_model.plot_factor_coefficients(ax=ax)
            figures.append({
                "title": "Factor Coefficients",
                "format": "svg",
                "figure": report.svg_plot(ax.figure)
            })
            ax = figax()
            retention_time_model.plot_residuals(ax=ax)
            figures.append({
                "title": "Factor Coefficients",
                "format": "svg",
                "figure": report.svg_plot(ax.figure)
            })
            width_range = {
                "lower": retention_time_model.width_range.lower,
                "upper": retention_time_model.width_range.upper,
            },
            interval_padding = retention_time_model.interval_padding
            R2 = retention_time_model.R2()
    return jsonify(figures=figures, interval_padding=interval_padding, width_range=width_range, R2=R2)



@app.route("/view_glycopeptide_lcmsms_analysis/<analysis_uuid>/search_by_scan/<scan_id>")
def search_by_scan(analysis_uuid, scan_id):
    view = get_view(analysis_uuid)
    scan_id = scan_id.strip()
    with view:
        match = view.search_by_scan(scan_id)
        if match:
            top = match[0]
            target = top.target
            ident = view.session.query(IdentifiedGlycopeptide).filter(
                IdentifiedGlycopeptide.structure_id == target.id,
                IdentifiedGlycopeptide.analysis_id == view.analysis_id).first()
            return glycopeptide_detail(
                analysis_uuid,
                target.protein_relation.protein_id,
                ident.id, top.scan.id)
        else:
            return Response('''
<h3 style="text-align: center;">
    No Match
</h3>
                ''')


@app.route(
    "/view_glycopeptide_lcmsms_analysis/<analysis_uuid>/<int:protein_id>/details_for/<int:glycopeptide_id>",
    methods=['POST'])
def glycopeptide_detail(analysis_uuid, protein_id, glycopeptide_id, scan_id=None):
    view = get_view(analysis_uuid)
    with view:
        snapshot = view.get_items_for_display(protein_id)
        with snapshot.bind(view.session):
            session = view.session
            gp = view.get_glycopeptide(glycopeptide_id)

            matched_scans = []

            for solution_set in gp.spectrum_matches:

                best_solution = solution_set.best_solution()
                try:
                    selected_solution = solution_set.solution_for(gp.structure)
                except KeyError:
                    continue
                pass_threshold = abs(selected_solution.score - best_solution.score) < 1e-6

                if not pass_threshold:
                    continue

                if isinstance(selected_solution.scan, SpectrumReference):
                    scan = session.query(MSScan).filter(
                        MSScan.scan_id == selected_solution.scan.id,
                        MSScan.sample_run_id == view.analysis.sample_run_id).first().convert()
                else:
                    scan = selected_solution.scan
                scan.score = selected_solution.score
                matched_scans.append(scan)

            if scan_id is None:
                spectrum_match_ref = max(gp.spectrum_matches, key=lambda x: x.score)
                scan_id = spectrum_match_ref.scan.id

            try:
                scan = view.peak_loader.get_scan_by_id(scan_id)
            except IOError:
                current_app.logger.error(
                    "Failed to fetch reference scan (%r)", scan_id, exc_info=True)

            match = view.match_spectrum(scan, gp.structure)

            max_peak = max([p.intensity for p in match.spectrum])
            ax = figax()
            if gp.chromatogram:
                art = SmoothingChromatogramArtist([gp], ax=ax, colorizer=lambda *a, **k: 'green').draw(
                    label_function=lambda *a, **k: "", legend=False)
                lo, hi = ax.get_xlim()
                lo -= 0.5
                hi += 0.5
                art._interpolate_xticks(lo, hi)
                # ax.set_xlim(lo, hi)
                ax.set_xlabel(ax.get_xlabel(), fontsize=16)
                yl = ax.get_ylabel()
                ax.set_ylabel(yl, fontsize=16)

                labels = [tl for tl in ax.get_xticklabels()]
                for label in labels:
                    label.set(fontsize=12)
                for label in ax.get_yticklabels():
                    label.set(fontsize=12)
            else:
                ax.text(0.5, 0.5, "No Chromatogram Extracted", ha='center')
                ax.set_axis_off()

            specmatch_artist = TidySpectrumMatchAnnotator(match, ax=figax())
            specmatch_artist.draw(fontsize=10, pretty=True)
            annotated_match_ax = specmatch_artist.ax

            annotated_match_ax.set_title("%s\n" % (scan_id,), fontsize=18)
            annotated_match_ax.set_ylabel(annotated_match_ax.get_ylabel(), fontsize=16)
            annotated_match_ax.set_xlabel(annotated_match_ax.get_xlabel(), fontsize=16)

            sequence_logo_plot = glycopeptide_match_logo(
                match, ax=figax(), return_artist=False
            )

            def xml_transform(root):
                view_box_str = root.attrib["viewBox"]
                x_start, y_start, x_end, y_end = map(float, view_box_str.split(" "))
                x_start += 25
                updated_view_box_str = " ".join(map(str, [x_start, y_start, x_end, y_end]))
                root.attrib["viewBox"] = updated_view_box_str
                fig_g = root.find(".//{http://www.w3.org/2000/svg}g[@id=\"figure_1\"]")
                fig_g.attrib["transform"] = "scale(1.0, 1.0)"
                return root

            retention_time_score = None
            retention_time_interval = None
            has_retention_time_model = False
            if view.retention_time_model:
                has_retention_time_model = True
                if gp.chromatogram:
                    retention_time_score = view.retention_time_model.score_interval(
                        gp, alpha=0.01
                    )
                    retention_time_interval = view.retention_time_model._truncate_interval(
                        view.retention_time_model.predict_interval(gp, alpha=0.01)
                    )
            return render_template(
                "/view_glycopeptide_search/components/glycopeptide_detail.templ",
                glycopeptide=gp,
                match=match,
                chromatogram_plot=report.svg_plot(
                    ax, svg_width="100%", bbox_inches='tight', height=4, width=10, patchless=True),
                spectrum_plot=report.svg_plot(
                    annotated_match_ax, svg_width="100%", bbox_inches='tight', height=3.5, width=10, patchless=True),
                sequence_logo_plot=report.svg_plot(
                    sequence_logo_plot, svg_width="100%", xml_transform=xml_transform, bbox_inches='tight',
                    height=3, width=7, patchless=True),
                matched_scans=matched_scans,
                max_peak=max_peak,
                retention_time_score=retention_time_score,
                retention_time_interval=retention_time_interval,
                has_retention_time_model=has_retention_time_model,
            )


@app.route(
    "/view_glycopeptide_lcmsms_analysis/<analysis_uuid>/evaluate_spectrum",
    methods=['GET', 'POST'])
def evalute_spectrum(analysis_uuid):
    if request.method == 'GET':
        return render_template(
            "/view_glycopeptide_search/components/spectrum_evaluation.templ", glycopeptide=None)
    view = get_view(analysis_uuid)
    scan_id = request.values['scan_id'].strip()
    glycopeptide = request.values['glycopeptide'].strip()
    if not glycopeptide or not scan_id:
        return render_template(
            "/view_glycopeptide_search/components/spectrum_evaluation.templ", glycopeptide=None)
    gp = PeptideSequence(glycopeptide)
    with view:
        scan = view.peak_loader.get_scan_by_id(scan_id)

        match = view.match_spectrum(scan, gp)

        specmatch_artist = TidySpectrumMatchAnnotator(match, ax=figax())
        specmatch_artist.draw(fontsize=10, pretty=True)
        annotated_match_ax = specmatch_artist.ax

        annotated_match_ax.set_title("%s\n" % (scan_id,), fontsize=18)
        annotated_match_ax.set_ylabel(annotated_match_ax.get_ylabel(), fontsize=16)
        annotated_match_ax.set_xlabel(annotated_match_ax.get_xlabel(), fontsize=16)

        sequence_logo_plot = glycopeptide_match_logo(
            match, ax=figax(), return_artist=False
        )
        xlim = list(sequence_logo_plot.get_xlim())
        xlim[0] += 1

        sequence_logo_plot.set_xlim(xlim[0], xlim[1])

    def xml_transform(root):
        view_box_str = root.attrib["viewBox"]
        x_start, y_start, x_end, y_end = map(float, view_box_str.split(" "))
        x_start += 25
        updated_view_box_str = " ".join(map(str, [x_start, y_start, x_end, y_end]))
        root.attrib["viewBox"] = updated_view_box_str
        fig_g = root.find(".//{http://www.w3.org/2000/svg}g[@id=\"figure_1\"]")
        fig_g.attrib["transform"] = "scale(1.0, 1.0)"
        return root

    payload = {
        "spectrum_plot": report.svg_plot(annotated_match_ax, svg_width="100%", bbox_inches='tight', height=3.5, width=10, patchless=True),
        "sequence_logo_plot": report.svg_plot(
            sequence_logo_plot, svg_width="100%", xml_transform=xml_transform, bbox_inches='tight',
            height=3, width=7, patchless=True),
        "score": match.score,
        "glycopeptide": str(glycopeptide)
    }
    return render_template(
        "/view_glycopeptide_search/components/spectrum_evaluation.templ", **payload)


# TODO: All of these export methods run in the web server's process, which means they
# trade off between the thread handling this request and all other requests. These export
# tasks still use the GIL substantial amount of time and and could be foisted off onto
# a separate process in the job scheduler, but care must be taken to make sure the results
# conform to the same filters that the `view` applies automatically.
#
# This could be accomplished by enumerating all the primary keys to be visited first
# within a function with access to the view and then send that across to a worker process.
# This has the added benefit that it would allow the user to see the process log updates
# which hard to expose to the browser client right now. One limitation we'll need to work
# around is that the job scheduler only runs one task at a time, but an actual analysis
# job would block an export job, and vice versa. A better design choice might create separate
# pools that the job scheduler can run concurrently.

def _export_csv(analysis_uuid):
    view = get_view(analysis_uuid)
    with view:
        g.add_message(Message("Building Glycopeptide CSV Export", "update"))
        protein_name_resolver = {entry['protein_id']: entry['protein_name'] for entry in view.protein_index}

        file_name = "%s-glycopeptides.csv" % (view.analysis.name)
        path = g.manager.get_temp_path(file_name)

        def generate_entities():
            for protein_id in protein_name_resolver:
                snapshot = view.get_items_for_display(protein_id)
                with snapshot.bind(view.session):
                    for gp in snapshot.members:
                        yield gp.id

        entity_id_list = list(generate_entities())
        job = ExportJob(
            GlycopeptideCSVExport(
                analysis_path=view.connection._original_connection,
                analysis_id=view.analysis_id,
                output_path=path,
                is_multiscore=view.is_multiscore,
                ms_file_path=view.peak_loader.source_file,
                entity_id_list=entity_id_list,
                protein_name_resolver=protein_name_resolver,
            )
        )
    return job


def _export_spectrum_match_csv(analysis_uuid):
    view = get_view(analysis_uuid)
    with view:
        g.add_message(Message("Building Spectrum Match CSV Export", "update"))
        protein_name_resolver = {entry['protein_id']: entry['protein_name'] for entry in view.protein_index}

        file_name = "%s-glycopeptide-spectrum-matches.csv" % (view.analysis.name)
        path = safepath(g.manager.get_temp_path(file_name))

        def generate_entities():
            for protein_id in protein_name_resolver:
                snapshot = view.get_items_for_display(protein_id)
                with snapshot.bind(view.session):
                    for gp in snapshot.members:
                        for ss in gp.spectrum_matches:
                            for sm in ss:
                                if sm.target.protein_relation.protein_id in protein_name_resolver:
                                    yield sm.id
        entity_id_list = list(generate_entities())
        spec = GlycopeptideSpectrumMatchCSVExport(
            analysis_path=view.connection._original_connection,
            analysis_id=view.analysis_id,
            output_path=path,
            is_multiscore=view.is_multiscore,
            ms_file_path=view.peak_loader.source_file,
            entity_id_list=entity_id_list,
            protein_name_resolver=protein_name_resolver,
        )
        job = ExportJob(spec)
    return job


def _export_mzid(analysis_uuid):
    view = get_view(analysis_uuid)
    with view:
        g.add_message(Message("Building mzIdentML Export", "update"))
        protein_name_resolver = {entry['protein_id']: entry['protein_name'] for entry in view.protein_index}
        file_name = "%s.mzid" % (view.analysis.name,)
        path = safepath(g.manager.get_temp_path(file_name))

        glycopeptides = [
            gp for protein_id in protein_name_resolver for gp in
            view.get_items_for_display(protein_id).members
        ]
        for glycopeptide in glycopeptides:
            view.session.merge(glycopeptide)
            list(map(view.session.merge, glycopeptide.spectrum_matches))
        writer = MzIdentMLSerializer(
            open(path, 'wb'), glycopeptides, view.analysis, view.connection)
        writer.start()
    return [file_name, writer.output_mzml_path]


def _export_associated_glycan_compositions(analysis_uuid):
    view = get_view(analysis_uuid)
    with view:
        g.add_message(Message("Building Associated Glycan List Export", "update"))
        reader = AnalysisDeserializer(view.connection._original_connection, analysis_id=view.analysis_id)
        compositions = reader.load_glycans_from_identified_glycopeptides()
        file_name = "%s-associated-glycans.txt" % (view.analysis.name,)
        path = safepath(g.manager.get_temp_path(file_name))
        spec = GlycopeptideGlycansCSVExport(
            view.connection._original_connection,
            view.analysis_id,
            path,
            is_multiscore=view.is_multiscore,
            entity_id_list=[gc.id for gc in compositions],
            protein_name_resolver={},
        )
        job = ExportJob(spec)
    return job


def _export_annotated_spectra(analysis_uuid):
    view = get_view(analysis_uuid)
    with view:
        g.add_message(Message("Annotating Spectra"))
        dir_name = "%s-annotated-spectra" % (view.analysis.name)
        path = g.manager.get_temp_path(dir_name)
        spec = AnnotatedSpectraExport(
            view.connection._original_connection,
            view.analysis_id,
            path,
            view.is_multiscore,
            view.peak_loader.source_file
        )
        job = ExportJob(spec)
    return job


def _export_html(analysis_uuid):
    view = get_view(analysis_uuid)
    with view:
        g.add_message(Message("Building Glycopeptide HTML Report Export", "update"))
        file_name = "%s-report.html" % (view.analysis.name)
        path = safepath(g.manager.get_temp_path(file_name))
        job = ExportJob(
            HTMLReportExport(
                view.connection._original_connection,
                view.analysis_id,
                path,
                view.is_multiscore,
                view.peak_loader.source_file
            )
        )
    return job

@app.route("/view_glycopeptide_lcmsms_analysis/<analysis_uuid>/to-csv")
def to_csv(analysis_uuid):
    file_name = _export_csv(analysis_uuid)[0]
    return jsonify(filename=file_name)


@app.route("/view_glycopeptide_lcmsms_analysis/<analysis_uuid>/<int:protein_id>/chromatogram_group")
def chromatogram_group_plot(analysis_uuid, protein_id):
    view = get_view(analysis_uuid)
    with view:
        snapshot = view.get_items_for_display(protein_id)
        chroma = [
            gp for gp in snapshot
            if gp.chromatogram is not None
        ]
        for chrom in chroma:
            view.session.add(chrom)

        groups = groupby(chroma, key_fn=lambda x: x.structure.peptide_id)
        axes = []
        for _group_key, group in sorted(groups.items()):
            ax = figax()
            artist = SmoothingChromatogramArtist(
                group, ax=ax)
            artist.draw(
                legend=False,
                label_function=lambda chrom, *args, **kwargs: str(chrom.glycan_composition)
            )
            ax.set_title(str(group[0].structure.convert().clone().deglycosylate()))
            artist.minimum_ident_time -= artist.minimum_ident_time * 0.1
            artist.maximum_ident_time += artist.maximum_ident_time * 0.1
            artist.layout_axes(legend=False)

            axes.append(ax)
    figures = [report.svg_plot(ax, bbox_inches='tight', height=5, width=12, patchless=True) for ax in axes]
    response = {
        "figures": [
            {
                "figure": figure,
            } for figure in figures
        ]
    }
    return jsonify(response)


serialization_formats = {
    "glycopeptides (csv)": _export_csv,
    "glycopeptide spectrum matches (csv)": _export_spectrum_match_csv,
    # "mzIdentML (mzid 1.1.0)": _export_mzid,
    "associated glycans (txt)": _export_associated_glycan_compositions,
    'annotated spectra (pdf)': _export_annotated_spectra,
    'glycopeptide report (html)': _export_html,
}


@app.route("/view_glycopeptide_lcmsms_analysis/<analysis_uuid>/export")
def export_menu(analysis_uuid):
    view = get_view(analysis_uuid)
    with view:
        options = [
            "glycopeptides (csv)",
            "glycopeptide spectrum matches (csv)",
            # "mzIdentML (mzid 1.1.0)",
            "associated glycans (txt)",
            'annotated spectra (pdf)',
            'glycopeptide report (html)',
        ]
        return render_template(
            "/view_glycopeptide_search/components/export_formats.templ",
            analysis_id=analysis_uuid, export_type_list=options,
            name=view.analysis.name)


@app.route("/view_glycopeptide_lcmsms_analysis/<analysis_uuid>/export", methods=["POST"])
def export_data(analysis_uuid):
    file_names = []
    view = get_view(analysis_uuid)
    with view:
        state = ExportState(
            view.analysis.name,
            g.user,
            g.manager.add_message
        )

    jobs = []
    for format_key in request.values:
        if format_key in serialization_formats:
            work_task = serialization_formats[format_key]
            job = work_task(analysis_uuid)
            state.add_job(job)
            jobs.append(job)

    manager: ApplicationManager = g.manager
    for job in jobs:
        manager.add_task(job, background=True)

    return jsonify(status='success', filenames=file_names)


@app.route("/view_glycopeptide_lcmsms_analysis/<analysis_uuid>/view_log")
def view_log(analysis_uuid):
    # find_log_file
    view = get_view(analysis_uuid)
    with view:
        task_name = view.analysis.name
        return jsonify(task_name=task_name)
