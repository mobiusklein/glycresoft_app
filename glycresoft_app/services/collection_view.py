import os
import logging
import contextlib

from threading import RLock

from sqlalchemy.orm import object_session

from glycresoft.serialize import (
    DatabaseBoundOperation)

from glycresoft.structure import lru

logger = logging.getLogger("glycresoft_app.view_services")


class ViewCache(object):
    def __init__(self, size=3):
        self.cache = dict()
        self.policy = lru.LRUCache()
        self.size = size
        self.lock = RLock()

    def __contains__(self, key):
        with self.lock:
            return key in self.cache

    def get(self, key):
        with self.lock:
            view = self.cache[key]
            self.policy.hit_node(key)
        return view

    def __getitem__(self, key):
        return self.get(key)

    def set(self, key, value):
        logger.info("Storing %r, (Total Size: %d)\n%r", key, len(self.cache), self.cache.keys())
        with self.lock:
            if len(self.cache) >= self.size:
                try:
                    to_remove = self.policy.get_least_recently_used()
                    logger.info("Removing %r", to_remove)
                    self.cache.pop(to_remove)
                    self.policy.remove_node(to_remove)
                except KeyError:
                    pass
            self.cache[key] = value
            self.policy.add_node(key)

    def __setitem__(self, key, value):
        self.set(key, value)



class SimpleViewBase(object):
    def __init__(self, *args, **kwargs):
        self._instance_lock = RLock()

    def __enter__(self):
        self._instance_lock.acquire()
        self._resolve_sources()

    def __exit__(self, *args, **kwargs):
        self.close()
        self._instance_lock.release()

    def close(self):
        pass

    def _resolve_sources(self):
        pass


class CollectionViewBase(SimpleViewBase):
    def __init__(self, storage_record):
        super(CollectionViewBase, self).__init__(storage_record)
        self.storage_record = storage_record
        self.session = None

    def connect(self):
        self.connection = DatabaseBoundOperation(self.storage_record.path)
        logger.debug("Connecting %r to %r (CWD: %r)" % (self, self.storage_record.path, os.getcwd()))
        self.session = self.connection.session

    def close(self):
        if self.session is not None:
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


class SnapshotBase(object):
    def __init__(self):
        self.session = None
        self._instance_lock = RLock()

    def _update_bindings(self, session):
        self.session = session

    def _clear_bindings(self):
        self.session.expunge_all()
        self.session = None

    def _detatch_object(self, obj):
        session = object_session(obj)
        if session is not None:
            session.expunge(obj)

    @contextlib.contextmanager
    def bind(self, session):
        with self._instance_lock:
            self._update_bindings(session)
            yield
            self._clear_bindings()
