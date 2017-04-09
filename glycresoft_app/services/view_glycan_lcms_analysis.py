from weakref import WeakValueDictionary

from flask import Response, g, request, render_template, jsonify
from .service_module import register_service
from .collection_view import CollectionViewBase, ViewCache

from threading import RLock
from glycresoft_app.utils.state_transfer import request_arguments_and_context, FilterSpecificationSet
from glycresoft_app import report
from glycresoft_app.utils.pagination import SequencePagination
from glycresoft_app.task import Message

from glycan_profiling.serialize import (
    DatabaseBoundOperation,
    Analysis, GlycanComposition, GlycanHypothesis,
    GlycanCompositionChromatogram,
    UnidentifiedChromatogram, func)

from glycan_profiling.chromatogram_tree import ChromatogramFilter

from glycan_profiling.database.glycan_composition_filter import (
    GlycanCompositionFilter, InclusionFilter)

from glycan_profiling.plotting.summaries import (
    GlycanChromatographySummaryGraphBuilder, SmoothingChromatogramArtist,
    figax)

from glycan_profiling.plotting import ArtistBase

from glycan_profiling.plotting.chromatogram_artist import ChargeSeparatingSmoothingChromatogramArtist


from glycan_profiling.output import (
    GlycanLCMSAnalysisCSVSerializer, ImportableGlycanHypothesisCSVSerializer)

app = view_glycan_lcms_analysis = register_service("view_glycan_lcms_analysis", __name__)


VIEW_CACHE = ViewCache()


class GlycanChromatographySnapShot(object):
    def __init__(self, score_threshold, glycan_filters, glycan_chromatograms, unidentified_chromatograms):
        self.score_threshold = score_threshold
        self.glycan_filters = glycan_filters
        self.glycan_chromatograms = sorted(
            glycan_chromatograms, key=lambda x: (x.score, x.total_signal), reverse=True)
        self.unidentified_chromatograms = sorted(
            unidentified_chromatograms, key=lambda x: (x.score, x.total_signal), reverse=True)
        self.figure_axes = {}
        self._make_summary_graphics()
        self.member_id_map = {
            x.id: x for x in self.glycan_chromatograms
        }

    def is_valid(self, score_threshold, glycan_filters):
        if self.score_threshold != score_threshold:
            return False
        if self.glycan_filters != glycan_filters:
            return False
        return True

    def _make_summary_graphics(self):
        try:
            builder = GlycanChromatographySummaryGraphBuilder(
                ChromatogramFilter(self.glycan_chromatograms + self.unidentified_chromatograms))
            chrom, bar = builder.draw(self.score_threshold)
            self.figure_axes['chromatograms_chart'] = chrom
            self.figure_axes['abundance_bar_chart'] = bar
        except ValueError:
            ax = figax()
            ax.text(0.5, 0.5, "No Chromatograms Extracted", ha='center')
            ax.set_axis_off()
            self.figure_axes["chromatograms_chart"] = ArtistBase(ax)
            ax = figax()
            ax.text(0.5, 0.5, "No Entities Matched", ha='center')
            ax.set_axis_off()
            self.figure_axes['abundance_bar_chart'] = ArtistBase(ax)

    def abundance_bar_chart(self):
        try:
            return self.figure_axes['abundance_bar_chart']
        except KeyError:
            self._make_summary_graphics()
            return self.figure_axes['abundance_bar_chart']

    def chromatograms_chart(self):
        try:
            return self.figure_axes['chromatograms_chart']
        except KeyError:
            self._make_summary_graphics()
            return self.figure_axes['chromatograms_chart']

    def paginate(self, page, per_page=50):
        return SequencePagination.paginate(self.glycan_chromatograms, page, per_page)

    def __getitem__(self, i):
        return self.member_id_map[i]


