import os
import uuid
import logging
import time
from typing import List, Optional

import requests
import typer

from job_cd.core.interfaces import ContactFinderStrategy, CacheStrategy
from job_cd.core.models import Company, Contact, DeploymentProfile


# ── Provider Registry ─────────────────────────────────────────────────────
# Allows selecting the lead generation provider via CLI.

PROVIDER_REGISTRY: dict[str, type[ContactFinderStrategy]] = {}


def register_provider(name: str):
    """Decorator that registers a finder class under a CLI-friendly name."""
    def wrapper(cls):
        PROVIDER_REGISTRY[name] = cls
        return cls
    return wrapper


def get_finder(name: str, cache: CacheStrategy) -> ContactFinderStrategy:
    """Factory: instantiate a registered finder by name."""
    cls = PROVIDER_REGISTRY.get(name)
    if not cls:
        available = ", ".join(sorted(PROVIDER_REGISTRY))
        raise ValueError(
            f"Unknown lead provider '{name}'. Available: {available}"
        )
    return cls(cache=cache)


def _safe_name(person: dict) -> tuple[str, Optional[str], str]:
    """Return (first_name, last_name, full_name) from a person dict.
    Falls back to splitting 'name' if individual fields are missing.
    """
    first = person.get("first_name")
    last = person.get("last_name")
    full = person.get("name") or ""

    if not first and full:
        parts = full.strip().split(" ", 1)
        first = parts[0]
        last = parts[1] if len(parts) > 1 else None

    return first or full or "Unknown", last, full or first or "Unknown"


# ═══════════════════════════════════════════════════════════════════════════
# APOLLO
# ═══════════════════════════════════════════════════════════════════════════


@register_provider("apollo")
class ApolloFinder(ContactFinderStrategy):
    """
    Uses the Apollo.io REST API to find recruiter contacts based on
    the company and your target job titles.
    """
    def __init__(self, cache: CacheStrategy):
        self.api_key = os.getenv("APOLLO_API_KEY")
        if not self.api_key:
            raise ValueError("APOLLO_API_KEY not found in environment variables.")
        self.base_url = 'https://api.apollo.io/api/v1'
        self.people_api_search_endpoint = f'{self.base_url}/mixed_people/api_search'
        self.bulk_people_enrichment_endpoint = f'{self.base_url}/people/bulk_match'
        self.cache = cache

    def find_contacts(self, company: Company, profile: DeploymentProfile) -> List[Contact]:
        logging.info(f"Hunting for contacts at {company.domain} using Apollo...")

        try:
            params = {
                'person_titles[]': profile.target_contact_titles,
                'include_similar_titles': 'true',
                'q_organization_domains_list[]': [company.domain],
                'contact_email_status[]': ['verified', 'likely to engage'],
                'page': 1,
                'per_page': 5,
            }
            headers = {
                'X-Api-Key': self.api_key,
                'Content-Type': 'application/json'
            }
            search_response = requests.post(self.people_api_search_endpoint, params=params, headers=headers)
            search_response.raise_for_status()
            search_data = search_response.json()
            people_search_results = search_data.get('people', [])

            if not people_search_results:
                logging.info(f"No contacts found at {company.domain}.")
                return []

            logging.info(f"Found {len(people_search_results)} potential matches. Enriching data...")

            contacts = []
            people_to_enrich = []
            for person in people_search_results:
                if len(people_to_enrich) == 5:
                    break
                cached_data = self.cache.get(person['id'])
                if cached_data:
                    contacts.append(Contact(**cached_data))
                else:
                    people_to_enrich.append(person)

            if len(people_to_enrich) > 0:
                enrichment_payload = {'details': people_to_enrich}
                enrichment_params = {
                    'reveal_personal_emails': 'false',
                    'reveal_phone_number': 'false'
                }
                enrichment_response = requests.post(
                    self.bulk_people_enrichment_endpoint,
                    json=enrichment_payload,
                    headers=headers,
                    params=enrichment_params
                )
                enrichment_response.raise_for_status()
                enrichment_data = enrichment_response.json()
                enriched_people = enrichment_data.get('matches', [])

                for person in enriched_people:
                    if not person.get('email'):
                        continue
                    first, last, full = _safe_name(person)
                    contact = Contact(
                        id=person.get('id'),
                        first_name=first,
                        last_name=last,
                        name=full,
                        email=person.get('email'),
                        phone=person.get('phone'),
                        linkedin=person.get('linkedin_url'),
                        company=company,
                        title=person.get('title'),
                        headline=person.get('headline'),
                        email_status=person.get('email_status'),
                        seniority=person.get('seniority'),
                        departments=person.get('departments', [])
                    )
                    contacts.append(contact)
                    self.cache.set(contact.id, contact.model_dump())

            logging.info(f"Successfully enriched {len(contacts)} actionable contacts!")
            return contacts

        except requests.exceptions.RequestException as e:
            logging.debug(f"Apollo API failed: {e}")
            return []
        except Exception as e:
            logging.debug(f"Apollo unexpected error: {e}")
            return []


