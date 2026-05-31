# Job-CD 🚀

**An Automated Outreach Engine for Job Applications.**

`job-cd` is a specialized automation tool focused on the most critical phase of the job search: **personalized email outreach to hiring managers and recruiters**. It treats your career search like a modern software pipeline: taking a job URL as "source code," processing it through various "build steps" (extraction, contact discovery, email drafting), and finally "deploying" (sending) hyper-personalized outreach.

---

## 🚀 Quick Start

### 1. Installation

#### Prerequisites
- **Python 3.12+**
- **[Gemini CLI](https://geminicli.com/docs/get-started/installation/):** Used by default for AI tasks. *(Can be swapped for any AI tool or LLM).*
- **Apollo.io API Key:** Default for contact discovery. *(Can be swapped for other lead discovery services).*
- **SMTP Credentials:** For email dispatch. *(Works with any SMTP-compatible provider).*

#### Setup
```bash
# Clone the repository
git clone https://github.com/yourusername/job-cd.git
cd job-cd

# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate

# Install the package
pip install -e .
```

### 2. Basic Usage

Automate your outreach in three simple steps:

```bash
# 1. Build a Deployment (Extract info & find recruiter's emails)
jobcd build "https://www.linkedin.com/jobs/view/123456789/"

# 2. Preview Drafts (Review AI-generated emails)
jobcd preview

# 3. Dispatch (Send emails)
jobcd dispatch
```

---

## ✨ Features

- **Modular & Extensible:** Built on an "Interface-First" architecture. Every component—from the lead finder to the AI model—is a pluggable strategy.
- **AI-Driven Extraction:** Automatically identifies company context and role requirements from unstructured text using Gemini.
- **Intelligent Discovery:** Locates specific recruitment and engineering contacts at target companies via Apollo.io.
- **Hyper-Personalized Content:** Generates tailored, high-conversion cold emails based on your profile and the specific job requirements.
- **Profile Management:** Define your "Persona" (experience, target roles, current title) in a local cache for consistent tailoring.
- **Audit & History:** Comprehensive tracking of every application, contact, and email status in a local SQLite database.

---

## ⚙️ Configuration

### 1. Environment Variables
Create a `.env` file in the root directory:

```env
GOOGLE_API_KEY=your_gemini_key
APOLLO_API_KEY=your_apollo_key
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password
```

### 2. Personalization (Profiles)
`job-cd` uses your profile to tailor outreach. Create `.cache/profiles.json`:

```json
{
  "default": {
    "first_name": "Ted",
    "last_name": "Lasso",
    "email": "ted.lasso@afcrichmond.com",
    "current_role": "Head Coach",
    "years_of_experience": 20,
    "target_contact_titles": ["Owner", "Director of Football"],
    "resume_text": "# TED LASSO\nHead Coach | AFC Richmond\n\n- Expert in team building and 'Believe' philosophy."
  }
}
```

---

## 🔌 Default Providers & Extensibility

`job-cd` is provider-agnostic. You can swap any component by implementing its interface.

| Component | Default Provider | Purpose |
| :--- | :--- | :--- |
| **Intake** | `SimpleWebIntake` | Fetches raw data from job URLs. |
| **Extraction** | `GeminiCliExtractor` | Parses job text into structured data. |
| **Discovery** | `ApolloFinder` | Finds relevant recruiter/manager emails. |
| **Composition** | `GeminiCliEmailComposer` | Drafts the personalized email body. |
| **Dispatch** | `SmtpEmailSender` | Sends the final emails to recipients. |

---

## 📚 Documentation

- **[Architecture Overview](docs/ARCHITECTURE.md)**: System design and pipeline engine.
- **[Service Providers](docs/PROVIDERS.md)**: Third-party integrations.
- **[Contributing Guide](CONTRIBUTING.md)**: How to extend the system.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
