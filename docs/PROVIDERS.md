# Supported Service Providers

`job-cd` is designed to be provider-agnostic. Below are the third-party services currently implemented as concrete strategies.

## 🤖 AI & LLMs (Extraction & Composition)
- **Antigravity CLI** (Default): Used for high-speed, cost-effective job detail extraction and hyper-personalized email composition.
  - **Implementation**: `AntigravityCliExtractor`, `AntigravityCliEmailComposer`
- **Google Gemini CLI**: Alternate provider for job detail extraction and hyper-personalized email composition.
  - **Implementation**: `GeminiCliExtractor`, `GeminiCliEmailComposer`
  - **Requirement**: `GOOGLE_API_KEY`

## 🔍 Contact Discovery (Finding)
- **Apollo.io**: Used to find specific recruitment and engineering contacts at target companies.
  - **Implementation**: `ApolloFinder`
  - **Requirement**: `APOLLO_API_KEY`

## 📧 Email Dispatch (Sending)
- **SMTP**: Standard protocol for sending emails. Tested with Gmail, Outlook, and ProtonMail.
  - **Implementation**: `SmtpEmailSender`
  - **Requirement**: `SMTP_SERVER`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`

## 🗄️ Persistence & Storage
- **SQLite**: Local relational database for tracking history and deployment states.
  - **Implementation**: `SQLiteDatabaseAdapter`
- **Local JSON Cache**: Simple file-based storage for API response caching and user profiles.
  - **Implementation**: `LocalCache`

---

## 🛠️ How to Add a New Provider (Example: Hunter.io)

If you want to use a different service for finding emails (e.g., [Hunter.io](https://hunter.io/)), follow this pattern:

### 1. Create the Provider
Create a new file: `job_cd/providers/hunter_finder.py`. This class must implement the `ContactFinderStrategy` interface.

```python
from typing import List
from job_cd.core.interfaces import ContactFinderStrategy
# ... rest of code
```

### 2. Swap it in the Main Pipeline
In `job_cd/main.py`, simply replace the default finder. Because both `ApolloFinder` and `HunterFinder` follow the same `ContactFinderStrategy` contract, the engine won't know the difference.

---

## 🤖 Swapping LLMs (Example: OpenAI Composer)

If you prefer to use OpenAI's GPT-4 for writing your emails instead of Google Gemini, you would implement a new class using the `EmailComposerStrategy` interface.

### 1. Create the OpenAI Composer
Create `job_cd/providers/openai_composer.py`:

```python
from job_cd.core.interfaces import EmailComposerStrategy
from job_cd.core.models import Job, Company, Contact, DeploymentProfile, EmailDraft

class OpenAIComposer(EmailComposerStrategy):
    def draft_email(self, job: Job, company: Company, contact: Contact, profile: DeploymentProfile) -> EmailDraft:
        # 1. Format prompt for GPT-4
        # 2. Call OpenAI API
        # 3. Return an EmailDraft object
        pass
```

### 2. Update the Pipeline
In `job_cd/main.py`, update the engine configuration:

```python
from job_cd.providers.openai_composer import OpenAIComposer

# ...
composer = OpenAIComposer(api_key=...)
# ...
```

By following this pattern of **Interface -> Concrete Implementation -> Injection**, you can customize every single step of the `job-cd` pipeline without modifying the core logic.
