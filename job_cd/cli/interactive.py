import shlex

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggest, Suggestion
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style
from rich.panel import Panel
from rich.prompt import Prompt as RichPrompt

from job_cd.cli.app import BANNER, console
from job_cd.cli.commands import (
    do_build,
    do_config,
    do_dispatch,
    do_history,
    do_init,
    do_preview,
    do_retry,
)
from job_cd.core.config import config_manager

INTERACTIVE_COMMANDS = sorted([
    "init", "config", "build", "preview",
    "dispatch", "retry", "history", "help", "exit",
])

INTERACTIVE_FLAGS = {
    "config": ["--edit", "--open"],
    "build": ["--title", "--company", "--domain"],
    "dispatch": ["--force", "-f"],
    "history": ["--detail", "-d"],
}

PROMPT_STYLE = Style.from_dict({
    "prompt": "bold blue",
})


class AutoCompleter(Completer):
    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        parts = shlex.split(text) if text.strip() else []

        if not parts:
            for cmd in INTERACTIVE_COMMANDS:
                if cmd.startswith(text):
                    yield Completion(cmd, start_position=-len(text))
        elif len(parts) == 1 and not text.endswith(" "):
            word = parts[0]
            for cmd in INTERACTIVE_COMMANDS:
                if cmd.startswith(word):
                    yield Completion(cmd, start_position=-len(word))
        else:
            cmd = parts[0].lower()
            flags = INTERACTIVE_FLAGS.get(cmd, [])
            current = parts[-1] if not text.endswith(" ") else ""
            for flag in flags:
                if flag.startswith(current):
                    yield Completion(flag, start_position=-len(current))


class AutoSuggestCommands(AutoSuggest):
    def get_suggestion(self, buffer, document):
        text = document.text
        if not text:
            return None
        for cmd in INTERACTIVE_COMMANDS:
            if cmd.startswith(text) and cmd != text:
                return Suggestion(cmd[len(text):])
        return None


INTERACTIVE_HELP = """\
[bold cyan]Available Commands:[/]

  [bold]init[/]                    Initialize configuration
  [bold]config[/]                  View configuration
  [bold]config --edit[/]           Edit configuration in your editor
  [bold]build <url>[/]             Run pipeline for a job posting
  [bold]build <url> --title ...[/]  Build with manual overrides
  [bold]preview[/]                 Preview next drafted email
  [bold]dispatch[/]                Send scheduled emails
  [bold]dispatch --force[/]        Send all drafts immediately
  [bold]retry[/]                   Retry failed emails
  [bold]history[/]                 View recent history
  [bold]history --detail[/]        View history with details
  [bold]help[/]                    Show this help
  [bold]exit[/]                    Exit interactive mode

[dim]Press [bold]Tab[/] to auto-complete \u00b7 [bold]\u2191\u2193[/] for history \u00b7 suggestions appear as you type[/]
"""


def interactive_mode():
    """Interactive REPL with auto-suggestions and tab completion."""
    history_path = config_manager.app_dir / ".history"
    history_path.parent.mkdir(parents=True, exist_ok=True)

    session = PromptSession(
        completer=AutoCompleter(),
        auto_suggest=AutoSuggestCommands(),
        history=FileHistory(str(history_path)),
        style=PROMPT_STYLE,
        message=[("class:prompt", "\u25b8 ")],
        complete_while_typing=True,
    )

    console.print(BANNER)
    console.print(
        Panel(
            "[white]Welcome to job-cd interactive mode.[/]\n\n"
            "[dim]Type [bold]help[/] for commands \u00b7 [bold]Tab[/] to complete \u00b7 "
            "[bold]\u2191\u2193[/] for history[/]\n"
            "[dim]Suggestions appear in dimmed text as you type.[/]",
            border_style="blue",
        )
    )
    console.print()

    while True:
        try:
            raw = session.prompt().strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Goodbye![/]")
            break

        if not raw:
            continue

        raw_lower = raw.lower()

        if raw_lower in ("exit", "quit", "q"):
            console.print("[yellow]Goodbye![/]")
            break

        if raw_lower in ("help", "h", "?"):
            console.print(Panel(INTERACTIVE_HELP, border_style="cyan"))
            continue

        try:
            parts = shlex.split(raw)
        except ValueError as e:
            console.print(f"[red]Invalid input: {e}[/]")
            continue

        cmd = parts[0].lower()
        args = parts[1:]

        try:
            if cmd == "init":
                do_init()

            elif cmd == "config":
                flags = {a for a in args if a.startswith("--")}
                do_config(edit=bool(flags & {"--edit", "--open"}))

            elif cmd == "build":
                urls = [a for a in args if not a.startswith("--")]
                if not urls:
                    url = RichPrompt.ask("Enter job posting URL")
                else:
                    url = urls[0]

                opt_overrides = {}
                for i, a in enumerate(args):
                    if a == "--title" and i + 1 < len(args):
                        opt_overrides["title"] = args[i + 1]
                    elif a == "--company" and i + 1 < len(args):
                        opt_overrides["company"] = args[i + 1]
                    elif a == "--domain" and i + 1 < len(args):
                        opt_overrides["domain"] = args[i + 1]

                do_build(url, **opt_overrides)

            elif cmd == "preview":
                limit_val = 1
                for a in args:
                    if a.lstrip("-").isdigit():
                        limit_val = int(a)
                do_preview(limit=limit_val)

            elif cmd == "dispatch":
                do_dispatch(force="--force" in args or "-f" in args)

            elif cmd == "retry":
                do_retry()

            elif cmd == "history":
                limit_val = 10
                for a in args:
                    if a.lstrip("-").isdigit():
                        limit_val = int(a)
                do_history(limit=limit_val, detail="--detail" in args or "-d" in args)

            else:
                console.print(f"[red]Unknown command: {cmd}. Type 'help' for available commands.[/]")

        except Exception as e:
            console.print(f"[red]Error: {e}[/]")
