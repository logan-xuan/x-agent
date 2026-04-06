"""Lightweight memory maintenance service used by integration tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class MemoryMaintenanceService:
    """Scan daily logs and append notable entries into MEMORY.md."""

    workspace_path: str

    async def run_maintenance(self) -> dict[str, object]:
        workspace = Path(self.workspace_path)
        memory_dir = workspace / "memory"
        memory_md = workspace / "MEMORY.md"
        processed_entries = 0
        harvested: list[str] = []

        if memory_dir.exists():
            for path in sorted(memory_dir.glob("*.md")):
                text = path.read_text(encoding="utf-8")
                for line in text.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    if "重要决策" in line or "关键偏好" in line:
                        harvested.append(f"- {line}")
                        processed_entries += 1

        if harvested:
            existing = memory_md.read_text(encoding="utf-8") if memory_md.exists() else "# 长期记忆\n\n"
            additions = "\n".join(item for item in harvested if item not in existing)
            if additions:
                if not existing.endswith("\n"):
                    existing += "\n"
                memory_md.write_text(existing + additions + "\n", encoding="utf-8")

        return {
            "success": True,
            "processed_entries": processed_entries,
            "memory_path": str(memory_md),
        }
