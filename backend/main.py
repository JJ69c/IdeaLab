"""IdeaLab — Synthetic Population Idea Testing Engine."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes.assets import router as assets_router
from backend.api.routes.npcs import router as npcs_router
from backend.api.routes.simulation import router as simulation_router
from backend.api.schemas.responses import HealthResponse
from backend.config import settings
from backend.db.database import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="IdeaLab",
    description="Synthetic population idea testing engine",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(simulation_router)
app.include_router(npcs_router)
app.include_router(assets_router)


@app.get("/api/health", response_model=HealthResponse)
async def health():
    return HealthResponse()
