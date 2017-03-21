import logging

from flask import Response, g, jsonify, render_template, request
from .service_module import register_service

from glycresoft_app.task.index_db import IndexDatabaseTask

api = register_service("maintenance", __name__)

logger = logging.getLogger("glycresoft_app.js_error")


@api.route("/index_db")
def index_db():
    g.manager.add_task(IndexDatabaseTask(g.manager.database_connection._original_connection))
    return jsonify(status="success")


@api.route("/server_log")
def view_server_log():
    path = g.manager.application_log_path
    return Response(
        "<pre>%s</pre>" % open(path).read().replace(
            ">", "&gt;").replace(
            "<", "&lt;").decode(
            "string_escape"),
        mimetype='application/text')


@api.route("/server_settings")
def form_render():
    return render_template("components/settings-form.templ")


@api.route("/log_js_error", methods=["POST"])
def log_js_errors():
    json = request.get_json()
    logger.info("JS Error: %r\n%r" % (json, request.values))
    return Response("logged")
