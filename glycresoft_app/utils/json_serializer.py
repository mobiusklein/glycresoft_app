from glycan_profiling.serialize import (
    SampleRun, GlycanHypothesis, GlycopeptideHypothesis,
    Analysis)


def handle_sample_run(sample):
    return {
        "id": sample.id,
        "name": sample.name,
        "uuid": sample.uuid,
        "completed": sample.completed,
        "sample_type": "MS Sample"
    }


SampleRun.to_json = handle_sample_run


def handle_glycan_hypothesis(hypothesis):
    return {
        "id": hypothesis.id,
        "name": hypothesis.name,
        "uuid": hypothesis.uuid,
        "hypothesis_type": "Glycan Hypothesis",
        "status": hypothesis.status
    }


GlycanHypothesis.to_json = handle_glycan_hypothesis


def handle_glycopeptide_hypothesis(hypothesis):
    return {
        "id": hypothesis.id,
        "name": hypothesis.name,
        "uuid": hypothesis.uuid,
        "hypothesis_type": "Glycopeptide Hypothesis",
        "status": hypothesis.status
    }


GlycopeptideHypothesis.to_json = handle_glycopeptide_hypothesis


def handle_analysis(analysis):
    return {
        "id": analysis.id,
        "name": analysis.name,
        "uuid": analysis.uuid,
        "analysis_type": analysis.analysis_type,
        # "status": analysis.status
        "hypothesis_id": analysis.hypothesis.id
    }


Analysis.to_json = handle_analysis
