import textwrap
from typing import Optional

import typer
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.syntax import Syntax
from rich.table import Table

from job_cd.cli.app import console, get_cache, get_db
from job_cd.core.config import config_manager
from job_cd.core.dispatcher import Dispatcher
from job_cd.core.models import DeploymentProfile, IntakePayload
from job_cd.core.pipeline import ExtractorStep, JobPipelineEngine, FinderStep, EmailComposerStep
from job_cd.enums import DeploymentStatus
from job_cd.providers.composer import GeminiCliEmailComposer
from job_cd.providers.extractor import GeminiCliExtractor
from job_cd.providers.finder import get_finder
from job_cd.providers.intake import SimpleWebIntake
from job_cd.providers.sender import SmtpEmailSender


def do_init():
    """Initialize job-cd environment."""
    console.print(
        Panel("[bold blue]🛠️  Initializing job-cd Global Configuration[/]",
              border_style="blue")
    )

    config_manager.ensure_dirs()
    console.print(f"📂 [bold]Config Directory:[/] [cyan]{config_manager.app_dir}[/]")

    if config_manager.env_path.exists():
        if not Confirm.ask("⚠️  .env file already exists. Do you want to overwrite it?"):
            console.print("[yellow]Aborted initialization.[/]")
            return

    google_api_key = Prompt.ask("Enter your Google Gemini API Key", password=True)
    apollo_api_key = Prompt.ask("Enter your Apollo.io API Key", password=True)

    smtp_server = Prompt.ask("SMTP Server", default="smtp.gmail.com")
    smtp_port = Prompt.ask("SMTP Port", default="587")
    smtp_user = Prompt.ask("SMTP Username (Email)")
    smtp_pass = Prompt.ask("SMTP Password (App Password)", password=True)

    env_content = textwrap.dedent(f"""\
            # job-cd Global Configuration
            GOOGLE_API_KEY={google_api_key}
            APOLLO_API_KEY={apollo_api_key}

            # SMTP Configuration
            SMTP_SERVER={smtp_server}
            SMTP_PORT={smtp_port}
            SMTP_USERNAME={smtp_user}
            SMTP_PASSWORD={smtp_pass}
        """)

    config_manager.env_path.write_text(env_content, encoding="utf-8")
    console.print(f"[green]✅ Configuration saved to[/] [cyan]{config_manager.env_path}[/]")

    if not config_manager.profiles_path.exists():
        default_profile = {
            "first_name": "Ted",
            "last_name": "Lasso",
            "email": "ted.lasso@afcrichmond.com",
            "current_role": "Head Coach",
            "years_of_experience": 20,
            "target_contact_titles": ["Owner", "Director of Football"],
            "resume_url": "https://example.com/resume.pdf",
            "resume_text": "# TED LASSO\nHead Coach | AFC Richmond\n\n- Expert in team building and 'Believe' philosophy."
        }
        profile_cache = get_cache("profiles.json")
        profile_cache.set("default", default_profile)
        console.print(f"[green]✅ Default profile created at[/] [cyan]{config_manager.profiles_path}[/]")

    console.print(
        Panel("[bold blue]🚀  job-cd is ready! Use 'jobcd build <url>' to get started.[/]",
              border_style="green")
    )


def do_config(edit: bool = False):
    """View or edit API keys and SMTP settings."""
    env_path = config_manager.env_path

    if not env_path.exists():
        console.print("[red]✖ No global configuration found. Please run 'jobcd init' first.[/]")
        return 1

    if edit:
        console.print(
            Panel(
                "[yellow]⚠️  WARNING: This file contains sensitive credentials "
                "(API keys, passwords). Do not share or commit this file.[/]",
                border_style="yellow",
            )
        )
        typer.launch(str(env_path))
    else:
        syntax = Syntax(
            env_path.read_text(encoding="utf-8"),
            "bash",
            theme="monokai",
            line_numbers=True,
        )
        console.print(
            Panel(syntax, title="[bold]job-cd Configuration[/]", border_style="cyan")
        )


