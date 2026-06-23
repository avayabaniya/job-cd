from dotenv import load_dotenv
from rich.console import Console

from job_cd.core.config import config_manager
from job_cd.core.interfaces import CacheStrategy
from job_cd.providers.cache import LocalCache
from job_cd.providers.database import SQLiteDatabaseAdapter

load_dotenv(config_manager.env_path)
load_dotenv()

console = Console()

BANNER = """
[bold blue]   ╦╔═╗╔╗ ╔═╗╔╦╗[/]
[bold blue]   ║║ ║╠╩╗║   ║║[/]
[bold blue]   ╩╚═╝╚═╝╚═╝═╩╝[/]
[bold cyan]   Continuous Deployment for Jobs[/]
"""


def get_db():
    return SQLiteDatabaseAdapter()


def get_cache(filename: str = "contacts.json") -> CacheStrategy:
    return LocalCache(filename=filename)
