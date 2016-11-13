from glycan_profiling.serialize import (
    SampleRun, GlycanHypothesis, GlycopeptideHypothesis,
    Analysis, MSScan)


def handle_sample_run(sample):
    if sample.ms_scans.filter(MSScan.ms_level > 1).first() is not None:
        sample_type = "MS/MS Sample"
    else:
        sample_type = "MS Sample"
    return {
        "id": sample.id,
        "name": sample.name,
        "uuid": sample.uuid,
        "completed": sample.completed,
        "sample_type": sample_type
    }


SampleRun.to_json = handle_sample_run


def handle_glycan_hypothesis(hypothesis):
    return {
        "id": hypothesis.id,
        "name": hypothesis.name,
        "uuid": hypothesis.uuid,
        "hypothesis_type": "Glycan Hypothesis",
        "status": hypothesis.status,
        "monosaccharide_bounds": hypothesis.monosaccharide_bounds()
    }


GlycanHypothesis.to_json = handle_glycan_hypothesis


def handle_glycopeptide_hypothesis(hypothesis):
    return {
        "id": hypothesis.id,
        "name": hypothesis.name,
        "uuid": hypothesis.uuid,
        "hypothesis_type": "Glycopeptide Hypothesis",
        "status": hypothesis.status,
        "glycan_hypothesis_id": hypothesis.glycan_hypothesis_id,
        "monosaccharide_bounds": hypothesis.monosaccharide_bounds()
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
