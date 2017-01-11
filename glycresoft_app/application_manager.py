import logging
import os
import pickle
from os import path
from threading import RLock

from glycan_profiling.serialize import (
    DatabaseBoundOperation, SampleRun, GlycanHypothesis,
    GlycopeptideHypothesis, Analysis, AnalysisTypeEnum)

from glycresoft_app.task.task_process import TaskManager
from glycresoft_app.vendor import sqlitedict
from glycresoft_app.config import get as config_from_path


class ApplicationManager(object):
    app_data_name = "app_data.db"
    _config_file_name = "config.ini"

    project_id = None

    def __init__(self, database_connection, base_path=None):
        if base_path is None:
            base_path = os.getcwd()
        self.base_path = os.path.abspath(base_path)
        self.configuration = dict()
        self.configuration.update(
            config_from_path(self.configuration_path))

        self.database_connection = DatabaseBoundOperation(database_connection)

        self.sample_dir = path.join(base_path, 'sample_dir')
        self.results_dir = path.join(base_path, 'results_dir')
        self.temp_dir = path.join(base_path, 'temp_dir')
        self.task_dir = path.join(base_path, 'task_dir')

        self._ensure_paths_exist()

        self._data_lock = RLock()
        self.app_data = sqlitedict.SqliteDict(self.app_data_path, autocommit=True)

        self.task_manager = TaskManager(self.task_dir)

        logger = logging.getLogger()
        logger.addHandler(logging.FileHandler(self.application_log_path, mode='a'))

    def __eq__(self, other):
        try:
            return self.database_connection == other.database_connection
        except AttributeError:
            return NotImplemented

    def __hash__(self):
        return hash(self.database_connection)

    @property
    def application_log_path(self):
        return os.path.join(self.base_path, "glycresoft-log")

    @property
    def configuration_path(self):
        return os.path.join(self.base_path, self._config_file_name)

    @property
    def halting(self):
        return self.task_manager.halting

    @halting.setter
    def halting(self, value):
        self.task_manager.halting = bool(value)

    @property
    def messages(self):
        return self.task_manager.messages

    @property
    def tasks(self):
        return self.task_manager.tasks

    def stoploop(self):
        return self.task_manager.stoploop()

    def add_message(self, message):
        return self.task_manager.add_message(message)

    @property
    def session(self):
        return self.database_connection.session

    @property
    def connection_bridge(self):
        return self.database_connection._original_connection

    @property
    def app_data_path(self):
        return self.get_temp_path(self.app_data_name)

    def _ensure_paths_exist(self):
        try:
            os.makedirs(self.sample_dir)
        except:
            pass
        try:
            os.makedirs(self.results_dir)
        except:
            pass
        try:
            os.makedirs(self.temp_dir)
        except:
            pass
        try:
            os.makedirs(self.task_dir)
        except:
            pass

    def get_sample_path(self, name):
        return path.join(self.sample_dir, name)

    def get_temp_path(self, name):
        return path.join(self.temp_dir, name)

    def get_task_path(self, name):
        return path.join(self.task_dir, name)

    def get_results_path(self, name):
        return path.join(self.results_dir, name)

    def make_task_context(self, name):
        return {
            "results_dir": self.get_results_path(name),
            "temp_dir": self.get_temp_path(name),
        }

    def add_task(self, task):
        context = self.make_task_context(task.name)
        task.update_control_context(context)
        self.task_manager.add_task(task)
        path = self.get_task_path(task.name)
        pickle.dump(task.args[:-1], open(path, 'wb'))

    def cancel_task(self, task_id):
        self.task_manager.cancel_task(task_id)

    def cancel_all_tasks(self):
        self.task_manager.cancel_all_tasks()

    def __getitem__(self, key):
        return self.app_data[key]

    def __setitem__(self, key, value):
        self.app_data[key] = value

    def samples(self, include_incomplete=True):
        q = self.session.query(SampleRun)
        if not include_incomplete:
            q = q.filter(SampleRun.completed)
        return q

    def glycan_hypotheses(self):
        return self.session.query(GlycanHypothesis)

    def glycopeptide_hypotheses(self):
        return self.session.query(GlycopeptideHypothesis)

    def analyses(self):
        return self.session.query(Analysis)

    def glycan_analyses(self):
        return self.session.query(Analysis).filter(
            Analysis.analysis_type == AnalysisTypeEnum.glycan_lc_ms.name)

    def get_next_job_number(self):
        with self._data_lock:
            try:
                job_count = self.app_data['_job_count']
            except KeyError:
                job_count = 0
            self.app_data['_job_count'] = job_count + 1
        return job_count


class UnknownProjectError(Exception):
    pass


class ProjectIDAllocationError(Exception):
    pass


class ProjectMultiplexer(object):
    def __init__(self):
        self.storage = dict()
        self.counter = 0
        self._lock = RLock()

    def register_project(self, project_manager):
        if project_manager.project_id is not None:
            with self._lock:
                project_id = project_manager.project_id
                if project_id in self.storage:
                    if project_manager == self.get_project(project_id):
                        return project_id
                    else:
                        raise ProjectIDAllocationError("Project Manager %r's ID has been reallocated." % (
                            project_manager,))
        with self._lock:
            self.storage[self.counter] = project_manager
            project_manager.project_id = self.counter
            self.counter += 1
        return project_manager.project_id

    def unregister_project(self, project_id):
        with self._lock:
            self.storage.pop(project_id, None)

    def get_project(self, project_id):
        try:
            with self._lock:
                project = self.storage[project_id]
            return project
        except KeyError:
            raise UnknownProjectError(project_id)

    def __len__(self):
        with self._lock:
            n = len(self.storage)
        return n

    def __iter__(self):
        with self._lock:
            gen = iter(list(self.storage.items()))
        return gen
