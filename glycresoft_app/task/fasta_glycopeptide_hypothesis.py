from click import Abort

from glycan_profiling.cli.validators import (
    validate_modifications, validate_glycan_source,
    validate_glycopeptide_hypothesis_name)

from glycan_profiling.cli.build_db import _glycan_hypothesis_builders

from glycan_profiling.database.builder.glycopeptide.naive_glycopeptide import (
    MultipleProcessFastaGlycopeptideHypothesisSerializer,
    ReversingMultipleProcessFastaGlycopeptideHypothesisSerializer)

from glycresoft_app.project import hypothesis as project_hypothesis

from glycopeptidepy.structure.modification import RestrictedModificationTable

from .task_process import Task, Message


def fasta_glycopeptide(database_connection, fasta_file, enzyme, missed_cleavages, occupied_glycosites, name,
                       constant_modification, variable_modification, processes, glycan_source, glycan_source_type,
                       glycan_source_identifier, peptide_length_range, semispecific_digest, generate_full_crossproduct,
                       generate_reverse_decoys, channel):
    context = None
    try:
        validate_modifications(
            context, constant_modification + variable_modification)
    except Exception:
        channel.abort(
            "Could not validate the modification specification, Constant: %s, Variable: %s" % (
                constant_modification, variable_modification))
    try:
        validate_glycan_source(context, database_connection,
                               glycan_source, glycan_source_type,
                               glycan_source_identifier)
    except Abort:
        channel.abort("Could not validate the glycan source, %s, %s" % (glycan_source, glycan_source_type))

    if name is not None:
        name = validate_glycopeptide_hypothesis_name(
            context, database_connection, name)

    mt = RestrictedModificationTable(
        None, constant_modification, variable_modification)
    constant_modification = [mt[c] for c in constant_modification]
    variable_modification = [mt[c] for c in variable_modification]

    glycan_hypothesis_id = _glycan_hypothesis_builders[
        glycan_source_type](database_connection, glycan_source, name, glycan_source_identifier)

    builder = MultipleProcessFastaGlycopeptideHypothesisSerializer(
        fasta_file, database_connection,
        glycan_hypothesis_id=glycan_hypothesis_id,
        protease=enzyme,
        constant_modifications=constant_modification,
        variable_modifications=variable_modification,
        max_missed_cleavages=missed_cleavages,
        max_glycosylation_events=occupied_glycosites,
        hypothesis_name=name,
        peptide_length_range=peptide_length_range,
        semispecific=semispecific_digest,
        n_processes=processes,
        full_cross_product=generate_full_crossproduct)

    decoy_builder = None
    decoy_database_connection = None
    if generate_reverse_decoys:
        prefix, ext = database_connection.rsplit(".", 1)
        decoy_database_connection = "%s.decoy.%s" % (prefix, ext)

        try:
            validate_glycan_source(context, decoy_database_connection,
                                   glycan_source, glycan_source_type,
                                   glycan_source_identifier)
        except Abort:
            channel.abort("Could not validate the glycan source, %s, %s" %
                        (glycan_source, glycan_source_type))

        decoy_glycan_hypothesis_id = _glycan_hypothesis_builders[
            glycan_source_type](decoy_database_connection, glycan_source, name, glycan_source_identifier)

        decoy_builder = ReversingMultipleProcessFastaGlycopeptideHypothesisSerializer(
            fasta_file, decoy_database_connection,
            glycan_hypothesis_id=decoy_glycan_hypothesis_id,
            protease=enzyme,
            constant_modifications=constant_modification,
            variable_modifications=variable_modification,
            max_missed_cleavages=missed_cleavages,
            max_glycosylation_events=occupied_glycosites,
            hypothesis_name=name,
            peptide_length_range=peptide_length_range,
            semispecific=semispecific_digest,
            n_processes=processes,
            full_cross_product=generate_full_crossproduct)

    try:
        builder.start()
        record = project_hypothesis.HypothesisRecordSet(database_connection)
        hypothesis_record = None
        decoy_hypothesis_record = None

        if decoy_builder:
            decoy_builder.start()
            decoy_record = project_hypothesis.HypothesisRecordSet(
                decoy_database_connection)
            for item in decoy_record:
                if item.uuid == decoy_builder.hypothesis.uuid:
                    decoy_hypothesis_record = item._replace(
                        user_id=channel.user.id,
                        options={'full_cross_product': generate_full_crossproduct})
                    break
            else:
                channel.send(Message("Something went wrong (%r)" %
                                    (list(record),)))
                channel.abort("Could not extract decoy hypothesis")

        for item in record:
            if item.uuid == builder.hypothesis.uuid:
                hypothesis_record = item
                hypothesis_record = hypothesis_record._replace(
                    user_id=channel.user.id,
                    options={'full_cross_product': generate_full_crossproduct})
                if decoy_hypothesis_record is not None:
                    hypothesis_record = hypothesis_record._replace(
                        decoy_hypothesis=decoy_hypothesis_record)
                channel.send(Message(hypothesis_record.to_json(), "new-hypothesis"))
                break
        else:
            channel.send(Message("Something went wrong (%r)" % (list(record),)))
    except Exception:
        channel.send(Message.traceback())


class BuildGlycopeptideHypothesisFasta(Task):
    def __init__(self, database_connection, fasta_file, enzyme, missed_cleavages, occupied_glycosites, name,
                 constant_modification, variable_modification, processes, glycan_source, glycan_source_type,
                 glycan_source_identifier, peptide_length_range, semispecific_digest, generate_full_crossproduct=True,
                 generate_reverse_decoys=False,
                 callback=lambda: 0, **kwargs):
        args = (database_connection, fasta_file, enzyme, missed_cleavages, occupied_glycosites, name,
                constant_modification, variable_modification, processes, glycan_source, glycan_source_type,
                glycan_source_identifier, peptide_length_range, semispecific_digest, generate_full_crossproduct,
                generate_reverse_decoys)
        job_name = "Fasta Glycopeptide Hypothesis %s" % (name,)
        kwargs.setdefault('name', job_name)
        super(BuildGlycopeptideHypothesisFasta, self).__init__(fasta_glycopeptide, args, callback, **kwargs)
