# X-Agent

Personal AI Agent with modular architecture and long-term memory system.

## Architecture

- **Backend**: FastAPI-based API service with WebSocket support
- **Frontend**: React + TypeScript web interface
- **Memory System**: Long-term memory with automatic recording and context building

## Quick Start

### Start All Services

```bash
./start.sh
```

This will start both backend and frontend services with the correct ports.

### Start Services Separately

Backend:
```bash
./start-backend.sh
```

Frontend:
```bash
./start-frontend.sh
```

## Port Configuration

**All ports are configured in `backend/x-agent.yaml`:**

- **Backend API**: http://localhost:8000 (configured in `server.port`)
- **Frontend**: http://localhost:5173 (configured in vite.config.ts)

### API Endpoints

- Health Check: http://localhost:8000/api/v1/health
- Chat API: http://localhost:8000/api/v1/chat
- WebSocket: http://localhost:8000/ws/chat
- Configuration: http://localhost:8000/api/v1/config/status
- Memory: http://localhost:8000/api/v1/memory
- Developer Mode: http://localhost:8000/api/v1/dev/prompt-logs

### Frontend Proxy

The frontend automatically proxies `/api` and `/ws` requests to the backend server (configured in `frontend/vite.config.ts`).

## Configuration

1. Copy the example configuration:
```bash
cd backend
cp x-agent.yaml.example x-agent.yaml
```

2. Edit `x-agent.yaml` with your LLM provider API keys:
```yaml
models:
- api_key: your-api-key-here
  base_url: https://api.openai.com/v1
  model_id: gpt-4
  name: primary
  provider: openai
```

3. Server configuration in `x-agent.yaml`:
```yaml
server:
  host: 0.0.0.0
  port: 8000        # Backend port
  cors_origins:
    - http://localhost:5173    # Frontend port
    - http://127.0.0.1:5173
```

## Project Structure

```
.
├── backend/              # FastAPI backend
│   ├── src/             # Source code
│   │   ├── api/         # API routes
│   │   ├── config/      # Configuration management
│   │   ├── core/        # Core agent logic
│   │   ├── memory/      # Memory system
│   │   ├── models/      # Data models
│   │   ├── services/    # Business services
│   │   └── main.py      # Application entry
│   └── x-agent.yaml     # Configuration file
├── frontend/            # React frontend
│   ├── src/            # Source code
│   │   ├── components/ # React components
│   │   ├── hooks/      # Custom hooks
│   │   ├── services/   # API services
│   │   └── types/      # TypeScript types
│   └── vite.config.ts  # Vite configuration (port: 5173)
├── workspace/          # User workspace
│   └── memory/         # Memory markdown files
└── start.sh           # Startup script

```

## Features

### Memory System
- Automatic memory recording from conversations
- Daily log files in `workspace/memory/`
- Natural language memory search
- Context-aware responses

### Developer Mode
- View LLM interaction logs
- Test prompts directly with primary LLM
- Monitor token usage and latency

### Trace Viewer
- Visual request flow tracing with React Flow
- LLM-powered trace analysis for performance and error insights
- Support for multiple detail levels (high/medium/detailed)
- Access at: http://localhost:5173 → Dev Tools → Trace Viewer

### Configuration Hot-Reload
- Modify `x-agent.yaml` without restarting
- Dynamic provider switching
- Circuit breaker for failover

## Trace Instrumentation Guide

All new modules **MUST** include trace instrumentation for observability and debugging.

### Logging with Trace Context

```python
from src.utils.logger import get_logger, log_execution

logger = get_logger(__name__)

# Basic logging with automatic trace_id injection
logger.info("Operation started", extra={
    'event': 'operation_started',
    'operation_type': 'memory_search',
    'query': query[:100],  # Truncate long values
})

# Log with structured data
logger.info("Search completed", extra={
    'event': 'search_completed',
    'results_count': len(results),
    'duration_ms': elapsed_ms,
})
```

### Using the `@log_execution` Decorator

For automatic function entry/exit logging:

```python
from src.utils.logger import log_execution

@log_execution
async def process_message(message: str) -> dict:
    # Function entry, exit, and duration are logged automatically
    # Exceptions are logged with stack traces
    return {"status": "success"}
```

### Creating Context for New Operations

```python
from src.core.context import AgentContext, ContextSource, context_manager

# For request-scoped operations
async with context_manager.request(
    session_id="session-123",
    source=ContextSource.INTERNAL,
    custom_data="value"
) as ctx:
    # ctx.trace_id is automatically available in all logs
    await process_something()
```

### Node Types for Visualization

The Trace Viewer automatically categorizes log entries by module:

| Node Type | Module Keywords | Color |
|-----------|-----------------|-------|
| `api` | `api`, routes | Blue |
| `middleware` | `middleware` | Cyan |
| `agent` | `agent`, `core` | Purple |
| `llm` | `llm`, `router` | Amber |
| `memory` | `memory`, `vector_store` | Green |
| `service` | `service` | Slate |

### Log Files

- **x-agent.log**: General application logs with trace context
- **prompt-llm.log**: LLM request/response logs for detailed analysis

### Best Practices

1. **Always use `get_logger(__name__)`**: Ensures proper module path in traces
2. **Include `event` field**: Helps identify operation type in visualization
3. **Add structured data**: Use `extra` parameter for searchable fields
4. **Truncate large data**: Avoid logging full request/response bodies
5. **Use appropriate log levels**: INFO for operations, DEBUG for details, ERROR for failures

## Development

See individual README files:
- [Backend README](backend/README.md)

## Documentation

- Architecture diagrams: `arch/`
- Specifications: `specs/`
