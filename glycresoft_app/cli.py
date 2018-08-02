import os
from os.path import abspath
import click

from glycan_profiling.cli.tools import tools
from glycan_profiling.cli.base import cli, HiddenOption


@cli.command(short_help="Launch the application web server")
@click.pass_context
@click.argument("project-store-root")
@click.option("-b", "--base-path", default=None, help='Location to store application instance information')
@click.option("-e", "--external", is_flag=True, help="Allow connections from non-local machines")
@click.option("-p", "--port", default=8080, type=int, help="The port to listen on")
@click.option("-m", "--multiuser", is_flag=True, default=False)
@click.option("-t", "--max-tasks", type=int, default=1)
@click.option("-v", "--validate-project", is_flag=True, default=False, help="Validate the project structure")
@click.option("-x", "--native-client-key", type=str, required=False, default=None, cls=HiddenOption)
def server(context, project_store_root, base_path, external=False, port=None, no_execute_tasks=False,
           multiuser=False, max_tasks=1, validate_project=False, native_client_key=None):
    '''
    Start a web server to allow users to build hypotheses, preprocess MS data, run
    database search analyses, and view results.
    '''
    from glycresoft_app.server import server as inner_fn
    inner_fn(context, project_store_root, base_path, external, port, multi_user=multiuser,
             max_tasks=max_tasks, native_client_key=native_client_key, validate_project=validate_project)


@cli.group("project")
def project():
    pass


@project.command("init", short_help="Create an empty project structure")
@click.argument("path")
@click.option("-r", "--reinitialize-check", is_flag=True, help='Whether to test if the project is already initialized')
def project_init(path, reinitialize_check=False):
    from glycresoft_app.project.project import Project
    proj = Project(path, validate=reinitialize_check)
    click.secho("%r" % (proj,))


@project.command("add-analysis", short_help='Add an existing analysis to the project')
@click.argument("project-path")
@click.argument("analysis-path")
def add_analysis(project_path, analysis_path):
    from glycresoft_app.project.project import Project
    from glycresoft_app.project.analysis import AnalysisRecordSet
    project = Project(project_path)
    analyses = AnalysisRecordSet(abspath(analysis_path))
    for record in analyses:
        project.analysis_manager.put(record)
    project.analysis_manager.dump()


@project.command("add-sample", short_help='Add an existing sample to the project')
@click.argument("project-path")
@click.argument("sample-path")
def add_sample(project_path, sample_path):
    from glycresoft_app.project.project import Project
    from ms_deisotope.output.mzml import ProcessedMzMLDeserializer
    project = Project(project_path)
    reader = ProcessedMzMLDeserializer(abspath(sample_path))
    record = project.sample_manager.make_record(reader)
    project.sample_manager.put(record)
    project.sample_manager.dump()


@project.command("add-hypothesis", short_help="Add an existing hypothesis to the project")
@click.argument("project-path")
@click.argument("hypothesis-path")
def add_hypothesis(project_path, hypothesis_path):
    from glycresoft_app.project.project import Project
    from glycresoft_app.project.hypothesis import HypothesisRecordSet
    project = Project(project_path)
    hypotheses = HypothesisRecordSet(abs(hypothesis_path))
    for record in hypotheses:
        project.hypothesis_manager.put(record)
    project.hypothesis_manager.dump()
