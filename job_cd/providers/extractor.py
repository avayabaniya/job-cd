import logging
import json
import os
import uuid
import subprocess
import typer
from google import genai
from google.genai import types
from typing import Optional
from pydantic import ValidationError
from job_cd.core.interfaces import CompanyExtractorStrategy
from job_cd.core.models import Job, Company

class GeminiExtractor(CompanyExtractorStrategy):
    """
    Uses Google's Gemini model to read a raw job description and extract 
    the standardized Company details.
    """
    def __init__(self, model_name: str = "gemini-2.5-flash-lite"):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables.")
        self.client = genai.Client(api_key=api_key)
        self.model_name = model_name

    def extract_company(self, job: Job) -> Optional[Company]:
        logging.info(f"Asking Gemini to extract company details for job ID: {job.id}")

        if not job.job_description:
            logging.error("Job has no description text. Cannot extract company.")
            return None

        prompt = f"""
        Analyze the following job description text.
        Extract the job title, official company name and their primary website domain (e.g., 'google.com', 'stripe.com').
        
        If the domain is not explicitly mentioned in the text, use your broad internal knowledge to provide the company's actual, real-world website domain. Do not guess or hallucinate a fake URL.
        
        Job URL: 
        {job.job_url}

        Job Description Text:
        {job.job_description}
        """
        
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=Company,
                    temperature=0.1
                )
            )
            
            response_text = response.text.strip()
            company_data = json.loads(response_text)
            company = Company(**company_data)

            company.id = str(uuid.uuid4()) if not company.id else company.id

            logging.info(f"Successfully extracted: {company.name} ({company.domain}) from job {job.id}")
            return company
        except ValidationError as e:
            logging.error(f"Failed to validate company data for job {job.id}: {e}")
            return None
        except Exception as e:
            logging.error(f"Failed to extract company details for job {job.id}: {e}")
            return None


class GeminiCliExtractor(CompanyExtractorStrategy):
    """
    Run google gemini-cli in headless mode to read a raw job description and extract
    the standardized Company details.

    The user needs to make sure that they are logged in into gemini-cli to use this extractor.
    """
    def __init__(self, model_name: str = "gemini-2.5-flash"):
        self.model_name = model_name

    def extract_company(self, job: Job) -> Optional[Company]:
        logging.info(f"Asking Gemini Cli to extract company details for job ID: {job.id}")

        if not job.job_description:
            logging.error("Job has no description text. Cannot extract company.")
            return None

        prompt = f"""
        Extract the job title, official company name and their primary website domain (e.g., 'google.com', 'stripe.com') from the provided text.
        If the domain is not explicitly mentioned, infer it from your internal knowledge.
        
        CRITICAL INSTRUCTION: You must respond ONLY with a valid JSON object matching this exact schema:
        {{
            "name": "string",
            "domain": "string",
            "job_title": "string"
        }}
        Do not include markdown blocks (like ```json), explanations, or any other text.
        """

        context = f"Job URL: {job.job_url}\n\nJob Description Text:\n{job.job_description}"

        try:
            typer.secho("👀  Gemini CLI is taking a look...", fg=typer.colors.BLUE, bold=True)
            # Call the CLI using Python's subprocess.
            # -p passes the prompt, --output-format json forces the CLI to return a predictable JSON payload
            process = subprocess.run(
                ["gemini", "-m", f"{self.model_name}", "-p", prompt, "--output-format", "json"],
                input=context,
                capture_output=True,
                text=True,
                check=True  # Throws an error if the CLI crashes
            )

            cli_output = json.loads(process.stdout)
            raw_ai_text = cli_output.get("response", "").strip()

            typer.secho("📊  Gemini CLI raw output:", fg=typer.colors.BLUE, bold=True)
            typer.secho(raw_ai_text, fg=typer.colors.YELLOW)

            # Clean up potential AI response
            if raw_ai_text.startswith("```json"):
                raw_ai_text = raw_ai_text.replace("```json", "", 1)
            if raw_ai_text.endswith("```"):
                raw_ai_text = raw_ai_text[:-3]
            raw_ai_text = raw_ai_text.strip()

            company_data = json.loads(raw_ai_text)
            company_data["id"] = str(uuid.uuid4())

            company = Company(**company_data)

            logging.info(f"Successfully extracted: {company.name} ({company.domain})")
            return company

        except subprocess.CalledProcessError as e:
            logging.error(f"Gemini CLI command failed (Exit code {e.returncode}): {e.stderr}")
            return None
        except FileNotFoundError:
            logging.error("Gemini CLI not found. Make sure you ran `npm install -g @google/gemini-cli`.")
            return None
        except json.JSONDecodeError as e:
            logging.error(f"Failed to parse JSON from Gemini CLI output: {e}")
            return None
        except ValidationError as e:
            logging.error(f"Failed to validate company data for job {job.id}: {e}")
            return None
        except Exception as e:
            logging.error(f"Failed to extract company details for job {job.id}: {e}")
            return None