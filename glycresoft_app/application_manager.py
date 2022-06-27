import logging
import os
import pickle

from time import sleep
from threading import RLock

import dill

from glycan_profiling.serialize import (
    DatabaseBoundOperation, SampleRun, GlycanHypothesis,
    GlycopeptideHypothesis, Analysis, AnalysisTypeEnum)


from glycan_profiling.task import log_handle

from glycresoft_app.task.task_process import TaskManager
from glycresoft_app.config import get as config_from_path

from glycresoft_app.project.project import Project, safepath
from glycresoft_app.utils.message_queue import null_user



def has_access(record, user):
    if user is None:
        return True
    else:
        return user.has_access(record)


class ApplicationManager(Project):
    _config_file_name = "config.ini"

    project_id = None

    def __init__(self, database_connection, base_path=None, validate=False):
        if base_path is None:
            base_path = os.getcwd()
        Project.__init__(self, base_path, validate=validate)

        self.load_configuration()

        self.database_connection = DatabaseBoundOperation(
            database_connection)

        self.task_manager = TaskManager(
            self.task_dir)

        self.task_manager.register_event_handler("new-sample-run", self.handle_new_sample_run)
        self.task_manager.register_event_handler("new-hypothesis", self.handle_new_hypothesis)
        self.task_manager.register_event_handler("new-analysis", self.handle_new_analysis)

        logger = logging.getLogger()
        logger.addHandler(
            logging.FileHandler(
                self.application_log_path, mode='a'))

    def __eq__(self, other):
        try:
            return self.database_connection == other.database_connection
        except AttributeError:
            return NotImplemented

    def __hash__(self):
        return hash(self.database_connection)

    @property
    def application_log_path(self):
        return safepath(os.path.join(
            self.base_path, "glycresoft-log"))

    @property
    def escaped_base_path(self):
        return self.base_path.encode("unicode_escape").decode('utf8')

    @property
    def configuration_path(self):
        return safepath(os.path.join(
            self.base_path, self._config_file_name))

    def load_configuration(self):
        self.configuration = dict()
        self.configuration.update(
            config_from_path(
                self.configuration_path))

    @property
    def halting(self):
        return self.task_manager.halting

    @halting.setter
    def halting(self, value):
        self.task_manager.halting = bool(value)

    @property
    def messages(self):
        return self.task_manager.messages

    def tasks(self, user_id=None):
        tasks_dict = self.task_manager.tasks
        return {
            key: task for key, task in tasks_dict.items()
            if has_access(task, user_id)
        }

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
        return safepath(self.get_temp_path(self.app_data_name))

    def make_task_context(self, name):
        return {
            "results_dir": self.get_results_path(name),
            "temp_dir": self.get_temp_path(name),
        }

    def add_task(self, task):
        log_handle.log("Received Task %r (%s, %r)" % (task, task.name, task.id))
        context = self.make_task_context(task.name)
        task.update_control_context(context)
        self.task_manager.add_task(task)
        path = self.get_task_path(task.name)
        dill.dump(task.args[:-1], open(path, 'wb'))

    def cancel_task(self, task_id):
        self.task_manager.cancel_task(task_id)

    def cancel_all_tasks(self):
        self.task_manager.cancel_all_tasks()

    @property
    def max_running_tasks(self):
        return self.task_manager.max_running

    @max_running_tasks.setter
    def max_running_tasks(self, count):
        self.task_manager.max_running = count


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