def do_build(url: str, title: Optional[str] = None, company: Optional[str] = None, domain: Optional[str] = None, finder: str = "apollo"):
    """Execute the job pipeline for a job posting."""
    console.print(
        Panel(f"[bold blue]🚀  Starting Build Pipeline[/]\n[white]🔗  {url}[/]",
              border_style="blue")
    )

    db = get_db()
    existing_deployments = db.filter(job_link=url)
    if existing_deployments:
        if not Confirm.ask("⚠️  A record for this job URL already exists. Do you want to continue?"):
            console.print("[yellow]Aborted.[/]")
            return

    payload = IntakePayload(url=url, manual_title=title, manual_company=company, manual_domain=domain)
    cache = get_cache(filename="contacts.json")
    profile_cache = get_cache(filename="profiles.json")
    profile_data = profile_cache.get("default")
    if not profile_data:
        console.print(
            Panel("[yellow]⚠️  No Profile Found![/]\n"
                  "To use job-cd, you must first define your application persona.\n"
                  f"Please create a profile at: [cyan]{config_manager.profiles_path}[/]",
                  border_style="yellow")
        )
        return

    default_profile = DeploymentProfile(**profile_data)

    intake = SimpleWebIntake()
    extractor = GeminiCliExtractor()
    try:
        finder = get_finder(name=finder, cache=cache)
    except ValueError as e:
        console.print(f"[red]{e}[/]")
        return
    composer = GeminiCliEmailComposer()

    engine = JobPipelineEngine(
        intake_strategy=intake,
        pipeline_steps=[
            ExtractorStep(extractor=extractor),
            FinderStep(finder=finder),
            EmailComposerStep(composer=composer),
        ],
        db=db,
    )

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
        console=console,
    ) as progress:
        progress.add_task(description="[cyan]Running pipeline...[/]", total=None)
        try:
            deployments = engine.run(payload=payload, profile=default_profile)
        except Exception as e:
            console.print(f"[red]❌  Pipeline Crash: {e}[/]")
            return

    if not deployments or all(d.status == DeploymentStatus.FAILED for d in deployments):
        return

    total_contacts = sum(len(d.outreaches) for d in deployments)
    total_drafted = sum(1 for d in deployments for o in d.outreaches if o.status == DeploymentStatus.DRAFTED)

    table = Table(title="✨ Build Summary", border_style="green", header_style="bold cyan")
    table.add_column("Company", style="white")
    table.add_column("Domain", style="cyan")
    table.add_column("Contacts", justify="right", style="magenta")
    table.add_column("Drafts", justify="right", style="green")

    for d in deployments:
        company_name = d.company.name if d.company else "Unknown"
        company_domain = d.company.domain if d.company else "N/A"
        contact_count = len(d.outreaches)
        draft_count = sum(1 for o in d.outreaches if o.status == DeploymentStatus.DRAFTED)
        table.add_row(company_name, company_domain, str(contact_count), str(draft_count))

    console.print(table)

    totals = Table(border_style="green", show_header=False)
    totals.add_column("Metric", style="bold white")
    totals.add_column("Value", style="cyan")
    totals.add_row("Contacts Identified", str(total_contacts))
    totals.add_row("Emails Drafted", str(total_drafted))
    console.print(totals)

    console.print("[bold green]🚀 Pipeline Complete![/]")


def do_dispatch(force: bool = False):
    """Release scheduled emails to recruiters."""
    if force:
        console.print("[yellow]⚠️  FORCE MODE: Bypassing schedule constraints...[/]")
    else:
        console.print("[blue]🔄  Checking outbox for due deployments...[/]")

    db = get_db()
    sender = SmtpEmailSender()
    dispatcher = Dispatcher(db=db, sender=sender)

    try:
        sent, failed = dispatcher.dispatch_due_email(force=force)
        if sent == 0 and failed == 0:
            console.print("[dim]📭  No emails were due for delivery.[/]")
        else:
            if sent > 0:
                console.print(f"[green]📤  Success: {sent} email(s) dispatched.[/]")
            if failed > 0:
                console.print(f"[red]🚨  Failed: {failed} email(s) encountered errors. Run 'retry' to fix.[/]")
    except Exception as e:
        console.print(f"[red]Critical Dispatch Error: {e}[/]")


