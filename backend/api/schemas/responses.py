from datetime import datetime

from pydantic import BaseModel


class SimulationSummary(BaseModel):
    id: str
    idea_title: str
    status: str
    created_at: datetime
    completed_at: datetime | None = None
    metrics: dict | None = None


class SimulationDetail(BaseModel):
    id: str
    idea_title: str
    idea_description: str
    idea_category: str
    config: dict
    status: str
    created_at: datetime
    completed_at: datetime | None = None
    report: dict | None = None
    summary: str | None = None
    metrics: dict | None = None


class NpcSummary(BaseModel):
    id: str
    name: str
    age: int
    occupation: str
    income_level: str
    interests: list[str]
    personality_summary: str


class AskNpcResponse(BaseModel):
    npc_id: str
    npc_name: str
    question: str
    answer: str
    stance: str
    interest_score: float


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