# ═══════════════════════════════════════════════════════════════════════════
# LEADMAGIC
# ═══════════════════════════════════════════════════════════════════════════


@register_provider("leadmagic")
class LeadMagicFinder(ContactFinderStrategy):
    """
    Uses LeadMagic API (employee-finder + email-finder) to find contacts.
    """
    def __init__(self, cache: CacheStrategy):
        self.api_key = os.getenv("LEADMAGIC_API_KEY")
        if not self.api_key:
            raise ValueError("LEADMAGIC_API_KEY not found in environment variables.")
        self.base_url = "https://api.leadmagic.io/v1"
        self.cache = cache

    def _headers(self):
        return {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }

    def find_contacts(self, company: Company, profile: DeploymentProfile) -> List[Contact]:
        logging.info(f"Hunting for contacts at {company.domain} using LeadMagic...")

        try:
            # Step 1: find employees at the company domain
            resp = requests.post(
                f"{self.base_url}/people/employee-finder",
                headers=self._headers(),
                json={
                    "domain": company.domain,
                    "title_keywords": profile.target_contact_titles,
                    "limit": 5,
                },
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            employees = data.get("employees") or data.get("data", [])
            if not employees:
                return []

            contacts = []
            for emp in employees:
                email = emp.get("email")
                if not email:
                    continue
                first, last, full = _safe_name(emp)
                contact = Contact(
                    id=emp.get("id") or str(uuid.uuid4()),
                    first_name=first,
                    last_name=last,
                    name=full,
                    email=email,
                    company=company,
                    title=emp.get("title") or emp.get("position"),
                    linkedin=emp.get("linkedin_url") or emp.get("linkedin"),
                    headline=emp.get("headline"),
                    departments=emp.get("departments"),
                )
                contacts.append(contact)
                self.cache.set(contact.id, contact.model_dump())

            return contacts

        except requests.exceptions.RequestException as e:
            logging.debug(f"LeadMagic API failed: {e}")
            return []
        except Exception as e:
            logging.debug(f"LeadMagic unexpected error: {e}")
            return []


# ═══════════════════════════════════════════════════════════════════════════
# GETPROSPECT
# ═══════════════════════════════════════════════════════════════════════════


@register_provider("getprospect")
class GetProspectFinder(ContactFinderStrategy):
    """
    Uses GetProspect v2 API to find contact emails by name + domain.
    Because GetProspect requires a name, we first scrape generic patterns.
    """
    def __init__(self, cache: CacheStrategy):
        self.api_key = os.getenv("GET_PROSPCT_API_KEY")
        if not self.api_key:
            raise ValueError("GET_PROSPCT_API_KEY not found in environment variables.")
        self.base_url = "https://api.getprospect.com"
        self.cache = cache

    def _headers(self):
        return {"apiKey": self.api_key, "accept": "application/json"}

    def find_contacts(self, company: Company, profile: DeploymentProfile) -> List[Contact]:
        logging.info(f"Hunting for contacts at {company.domain} using GetProspect...")

        try:
            # Step 1: search contacts in the B2B database
            resp = requests.get(
                f"{self.base_url}/public/v1/insights/contacts/search",
                headers=self._headers(),
                params={
                    "domain": company.domain,
                    "title": profile.target_contact_titles,
                    "limit": 5,
                },
                timeout=30,
            )
            if resp.status_code == 403:
                return self._find_by_title_patterns(company, profile)

            resp.raise_for_status()
            data = resp.json()
            results = data.get("data") or data.get("contacts", [])
            if not results:
                return []

            contacts = []
            for entry in results:
                email = entry.get("email")
                if not email:
                    continue
                first, last, full = _safe_name(entry)
                contact = Contact(
                    id=entry.get("id") or str(uuid.uuid4()),
                    first_name=first,
                    last_name=last,
                    name=full,
                    email=email,
                    company=company,
                    title=entry.get("title"),
                    linkedin=entry.get("linkedin_url"),
                    headline=entry.get("headline"),
                )
                contacts.append(contact)
                self.cache.set(contact.id, contact.model_dump())

            return contacts

        except requests.exceptions.RequestException as e:
            logging.debug(f"GetProspect API failed: {e}")
            return []
        except Exception as e:
            logging.debug(f"GetProspect unexpected error: {e}")
            return []

    def _find_by_title_patterns(self, company: Company, profile: DeploymentProfile) -> List[Contact]:
        """
        Fallback: use the v2 email-finder with common name patterns
        generated from the target title keywords.
        """
        contacts = []
        for title in profile.target_contact_titles:
            keywords = title.lower().replace("/", " ").split()
            # Derive a plausible name prefix from the title
            # (e.g. "Head of Engineering" -> "Head")
            prefix = keywords[0].capitalize() if keywords else "Head"
            for candidate in [f"{prefix}"]:
                try:
                    resp = requests.get(
                        f"{self.base_url}/v2/email-finder",
                        headers=self._headers(),
                        params={
                            "full_name": candidate,
                            "domain": company.domain,
                            "company": company.name,
                        },
                        timeout=15,
                    )
                    if resp.status_code != 200:
                        continue
                    data = resp.json().get("data", {})
                    email = data.get("email")
                    if not email:
                        continue
                    first, last, full = _safe_name(data)
                    contact = Contact(
                        id=str(uuid.uuid4()),
                        first_name=first or candidate,
                        last_name=last,
                        name=full or candidate,
                        email=email,
                        company=company,
                        title=title,
                    )
                    contacts.append(contact)
                    self.cache.set(contact.id, contact.model_dump())
                except requests.exceptions.RequestException:
                    continue

        return contacts


# ═══════════════════════════════════════════════════════════════════════════
# SNOV.IO
# ═══════════════════════════════════════════════════════════════════════════


@register_provider("snovio")
class SnovioFinder(ContactFinderStrategy):
    """
    Uses Snov.io API (OAuth2 + async domain search) to find contacts.
    """
    def __init__(self, cache: CacheStrategy):
        self.client_id = os.getenv("SNOV_PUBLIC_KEY")
        self.client_secret = os.getenv("SNOV_SECRET_KEY")
        if not self.client_id or not self.client_secret:
            raise ValueError("SNOV_PUBLIC_KEY and SNOV_SECRET_KEY must be set in .env")
        self.base_url = "https://api.snov.io"
        self._token: Optional[str] = None
        self.cache = cache

    def _get_token(self) -> str:
        """Obtain or refresh OAuth2 bearer token."""
        if self._token:
            return self._token
        resp = requests.post(
            f"{self.base_url}/v1/oauth/access_token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            timeout=15,
        )
        resp.raise_for_status()
        self._token = resp.json()["access_token"]
        return self._token

    def _auth_headers(self):
        return {"Authorization": f"Bearer {self._get_token()}", "Content-Type": "application/json"}

    def find_contacts(self, company: Company, profile: DeploymentProfile) -> List[Contact]:
        logging.info(f"Hunting for contacts at {company.domain} using Snov.io...")

        try:
            # Step 1: start domain search (async)
            start_resp = requests.post(
                f"{self.base_url}/v2/domain-search/start",
                headers=self._auth_headers(),
                json={"domain": company.domain},
                timeout=30,
            )
            start_resp.raise_for_status()
            task_data = start_resp.json()
            task_hash = task_data.get("data", {}).get("task_hash") or task_data.get("task_hash")
            if not task_hash:
                return []


            result_url = f"{self.base_url}/v2/domain-search/result/{task_hash}"
            for attempt in range(10):
                time.sleep(2)
                poll = requests.get(result_url, headers=self._auth_headers(), timeout=15)
                poll.raise_for_status()
                status = poll.json().get("status", "")
                if status == "completed":
                    break
            else:
                return []


            prospects_resp = requests.post(
                f"{self.base_url}/v2/domain-search/domain-emails/start",
                headers=self._auth_headers(),
                json={"task_hash": task_hash},
                timeout=30,
            )
            prospects_resp.raise_for_status()
            emails_data = prospects_resp.json()

            email_results = emails_data.get("data") or emails_data.get("emails", [])
            if not email_results:
                return []

            contacts = []
            for entry in email_results[:5]:
                email = entry.get("email")
                if not email:
                    continue
                first, last, full = _safe_name(entry)
                contact = Contact(
                    id=str(uuid.uuid4()),
                    first_name=first,
                    last_name=last,
                    name=full,
                    email=email,
                    company=company,
                    title=entry.get("title"),
                    linkedin=entry.get("linkedin_url"),
                )
                contacts.append(contact)
                self.cache.set(contact.id, contact.model_dump())

            return contacts

        except requests.exceptions.RequestException as e:
            logging.debug(f"Snov.io API failed: {e}")
            return []
        except Exception as e:
            logging.debug(f"Snov.io unexpected error: {e}")
            return []


# ═══════════════════════════════════════════════════════════════════════════
# AUTO-FALLBACK: tries every registered provider in order
# ═══════════════════════════════════════════════════════════════════════════


class AutoFallbackFinder(ContactFinderStrategy):
    """
    Tries every registered lead provider in sequence until one returns contacts.
    Swallows individual provider errors silently — only reports if ALL fail.

    Fallback order: apollo → leadmagic → getprospect → snovio
    """
    def __init__(self, cache: CacheStrategy):
        self.cache = cache
        self.providers = []

        order = ["apollo", "leadmagic", "getprospect", "snovio"]
        for name in order:
            cls = PROVIDER_REGISTRY.get(name)
            if cls:
                try:
                    self.providers.append((name, cls(cache=cache)))
                except Exception:
                    continue

    def find_contacts(self, company: Company, profile: DeploymentProfile) -> List[Contact]:
        errors = []

        for name, provider in self.providers:
            typer.secho(f"  [{name}] Searching for contacts at {company.domain}...", fg=typer.colors.CYAN)
            try:
                contacts = provider.find_contacts(company, profile)
                if contacts:
                    if len(self.providers) > 1:
                        typer.secho(f"  [{name}] Found {len(contacts)} contacts.", fg=typer.colors.GREEN, bold=True)
                    return contacts
            except Exception as e:
                msg = str(e).split("\n")[0][:100]
                errors.append(f"{name}: {msg}")
                continue

        if errors:
            typer.secho(
                "  All lead providers failed. Try --finder <name> to pick one:\n"
                f"    apollo, leadmagic, getprospect, snovio",
                fg=typer.colors.YELLOW,
            )
        else:
            typer.secho(
                "  No contacts found by any provider.",
                fg=typer.colors.YELLOW,
            )
        return []


@register_provider("auto")
class _AutoAlias(AutoFallbackFinder):
    """Alias so --finder auto works the same as AutoFallbackFinder."""
    pass
