from click import Abort

from glycan_profiling.cli.build_db import (
    GlycanCompositionHypothesisMerger, validate_reduction,
    validate_derivatization, validate_glycan_hypothesis_name)

from glycresoft_app.utils import json_serializer
from .task_process import Task, Message


def merge_glycan_hypothesis(database_connection, hypothesis_ids, name, channel):
        if name is not None:
            name = validate_glycan_hypothesis_name(None, database_connection, name)
            channel.send(Message("Merging Glycan Hypothesis %s" % name, 'info'))
        try:
            task = GlycanCompositionHypothesisMerger(database_connection, [int(i) for i in hypothesis_ids], name)
            task.start()
            channel.send(Message(json_serializer.handle_glycan_hypothesis(task.hypothesis), "new-hypothesis"))
        except Exception as e:
            channel.send(Message.traceback())


class MergeGlycanHypotheses(Task):
    def __init__(self, database_connection, hypothesis_ids, name,
                 callback, **kwargs):
        args = (database_connection, hypothesis_ids, name)
        job_name = "Merged Glycan Hypothesis %s" % (name,)
        kwargs.setdefault('name', job_name)
        Task.__init__(self, merge_glycan_hypothesis, args, callback, **kwargs)
