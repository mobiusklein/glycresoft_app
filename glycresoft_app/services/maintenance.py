from uuid import uuid4
from flask import Response, g, jsonify, current_app, render_template
from .service_module import register_service

from glycresoft_app.task.index_db import IndexDatabaseTask
from glycresoft_app.task.task_process import Message

api = register_service("maintenance", __name__)


@api.route("/index_db")
def index_db():
    g.manager.add_task(IndexDatabaseTask())
    return jsonify(status="success")


@api.route("/server_log")
def view_server_log():
    path = g.manager.application_log_path
    return Response(
        "<pre>%s</pre>" % open(path).read().replace(
            ">", "&gt;").replace("<", "&lt;").decode('string_escape'),
        mimetype='application/text')


@api.route("/server_settings")
def form_render():
    return render_template("components/settings-form.templ")
