from __future__ import print_function
import logging
from glycan_profiling.cli.base import cli

from flask import (
    Flask, request, session, g, redirect, url_for,
    abort, render_template, flash, Markup, make_response, jsonify,
    Response, current_app)

import click
from werkzeug.wsgi import LimitedStream

from glycresoft_app import report
# Set up json serialization methods
from glycresoft_app.utils import json_serializer
from glycresoft_app.application_manager import (
    ApplicationManager, ProjectMultiplexer, ProjectIDAllocationError,
    UnknownProjectError)
from glycresoft_app.services import (
    service_module)


class StreamConsumingMiddleware(object):

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        stream = LimitedStream(environ['wsgi.input'],
                               int(environ['CONTENT_LENGTH'] or 0))
        environ['wsgi.input'] = stream
        app_iter = self.app(environ, start_response)
        try:
            stream.exhaust()
            for event in app_iter:
                yield event
        finally:
            if hasattr(app_iter, 'close'):
                app_iter.close()


app = Flask(__name__)
app.wsgi_app = StreamConsumingMiddleware(app.wsgi_app)
app.config['PROPAGATE_EXCEPTIONS'] = True
report.prepare_environment(app.jinja_env)

DEBUG = True
SECRETKEY = 'TG9yZW0gaXBzdW0gZG90dW0'
SERVER = None
manager = None
project_multiplexer = None

service_module.load_all_services(app)


class ApplicationServerManager(object):
    def __init__(self, state=None):
        if state is None:
            state = dict()
        self.state = state

    @property
    def shutdown_server(self):
        return self.state["shutdown_server"]

    @shutdown_server.setter
    def shutdown_server(self, value):
        self.state["shutdown_server"] = value

    @classmethod
    def werkzeug_server(cls):
        def shutdown_func():
            func = request.environ.get('werkzeug.server.shutdown')
            if func is None:
                raise RuntimeError('Not running with the Werkzeug Server')

            func()
        inst = cls()
        inst.shutdown_server = shutdown_func
        return inst

# ----------------------------------------
# Server Shutdown
# ----------------------------------------


@app.route('/internal/shutdown', methods=['POST'])
def shutdown():
    g.manager.halting = True
    g.manager.stoploop()
    g.manager.cancel_all_tasks()
    SERVER.shutdown_server()
    return Response("Should be dead")

# ----------------------------------------
#
# ----------------------------------------


@app.route("/register_project", methods=["POST"])
def register_project():
    connection_string = request.values["connection_string"]
    base_path = request.values.get("basepath", manager.base_path)
    new_manager = ApplicationManager(connection_string, base_path)
    project_id = project_multiplexer.register_project(new_manager)
    return jsonify(project_id=project_id)


@app.route("/unregister_project", methods=["POST"])
def unregister_project():
    try:
        project_id = int(request.values["project_id"])
        project_multiplexer.unregister_project(project_id)
        return jsonify(status='success', project_id=project_id)
    except Exception:
        project_id = (request.values.get("project_id"))
        current_app.logger.error(
            "An error occurred while unregistering project %r." % project_id, exc_info=True)


# ----------------------------------------
#
# ----------------------------------------


@app.route("/internal/show_cache")
def show_cache():
    print(dict(g.manager.app_data))
    return Response("Printed")


def connect_db(project_id):
    try:
        manager = project_multiplexer.get_project(project_id)
        g.manager = manager
        g.db = manager.session
    except UnknownProjectError:
        current_app.logger.error("Unknown Project ID %d" % project_id)
        g.manager = manager
        g.db = manager.session
    except ProjectIDAllocationError:
        current_app.logger.error("ProjectIDAllocationError %d" % project_id)
        g.manager = manager
        g.db = manager.session


@app.route("/")
def index():
    return render_template("index.templ")


@app.before_request
def before_request():
    project_id = request.cookies.get("project_id", 0)
    connect_db(project_id)


@app.after_request
def per_request_callbacks(response):
    for func in getattr(g, 'call_after_request', ()):
        response = func(response)
    return response


@app.teardown_request
def teardown_request(exception):
    db = getattr(g, 'db', None)
    if db is not None:
        db.close()


@app.context_processor
def inject_info():
    from glycresoft_app.version import version
    return {
        "application_version": version
    }


@app.context_processor
def inject_config():
    return {
        "configuration": g.manager.configuration
    }


class RouteLoggingFilter(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        is_task_api = "GET /api/tasks " not in msg
        is_task_log = "GET /internal/log/" not in msg
        if is_task_api and is_task_log:
            return True
        else:
            return False


logging.getLogger("werkzeug").addFilter(RouteLoggingFilter())


@cli.command()
@click.pass_context
@click.argument("database-connection")
@click.option("-b", "--base-path", default=None, help='Location to store application instance information')
@click.option("-e", "--external", is_flag=True, help="Allow connections from non-local machines")
@click.option("-p", "--port", default=8080, type=int, help="The port to listen on")
def server(context, database_connection, base_path, external=False, port=None, no_execute_tasks=False):
    global manager, SERVER, project_multiplexer
    project_multiplexer = ProjectMultiplexer()
    manager = ApplicationManager(database_connection, base_path)
    project_multiplexer.register_project(manager)

    manager.configuration["allow_external_connections"] |= external
    host = None
    if manager.configuration["allow_external_connections"]:
        host = "0.0.0.0"
    app.debug = DEBUG
    app.secret_key = SECRETKEY
    SERVER = ApplicationServerManager.werkzeug_server()
    app.run(host=host, use_reloader=False, threaded=True, debug=DEBUG, port=port, passthrough_errors=True)
