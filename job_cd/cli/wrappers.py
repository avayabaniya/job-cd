from typing import Optional

import typer

from job_cd import __version__
from job_cd.cli.app import console
from job_cd.cli.commands import (
    do_build,
    do_config,
    do_dispatch,
    do_history,
    do_init,
    do_preview,
    do_retry,
)
from job_cd.cli.interactive import interactive_mode

app = typer.Typer(
    help="job-cd: Continuous Deployment for Job Applications",
    rich_markup_mode="rich",
    pretty_exceptions_show_locals=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)


def _version_callback(value: bool):
    if value:
        console.print(f"[bold]job-cd[/] [cyan]v{__version__}[/]")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False, "--version", "-v", help="Show version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
):
    if not ctx.invoked_subcommand:
        interactive_mode()


@app.command(rich_help_panel="Setup")
def init():
    """Bootstrap the job-cd environment."""
    do_init()


@app.command(rich_help_panel="Setup")
def config(
    edit: bool = typer.Option(
        False, "--edit", "--open",
        help="Open the .env file in your default editor"
    )
):
    """View or edit API keys and SMTP settings."""
    rc = do_config(edit=edit)
    if rc:
        raise typer.Exit(code=rc)


@app.command(rich_help_panel="Pipeline")
def build(
    url: str,
    title: Optional[str] = typer.Option(None, "--title", help="Manual override for job title"),
    company: Optional[str] = typer.Option(None, "--company", help="Manual override for company name"),
    domain: Optional[str] = typer.Option(None, "--domain", help="Manual override for company domain"),
    finder: str = typer.Option("apollo", "--finder", "-f", help="Lead generation provider: apollo, leadmagic, getprospect, snovio"),
):
    """Execute the job pipeline for a job posting."""
    do_build(url=url, title=title, company=company, domain=domain, finder=finder)


@app.command(rich_help_panel="Pipeline")
def dispatch(
    force: bool = typer.Option(
        False, "--force", "-f", help="Ignore schedule and send all drafted emails."
    )
):
    """Release scheduled emails to recruiters."""
    do_dispatch(force=force)


@app.command(rich_help_panel="Pipeline")
def retry():
    """Recovery Step: Resend any emails that failed previously."""
    do_retry()


@app.command(rich_help_panel="Pipeline")
def preview(limit: int = 1):
    """Read the next drafted email waiting in the queue."""
    do_preview(limit=limit)


@app.command(rich_help_panel="Data")
def history(
    limit: int = 10,
    detail: bool = typer.Option(False, "--detail", "-d", help="Show detailed outreach and email status.")
):
    """Audit Log: View recent job application history."""
    do_history(limit=limit, detail=detail)
