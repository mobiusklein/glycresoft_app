import json
import os
import glob
import warnings

from glycan_profiling import serialize

from glycresoft_app.utils.base import RecordType

from .base import SyncableStore, structure

_HypothesisRecord = structure("HypothesisRecord", [
    'name',
    'id',
    'uuid',
    'path',
    'hypothesis_type',
    'monosaccharide_bounds',
    'decoy_hypothesis',
    'options',
])


class HypothesisRecord(_HypothesisRecord):
    GLYCAN_COMPOSITION = 'glycan_composition'
    GLYCOPEPTIDE = 'glycopeptide'

    def is_resolvable(self):
        if not os.path.exists(self.path):
            return False
        conn = serialize.DatabaseBoundOperation(self.path)
        if self.hypothesis_type == self.GLYCAN_COMPOSITION:
            obj = conn.query(serialize.GlycanHypothesis).get(self.id)
        elif self.hypothesis_type == self.GLYCOPEPTIDE:
            obj = conn.query(serialize.GlycopeptideHypothesis).get(self.id)
        else:
            warnings.warn("Unrecognized hypothesis_type %r for %r" % (self.hypothesis_type, self))
            return False
        if obj is None:
            return False
        if obj.uuid != self.uuid:
            return False
        return True

    @classmethod
    def from_json(cls, state):
        decoy_state = state.get('decoy_hypothesis')
        if decoy_state is not None:
            state['decoy_hypothesis'] = cls.from_json(decoy_state)
        inst = cls(**state)
        return inst

    @property
    def is_full_crossproduct(self):
        return (self.options or {}).get("full_cross_product", False)


def json_serializable(value):
    try:
        json.dumps(value)
        return True
    except TypeError:
        return False


class HypothesisRecordSet(object):
    def __init__(self, path):
        self.path = path
        self.records = []
        self.build()

    def __iter__(self):
        return iter(self.records)

    def build(self):
        connection = serialize.DatabaseBoundOperation(self.path)
        records = []

        for hypothesis in connection.query(serialize.GlycanHypothesis):
            record = HypothesisRecord(
                id=hypothesis.id,
                name=hypothesis.name, uuid=hypothesis.uuid, path=self.path,
                monosaccharide_bounds=hypothesis.monosaccharide_bounds(),
                hypothesis_type=HypothesisRecord.GLYCAN_COMPOSITION)
            records.append(record)

        for hypothesis in connection.query(serialize.GlycopeptideHypothesis):
            record = HypothesisRecord(
                id=hypothesis.id,
                name=hypothesis.name, uuid=hypothesis.uuid, path=self.path,
                monosaccharide_bounds=hypothesis.monosaccharide_bounds(),
                hypothesis_type=HypothesisRecord.GLYCOPEPTIDE,
                options={
                    k: v for k, v in hypothesis.parameters.items()
                    if json_serializable(v)
                }
            )
            records.append(record)
        self.records = records


class HypothesisManager(SyncableStore[RecordType]):
    record_type = HypothesisRecord

    @staticmethod
    def list_files(base_path):
        indices = glob.glob(os.path.join(base_path, "*.database"))
        return indices

    @staticmethod
    def open_file(db_file):
        return (db_file)

    @staticmethod
    def store_record(store, record):
        for entry in record:
            store[entry.uuid] = entry

    @classmethod
    def make_record(cls, datum):
        record_set = HypothesisRecordSet(datum)
        return record_set

    @classmethod
    def from_json(cls, state):
        return HypothesisRecord.from_json(state)
