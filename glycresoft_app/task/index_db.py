from glycan_profiling.serialize import DatabaseBoundOperation
from glycan_profiling.serialize.hypothesis import Glycopeptide
from .task_process import Task, Message


def find_index_by_name(table, index_name):
    for ix in table.indexes:
        if ix.name == index_name:
            return ix
    return None


index_updates = [(Glycopeptide.__table__, "ix_Glycopeptide_mass_search_index")]


def index_database(database_connection, channel):
    try:
        channel.send(Message("Analyzing Database", 'update'))
        handle = DatabaseBoundOperation(database_connection)

        for (table, ix_name) in index_updates:
            session = handle.session()
            connection = session.connection()
            index = find_index_by_name(table, ix_name)
            if index is None:
                continue
            try:
                index.create(connection)
            except:
                session.rollback()
            session.commit()

        handle._analyze_database()
        channel.send(Message("Indexing Complete", 'update'))
    except:
        channel.send(Message.traceback())


class IndexDatabaseTask(Task):
    def __init__(self, *args, **kwargs):
        Task.__init__(self, index_database, args, **kwargs)
