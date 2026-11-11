"""Idempotent retry tracking for unfinished worker tasks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass
class RetryRecord:
    task_id: str
    attempts: int = 0
    state: str = "pending"
    next_retry_at: datetime | None = None
    last_error: str = ""


class TaskRetryTracker:
    """Small process-local tracker; replace the store with a durable backend later."""

    def __init__(self) -> None:
        self.records: dict[str, RetryRecord] = {}

    def record_failure(
        self,
        task_id: str,
        error: str,
        max_retries: int,
        backoff_seconds: int,
        now: datetime | None = None,
    ) -> RetryRecord:
        now = now or datetime.now(timezone.utc)
        record = self.records.setdefault(task_id, RetryRecord(task_id=task_id))
        record.last_error = error
        if record.attempts >= max_retries:
            record.state = "exhausted"
            record.next_retry_at = None
            return record
        record.attempts += 1
        record.state = "scheduled"
        record.next_retry_at = now + timedelta(seconds=backoff_seconds)
        return record

    def ready_for_retry(self, task_id: str, now: datetime | None = None) -> bool:
        record = self.records.get(task_id)
        if not record or record.state != "scheduled" or not record.next_retry_at:
            return False
        return (now or datetime.now(timezone.utc)) >= record.next_retry_at

    def mark_success(self, task_id: str) -> RetryRecord:
        record = self.records.setdefault(task_id, RetryRecord(task_id=task_id))
        record.state = "succeeded"
        record.next_retry_at = None
        return record
