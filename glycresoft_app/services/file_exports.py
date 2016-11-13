import os
import base64

from flask import Response, g, abort
from .service_module import register_service

file_exports = register_service("file_exports", __name__)


@file_exports.route("/internal/file_download/<b64name>")
def download_file(b64name):
    name = base64.b64decode(b64name)
    path = os.path.join(g.manager.temp_dir, name)
    if os.path.exists(path):
        def yielder():
            for line in open(path):
                yield line
        return Response(yielder(), mimetype="application/octet-stream",
                        headers={"Content-Disposition": "attachment; filename=%s;" % name})
    else:
        return abort(404)
