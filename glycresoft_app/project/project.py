import os
import platform
import glob

from os import path
from threading import RLock
from typing import List, Optional

from glycresoft.serialize import (
    DatabaseBoundOperation, SampleRun, GlycanHypothesis,
    GlycopeptideHypothesis, Analysis, AnalysisTypeEnum)

from glycresoft.task import log_handle

from glycresoft_app.vendor import sqlitedict
from glycresoft_app.utils.message_queue import null_user, has_access

from . import sample, hypothesis, analysis


def _winapi_path(path: str) -> str:
    if path.startswith('\\\\?\\'):
        return path
    path = os.path.abspath(path)
    return '\\\\?\\' + path


def safepath(path: str) -> str:
    if platform.system().lower() == 'windows' and len(path) > 259:
        # Use UNC path notation to circumvent the ever-painful Win32 path length
        # constraint
        return _winapi_path(path)
    else:
        return path


def ensure_text(s) -> str:
    if isinstance(s, (bytes, bytearray)):
        s = s.decode('utf8')
    elif isinstance(s, str):
        pass
    else:
        s = str(s)
    return s


class Project(object):
    _directories_def = {
        "sample_dir": sample.SampleManager,
        "hypothesis_dir": hypothesis.HypothesisManager,
        "results_dir": analysis.AnalysisManager,
        "task_dir": None,
        "temp_dir": None
    }

    base_path: str
    sample_manager: sample.SampleManager
    hypothesis_manager: hypothesis.HypothesisManager
    analysis_manager: analysis.AnalysisManager
    _data_lock: RLock
    app_data: sqlitedict.SqliteDict

    app_data_name = "app_data.db"

    project_id = None

    def __init__(self, base_path, validate=False):
        self.base_path = safepath(os.path.abspath(base_path))

        self.ensure_subdirectories()
        self.sample_manager = sample.SampleManager(path.join(self.sample_dir, "store.json"))
        self.hypothesis_manager = hypothesis.HypothesisManager(path.join(self.hypothesis_dir, "store.json"))
        self.analysis_manager = analysis.AnalysisManager(path.join(self.results_dir, "analysis.json"))

        self._data_lock = RLock()
        self.app_data = sqlitedict.SqliteDict(
            self.app_data_path, autocommit=True)
        if validate:
            self.validate_indices()

    def __repr__(self):
        return "Project(%r)" % (self.base_path,)

    def ensure_subdirectories(self):
        for key in self._directories_def:
            try:
                subdir = safepath(os.path.join(self.base_path, key))
                setattr(self, key, subdir)
                os.makedirs(subdir)
            except Exception:
                pass

    def handle_new_sample_run(self, message):
        record = self.sample_manager.make_instance_record(message.message)
        self.sample_manager.put(record)
        self.sample_manager.dump()

    def handle_new_hypothesis(self, message):
        record = self.hypothesis_manager.make_instance_record(message.message)
        self.hypothesis_manager.put(record)
        self.hypothesis_manager.dump()

    def handle_new_analysis(self, message):
        record = self.analysis_manager.make_instance_record(message.message)
        self.analysis_manager.put(record)
        self.analysis_manager.dump()

    def force_build_indices(self):
        log_handle.log("Building Sample Index")
        self.sample_manager.rebuild()
        log_handle.log("Building Analysis Index")
        self.analysis_manager.rebuild()
        log_handle.log("Building Hypothesis Index")
        self.hypothesis_manager.rebuild()

    def get_sample_path(self, name):
        name = ensure_text(name)
        return safepath(path.join(self.sample_dir, name))

    def get_temp_path(self, name: str):
        name = ensure_text(name)
        return safepath(path.join(self.temp_dir, name))

    def get_task_path(self, name: str):
        name = ensure_text(name)
        return safepath(path.join(self.task_dir, name))

    def get_results_path(self, name):
        name = ensure_text(name)
        return safepath(path.join(self.results_dir, name))

    def get_hypothesis_path(self, name):
        name = ensure_text(name)
        return safepath(path.join(self.hypothesis_dir, name))

    def make_unique_sample_name(self, sample_name):
        base_name = sample_name
        current_name = base_name
        i = 0
        existing_names = {s.name for s in self.samples()}
        with self._data_lock:
            while current_name in existing_names:
                i += 1
                current_name = "%s (%d)" % (base_name, i)
        return current_name

    def make_unique_hypothesis_name(self, hypothesis_name):
        base_name = hypothesis_name
        current_name = base_name
        i = 0
        existing_names = {s.name for s in self.hypotheses()}
        with self._data_lock:
            while current_name in existing_names:
                i += 1
                current_name = "%s (%d)" % (base_name, i)
        return current_name

    @property
    def app_data_path(self):
        return self.get_temp_path(self.app_data_name)

    def __getitem__(self, key):
        if key == "preferences":
            raise RuntimeError()
        return self.app_data[key]

    def preferences(self, user_id=None):
        if user_id is None:
            user_id = null_user.id
        try:
            return self[user_id]['preferences']
        except KeyError:
            return {}

    def set_preferences(self, user_id=None, preferences=None):
        if preferences is None:
            return
        if user_id is None:
            user_id = null_user.id
        self.app_data.setdefault(user_id, {})
        user_data = self[user_id]
        user_data['preferences'] = preferences
        self[user_id] = user_data

    def __setitem__(self, key, value):
        self.app_data[key] = value

    def samples(self, user_id=None) -> List[sample.SampleRunRecord]:
        """Obtain all of the preprocessed MS runs available to the specified user"""
        q = [sample for sample in self.sample_manager
             if has_access(sample, user_id)]
        return q

    def hypotheses(self, user=None) -> List[hypothesis.HypothesisRecord]:
        """Obtain all of the search databases available to the specified user"""
        return [
            hypothesis
            for hypothesis in self.hypothesis_manager
            if has_access(hypothesis, user)
        ]

    def glycan_hypotheses(self, user=None) -> List[hypothesis.HypothesisRecord]:
        """Obtain all of the glycomics databases available to the specified user"""
        return [
            hypothesis
            for hypothesis in self.hypothesis_manager
            if hypothesis.hypothesis_type == "glycan_composition" and
            has_access(hypothesis, user)
        ]

    def glycopeptide_hypotheses(self, user=None) -> List[hypothesis.HypothesisRecord]:
        """Obtain all of the glycopeptide databases to the specified user"""
        return [
            hypothesis
            for hypothesis in self.hypothesis_manager
            if hypothesis.hypothesis_type == "glycopeptide" and
            has_access(hypothesis, user)
        ]

    def analyses(self, user=None):
        """Obtain all of the analyses available to the specified user"""
        return [analysis for analysis in self.analysis_manager
                if has_access(analysis, user)]

    def glycan_analyses(self, user=None) -> List[analysis.AnalysisRecord]:
        """Obtain all of the glycomics analyses available to the specified user"""
        return [analysis for analysis in (self.analysis_manager)
                if AnalysisTypeEnum.glycan_lc_ms == analysis.analysis_type and
                has_access(analysis, user)]

    def analyses_for_sample(self, sample_name: str) -> List[analysis.AnalysisRecord]:
        """Obtain all analyses of the given sample by name"""
        return [
            analysis for analysis in self.analysis_manager
            if analysis.sample_name == sample_name
        ]

    def get_next_job_number(self) -> int:
        """Get the next sequential job number and increment the counter"""
        with self._data_lock:
            try:
                job_count = self.app_data['_job_count']
            except KeyError:
                job_count = 0
            self.app_data['_job_count'] = job_count + 1
        return job_count

    def is_project_resolved(self, ratio=0.5):
        """Verifies that each hypothesis, sample, and analysis in the project can be loaded"""
        n = 0
        k = 0
        for record in self.hypotheses():
            log_handle.log("Testing %r" % (record, ))
            if record.is_resolvable():
                k += 1
            n += 1
        for record in self.samples():
            log_handle.log("Testing %r" % (record, ))
            if record.is_resolvable():
                k += 1
            n += 1
        for record in self.analyses():
            log_handle.log("Testing %r" % (record, ))
            if record.is_resolvable():
                k += 1
            n += 1
        if n == 0:
            return True
        return k / float(n) > ratio

    def validate_indices(self, ratio=0.5):
        """Regenerate the index JSON files for hypotheses, samples, and analyses"""
        with self._data_lock:
            if not self.is_project_resolved(ratio):
                log_handle.log("Rebuilding Project Indices")
                self.force_build_indices()

    def find_log_file(self, task_name: str) -> Optional[str]:
        """Find a log file path for the given task name"""
        base = self.get_task_path("*" + task_name)
        paths = glob.glob(base + '*.log')
        if paths:
            paths.sort(key=len, reverse=True)
            return paths[0]
        return None
