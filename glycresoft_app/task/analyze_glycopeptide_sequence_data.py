import os

from click import Abort

from glypy.utils import Enum

from glycresoft_app.project import analysis as project_analysis


from glycan_profiling.serialize import (
    DatabaseBoundOperation, GlycopeptideHypothesis)

from glycan_profiling.profiler import (
    MzMLGlycopeptideLCMSMSAnalyzer,
    MzMLGlycanChromatogramAnalyzer,
    MzMLComparisonGlycopeptideLCMSMSAnalyzer,
    MultipartGlycopeptideLCMSMSAnalyzer)

from glycan_profiling.models import GeneralScorer, get_feature

from glycan_profiling.cli.validators import (
    validate_analysis_name,
    validate_mass_shift)

from ms_deisotope.output.mzml import ProcessedMzMLDeserializer

from .task_process import Task, Message


class GlycopeptideSearchStrategyEnum(Enum):
    classic = 1
    classic_comparison = 2
    multipart = 3


def get_by_name_or_id(session, model_type, name_or_id):
    try:
        object_id = int(name_or_id)
        inst = session.query(model_type).get(object_id)
        if inst is None:
            raise ValueError("No instance of type %s with id %r" %
                             (model_type, name_or_id))
        return inst
    except ValueError:
        inst = session.query(model_type).filter(
            model_type.name == name_or_id).one()
        return inst


def analyze_glycopeptide_sequences(database_connection, sample_path, hypothesis_identifier,
                                   output_path, analysis_name, grouping_error_tolerance=1.5e-5,
                                   mass_error_tolerance=1e-5, msn_mass_error_tolerance=2e-5,
                                   psm_fdr_threshold=0.05, peak_shape_scoring_model=None,
                                   minimum_oxonium_threshold=0.05, workload_size=1000,
                                   use_peptide_mass_filter=True, mass_shifts=None,
                                   permute_decoy_glycan_fragments=False,
                                   include_rare_signature_ions=False,
                                   model_retention_time=False,
                                   search_strategy=GlycopeptideSearchStrategyEnum.classic,
                                   decoy_database_connection=None,
                                   decoy_hypothesis_id=None,
                                   tandem_scoring_model=None,
                                   channel=None, **kwargs):
    if peak_shape_scoring_model is None:
        peak_shape_scoring_model = GeneralScorer.clone()
        peak_shape_scoring_model.add_feature(get_feature("null_charge"))


    database_connection = DatabaseBoundOperation(database_connection)
    if decoy_database_connection:
        decoy_database_connection = DatabaseBoundOperation(decoy_database_connection)

    if not os.path.exists(sample_path):
        channel.send(Message("Could not locate sample %r" % sample_path, "error"))
        return

    reader = ProcessedMzMLDeserializer(sample_path, use_index=False)
    sample_run = reader.sample_run

    try:
        hypothesis = get_by_name_or_id(
            database_connection, GlycopeptideHypothesis, hypothesis_identifier)
    except Exception:
        channel.send(Message("Could not locate hypothesis %r" % hypothesis_identifier, "error"))
        channel.abort("An error occurred during analysis.")

    if decoy_database_connection:
        try:
            decoy_hypothesis = get_by_name_or_id(
                decoy_database_connection, GlycopeptideHypothesis, decoy_hypothesis_id)
        except Exception:
            channel.send(Message("Could not locate hypothesis %r" %
                                decoy_hypothesis_id, "error"))
            channel.abort("An error occurred during analysis.")

    if analysis_name is None:
        analysis_name = "%s @ %s" % (sample_run.name, hypothesis.name)
    analysis_name = validate_analysis_name(None, database_connection.session, analysis_name)

    try:
        mass_shift_out = []
        for mass_shift, multiplicity in mass_shifts:
            mass_shift_out.append(validate_mass_shift(mass_shift, multiplicity))
        expanded = []
        expanded = MzMLGlycanChromatogramAnalyzer.expand_mass_shifts(
            dict(mass_shift_out), crossproduct=False)
        mass_shifts = expanded
    except Abort:
        channel.send(Message.traceback())
        return

    try:
        if search_strategy == GlycopeptideSearchStrategyEnum.classic:
            analyzer = MzMLGlycopeptideLCMSMSAnalyzer(
                database_connection._original_connection, hypothesis.id, sample_path,
                output_path=output_path,
                analysis_name=analysis_name,
                grouping_error_tolerance=grouping_error_tolerance,
                mass_error_tolerance=mass_error_tolerance,
                msn_mass_error_tolerance=msn_mass_error_tolerance,
                psm_fdr_threshold=psm_fdr_threshold,
                peak_shape_scoring_model=peak_shape_scoring_model,
                oxonium_threshold=minimum_oxonium_threshold,
                spectrum_batch_size=workload_size,
                use_peptide_mass_filter=use_peptide_mass_filter,
                mass_shifts=mass_shifts,
                permute_decoy_glycans=permute_decoy_glycan_fragments,
                rare_signatures=include_rare_signature_ions,
                model_retention_time=model_retention_time,
                tandem_scoring_model=tandem_scoring_model
            )
        elif search_strategy == GlycopeptideSearchStrategyEnum.classic_comparison:
            analyzer = MzMLComparisonGlycopeptideLCMSMSAnalyzer(
                database_connection._original_connection, decoy_database_connection._original_connection, hypothesis.id, sample_path,
                output_path=output_path,
                analysis_name=analysis_name,
                grouping_error_tolerance=grouping_error_tolerance,
                mass_error_tolerance=mass_error_tolerance,
                msn_mass_error_tolerance=msn_mass_error_tolerance,
                psm_fdr_threshold=psm_fdr_threshold,
                peak_shape_scoring_model=peak_shape_scoring_model,
                oxonium_threshold=minimum_oxonium_threshold,
                spectrum_batch_size=workload_size,
                use_peptide_mass_filter=use_peptide_mass_filter,
                mass_shifts=mass_shifts,
                permute_decoy_glycans=permute_decoy_glycan_fragments,
                rare_signatures=include_rare_signature_ions,
                model_retention_time=model_retention_time,
                tandem_scoring_model=tandem_scoring_model
            )
        elif search_strategy == GlycopeptideSearchStrategyEnum.multipart:
            analyzer = MultipartGlycopeptideLCMSMSAnalyzer(
                database_connection._original_connection, decoy_database_connection._original_connection,
                hypothesis.id, decoy_hypothesis.id, sample_path,
                output_path=output_path,
                analysis_name=analysis_name,
                grouping_error_tolerance=grouping_error_tolerance,
                mass_error_tolerance=mass_error_tolerance,
                msn_mass_error_tolerance=msn_mass_error_tolerance,
                psm_fdr_threshold=psm_fdr_threshold,
                peak_shape_scoring_model=peak_shape_scoring_model,
                spectrum_batch_size=workload_size,
                mass_shifts=mass_shifts,
                rare_signatures=include_rare_signature_ions,
                model_retention_time=model_retention_time,
                tandem_scoring_model=tandem_scoring_model,
                oxonium_threshold=minimum_oxonium_threshold,
            )
        _ = analyzer.start()

        analysis = analyzer.analysis
        if analysis is not None:
            record = project_analysis.AnalysisRecord(
                name=analysis.name, id=analysis.id, uuid=analysis.uuid, path=output_path,
                analysis_type=analysis.analysis_type,
                hypothesis_uuid=analysis.hypothesis.uuid,
                hypothesis_name=analysis.hypothesis.name,
                sample_name=analysis.parameters['sample_name'],
                user_id=channel.user.id
            )
            channel.send(Message(record.to_json(), 'new-analysis'))
        else:
            channel.send(Message("No glycopeptides were identified for \"%s\"" % (analysis_name,)))

    except Exception:
        channel.send(Message.traceback())
        channel.abort("An error occurred during analysis.")


