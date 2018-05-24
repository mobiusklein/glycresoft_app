import logging
from collections import defaultdict

from flask import Response, g, jsonify, render_template, request
from .service_module import register_service

from glycresoft_app.config import (
    get_parser as get_config_parser,
    write as write_config,
    convert_parser_to_config_dict,
    make_parser_from_ini_dict)

api = register_service("maintenance", __name__)

logger = logging.getLogger("glycresoft_app.js_error")


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
    manager = g.manager
    parser = get_config_parser(manager.configuration_path)
    return render_template("components/settings-form.templ", application_config=parser)


@api.route("/configuration")
def show_configuration():
    manager = g.manager
    parser = get_config_parser(manager.configuration_path)
    return render_template("components/configuration_form.templ", application_config=parser)


@api.route("/configuration", methods=["POST"])
def update_configuration():
    new_configuration = request.values.to_dict()
    config_hierarchy = defaultdict(dict)
    for key, value in new_configuration.items():
        section, name = key.split("_", 1)
        config_hierarchy[section][name] = value
    print("new_configuration")
    print(config_hierarchy)
    manager = g.manager
    config_parser = make_parser_from_ini_dict(config_hierarchy)
    with open(manager.configuration_path, 'w') as fh:
        config_parser.write(fh)
    manager.load_configuration()
    return jsonify(**config_hierarchy)


@api.route("/log_js_error", methods=["POST"])
def log_js_errors():
    json = request.get_json()
    logger.info("JS Error: %r\n%r" % (json, request.values))
    return Response("logged")


@api.route("/error_server")
def error_server():
    raise Exception("You asked for it!")


@api.errorhandler(Exception)
def error_logging_hook(error):
    logging.exception("Unhandled Error: %r" % error)
    return str(error), 500
