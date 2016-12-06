from flask import Response, g, jsonify
from ..task.dummy_task import DummyTask
from .service_module import register_service

task_actions = register_service("task_management", __name__)


@task_actions.route("/internal/log/<task_name>")
def send_log(task_name):
    try:
        return Response("<pre>%s</pre>" % open(
            g.manager.get_task_path(task_name + '.log'), 'r').read().replace(
            ">", "&gt;").replace("<", "&lt;").decode('string_escape'),
            mimetype='application/text')
    except KeyError:
        return Response("<span class='red-text'>There does not appear to be a log for this task</span>")


@task_actions.route("/internal/cancel_task/<task_id>")
def cancel_task(task_id):
    g.manager.cancel_task(task_id)
    return Response(task_id)


@task_actions.route("/internal/test_task")
def schedule_dummy_task():
    task = DummyTask()
    g.manager.add_task(task)
    return jsonify(task_id=task.id)
