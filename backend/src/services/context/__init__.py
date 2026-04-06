"""Lightweight stateful-context compatibility layer for runtime tests."""

from __future__ import annotations

from .artifact_store import ArtifactStore, StoredArtifact
from .context_assembler import ContextAssembler
from .episodic_memory_store import EpisodicMemoryEntry, EpisodicMemoryStore
from .evidence_ledger_store import EvidenceLedgerEntry, EvidenceLedgerStore
from .mode_detector import ModeDetector
from .session_state_store import SessionContextState, SessionContextStateStore
from .session_state_updater import SessionStateUpdater
from .tool_result_archiver import ToolResultArchiver
from .types import ContextBuildBundle, ContextBuildRequest

_session_state_updater = None
_tool_result_archiver = None


def get_session_state_updater():
    return _session_state_updater


def set_session_state_updater(value) -> None:
    global _session_state_updater
    _session_state_updater = value


def get_tool_result_archiver():
    return _tool_result_archiver


def set_tool_result_archiver(value) -> None:
    global _tool_result_archiver
    _tool_result_archiver = value


__all__ = [
    "ArtifactStore",
    "ContextAssembler",
    "ContextBuildBundle",
    "ContextBuildRequest",
    "EpisodicMemoryEntry",
    "EpisodicMemoryStore",
    "EvidenceLedgerEntry",
    "EvidenceLedgerStore",
    "ModeDetector",
    "SessionContextState",
    "SessionContextStateStore",
    "SessionStateUpdater",
    "StoredArtifact",
    "ToolResultArchiver",
    "get_session_state_updater",
    "get_tool_result_archiver",
    "set_session_state_updater",
    "set_tool_result_archiver",
]