class GlycanChromatographyAnalysisView(CollectionViewBase):
    def __init__(self, storage_record, analysis_id):
        CollectionViewBase.__init__(self, storage_record)
        self.analysis_id = analysis_id

        self.glycan_composition_filter = None
        self.monosaccharide_bounds = FilterSpecificationSet()
        self.score_threshold = 0.4
        self.analysis = None
        self.hypothesis = None

        self._converted_cache = WeakValueDictionary()

        self._snapshot_lock = RLock()
        self._snapshot = None

        with self:
            self._build_glycan_filter()

    def _resolve_sources(self):
        self.analysis = self.session.query(Analysis).get(self.analysis_id)
        self.hypothesis = self.analysis.hypothesis

    def _build_glycan_filter(self):
        self.glycan_composition_filter = GlycanCompositionFilter(self.hypothesis.glycans.all())

    def _get_valid_glycan_compositions(self):
        assert len(self.glycan_composition_filter.members) != 0
        query = self.monosaccharide_bounds.to_filter_query(self.glycan_composition_filter)
        inclusion_filter = InclusionFilter(query)
        return inclusion_filter

    def convert_glycan_chromatogram(self, glycan_chromatogram):
        if glycan_chromatogram.id in self._converted_cache:
            return self._converted_cache[glycan_chromatogram.id]
        else:
            inst = glycan_chromatogram.convert()
            self._converted_cache[glycan_chromatogram.id] = inst
            return inst

    def _get_glycan_chromatograms(self):
        chroma = self.session.query(GlycanCompositionChromatogram).filter(
            GlycanCompositionChromatogram.analysis_id == self.analysis_id,
            GlycanCompositionChromatogram.score > self.score_threshold).all()

        inclusion_filter = self._get_valid_glycan_compositions()

        return [self.convert_glycan_chromatogram(c) for c in chroma if c.glycan_composition_id in inclusion_filter]

    def _get_unidentified_chromatograms(self):
        chroma = self.session.query(UnidentifiedChromatogram).filter(
            UnidentifiedChromatogram.analysis_id == self.analysis_id,
            UnidentifiedChromatogram.score > self.score_threshold).all()
        return [c.convert() for c in chroma]

    def _build_snapshot(self):
        snapshot = GlycanChromatographySnapShot(
            self.score_threshold, self.monosaccharide_bounds,
            self._get_glycan_chromatograms(),
            self._get_unidentified_chromatograms())
        return snapshot

    def get_items_for_display(self):
        with self._snapshot_lock:
            if self._snapshot is None:
                self._snapshot = self._build_snapshot()
            elif not self._snapshot.is_valid(self.score_threshold, self.monosaccharide_bounds):
                self._snapshot = self._build_snapshot()
        return self._snapshot

    def paginate(self, page, per_page=25):
        return self.get_items_for_display().paginate(page, per_page)

    def update_connection(self):
        self.connect()

    def update_threshold(self, score_threshold, monosaccharide_bounds):
        self.score_threshold = score_threshold
        self.monosaccharide_bounds = monosaccharide_bounds


def get_view(analysis_uuid):
    if analysis_uuid in VIEW_CACHE:
        view = VIEW_CACHE[analysis_uuid]
        view.update_connection()
    else:
        record = g.manager.analysis_manager.get(analysis_uuid)
        view = GlycanChromatographyAnalysisView(record, record.id)
        VIEW_CACHE[analysis_uuid] = view
    return view


@app.route("/view_glycan_lcms_analysis/<analysis_uuid>")
def index(analysis_uuid):
    view = get_view(analysis_uuid)
    with view:
        args, state = request_arguments_and_context()
        view.update_threshold(state.settings['minimum_ms1_score'], state.monosaccharide_filters)
        return render_template("/view_glycan_search/overview.templ", analysis=view.analysis)


@app.route("/view_glycan_lcms_analysis/<analysis_uuid>/content", methods=['POST'])
def initialize_content(analysis_uuid):
    return render_template("/view_glycan_search/content.templ")


@app.route("/view_glycan_lcms_analysis/<analysis_uuid>/chromatograms_chart")
def chromatograms_chart(analysis_uuid):
    view = get_view(analysis_uuid)
    with view:
        snapshot = view.get_items_for_display()
        return report.svg_plot(snapshot.chromatograms_chart().ax, bbox_inches='tight')


@app.route("/view_glycan_lcms_analysis/<analysis_uuid>/page/<int:page>", methods=['POST'])
def page(analysis_uuid, page):
    view = get_view(analysis_uuid)
    with view:
        paginator = view.paginate(page, per_page=25)
        return render_template("/view_glycan_search/table.templ", paginator=paginator)


@app.route("/view_glycan_lcms_analysis/<analysis_uuid>/abundance_bar_chart")
def abundance_bar_chart(analysis_uuid):
    view = get_view(analysis_uuid)
    with view:
        snapshot = view.get_items_for_display()
        return report.svg_plot(snapshot.abundance_bar_chart().ax, bbox_inches='tight',
                               width=12, height=6)


