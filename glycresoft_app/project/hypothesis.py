import os
import glob
import warnings

from glycan_profiling import serialize

from .base import SyncableStore, structure

_HypothesisRecord = structure("HypothesisRecord", ["name", 'id', 'uuid', 'path',
                                                   'hypothesis_type', "monosaccharide_bounds"])


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
                hypothesis_type=HypothesisRecord.GLYCOPEPTIDE)
            records.append(record)
        self.records = records


class HypothesisManager(SyncableStore):
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
