#!/usr/bin/env python3
"""Update backend/x-agent.yaml voice.public_base_url in place."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update voice.public_base_url in backend/x-agent.yaml")
    parser.add_argument("public_base_url", help="New public base URL for audio assets")
    parser.add_argument(
        "--config",
        default="backend/x-agent.yaml",
        help="Path to x-agent.yaml",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path = Path(args.config).resolve()
    if not config_path.exists():
        raise SystemExit(f"Config file not found: {config_path}")

    with config_path.open(encoding="utf-8") as fh:
        yaml_data = yaml.safe_load(fh) or {}

    voice = dict(yaml_data.get("voice", {}) or {})
    voice["public_base_url"] = args.public_base_url
    yaml_data["voice"] = voice

    with config_path.open("w", encoding="utf-8") as fh:
        yaml.dump(yaml_data, fh, allow_unicode=True, default_flow_style=False, sort_keys=False)

    print(args.public_base_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
