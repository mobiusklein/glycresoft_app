from .task_process import Task, Message
import time


def echo(*args, **kwargs):
    args[-1].send(Message("Start.... %s" % [args[:-1]], 'update', user=args[-1].user))
    time.sleep(15)
    args[-1].send(Message("Echo.... %s" % [args[:-1]], 'update', user=args[-1].user))


class DummyTask(Task):
    def __init__(self, *args, **kwargs):
        Task.__init__(self, echo, args, **kwargs)
