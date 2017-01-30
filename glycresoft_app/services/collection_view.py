from threading import RLock
from glycan_profiling.serialize import (
    DatabaseBoundOperation)


class CollectionViewBase(object):
    def __init__(self, storage_record):
        self.storage_record = storage_record
        self.session = None
        self._instance_lock = RLock()

    def connect(self):
        connection = DatabaseBoundOperation(self.storage_record.path)
        self.session = connection.session

    def close(self):
        self.session.close()
        self.session = None

    def __enter__(self):
        self._instance_lock.acquire()
        if self.session is not None:
            self.close()
        self.connect()
        self._resolve_sources()

    def __exit__(self, *args, **kwargs):
        self.close()
        self._instance_lock.release()

    def _resolve_sources(self):
        pass
