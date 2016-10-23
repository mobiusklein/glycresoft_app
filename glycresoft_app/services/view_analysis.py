from flask import Response, g, request, render_template, abort
from .service_module import register_service
from . import view_glycan_lcms_analysis, view_glycopeptide_lcmsms_analysis


from glycan_profiling.serialize import Analysis, AnalysisTypeEnum


app = view_analysis = register_service("view_analysis", __name__)


@app.route("/view_analysis/<int:id>", methods=['POST'])
def view_analysis_dispatch(id):
    analysis = g.manager.session.query(Analysis).get(id)
    if analysis.analysis_type == AnalysisTypeEnum.glycan_lc_ms:
        return view_glycan_lcms_analysis.index(id)
    else:
        return abort(404)
