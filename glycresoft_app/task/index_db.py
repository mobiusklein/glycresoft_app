from glycan_profiling.serialize import DatabaseBoundOperation
from .task_process import Task, Message


def index_database(database_connection, channel):
    try:
        channel.send(Message("Analyzing Database", 'update'))
        handle = DatabaseBoundOperation(database_connection)
        handle._analyze_database()
        channel.send(Message("Indexing Complete", 'update'))
    except:
        channel.send(Message.traceback())


class IndexDatabaseTask(Task):
    def __init__(self, *args, **kwargs):
        Task.__init__(self, index_database, args, **kwargs)
