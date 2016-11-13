import os
import pickle
from os import path
from threading import RLock

from glycan_profiling.serialize import (
    DatabaseBoundOperation, SampleRun, GlycanHypothesis,
    GlycopeptideHypothesis, Analysis, AnalysisTypeEnum)

from glycresoft_app.task.task_process import TaskManager
from glycresoft_app.vendor import sqlitedict


class ApplicationManager(object):
    app_data_name = "app_data.db"

    def __init__(self, database_conection, base_path=None):
        if base_path is None:
            base_path = os.getcwd()
        self.base_path = os.path.abspath(base_path)
        self.database_conection = DatabaseBoundOperation(database_conection)

        self.sample_dir = path.join(base_path, 'sample_dir')
        self.results_dir = path.join(base_path, 'results_dir')
        self.temp_dir = path.join(base_path, 'temp_dir')
        self.task_dir = path.join(base_path, 'task_dir')

        self._ensure_paths_exist()

        self._data_lock = RLock()
        self.app_data = sqlitedict.SqliteDict(self.app_data_path, autocommit=True)

        self.task_manager = TaskManager(self.task_dir)

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
        return self.database_conection.session

    @property
    def connection_bridge(self):
        return self.database_conection._original_connection

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

    def add_task(self, task):
        self.task_manager.add_task(task)
        path = self.get_task_path(task.name)
        pickle.dump(task.args[:-1], open(path, 'wb'))

    def __getitem__(self, key):
        return self.app_data[key]

    def __setitem__(self, key, value):
        self.app_data[key] = value

    def samples(self):
        return self.session.query(SampleRun)

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
