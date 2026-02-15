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

The backend server will start on **http://localhost:8000** (as configured in `x-agent.yaml`).

## Server Configuration

The server configuration is defined in `x-agent.yaml`:

- **Backend Port**: 8000 (configured in `server.port`)
- **Frontend Port**: 5173 (for CORS configuration)
- **Host**: 0.0.0.0 (accessible from all network interfaces)

API endpoints are available at:
- Health Check: http://localhost:8000/api/v1/health
- Chat API: http://localhost:8000/api/v1/chat
- WebSocket: http://localhost:8000/ws/chat
- Developer Mode: http://localhost:8000/api/v1/dev/prompt-logs

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
