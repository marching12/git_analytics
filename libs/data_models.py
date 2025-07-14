from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class PullRequest(BaseModel):
    pr_id: int
    repo_id: int
    team_id: Optional[int] = None
    pr_number: int
    title: Optional[str] = None
    state: Optional[str] = None
    author_id: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    merged_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    additions: Optional[int] = None
    deletions: Optional[int] = None
    commit_count: Optional[int] = None

class Review(BaseModel):
    review_id: int
    pr_id: int
    reviewer_id: Optional[int] = None
    state: str
    submitted_at: datetime

class Issue(BaseModel):
    issue_id: int
    repo_id: Optional[int] = None
    issue_number: int
    title: Optional[str] = None
    state: str
    author_id: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None

