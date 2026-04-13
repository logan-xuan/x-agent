"""Shared in-memory backing for lightweight runtime context stores."""

from __future__ import annotations

from typing import Any

_GLOBAL_CONTEXT_BUCKET = {
    "session_state": {},
    "episodic_events": [],
    "evidence_entries": [],
    "artifacts": [],
}


def get_context_bucket(storage: Any) -> dict[str, Any]:
    """Return a mutable bucket attached to a StorageService-like object."""
    bucket = getattr(storage, "_runtime_context_bucket", None)
    if bucket is None:
        bucket = _GLOBAL_CONTEXT_BUCKET
        storage._runtime_context_bucket = bucket
    return bucket
