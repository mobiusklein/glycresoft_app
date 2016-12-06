from click import Abort

from glycan_profiling.cli.validators import (
    validate_modifications, validate_glycan_source,
    validate_glycopeptide_hypothesis_name)

from glycan_profiling.cli.build_db import _glycan_hypothesis_builders

from glycan_profiling.database.builder.glycopeptide.naive_glycopeptide import (
    MultipleProcessFastaGlycopeptideHypothesisSerializer)

from glycopeptidepy.structure.modification import RestrictedModificationTable

from glycresoft_app.utils import json_serializer
from .task_process import Task, Message, null_user


def fasta_glycopeptide(database_connection, fasta_file, enzyme, missed_cleavages, occupied_glycosites, name,
                       constant_modification, variable_modification, processes, glycan_source, glycan_source_type,
                       channel):
    context = None
    validate_modifications(
        context, constant_modification + variable_modification)
    validate_glycan_source(context, database_connection,
                           glycan_source, glycan_source_type)

    if name is not None:
        name = validate_glycopeptide_hypothesis_name(
            context, database_connection, name)

    mt = RestrictedModificationTable(
        None, constant_modification, variable_modification)
    constant_modification = [mt[c] for c in constant_modification]
    variable_modification = [mt[c] for c in variable_modification]

    glycan_hypothesis_id = _glycan_hypothesis_builders[
        glycan_source_type](database_connection, glycan_source, name)

    builder = MultipleProcessFastaGlycopeptideHypothesisSerializer(
        fasta_file, database_connection,
        glycan_hypothesis_id=glycan_hypothesis_id,
        protease=enzyme,
        constant_modifications=constant_modification,
        variable_modifications=variable_modification,
        max_missed_cleavages=missed_cleavages,
        max_glycosylation_events=occupied_glycosites,
        hypothesis_name=name,
        n_processes=processes)

    try:
        builder.start()
        builder.session.add(builder.hypothesis)
        channel.send(Message(json_serializer.handle_glycopeptide_hypothesis(
            builder.hypothesis), "new-hypothesis"))
    except Exception:
        channel.send(Message.traceback())


class BuildGlycopeptideHypothesisFasta(Task):
    def __init__(self, database_connection, fasta_file, enzyme, missed_cleavages, occupied_glycosites, name,
                 constant_modification, variable_modification, processes, glycan_source, glycan_source_type,
                 callback=lambda: 0, **kwargs):
        args = (database_connection, fasta_file, enzyme, missed_cleavages, occupied_glycosites, name,
                constant_modification, variable_modification, processes, glycan_source, glycan_source_type)
        job_name = "Fasta Glycopeptide Hypothesis %s" % (name,)
        kwargs.setdefault('name', job_name)
        super(BuildGlycopeptideHypothesisFasta, self).__init__(fasta_glycopeptide, args, callback, **kwargs)
