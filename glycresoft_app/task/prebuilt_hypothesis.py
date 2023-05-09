from click import Abort

from glycan_profiling.cli.build_db import (
    DatabaseBoundOperation, GlycanCompositionHypothesisMerger,
    validate_reduction, validate_derivatization, validate_glycan_hypothesis_name)

from glycan_profiling.cli.validators import validate_database_unlocked

from glycresoft_app.project import hypothesis as project_hypothesis
from .task_process import Task, Message


def build_prebuilt_hypothesis(recipes, database_connection, reduction, derivatization, name,
                              channel, **kwargs):

    if not validate_database_unlocked(database_connection):
        channel.send(Message("Database is locked.", "error"))
        return

    if name is not None:
        name = validate_glycan_hypothesis_name(None, database_connection, name)
        channel.send(Message("Building Glycan Hypothesis %s" % name, 'info'))
    try:
        reduction = str(reduction) if reduction is not None else None
        validate_reduction(None, reduction)
    except Abort:
        channel.send(Message("Could not validate reduction %s" % reduction), 'error')
        return
    try:
        derivatization = str(derivatization) if derivatization is not None else None
        validate_derivatization(None, derivatization)
    except Abort:
        channel.send(Message("Could not validate derivatization %s" % derivatization, 'error'))
        return
    try:
        if len(recipes) == 1:
            task = recipes[0]
            builder = task(
                database_connection, reduction=reduction, derivatization=derivatization,
                hypothesis_name=name)
        else:
            sub_builders = []
            for task in recipes:
                builder = task(
                    database_connection, reduction=reduction, derivatization=derivatization)
                sub_builders.append(builder)
            builder = GlycanCompositionHypothesisMerger(
                database_connection,
                [(database_connection, s.hypothesis.id) for s in sub_builders],
                hypothesis_name=name)
            builder.start()

        record = project_hypothesis.HypothesisRecordSet(database_connection)
        hypothesis_record = None

        for item in record:
            if item.uuid == builder.hypothesis.uuid:
                hypothesis_record = item
                hypothesis_record = hypothesis_record._replace(user_id=channel.user.id)
                channel.send(Message(hypothesis_record.to_json(), "new-hypothesis"))
                break
        else:
            channel.send(Message("Something went wrong (%r)" % (list(record),)))

    except Exception:
        channel.send(Message.traceback())


class BuildPreBuiltGlycanHypothesis(Task):
    def __init__(self, recipes, database_connection, reduction, derivatization, name,
                 callback, **kwargs):
        args = (recipes, database_connection, reduction, derivatization, name)
        job_name = "Glycan Hypothesis %s" % (name,)
        kwargs.setdefault('name', job_name)
        Task.__init__(self, build_prebuilt_hypothesis, args, callback, **kwargs)
