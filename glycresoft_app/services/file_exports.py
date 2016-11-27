import os
import base64

from flask import Response, g, abort, request, render_template
from .service_module import register_service

file_exports = register_service("file_exports", __name__)


@file_exports.route("/copy-file-form", methods=["GET"])
def copy_file_to_server():
    return render_template("components/copy_file_to_server.templ")


@file_exports.route("/copy-file-form", methods=["POST"])
def copy_file_to_server_post():
    print request.files['target-file']
    return Response("Done")


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
