from flask import Response, g, Blueprint, jsonify
from ..task.dummy_task import DummyTask
from .service_module import register_service

task_actions = register_service("task_management", __name__)


@task_actions.route("/internal/log/<task_id>")
def send_log(task_id):
    return Response("<pre>%s</pre>" % open(
        g.manager.get_task_path(task_id + '.log'), 'r').read().replace(
        ">", "&gt;").replace("<", "&lt;").decode('string_escape'),
        mimetype='application/text')


@task_actions.route("/internal/test_task")
def schedule_dummy_task():
    task = DummyTask()
    g.manager.add_task(task)
    return jsonify(task_id=task.id)
