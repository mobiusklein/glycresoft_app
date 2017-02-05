import click

from glycan_profiling.cli.base import cli


@cli.command()
@click.pass_context
@click.argument("database-connection")
@click.option("-b", "--base-path", default=None, help='Location to store application instance information')
@click.option("-e", "--external", is_flag=True, help="Allow connections from non-local machines")
@click.option("-p", "--port", default=8080, type=int, help="The port to listen on")
def server(context, database_connection, base_path, external=False, port=None, no_execute_tasks=False):
    from glycresoft_app.server import server as inner_fn
    inner_fn(context, database_connection, base_path, external, port)
