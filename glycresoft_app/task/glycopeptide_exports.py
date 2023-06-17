import io
import os
import dataclasses
import logging

from typing import Any, Callable, List, Mapping, Optional, ClassVar, Set

from sqlalchemy.orm import object_session

from glycan_profiling.serialize import (
    DatabaseBoundOperation,
    Analysis,
    IdentifiedGlycopeptide,
    GlycopeptideSpectrumMatch,
    GlycanComposition,
    AnalysisDeserializer,
)

from glycan_profiling.output import (
    GlycopeptideLCMSMSAnalysisCSVSerializer,
    GlycopeptideSpectrumMatchAnalysisCSVSerializer,
    MultiScoreGlycopeptideLCMSMSAnalysisCSVSerializer,
    MultiScoreGlycopeptideSpectrumMatchAnalysisCSVSerializer,
    MzIdentMLSerializer,
    ImportableGlycanHypothesisCSVSerializer,
    SpectrumAnnotatorExport,
    GlycopeptideDatabaseSearchReportCreator
)

from ms_deisotope.output import ProcessedMSFileLoader

from .task_process import Task, Message, TaskControlContext

logger = logging.getLogger("glycresoft.status")


@dataclasses.dataclass
class ExportOperationBase:
    job_type_name: ClassVar[str] = "Glycopeptide Export"

    analysis_path: str
    analysis_id: int
    output_path: str
    is_multiscore: bool
    ms_file_path: Optional[str] = None
    control_channel: Optional[TaskControlContext] = None

    def open_database(self):
        return AnalysisDeserializer(self.analysis_path, analysis_id=self.analysis_id)

    def run(self, *args, **kwargs):
        raise NotImplementedError()

    def __call__(self, *args: Any, **kwds: Any):
        self.run()

    def output_files(self) -> List[str]:
        return [self.output_path]


@dataclasses.dataclass
class GlycopeptideCSVExport(ExportOperationBase):
    job_type_name: ClassVar[str] = "Glycopeptide CSV Export"

    entity_id_list: List[int] = dataclasses.field(default_factory=list)
    protein_name_resolver: Mapping[Any, str] = dataclasses.field(default_factory=dict)

    def entity_generator(self, db):
        """Read entities out of the database in chunks"""
        chunk_size = 200
        for i in range(0, len(self.entity_id_list), chunk_size):
            entities = db.query(IdentifiedGlycopeptide).filter(
                IdentifiedGlycopeptide.id.in_(self.entity_id_list[i:i + chunk_size])
            ).all()
            yield from entities

    def get_job_cls(self):
        """Determine which job type to instantiate to do the job"""
        if self.is_multiscore:
            job_cls = GlycopeptideLCMSMSAnalysisCSVSerializer
        else:
            job_cls = MultiScoreGlycopeptideLCMSMSAnalysisCSVSerializer
        return job_cls

    def make_job(self, fh: io.FileIO, analysis: Analysis, db: DatabaseBoundOperation):
        """Make the actual object that will do the work of generating the output file"""
        job_cls = self.get_job_cls()
        job = job_cls(
            fh,
            self.entity_generator(db),
            self.protein_name_resolver,
            analysis
        )
        return job

    def run(self, *args, **kwargs):
        ads = self.open_database()
        analysis = ads.analysis

        with open(self.output_path, 'wb') as fh:
            job = self.make_job(fh, analysis, ads)
            try:
                job.run()
            except Exception:
                self.control_channel.send(Message.traceback())
                self.control_channel.abort(
                    "An error occurred during export.")


@dataclasses.dataclass
class GlycopeptideSpectrumMatchCSVExport(GlycopeptideCSVExport):
    job_type_name: ClassVar[str] = "Glycopeptide Spectrum Match CSV Export"

    def get_job_cls(self):
        if self.is_multiscore:
            return MultiScoreGlycopeptideSpectrumMatchAnalysisCSVSerializer
        else:
            return GlycopeptideSpectrumMatchAnalysisCSVSerializer

    def entity_generator(self, db):
        chunk_size = 200
        for i in range(0, len(self.entity_id_list), chunk_size):
            entities = db.query(GlycopeptideSpectrumMatch).filter(
                GlycopeptideSpectrumMatch.id.in_(
                    self.entity_id_list[i:i + chunk_size])
            ).all()
            yield from entities


