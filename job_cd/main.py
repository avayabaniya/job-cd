import textwrap

import typer
from typing import Optional
from dotenv import load_dotenv

from job_cd.core.config import config_manager
from job_cd.core.dispatcher import Dispatcher
from job_cd.core.interfaces import CacheStrategy
from job_cd.core.models import DeploymentProfile, IntakePayload
from job_cd.core.pipeline import ExtractorStep, JobPipelineEngine, FinderStep, EmailComposerStep
from job_cd.enums import DeploymentStatus
from job_cd.providers.cache import LocalCache
from job_cd.providers.composer import GeminiCliEmailComposer
from job_cd.providers.database import SQLiteDatabaseAdapter
from job_cd.providers.extractor import GeminiExtractor, GeminiCliExtractor
from job_cd.providers.finder import ApolloFinder
from job_cd.providers.intake import SimpleWebIntake
from job_cd.providers.sender import SmtpEmailSender

# Load global configuration first, then local override if exists
load_dotenv(config_manager.env_path)
load_dotenv()

app = typer.Typer(help="job-cd: Continuous Deployment for Job Applications")

def get_db():
    """Factory function to provide the db strategy."""
    return SQLiteDatabaseAdapter()

def get_cache(filename: str = "contacts.json") -> CacheStrategy:
    """Factory function to provide the cache strategy."""
    return LocalCache(filename=filename)

@app.command()
def init():
    """
    Bootstrap the job-cd environment. 
    Creates global config directories and initializes a default .env file.
    """
    typer.secho("\n🛠️  Initializing job-cd Global Configuration", fg=typer.colors.BLUE, bold=True)
    
    config_manager.ensure_dirs()
    
    typer.echo(f"Config Directory: {typer.style(str(config_manager.app_dir), fg=typer.colors.CYAN)}")

    if config_manager.env_path.exists():
        if not typer.confirm("⚠️  .env file already exists. Do you want to overwrite it?"):
            typer.secho("Aborted initialization.", fg=typer.colors.YELLOW)
            return

    # Prompt for key settings
    google_api_key = typer.prompt("Enter your Google Gemini API Key", hide_input=True)
    apollo_api_key = typer.prompt("Enter your Apollo.io API Key", hide_input=True)
    
    smtp_server = typer.prompt("SMTP Server", default="smtp.gmail.com")
    smtp_port = typer.prompt("SMTP Port", default="587")
    smtp_user = typer.prompt("SMTP Username (Email)")
    smtp_pass = typer.prompt("SMTP Password (App Password)", hide_input=True)

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
    typer.secho(f"\n✅ Configuration saved to {config_manager.env_path}", fg=typer.colors.GREEN)
    
    # Create a dummy default profile if it doesn't exist
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
        typer.secho(f"✅ Default profile created at {config_manager.profiles_path}", fg=typer.colors.GREEN)

    typer.secho("\n🚀  job-cd is ready! Use 'jobcd build <url>' to get started.", fg=typer.colors.BLUE, bold=True)


