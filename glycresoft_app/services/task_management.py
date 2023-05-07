import logging
import os

from xml.sax.saxutils import escape

from six import text_type

from flask import Response, g, jsonify, abort

from .service_module import register_service
from ..task.dummy_task import DummyTask

task_actions = register_service("task_management", __name__)

logger = logging.getLogger("glycresoft_app.task_management")

def format_log_content(log_buffer: str, task_name: str=None, wrap: bool=True) -> str:
    if not isinstance(log_buffer, text_type):
        encoded_contents = log_buffer.decode('string_escape')
    else:
        encoded_contents = log_buffer

    if wrap:
        encoded_contents = escape(encoded_contents)
        wrapper = """<pre class='log-display' data-log-name="{task_name}">{content}</pre>"""
        log_content = wrapper.format(
            task_name=task_name, content=encoded_contents.replace("\\n", "\n"))
    else:
        log_content = log_buffer
    return log_content


@task_actions.route("/internal/log/<task_name>")
def send_log(task_name):
    try:
        log_file = g.manager.get_task_path(task_name) + '.log'
        if not os.path.exists(log_file):
            log_file = g.manager.find_log_file(task_name)
            if log_file is None:
                return Response("<span class='red-text'>There does not appear to be a log for this task</span>")

        log_buffer = open(log_file, 'r').read()
        # wrapper = """<pre class='log-display' data-log-name="{task_name}">{content}</pre>"""
        # formatted_buffer = log_buffer.replace(
        #     ">", "&gt;").replace("<", "&lt;")
        # if not isinstance(formatted_buffer, text_type):
        #     encoded_contents = formatted_buffer.decode('string_escape')
        # else:
        #     encoded_contents = formatted_buffer

        # log_content = wrapper.format(
        #     task_name=task_name, content=encoded_contents.replace("\\n", "\n"))
        log_content = format_log_content(log_buffer, task_name, wrap=True)
        return Response(log_content, mimetype='text/html')
    except (KeyError, IOError):
        return Response("<span class='red-text'>There does not appear to be a log for this task</span>")


@task_actions.route("/internal/cancel_task/<task_id>")
def cancel_task(task_id):
    g.manager.cancel_task(task_id)
    return Response(task_id)


@task_actions.route("/internal/test_task")
def schedule_dummy_task():
    task = DummyTask()
    g.add_task(task)
    return jsonify(task_id=task.id)


@task_actions.route("/internal/test_task_error")
def schedule_error_dummy_task():
    task = DummyTask(throw=True)
    g.add_task(task)
    return jsonify(task_id=task.id)


@task_actions.route("/internal/download_log/<task_name>")
def download_log_file(task_name):
    path = g.manager.get_task_path(task_name) + '.log'
    if not os.path.exists(path):
        log_file = g.manager.find_log_file(task_name)
        if log_file is None:
            logger.info("Requested path %r, but file not found" % (path,))
            return abort(404)
        path = log_file

    if os.path.exists(path):
        def yielder():
            for line in open(path, 'rb'):
                yield line
        return Response(yielder(), mimetype="application/octet-stream",
                        headers={"Content-Disposition": "attachment; filename=%s" % (task_name + '.log', )})
    else:
        logger.info("Requested path %r, but file not found" % (path,))
        return abort(404)