def do_retry():
    """Resend any emails that failed previously."""
    console.print("[yellow]🚑  Attempting to rescue failed deployments...[/]")
    db = get_db()
    dispatcher = Dispatcher(db=db, sender=SmtpEmailSender())

    try:
        sent, failed = dispatcher.retry_failed_email()
        if sent > 0:
            console.print(f"[green]♻️  Rescued: {sent} email(s) sent successfully.[/]")
        if failed > 0:
            console.print(f"[red]⚠️  Still Failing: {failed} email(s) could not be sent.[/]")
        if sent == 0 and failed == 0:
            console.print("[dim]No failed emails found in database.[/]")
    except Exception as e:
        console.print(f"[red]Retry Error: {e}[/]")


def do_preview(limit: int = 1):
    """Read the next drafted email waiting in the queue."""
    db = get_db()
    deployments = db.filter(status=DeploymentStatus.DRAFTED, limit=limit)
    if not deployments:
        console.print("[yellow]📭  No drafted emails in the queue to preview.[/]")
        return

    found_any = False

    for d in deployments:
        for outreach in d.outreaches:
            if outreach.status == DeploymentStatus.DRAFTED:
                if not outreach.draft:
                    console.print(f"[red]⚠️  Warning: {d.company.name} is marked as DRAFTED but has no email body![/]")
                    continue

                found_any = True
                panel_content = (
                    f"[bold cyan]🏢  {d.company.name}[/]  |  [white]Role: {d.job.title}[/]\n"
                    f"[white]📧  To:[/] [cyan]{outreach.draft.recipient_email}[/] "
                    f"([white]{outreach.contact.name}[/])\n"
                    f"[magenta]📝  Subject:[/] [white]{outreach.draft.subject}[/]"
                )
                console.print(Panel(panel_content, border_style="cyan"))

                body_panel = Panel(
                    outreach.draft.body,
                    title="[bold]Email Draft[/]",
                    border_style="blue",
                )
                console.print(body_panel)

    if not found_any:
        console.print("[yellow]📭  Deployments were found, but none contained valid drafted emails.[/]")


def do_history(limit: int = 10, detail: bool = False):
    """View recent job application history."""
    db = get_db()
    deployments = db.filter(limit=limit)
    if not deployments:
        console.print("[dim]History is empty.[/]")
        return

    table = Table(
        title=f"Recent History (Last {limit})",
        border_style="magenta",
        header_style="bold magenta",
    )
    table.add_column("Date", style="dim", width=16)
    table.add_column("Company", style="cyan", bold=True)
    table.add_column("Role", style="white")
    table.add_column("Status", justify="center")

    for d in deployments:
        date_str = d.outreaches[0].scheduled_at.strftime("%Y-%m-%d %H:%M") if d.outreaches else "N/A"
        company_name = d.company.name if d.company else "Unknown"
        job_title = d.job.title if d.job else "N/A"

        status_style = {"SENT": "green", "FAILED": "red"}.get(d.status.value, "yellow")
        status_label = {"SENT": "✅ Sent", "FAILED": "❌ Failed"}.get(d.status.value, f"◉ {d.status.value}")

        table.add_row(date_str, company_name, job_title, f"[{status_style}]{status_label}[/]")

    console.print(table)

    if detail and deployments:
        for d in deployments:
            if d.outreaches:
                detail_table = Table(border_style="dim", box=None)
                detail_table.add_column("  ", style="dim", width=2)
                detail_table.add_column("Recipient", style="white")
                detail_table.add_column("Status", justify="center")
                detail_table.add_column("Sent At", style="dim")

                for o in d.outreaches:
                    o_status_style = {"SENT": "green", "FAILED": "red", "DRAFTED": "yellow"}.get(o.status.value, "white")
                    sent_at_str = o.sent_at.strftime("%m/%d %H:%M") if o.sent_at else "Pending"
                    name = o.contact.name if o.contact and o.contact.name else "—"

                    detail_table.add_row(
                        "📧",
                        f"{o.draft.recipient_email} ({name})",
                        f"[{o_status_style}]{o.status.value}[/]",
                        sent_at_str,
                    )

                console.print(detail_table)