@app.command()
def build(
    url: str,
    title: Optional[str] = typer.Option(None, "--title", help="Manual override for job title"),
    company: Optional[str] = typer.Option(None, "--company", help="Manual override for company name"),
    domain: Optional[str] = typer.Option(None, "--domain", help="Manual override for company domain")
):
    """
    Execute the job pipeline for a job posting.
    """
    typer.secho(f"\n🚀  Starting Build Pipeline", fg=typer.colors.BLUE, bold=True)
    typer.secho(f"🔗  Target: {url}", fg=typer.colors.WHITE, dim=True)

    db = get_db()
    existing_deployments = db.filter(job_link=url)
    if existing_deployments:
        if not typer.confirm("⚠️  A record for this job URL already exists. Do you want to continue adding a new record for this job post?"):
            typer.secho("Aborted.", fg=typer.colors.YELLOW)
            return
    
    payload = IntakePayload(url=url, manual_title=title, manual_company=company, manual_domain=domain)
    cache = get_cache(filename="contacts.json")
    profile_cache = get_cache(filename="profiles.json")
    profile_data = profile_cache.get("default")
    if not profile_data:
        typer.secho("\n⚠️  No Profile Found!", fg=typer.colors.YELLOW, bold=True)
        typer.echo("To use job-cd, you must first define your application persona.")
        typer.echo(f"Please create a profile at: {typer.style(config_manager.profiles_path, fg=typer.colors.CYAN)}")
        typer.echo("\nExample structure:")
        typer.secho('{\n  "default": {\n    "first_name": "Ted",\n    "last_name": "Lasso",\n    "email": "ted.lasso@afcrichmond.com",\n    ...\n  }\n}', fg=typer.colors.WHITE, dim=True)
        return

    default_profile = DeploymentProfile(**profile_data)

    intake = SimpleWebIntake()
    extractor = GeminiCliExtractor()
    finder = ApolloFinder(cache=cache)
    composer = GeminiCliEmailComposer()

    
    engine = JobPipelineEngine(
        intake_strategy=intake,
        pipeline_steps = [
            ExtractorStep(extractor=extractor),
            FinderStep(finder=finder),
            EmailComposerStep(composer=composer)
        ],
        db=db,
    )

    try:
        deployments = engine.run(payload=payload, profile=default_profile)

        if not deployments or all(d.status == DeploymentStatus.FAILED for d in deployments):
            return

        total_contacts = sum(len(d.outreaches) for d in deployments)
        total_drafted = sum(1 for d in deployments for o in d.outreaches if o.status == DeploymentStatus.DRAFTED)

        typer.secho(f"\n✨ Build Summary:", fg=typer.colors.GREEN, bold=True)
        for d in deployments:
            company_name = d.company.name if d.company else "Unknown"
            company_domain = d.company.domain if d.company else "N/A"
            typer.secho(f"  • {company_name} ({company_domain}): {len(d.outreaches)} contact(s) found.", fg=typer.colors.WHITE)

        typer.secho(f"\n📊 Totals:", fg=typer.colors.GREEN, bold=True)
        typer.secho(f"  • Contacts Identified: {total_contacts}", fg=typer.colors.WHITE)
        typer.secho(f"  • Emails Drafted:      {total_drafted}", fg=typer.colors.WHITE)
        
        typer.secho(f"\n🚀 Pipeline Complete!", fg=typer.colors.GREEN, bold=True)
    except Exception as e:
        typer.secho(f"❌  Pipeline Crash: {e}", fg=typer.colors.RED, bold=True)

@app.command()
def dispatch(
        force: bool = typer.Option(
            False, "--force", "-f", help="Ignore schedule and send all drafted emails."
        )
):
    """
    Release scheduled emails to recruiters.
    """
    if force:
        typer.secho("⚠️  FORCE MODE: Bypassing schedule constraints...", fg=typer.colors.YELLOW, bold=True)
    else:
        typer.secho("🔄  Checking outbox for due deployments...", fg=typer.colors.BLUE)

    db = get_db()
    sender = SmtpEmailSender()
    dispatcher = Dispatcher(db=db, sender=sender)

    try:
        sent, failed = dispatcher.dispatch_due_email(force=force)
        if sent == 0 and failed == 0:
            typer.secho("📭  No emails were due for delivery.", fg=typer.colors.WHITE, dim=True)
        else:
            if sent > 0:
                typer.secho(f"📤  Success: {sent} email(s) dispatched.", fg=typer.colors.GREEN, bold=True)
            if failed > 0:
                typer.secho(f"🚨  Failed: {failed} email(s) encountered errors. Run 'retry' to fix.", fg=typer.colors.RED, bold=True)
    except Exception as e:
        typer.secho(f"Critical Dispatch Error: {e}", fg=typer.colors.RED, bold=True)


@app.command()
def retry():
    """
    Recovery Step: Resend any emails that failed previously.
    """
    typer.secho("🚑  Attempting to rescue failed deployments...", fg=typer.colors.YELLOW, bold=True)
    db = get_db()
    dispatcher = Dispatcher(db=db, sender=SmtpEmailSender())

    try:
        sent, failed = dispatcher.retry_failed_email()
        if sent > 0:
            typer.secho(f"♻️  Rescued: {sent} email(s) sent successfully.", fg=typer.colors.GREEN, bold=True)
        if failed > 0:
            typer.secho(f"⚠️  Still Failing: {failed} email(s) could not be sent.", fg=typer.colors.RED)
        if sent == 0 and failed == 0:
            typer.secho("No failed emails found in database.", fg=typer.colors.WHITE, dim=True)
    except Exception as e:
        typer.secho(f"Retry Error: {e}", fg=typer.colors.RED, bold=True)


