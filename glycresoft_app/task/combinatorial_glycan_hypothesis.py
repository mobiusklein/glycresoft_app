from click import Abort

from glycan_profiling.cli.build_db import (
    CombinatorialGlycanHypothesisSerializer, validate_reduction,
    validate_derivatization, validate_glycan_hypothesis_name)

from glycresoft_app.utils import json_serializer
from .task_process import Task, Message


def build_combinatorial_hypothesis(rule_file, database_connection, reduction, derivatization, name, channel):
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
        builder = CombinatorialGlycanHypothesisSerializer(
            rule_file, database_connection,
            reduction=reduction,
            derivatization=derivatization,
            hypothesis_name=name)
        builder.start()
        channel.send(Message(json_serializer.handle_glycan_hypothesis(builder.hypothesis), "new-hypothesis"))
    except:
        channel.send(Message.traceback())


class BuildCombinatorialGlycanHypothesis(Task):
    def __init__(self, rule_file, database_connection, reduction, derivatization, name,
                 callback, **kwargs):
        args = (rule_file, database_connection, reduction, derivatization, name)
        job_name = "Combinatorial Glycan Hypothesis %s" % (name,)
        kwargs.setdefault('name', job_name)
        Task.__init__(self, build_combinatorial_hypothesis, args, callback, **kwargs)