@app.route("/view_glycan_lcms_analysis/<analysis_uuid>/details_for/<int:chromatogram_id>")
def details_for(analysis_uuid, chromatogram_id):
    view = get_view(analysis_uuid)
    with view:
        snapshot = view.get_items_for_display()
        chroma = snapshot[chromatogram_id]
        plot = SmoothingChromatogramArtist([chroma], colorizer=lambda *a, **k: 'green', ax=figax()).draw(
            label_function=lambda *a, **k: "", legend=False).ax
        plot.set_title("Aggregated\nExtracted Ion Chromatogram", fontsize=24)
        chroma_svg = report.svg_plot(plot, bbox_inches='tight', height=5, width=9)

        adduct_separation = ""
        if len(chroma.adducts) > 1:
            adducts = list(chroma.adducts)
            labels = {}
            rest = chroma
            for adduct in adducts:
                with_adduct, rest = rest.bisect_adduct(adduct)
                labels[adduct] = with_adduct
            adduct_plot = SmoothingChromatogramArtist(
                labels.values(),
                colorizer=lambda *a, **k: 'green', ax=figax()).draw(
                label_function=lambda *a, **k: tuple(a[0].adducts)[0].name,
                legend=False).ax
            adduct_plot.set_title(
                "Adduct-Separated\nExtracted Ion Chromatogram", fontsize=24)
            adduct_separation = report.svg_plot(adduct_plot, bbox_inches='tight', height=5, width=9)

        charge_separation = ""
        if len(chroma.charge_states) > 1:
            charge_separating_plot = ChargeSeparatingSmoothingChromatogramArtist(
                [chroma], ax=figax()).draw().ax
            charge_separating_plot.set_title("Charge-Separated\nExtracted Ion Chromatogram", fontsize=24)
            charge_separation = report.svg_plot(charge_separating_plot, bbox_inches='tight', height=5, width=9)

        return render_template(
            "/view_glycan_search/detail_modal.templ", chromatogram=chroma,
            chromatogram_svg=chroma_svg, adduct_separation_svg=adduct_separation,
            charge_chromatogram_svg=charge_separation)


@app.route("/view_glycan_lcms_analysis/<analysis_uuid>/to-csv")
def to_csv(analysis_uuid):
    view = get_view(analysis_uuid)
    with view:
        g.add_message(Message("Building CSV Export", "update"))
        snapshot = view.get_items_for_display()
        file_name = "%s-glycan-chromatograms.csv" % (view.analysis.name)
        path = g.manager.get_temp_path(file_name)
        GlycanLCMSAnalysisCSVSerializer(open(path, 'wb'), snapshot.glycan_chromatograms).start()
        return jsonify(filename=file_name)


def _export_csv(analysis_uuid):
    view = get_view(analysis_uuid)
    with view:
        g.add_message(Message("Building CSV Export", "update"))
        snapshot = view.get_items_for_display()
        file_name = "%s-glycan-chromatograms.csv" % (view.analysis.name)
        path = g.manager.get_temp_path(file_name)
        GlycanLCMSAnalysisCSVSerializer(open(path, 'wb'), snapshot.glycan_chromatograms).start()
    return [file_name]


def _export_hypothesis(analysis_uuid):
    view = get_view(analysis_uuid)
    with view:
        g.add_message(Message("Building CSV Export", "update"))
        snapshot = view.get_items_for_display()
        file_name = "%s-glycan-compositions.txt" % (view.analysis.name)
        path = g.manager.get_temp_path(file_name)
        composition_keys = {c.composition.id: c.composition for c in snapshot.glycan_chromatograms}
        compositions = [
            view.session.query(GlycanComposition).get(key) for key in composition_keys
        ]
        with open(path, 'wb') as handle:
            ImportableGlycanHypothesisCSVSerializer(handle, compositions).start()
    return [file_name]


serialization_formats = {
    "glycan chromatogrmas (csv)": _export_csv,
    "associated glycans (txt)": _export_hypothesis
}


@app.route("/view_glycan_lcms_analysis/<analysis_uuid>/export")
def export_menu(analysis_uuid):
    view = get_view(analysis_uuid)
    with view:
        options = [
            "glycan chromatogrmas (csv)",
            "associated glycans (txt)"
        ]
        return render_template(
            "/view_glycan_search/export_formats.templ",
            analysis_id=analysis_uuid, export_type_list=options,
            name=view.analysis.name)


@app.route("/view_glycan_lcms_analysis/<analysis_uuid>/export", methods=["POST"])
def export_data(analysis_uuid):
    file_names = []
    for format_key in request.values:
        if format_key in serialization_formats:
            work_task = serialization_formats[format_key]
            file_names.extend(
                work_task(analysis_uuid))
    return jsonify(status='success', filenames=file_names)

