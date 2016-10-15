from glycan_profiling.serialize import (
    SampleRun, GlycanHypothesis, GlycopeptideHypothesis)


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