class AnalyzeGlycopeptideSequenceTask(Task):
    count = 0

    def __init__(self, database_connection, sample_path, hypothesis_identifier,
                 output_path, analysis_name, grouping_error_tolerance=1.5e-5, mass_error_tolerance=1e-5,
                 msn_mass_error_tolerance=2e-5, psm_fdr_threshold=0.05, peak_shape_scoring_model=None,
                 minimum_oxonium_threshold=0.05, workload_size=1000, use_peptide_mass_filter=True,
                 mass_shifts=None, permute_decoy_glycan_fragments=False,
                 include_rare_signature_ions=False, model_retention_time=False,
                 search_strategy=GlycopeptideSearchStrategyEnum.classic,
                 decoy_database_connection=None, decoy_hypothesis_id=None,
                 tandem_scoring_model=None,
                 callback=lambda: 0, **kwargs):
        args = (database_connection, sample_path, hypothesis_identifier,
                output_path, analysis_name, grouping_error_tolerance, mass_error_tolerance,
                msn_mass_error_tolerance, psm_fdr_threshold, peak_shape_scoring_model,
                minimum_oxonium_threshold, workload_size, use_peptide_mass_filter,
                mass_shifts, permute_decoy_glycan_fragments, include_rare_signature_ions,
                model_retention_time, search_strategy, decoy_database_connection,
                decoy_hypothesis_id, tandem_scoring_model)
        if analysis_name is None:
            name_part = kwargs.pop("job_name_part", self.count)
            self.count += 1
        else:
            name_part = analysis_name
        job_name = "Analyze Glycopeptide Sequence %s" % (name_part,)
        kwargs.setdefault('name', job_name)
        Task.__init__(self, analyze_glycopeptide_sequences, args, callback, **kwargs)
