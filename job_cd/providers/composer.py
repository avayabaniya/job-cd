import json
import logging
import subprocess
from typing import Optional

from job_cd.core.interfaces import EmailComposerStrategy
from job_cd.core.models import Job, Company, Contact, DeploymentProfile, EmailDraft


class GeminiCliEmailComposer(EmailComposerStrategy):
    """
    Uses the Gemini CLI in headless mode to draft emails
    """
    def __init__(self, model_name: str = "gemini-2.5-flash"):
        self.model_name = model_name

    def draft_email(self, job: Job, company: Company, contact: Contact, profile: DeploymentProfile) -> Optional[EmailDraft]:
        logging.info(f"Drafting email for {contact.name} at {contact.company.name}...")

        default_hook = profile.default_hook or f"I recently saw the open {job.title} role and love the direction your team is heading."
        default_ask = profile.default_ask or "I would truly appreciate any guidance you could provide, whether through a referral, connecting me with the team, or a brief chat."
        resume_url = profile.resume_url or "https://linkedin.com/in/ted-lasso"  # Fallback to your LinkedIn

        # prompt for gemini cli
        prompt = f"""
        You are an elite executive recruiter writing a cold email. 
        We are assembling this email using predefined human templates. Your ONLY job is to write the dynamic "Value Bridge" in the middle.

        STEP 1: THE SNIPER BRIDGE (CRITICAL)
        Read the Job Description. Identify the SINGLE biggest technical or business problem this role needs to solve.
        Read the Candidate's Resume. Find the SINGLE best bullet point or metric that proves they can solve that problem.
        
        Write EXACTLY ONE SENTENCE connecting the two. 
        CRITICAL RULES for this sentence:
        - Write strictly in the FIRST PERSON ("I", "my").
        - Focus heavily on the COMPANY'S NEED first.
        - Use this exact two-sentence structure to make it punchy: "I noticed you need someone to [Company Problem]. With my experience [Resume Metric], I know I can help you get there."
        - DO NOT summarize the whole resume. DO NOT use adjectives like "thrilled" or "delve". Include a hard number/metric if the resume has one.

        STEP 2: Assemble the final JSON.
        Format the body exactly like this using HTML tags for the line breaks and links:

        Hi {contact.first_name},<br><br>

        {default_hook}<br><br>

        Job Link: <a href="{job.job_url}">View Job</a><br><br>

        [Your First-Person Sniper Bridge]<br><br>

        {default_ask}<br><br>

        Resume: <a href="{resume_url}">View Here</a><br><br>

        Best,<br>
        {profile.first_name} {profile.last_name}

        CRITICAL: Respond ONLY with a valid JSON object matching this schema:
        {{
            "subject": "Quick question about the {job.title} role",
            "body": "The assembled HTML email",
            "sender_email": "{profile.email}",
            "recipient_email": "{contact.email}"
        }}
        """

        # context for gemini cli
        context = f"""
        CANDIDATE INFO:
        Name: {profile.first_name} {profile.last_name}
        Role: {profile.current_role}

        CANDIDATE RESUME:
        {profile.resume_text}

        RECIPIENT INFO:
        Name: {contact.first_name}
        Title: {contact.title}

        JOB INFO:
        Company: {job.employer or contact.company.name}
        Job Title: {job.title}
        Description: {job.job_description[:3000]}
        """

        try:
            process = subprocess.run(
                ["gemini", "-m", self.model_name, "-p", prompt, "--output-format", "json", "--skip-trust"],
                input=context,
                capture_output=True,
                text=True,
                check=True
            )

            cli_output = json.loads(process.stdout)
            raw_ai_text = cli_output.get("response", "").strip()

            if raw_ai_text.startswith("```json"):
                raw_ai_text = raw_ai_text.replace("```json", "", 1)
            if raw_ai_text.endswith("```"):
                raw_ai_text = raw_ai_text[:-3]
            raw_ai_text = raw_ai_text.strip()

            draft_data = json.loads(raw_ai_text)
            draft = EmailDraft(**draft_data)

            logging.info(f"Successfully drafted email for {contact.email}")
            return draft
        except Exception as e:
            logging.error(f"Failed to draft email for contact {contact.name} at {company.name}: {e}")
            return None