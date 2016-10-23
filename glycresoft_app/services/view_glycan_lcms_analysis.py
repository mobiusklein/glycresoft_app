from flask import Response, g, request, render_template
from .service_module import register_service

from glycresoft_app.utils.state_transfer import request_arguments_and_context
from glycresoft_app import report
from glycresoft_app.utils.pagination import SequencePagination

from glycan_profiling.serialize import (
    Analysis, GlycanComposition, GlycanHypothesis, GlycanCompositionChromatogram,
    UnidentifiedChromatogram, func)

from glycan_profiling.database.glycan_composition_filter import (
    GlycanCompositionFilter, InclusionFilter)

from glycan_profiling.plotting.summaries import (
    GlycanChromatographySummaryGraphBuilder, SmoothingChromatogramArtist,
    figax)

app = view_glycan_lcms_analysis = register_service("view_glycan_lcms_analysis", __name__)


VIEW_CACHE = dict()


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
            x.id: x for x in self.glycan_chromatograms + self.unidentified_chromatograms
        }

    def is_valid(self, score_threshold, glycan_filters):
        if self.score_threshold != score_threshold:
            return False
        if self.glycan_filters != glycan_filters:
            return False
        return True

    def _make_summary_graphics(self):
        builder = GlycanChromatographySummaryGraphBuilder(self.glycan_chromatograms + self.unidentified_chromatograms)
        chrom, bar = builder.draw(self.score_threshold)
        self.figure_axes['chromatograms_chart'] = chrom
        self.figure_axes['abundance_bar_chart'] = bar

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


class AnalysisView(object):
    def __init__(self, session, analysis_id):
        self.analysis_id = analysis_id
        self.session = session
        self.glycan_composition_filter = None
        self.monosaccharide_bounds = []
        self.score_threshold = 0.4
        self.analysis = None
        self.hypothesis = None

        self._resolve_sources()
        self._build_glycan_filter()

        self._snapshot = None

    def _resolve_sources(self):
        self.analysis = self.session.query(Analysis).get(self.analysis_id)
        self.hypothesis = self.analysis.hypothesis

    def _build_glycan_filter(self):
        self.glycan_composition_filter = GlycanCompositionFilter(self.hypothesis.glycans)

    def _get_glycan_chromatograms(self):
        chroma = self.session.query(GlycanCompositionChromatogram).filter(
            GlycanCompositionChromatogram.analysis_id == self.analysis_id,
            GlycanCompositionChromatogram.score > self.score_threshold).all()
        return [c.convert() for c in chroma]

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
        if self._snapshot is None:
            self._snapshot = self._build_snapshot()
        elif self._snapshot.is_valid(self.score_threshold, self.monosaccharide_bounds):
            self._snapshot = self._build_snapshot()
        return self._snapshot

    def paginate(self, page, per_page=25):
        return self.get_items_for_display().paginate(page, per_page)

    def update_connection(self, session):
        self.session = session
        self._resolve_sources()


def get_view(analysis_id):
    if analysis_id in VIEW_CACHE:
        view = VIEW_CACHE[analysis_id]
        view.update_connection(g.manager.session)
    else:
        view = AnalysisView(g.manager.session, analysis_id)
        VIEW_CACHE[analysis_id] = view
    return view


@app.route("/view_glycan_lcms_analysis/<int:analysis_id>")
def index(analysis_id):
    view = get_view(analysis_id)
    return render_template("/view_glycan_search/overview.templ", analysis=view.analysis)


@app.route("/view_glycan_lcms_analysis/<int:analysis_id>/content", methods=['POST'])
def initialize_content(analysis_id):
    return render_template("/view_glycan_search/content.templ")


@app.route("/view_glycan_lcms_analysis/<int:analysis_id>/chromatograms_chart")
def chromatograms_chart(analysis_id):
    view = get_view(analysis_id)
    snapshot = view.get_items_for_display()
    return report.svg_plot(snapshot.chromatograms_chart().ax, bbox_inches='tight')


@app.route("/view_glycan_lcms_analysis/<int:analysis_id>/page/<int:page>", methods=['POST'])
def page(analysis_id, page):
    view = get_view(analysis_id)
    paginator = view.paginate(page, per_page=25)
    return render_template("/view_glycan_search/table.templ", paginator=paginator)


@app.route("/view_glycan_lcms_analysis/<int:analysis_id>/abundance_bar_chart")
def abundance_bar_chart(analysis_id):
    view = get_view(analysis_id)
    snapshot = view.get_items_for_display()
    return report.svg_plot(snapshot.abundance_bar_chart().ax, bbox_inches='tight',
                           width=12, height=6)


@app.route("/view_glycan_lcms_analysis/<int:analysis_id>/details_for/<int:chromatogram_id>")
def details_for(analysis_id, chromatogram_id):
    view = get_view(analysis_id)
    snapshot = view.get_items_for_display()
    chroma = snapshot[chromatogram_id]
    plot = SmoothingChromatogramArtist([chroma], ax=figax()).draw().ax
    chroma_svg = report.svg_plot(plot, bbox_inches='tight', height=4, width=6)
    return render_template(
        "/view_glycan_search/detail_modal.templ", chromatogram=chroma,
        chromatogram_svg=chroma_svg)
