import logging
import os

from six import text_type

from flask import Response, g, jsonify, abort

from .service_module import register_service
from ..task.dummy_task import DummyTask

task_actions = register_service("task_management", __name__)

logger = logging.getLogger("glycresoft_app.task_management")

@task_actions.route("/internal/log/<task_name>")
def send_log(task_name):
    try:
        log_file = g.manager.get_task_path(task_name + '.log')
        wrapper = """<pre class='log-display' data-log-name="{task_name}">{content}</pre>"""
        log_buffer = open(log_file, 'r').read()
        formatted_buffer = log_buffer.replace(
            ">", "&gt;").replace("<", "&lt;")
        if not isinstance(formatted_buffer, text_type):
            encoded_contents = formatted_buffer.decode('string_escape')
        else:
            encoded_contents = formatted_buffer

        log_content = wrapper.format(
            task_name=task_name, content=encoded_contents.replace("\\n", "\n"))
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
    path = g.manager.get_task_path(task_name + '.log')
    if os.path.exists(path):
        def yielder():
            for line in open(path, 'rb'):
                yield line
        return Response(yielder(), mimetype="application/octet-stream",
                        headers={"Content-Disposition": "attachment; filename=%s" % (task_name + '.log', )})
    else:
        logger.info("Requested path %r, but file not found" % (path,))
        return abort(404)
