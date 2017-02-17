import os
from os import path
from . import samples as sample, hypothesis, analysis


class Project(object):
    _directories_def = {
        "sample_dir": sample.SampleManager,
        "hypothesis_dir": hypothesis.HypothesisManager,
        "results_dir": analysis.AnalysisManager,
        "task_dir": None,
        "temp_dir": None
    }

    def __init__(self, base_path):
        self.base_path = base_path

        self.ensure_subdirectories()
        self.sample_manager = sample.SampleManager(path.join(self.sample_dir, "store.json"))
        self.hypothesis_manager = hypothesis.HypothesisManager(path.join(self.hypothesis_dir, "store.json"))
        self.analysis_manager = analysis.AnalysisManager(path.join(self.results_dir, "analysis.json"))

    def __repr__(self):
        return "Project(%r)" % (self.base_path,)

    def ensure_subdirectories(self):
        for key in self._directories_def:
            try:
                subdir = os.path.join(self.base_path, key)
                setattr(self, key, subdir)
                os.makedirs(subdir)
            except:
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
        self.sample_manager.rebuild()
        self.analysis_manager.rebuild()
        self.hypothesis_manager.rebuild()
