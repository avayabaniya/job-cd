import json
import sqlite3
import logging
from pathlib import Path
from typing import Optional, List, Union

from job_cd.core.config import config_manager
from job_cd.core.interfaces import DatabaseStrategy
from job_cd.core.models import JobDeployment
from job_cd.enums import DeploymentStatus


class SQLiteDatabaseAdapter(DatabaseStrategy):
    """
    A zero-dependency, local database using Python's built-in sqlite3.
    Stores the complex Pydantic model as a JSON string for easy retrieval.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or config_manager.db_path
        self._initialize_db()

    def _initialize_db(self):
        """Creates the database and table if they don't exist."""
        # Ensure the directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                         CREATE TABLE IF NOT EXISTS deployments (
                    id TEXT PRIMARY KEY,
                    company_name TEXT,
                    company_domain TEXT,
                    job_title TEXT,
                    job_link TEXT,         
                    status TEXT,
                    scheduled_at TEXT,
                    sent_at TEXT,         
                    full_data JSON
                )
                         ''')
            conn.commit()

    def save(self, deployment: JobDeployment) -> None:
        """Inserts a new deployment or overwrites an existing one (Upsert)."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                company_name = deployment.company.name if deployment.company else "Unknown"
                company_domain = deployment.company.domain if deployment.company else "Unknown"
                job_title = deployment.job.title if deployment.job else "Unknown"
                job_link = deployment.job.job_url if deployment.job else "Unknown"
                scheduled_at = None
                sent_at = None

                if hasattr(deployment, 'scheduled_at') and deployment.scheduled_at:
                    scheduled_at = deployment.scheduled_at.isoformat()
                elif deployment.outreaches and deployment.outreaches[0].scheduled_at:
                    scheduled_at = deployment.outreaches[0].scheduled_at.isoformat()

                if hasattr(deployment, 'sent_at') and deployment.sent_at:
                    sent_at = deployment.sent_at.isoformat()
                elif deployment.outreaches and deployment.outreaches[0].sent_at:
                    sent_at = deployment.outreaches[0].sent_at.isoformat()

                conn.execute('''
                    INSERT OR REPLACE INTO deployments (id, company_name, company_domain, job_title, job_link, status, scheduled_at, sent_at, full_data)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    deployment.id,
                    company_name,
                    company_domain,
                    job_title,
                    job_link,
                    deployment.status.value,
                    scheduled_at,
                    sent_at,
                    deployment.model_dump_json()
                ))
                conn.commit()
            logging.info(f"💾 Saved deployment state for {company_name} to local database.")
        except Exception as e:
            logging.error(f"Failed to save deployment to database: {e}")

    def get(self, deployment_id: str) -> Optional[JobDeployment]:
        """Retrieves a deployment by ID and rebuilds the Pydantic model."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute('SELECT full_data FROM deployments WHERE id = ?', (deployment_id,))
                row = cursor.fetchone()

                if row:
                    # row[0] is the raw JSON string we saved
                    data_dict = json.loads(row[0])
                    return JobDeployment(**data_dict)
                return None
        except Exception as e:
            logging.error(f"Failed to fetch deployment {deployment_id}: {e}")
            return None

    def filter(self,
               status: Optional[DeploymentStatus] = None,
               scheduled_only: bool = False,
               job_link: Optional[str] = None,
               limit: int = 50,
               order_by: str = "rowid DESC") -> List[JobDeployment]:
        """
        A single, flexible query method.
        """
        deployments = []

        # Safelist allowed order_by strings to prevent SQL injection
        allowed_orders = {"rowid DESC", "rowid ASC", "scheduled_at DESC", "scheduled_at ASC"}
        if order_by not in allowed_orders:
            order_by = "rowid DESC"

        query = "SELECT full_data FROM deployments WHERE 1=1"
        params = []

        if status:
            query += " AND status = ?"
            params.append(status.value)

        if scheduled_only:
            query += " AND scheduled_at IS NOT NULL"

        if job_link:
            query += " AND job_link = ?"
            params.append(job_link)

        query += f" ORDER BY {order_by} LIMIT ?"
        params.append(limit)

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(query, tuple(params))
                rows = cursor.fetchall()

                for row in rows:
                    data_dict = json.loads(row[0])
                    deployments.append(JobDeployment(**data_dict))

            return deployments
        except Exception as e:
            logging.error(f"Failed to filter deployments: {e}")
            return []

    def update_status(self, deployment_id: str, new_status: DeploymentStatus) -> bool:
        """
        Helper method to quickly update a job's status.
        Ensures both the SQL column and the JSON payload stay in sync.
        """
        deployment = self.get(deployment_id)

        if not deployment:
            logging.warning(f"Deployment {deployment_id} not found in database.")
            return False

        deployment.status = new_status

        self.save(deployment)
        return True