import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from job_cd.core.interfaces import JobIntakeStrategy
from job_cd.core.models import Job, IntakePayload
from job_cd.enums import DeploymentStatus


PAGE_TITLE_SEPARATORS = [
    r"\s+[:|]\s+",     # " : " or " | "
    r"\s+[-–]\s+",     # " - " or " – "
    r"\s+[·•]\s+",     # " · " or " • "
    r"\s+at\s+",       # " at "
]


def _parse_page_title(page_title: str) -> tuple[Optional[str], Optional[str]]:
    """Parse a page title into (title, company) using natural separator order.
    Most sites format as 'Job Title : Company Name || Site Name'.
    Returns the first segment as title, second as company candidate.
    """
    for sep in PAGE_TITLE_SEPARATORS:
        split = re.split(sep, page_title, maxsplit=1)
        if len(split) == 2:
            return split[0].strip(), split[1].strip()
    return page_title.strip(), None


def _strip_site_suffix(name: str, site_name: Optional[str] = None) -> str:
    """Remove known site/brand suffixes from a parsed company name.
    e.g. 'Smart Framework || Bdjobs.com' -> 'Smart Framework'"""
    for sep in [" || ", " | ", " — ", " – ", " · ", " • "]:
        parts = name.rsplit(sep, 1)
        if len(parts) == 2:
            candidate, suffix = parts[0].strip(), parts[1].strip()
            # If the suffix looks like a site name (short, or matches known site), strip it
            if site_name and suffix.lower() == site_name.lower():
                return candidate
            if len(suffix) < len(candidate) and ("." in suffix or len(suffix) < 25):
                return candidate
    return name


def _extract_site_name(soup: BeautifulSoup) -> Optional[str]:
    for tag in [
        'meta[property="og:site_name"]',
        'meta[name="og:site_name"]',
        'meta[name="application-name"]',
        'meta[property="og:title"]',
    ]:
        meta = soup.select_one(tag)
        if meta and meta.get("content"):
            return meta["content"].strip()
    return None


def _derive_domain(url: str) -> str:
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    return hostname.removeprefix("www.")


def _parse_json_ld(soup: BeautifulSoup) -> Optional[dict]:
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string)
            if isinstance(data, dict):
                return data
            if isinstance(data, list) and data:
                return data[0]
        except (json.JSONDecodeError, TypeError):
            continue
    return None


def _extract_from_json_ld(data: dict) -> dict:
    result = {}
    if "title" in data:
        result["title"] = data["title"]
    if "name" in data:
        result.setdefault("title", data["name"])
    if "hiringOrganization" in data:
        org = data["hiringOrganization"]
        if isinstance(org, dict):
            result["employer"] = org.get("name")
            if "url" in org and not result.get("url"):
                result["url"] = org["url"]
    if "description" in data:
        result["description"] = data["description"]
    if "url" in data and not result.get("url"):
        result["url"] = data["url"]
    if "identifier" in data:
        ident = data["identifier"]
        if isinstance(ident, dict) and "name" in ident:
            result.setdefault("employer", ident["name"])
    return result


class SimpleWebIntake(JobIntakeStrategy):
    """
    A lightweight scraper that takes any job URL, downloads the page,
    and strips the HTML to get the raw text.
    Also extracts structured metadata (OG tags, JSON-LD, <title>) for display.
    """
    def __init__(self, console=None):
        self.console = console

    def fetch_jobs(self, payload: IntakePayload) -> List[Job]:
        if not payload.url:
            raise ValueError("SimpleWebIntake requires a 'url' in the payload.")

        url_str = str(payload.url)
        logging.info(f"Fetching job data from {url_str}")

        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            response = requests.get(url_str, headers=headers, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')
            for script in soup(['script', 'style']):
                script.extract()

            clean_text = soup.get_text(separator=" ", strip=True)

            page_title = soup.title.string.strip() if soup.title and soup.title.string else None

            meta = {"title": page_title, "employer": None, "domain": None, "description": None}

            json_ld = _parse_json_ld(soup)
            if json_ld:
                meta.update(_extract_from_json_ld(json_ld))

            if not meta.get("title"):
                og_title_tag = soup.select_one('meta[property="og:title"], meta[name="og:title"]')
                if og_title_tag and og_title_tag.get("content"):
                    meta["title"] = og_title_tag["content"].strip()

            og_desc_tag = soup.select_one('meta[property="og:description"], meta[name="og:description"]')
            if og_desc_tag and og_desc_tag.get("content"):
                meta["description"] = og_desc_tag["content"].strip()
            elif not meta.get("description"):
                meta["description"] = clean_text[:2000]

            og_url_tag = soup.select_one('meta[property="og:url"], meta[name="og:url"]')
            canonical_url = og_url_tag["content"].strip() if og_url_tag and og_url_tag.get("content") else url_str
            meta["domain"] = _derive_domain(canonical_url)

            if not meta.get("employer"):
                site_name = _extract_site_name(soup)

                if meta.get("title"):
                    parsed_title, parsed_company = _parse_page_title(meta["title"])
                    meta["title"] = parsed_title

                    if site_name:
                        meta["employer"] = site_name
                    elif parsed_company:
                        parsed_company = _strip_site_suffix(parsed_company)
                        meta["employer"] = parsed_company
                elif site_name:
                    meta["employer"] = site_name

            if self.console:
                from rich.panel import Panel
                lines = [
                    f"[bold cyan]Job Title:[/]  {meta['title'] or '[dim]N/A[/]'}",
                    f"[bold cyan]Company:[/]    {meta['employer'] or '[dim]N/A[/]'}",
                    f"[bold cyan]Domain:[/]     {meta['domain'] or '[dim]N/A[/]'}",
                ]
                if meta.get("description"):
                    desc_short = meta["description"][:120].replace("\n", " ")
                    lines.append(f"[bold cyan]About:[/]      [dim]{desc_short}...[/dim]")

                self.console.print(
                    Panel(
                        "\n".join(lines),
                        title="[bold yellow]URL Preview (AI will verify)[/]",
                        border_style="yellow",
                    )
                )

            job = Job(
                id=str(uuid.uuid4()),
                source="web",
                job_url=url_str,
                title=meta["title"],
                employer=meta["employer"],
                status=DeploymentStatus.PENDING,
                job_description=clean_text[:5000],
                created_at=datetime.now(timezone.utc),
            )

            return [job]

        except Exception as e:
            logging.error(f"Failed to scrape URL {url_str}: {e}")
            return []
        