@dataclasses.dataclass
class GlycopeptideGlycansCSVExport(GlycopeptideCSVExport):
    job_type_name: ClassVar[str] = "Glycopeptide Glycan Export"

    def make_job(self, fh: io.FileIO, analysis: Analysis, db: DatabaseBoundOperation):
        job_cls = self.get_job_cls()
        logger.info(f"Creating job with {len(self.entity_id_list)} entities to export")
        job = job_cls(
            fh,
            self.entity_generator(db)
        )
        return job

    def get_job_cls(self):
        return ImportableGlycanHypothesisCSVSerializer

    def entity_generator(self, db):
        chunk_size = 200
        for i in range(0, len(self.entity_id_list), chunk_size):
            entities = db.query(GlycanComposition).filter(
                GlycanComposition.id.in_(
                    self.entity_id_list[i:i + chunk_size])
            ).all()
            yield from entities


@dataclasses.dataclass
class HTMLReportExport(ExportOperationBase):
    job_type_name: ClassVar[str] = "Glycopeptide HTML Export"

    def run(self, *args, **kwargs):
        with open(self.output_path, 'wb') as fh:
            job = GlycopeptideDatabaseSearchReportCreator(
                self.analysis_path,
                self.analysis_id,
                fh,
                0,
                self.ms_file_path
            )
            try:
                job.run()
            except Exception:
                self.control_channel.send(Message.traceback())
                self.control_channel.abort(
                    "An error occurred during export.")


@dataclasses.dataclass
class AnnotatedSpectraExport(ExportOperationBase):
    job_type_name: ClassVar[str] = "Glycopeptide Annotated Spectra Export"

    def run(self, *args, **kwargs):
        job = SpectrumAnnotatorExport(
            self.analysis_path,
            self.analysis_id,
            self.output_path,
            self.ms_file_path
        )
        try:
            job.run()
        except Exception:
            self.control_channel.send(Message.traceback())
            self.control_channel.abort(
                "An error occurred during export.")



class ExportJob(Task):
    """
    An export job to create an output file in a separate process.

    The actual export operation is given by :attr:`task_fn` which
    is an :class:`ExportOperationBase` instance.
    """

    count = 0

    def __init__(self, export_spec: ExportOperationBase, args=(), callback=lambda: 0, user=None, context=None, **kwargs):
        name_part = kwargs.pop("job_name_part", self.count)
        self.count += 1
        job_name = "%s %s" % (export_spec.job_type_name, name_part,)
        kwargs.setdefault('name', job_name)
        export_spec.control_channel = context
        super().__init__(export_spec, args, callback, user, context, **kwargs)

    @property
    def spec(self) -> ExportOperationBase:
        return self.task_fn

    def output_files(self) -> List[str]:
        return self.spec.output_files()


@dataclasses.dataclass
class ExportState:
    """
    A running set of export jobs tied to a single export request from
    the user.

    Is used to keep track of the jobs running on the background job queue
    and to signal the frontend to download the file bundle when available.
    """

    name: str
    user: str
    completion: Callable[[Message], None]
    files: List[str] = dataclasses.field(default_factory=list)
    job_tokens: Set[str] = dataclasses.field(default_factory=set)
    jobs_completed: Set[str] = dataclasses.field(default_factory=set, compare=False)

    def completion_message(self):
        """Generate a message to signal that files are ready to download"""
        return Message(
            {
                "filenames": self.files,
                "download_name": self.name
            },
            "directory-to-download",
            user=self.user
        )

    def token_completed(self, token: str):
        """
        Indicate a particular job given by the token has finished.

        If all jobs are finished, send the completion message.
        """
        self.jobs_completed.add(token)
        logger.info(f"Job {token} of Export {self.name} Finished")
        if self.jobs_completed == self.job_tokens:
            logger.info(f"Export {self.name} Finished!")
            self.completion(self.completion_message())

    def add_job(self, job: ExportJob):
        """
        Add a job to the running :class:`ExportState`, updating the files
        and tokens being managed by it.

        Also sets the job's completion callback to update this
        :class:`ExportState` object.
        """
        self.job_tokens.add(job.name)
        self.files.extend(job.output_files())
        job.callback = ExportCallback(self, job.name)


@dataclasses.dataclass
class ExportCallback:
    """A callback tied to a particular export state and job token to signal the job is done."""

    state: ExportState
    token: str
    fired: bool = False

    def __call__(self, *args: Any, **kwds: Any) -> Any:
        if not self.fired:
            self.state.token_completed(self.token)
            self.fired = True
        else:
            raise ValueError("Cannot fire more than once!")
