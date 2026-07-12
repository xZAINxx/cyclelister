"""Async job tracking (spec §5 `jobs`, §6 design rules).

In-process asyncio runner: jobs persist in the `jobs` table so the frontend
can poll status; a semaphore bounds concurrency.
"""
import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable

from sqlalchemy import select

from app.config import get_settings
from app.db.models import Job
from app.db.session import get_session_factory

logger = logging.getLogger(__name__)

_semaphore: asyncio.Semaphore | None = None
_tasks: set[asyncio.Task] = set()


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(get_settings().max_concurrent_jobs)
    return _semaphore


async def create_job(job_type: str, payload: dict) -> uuid.UUID:
    async with get_session_factory()() as session:
        job = Job(type=job_type, status="queued", payload=payload)
        session.add(job)
        await session.commit()
        return job.id


async def _set_status(job_id: uuid.UUID, status: str, *, result: dict | None = None, error: str | None = None) -> None:
    async with get_session_factory()() as session:
        job = (await session.execute(select(Job).where(Job.id == job_id))).scalar_one()
        job.status = status
        if result is not None:
            job.result = result
        if error is not None:
            job.error = error
        await session.commit()


def spawn(job_id: uuid.UUID, work: Callable[[], Awaitable[dict]]) -> None:
    """Run `work` in the background, recording status transitions on the job row."""

    async def _run() -> None:
        async with _get_semaphore():
            await _set_status(job_id, "running")
            try:
                result = await work()
            except Exception as err:
                logger.exception("job %s failed", job_id)
                await _set_status(job_id, "failed", error=str(err))
            else:
                await _set_status(job_id, "succeeded", result=result)

    task = asyncio.create_task(_run())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
