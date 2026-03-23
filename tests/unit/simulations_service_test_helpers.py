from __future__ import annotations
from datetime import UTC, datetime, time, timedelta
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker
from app.domains import CandidateSession, Job, Simulation
from app.domains.common.types import CANDIDATE_SESSION_STATUS_COMPLETED
from app.domains.simulations import service as sim_service
from app.services.simulations import creation as sim_creation
from tests.factories import create_recruiter, create_simulation

__all__ = [name for name in globals() if not name.startswith("__")]
