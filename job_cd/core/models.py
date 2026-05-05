import uuid
from datetime import datetime, timezone
from typing import Optional
from job_cd.enums import DeploymentStatus
from pydantic import BaseModel, EmailStr, Field, HttpUrl

class DeploymentProfile(BaseModel):
    """The context for who is applying and how to write the email."""
    first_name: str
    last_name: str
    email: EmailStr
    current_role: str
    years_of_experience: int
    target_contact_titles: list[str]
    resume_url: Optional[HttpUrl | str] = None
    resume_text: Optional[str] = None
    default_hook: Optional[str] = None
    default_ask: Optional[str] = None
    default_schedule_time: str = "9:00"
    timezone: str = "America/New_York"



class IntakePayload(BaseModel):
    """
    model defines how we can intake jobs
    currently we only have a job post url option
    but later on we can add more options like csv, api and so on
    """
    url: Optional[HttpUrl] = None
    manual_title: Optional[str] = None
    manual_company: Optional[str] = None
    manual_domain: Optional[str] = None


class Job(BaseModel):
    id: str
    source: str = ""
    title: Optional[str] = None
    employer: Optional[str] = None
    job_url: HttpUrl | str
    application_link: Optional[HttpUrl] = None
    date_posted: Optional[datetime] = None
    deadline: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    salary: Optional[str] = None
    location: Optional[str] = None
    status: str
    job_type: Optional[str] = None
    job_function: Optional[str] = None
    salary_min_amount: Optional[int] = None
    salary_max_amount: Optional[int] = None
    salary_currency: Optional[str] = "USD"
    job_description: Optional[str] = None


class Company(BaseModel):
    id: str
    name: str
    domain: str
    job_title: Optional[str] = None


class Contact(BaseModel):
    id: str
    first_name: str
    last_name: Optional[str]
    name: str
    email: EmailStr 
    phone: Optional[str] = None
    linkedin: Optional[str] = None
    company: Optional[Company] = None
    title: Optional[str] = None
    headline: Optional[str] = None
    email_status: Optional[str] = None
    seniority: Optional[str] = None
    departments: Optional[list[str]] = None


class EmailDraft(BaseModel):
    subject: str
    body: str
    sender_email: EmailStr
    recipient_email: EmailStr

class Outreach(BaseModel):
    """Tracks the status of an email to one specific person."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    contact: Contact
    draft: Optional[EmailDraft] = None
    scheduled_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    status: DeploymentStatus = DeploymentStatus.PENDING

class JobDeployment(BaseModel):
    id: str
    job: Job
    profile: DeploymentProfile
    company: Optional[Company] = None
    status: DeploymentStatus = DeploymentStatus.PENDING
    outreaches: list[Outreach] = Field(default_factory=list)
    intake_payload: Optional[IntakePayload] = None
    
    
    