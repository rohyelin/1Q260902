import threading
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class JobRecord:
    job_id: str
    status: str = "queued"
    progress: int = 0
    transcribe_progress: int = 0
    matching_progress: int = 0
    phase: str = "queued"
    message: str = ""
    error: Optional[str] = None
    options: dict[str, Any] = field(default_factory=dict)
    result: Optional[dict[str, Any]] = None
    warnings: list[str] = field(default_factory=list)


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._lock = threading.Lock()

    def create(self, job_id: str, options: dict[str, Any]) -> JobRecord:
        with self._lock:
            record = JobRecord(job_id=job_id, options=options)
            self._jobs[job_id] = record
            return record

    def get(self, job_id: str) -> Optional[JobRecord]:
        with self._lock:
            return self._jobs.get(job_id)

    def update(
        self,
        job_id: str,
        *,
        status: Optional[str] = None,
        progress: Optional[int] = None,
        transcribe_progress: Optional[int] = None,
        matching_progress: Optional[int] = None,
        phase: Optional[str] = None,
        message: Optional[str] = None,
        error: Optional[str] = None,
        result: Optional[dict[str, Any]] = None,
        warnings: Optional[list[str]] = None,
    ) -> None:
        with self._lock:
            record = self._jobs.get(job_id)
            if not record:
                return
            if status is not None:
                record.status = status
            if progress is not None:
                record.progress = progress
            if transcribe_progress is not None:
                record.transcribe_progress = transcribe_progress
            if matching_progress is not None:
                record.matching_progress = matching_progress
            if phase is not None:
                record.phase = phase
            if message is not None:
                record.message = message
            if error is not None:
                record.error = error
            if result is not None:
                record.result = result
            if warnings is not None:
                record.warnings = warnings


job_store = JobStore()