@app.command()
def history(
        limit: int = 10,
        detail: bool = typer.Option(False, "--detail", "-d", help="Show detailed outreach and email status.")
):
    """
    Audit Log: View recent job application history.
    """
    db = get_db()
    deployments = db.filter(limit=limit)
    if not deployments:
        typer.secho("History is empty.", fg=typer.colors.WHITE, dim=True)
        return

    typer.secho(f"\n--- RECENT HISTORY (Last {limit}) ---", fg=typer.colors.MAGENTA, bold=True)

    for d in deployments:
        # Determine overall deployment status color
        color = typer.colors.GREEN if d.status.value == "SENT" else typer.colors.YELLOW
        if d.status.value == "FAILED":
            color = typer.colors.RED

        # --- BASE VIEW (Always Shown) ---
        date_str = d.outreaches[0].scheduled_at.strftime("%Y-%m-%d %H:%M") if d.outreaches else "N/A"

        typer.secho(f"[{date_str}] ", fg=typer.colors.WHITE, dim=True, nl=False)
        typer.secho(f"🏢  {d.company.name: <20}", fg=typer.colors.CYAN, bold=True, nl=False)
        typer.secho(f" {d.job.title: <25}", fg=typer.colors.WHITE, nl=False)
        typer.secho(f" [{d.status.value}]", fg=color)

        # --- DETAILED VIEW (Only if -d is passed) ---
        if detail and d.outreaches:
            for outreach in d.outreaches:
                # Local status colors for specific emails
                o_color = typer.colors.WHITE
                if outreach.status.value == "SENT":
                    o_color = typer.colors.GREEN
                elif outreach.status.value == "FAILED":
                    o_color = typer.colors.RED
                elif outreach.status.value == "DRAFTED":
                    o_color = typer.colors.YELLOW

                sent_at_str = outreach.sent_at.strftime("%m/%d %H:%M") if outreach.sent_at else "Pending"

                # Indented outreach info
                typer.secho(f"  └─ 📧  {outreach.draft.recipient_email: <30}", fg=o_color, nl=False)
                typer.secho(f" | Sent: {sent_at_str}", fg=typer.colors.WHITE, dim=True)

                # Optional: Show Recruiter Name/Title if available
                if outreach.contact.name:
                    typer.secho(f"     👤  {outreach.contact.name} ({outreach.contact.title or 'Recruiter'})",
                                fg=typer.colors.WHITE, dim=True)


@app.command()
def preview(limit: int = 1):
    """
    Read the next drafted email waiting in the queue.
    """
    db = get_db()
    deployments = db.filter(status=DeploymentStatus.DRAFTED, limit=limit)
    if not deployments:
        typer.secho("📭  No drafted emails in the queue to preview.", fg=typer.colors.YELLOW)
        return

    found_any = False

    for d in deployments:
        for outreach in d.outreaches:
            if outreach.status == DeploymentStatus.DRAFTED:

                if not outreach.draft:
                    typer.secho(f"⚠️  Warning: {d.company.name} is marked as DRAFTED but has no email body!", fg=typer.colors.RED)
                    continue

                found_any = True
                typer.secho(f"\n🏢  Company: {d.company.name} | Role: {d.job.title}", fg=typer.colors.CYAN, bold=True)
                typer.secho(f"📧  To: {outreach.draft.recipient_email} ({outreach.contact.name})", fg=typer.colors.WHITE)
                typer.secho(f"📝  Subject: {outreach.draft.subject}", fg=typer.colors.MAGENTA)

                # Print the actual email body inside a nice terminal panel
                typer.secho("┌" + "─" * 60, fg=typer.colors.BLUE)
                typer.secho("│ Email Draft:", fg=typer.colors.BLUE, bold=True)
                typer.secho("├" + "─" * 60, fg=typer.colors.BLUE)

                # The actual email body
                typer.secho(outreach.draft.body, fg=typer.colors.WHITE)

                typer.secho("└" + "─" * 60, fg=typer.colors.BLUE)

    if not found_any:
         typer.secho("📭  Deployments were found, but none contained valid drafted emails.", fg=typer.colors.YELLOW)


@app.command()
def config():
    """Configure API keys and settings."""
    typer.secho("Settings coming soon...", fg=typer.colors.YELLOW)    

if __name__ == "__main__":
    app()