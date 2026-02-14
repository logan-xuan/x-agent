# X-Agent Backend

Personal AI Agent with modular architecture - Backend Service

## Features

- **High-Cohesion Configuration**: Unified YAML configuration with hot-reload support
- **Vendor-Agnostic LLM**: Support multiple providers (OpenAI, Bailian, etc.) with primary/backup failover
- **Modular Architecture**: Clean separation of concerns (API → Core → Services → Models)
- **Structured Logging**: JSON format with request tracing
- **Async Database**: SQLAlchemy 2.0 with aiosqlite for SQLite

## Quick Start

1. Install dependencies:
```bash
pip install -e ".[dev]"
```

2. Configure:
```bash
cp x-agent.yaml.example x-agent.yaml
# Edit x-agent.yaml with your API keys
```

3. Run:
```bash
python -m src.main
```

## Project Structure

```
src/
├── config/          # Configuration management
├── models/          # SQLAlchemy data models
├── services/        # Business services
├── utils/           # Utilities
└── main.py          # Application entry
```

## Configuration

See `x-agent.yaml.example` for configuration options.
