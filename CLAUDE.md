# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

X-Agent is a personal AI agent with modular architecture and long-term memory system. It consists of:
- **Backend**: FastAPI-based API service with WebSocket support
- **Frontend**: React + TypeScript web interface
- **Memory System**: Long-term memory with automatic recording and context building

## Constitutional Principles

The X-Agent project follows strict constitutional principles that must be adhered to:

### Core Principles
1. **Code Quality First**: All code must pass static analysis with zero warnings, functions must have type annotations, and maintain low complexity (max 15 decision points)
2. **Test-Driven Development**: All functionality must have tests first (80%+ coverage, 90%+ for core modules), with regression tests for each bug fix
3. **Separation of Concerns**: Clear layer separation (presentation, gateway, core, tools, data) with no circular dependencies
4. **Debuggability by Design**: Structured logging (JSON format), traceable context IDs, and comprehensive error information
5. **UX Consistency**: Unified response formats across all channels, consistent error messages with remediation suggestions
6. **Performance First**: LLM streaming with <500ms first-byte time, vector search <200ms, async I/O operations
7. **Composition Over Inheritance**: Maximum 2-level inheritance, plugin-based extensions
8. **Stable Abstractions**: Interfaces don't depend on implementations, stable contracts for core components
9. **YAGNI**: No speculative functionality, implement only confirmed user needs

### Development Standards
- **Languages**: TypeScript (strict mode) + Python 3.11+
- **Naming**: camelCase (TS) / snake_case (Python), PascalCase for classes
- **Security**: Input validation, command execution whitelisting, encrypted sensitive config storage

## Architecture

### Core Components
- **Agent Core** (`src/core/agent.py`): Central orchestration for chat processing, streaming, and memory recording
- **Memory System** (`src/memory/`): Automatic memory recording, daily logs, and context building
- **LLM Router** (`src/services/llm/router.py`): Multi-provider support with failover capabilities
- **Configuration Manager** (`src/config/`): YAML-based configuration with hot-reload
- **Context Management** (`src/core/context.py`): Distributed tracing with structured logging

### Memory System Architecture
The memory system implements a hierarchical context loading approach:
- **SPIRIT.md**: Defines AI's role, personality, values and behavior rules
- **OWNER.md**: Contains user information, preferences, goals and habits
- **TOOLS.md**: Defines available tools and capabilities for the AI
- **Daily Logs** (`workspace/memory/YYYY-MM-DD.md`): Daily important conversations/events
- **MEMORY.md**: Long-term memory summaries transcending daily logs
- **Vector Storage**: Semantic search using sqlite-vss with local embeddings

### Key Patterns
- **Trace Context**: Use `AgentContext` with `context_manager` for distributed tracing
- **Structured Logging**: All logs include trace_id automatically via `get_logger()` and `log_execution` decorator
- **Async Processing**: Heavy use of async/await for concurrent operations
- **Dependency Injection**: Core services are instantiated and passed to constructors
- **Memory Dual-Writing**: Changes to .md files automatically sync to vector store with watchdog file monitoring

## File Locations

### Backend (`/backend/src/`)
- `api/`: API route definitions (REST and WebSocket)
- `config/`: Configuration management with hot-reload capability
- `core/`: Core agent logic and session management
- `memory/`: Memory system (persistence, context building, vector storage, file watching)
- `models/`: SQLAlchemy data models
- `services/`: Business logic services
- `utils/`: Common utilities (logging, helpers)

### Frontend (`/frontend/src/`)
- `components/`: React UI components
- `hooks/`: Custom React hooks
- `services/`: API service clients
- `types/`: TypeScript type definitions

### Workspace (`/workspace/`)
- `SPIRIT.md`: AI personality definition
- `OWNER.md`: User profile and preferences
- `MEMORY.md`: Long-term memory summary
- `TOOLS.md`: Tool definitions
- `memory/`: Daily log files in YYYY-MM-DD.md format

## Common Commands

### Development
```bash
# Install dependencies
cd backend && pip install -e ".[dev]"

# Start all services
./start.sh

# Start services separately
./start-backend.sh  # Backend on http://localhost:8000
./start-frontend.sh # Frontend on http://localhost:5173

# Run backend standalone
python -m src.main
```

### Testing
```bash
# Backend tests
cd backend
pytest  # Run all tests
pytest tests/unit/  # Run unit tests
pytest tests/integration/  # Run integration tests
pytest --cov=x_agent  # Run with coverage

# Frontend development
cd frontend
npm run dev  # Start dev server
npm run lint  # Lint code
npm run format  # Format code
```

### Configuration
```bash
# Set up configuration
cd backend
cp x-agent.yaml.example x-agent.yaml
# Edit x-agent.yaml with your LLM provider API keys
```

## Key APIs

### Backend Endpoints
- Health Check: `GET /api/v1/health`
- Chat API: `POST /api/v1/chat`
- WebSocket: `ws://localhost:8000/ws/chat/{session_id}`
- Configuration: `GET /api/v1/config/status`
- Memory: `GET/POST /api/v1/memory`
- Developer Mode: `GET /api/v1/dev/prompt-logs`
- Traces: `GET /api/v1/trace`

### Frontend Proxies
The frontend automatically proxies `/api` and `/ws` requests to the backend server.

## Memory System

### Automatic Recording
- Important conversations are automatically detected and recorded based on keywords like "decide", "choose", "important", etc.
- Daily log files in `workspace/memory/` with frontmatter containing metadata (UUID, timestamps, tags)
- Context-aware responses using stored memories

### Memory File Structure
-  AGENTS.md : The behavioral norms general guidance process document, which encompasses the entire workflow of the agent.
- `SPIRIT.md`: Defines agent's personality and behavior
- `SPIRIT.md`: Defines agent's personality and behavior
- `SPIRIT.md`: Defines agent's personality and behavior
- `OWNER.md`: Contains owner information and preferences
- `TOOLS.md`: Defines available tools and capabilities
- Daily memory files: `YYYY-MM-DD.md` with timestamped entries
- `MEMORY.md`: Long-term persistent memory summaries

### File Format
Memory files use YAML frontmatter + Markdown content:
```markdown
---
id: 550e8400-e29b-41d4-a716-446655440000
type: decision
created_at: 2026-02-14T10:30:00
updated_at: 2026-02-14T10:30:00
tags: [decision, project]
---

# User decided to use React as the frontend framework

User confirmed choosing React over Vue based on team familiarity with React ecosystem.
```

## Tracing & Observability

### Trace Instrumentation
All new modules must include trace instrumentation. Use:

```python
from src.utils.logger import get_logger, log_execution

logger = get_logger(__name__)

@log_execution
async def my_function():
    # Automatically logs entry/exit with trace context
    pass

# Log with trace context
logger.info("Operation completed", extra={'event': 'operation_completed'})
```

### Trace Categories
- `api`: Routes and API endpoints (blue nodes)
- `middleware`: Middleware components (cyan nodes)
- `agent`: Core agent logic (purple nodes)
- `llm`: LLM interactions (amber nodes)
- `memory`: Memory operations (green nodes)
- `service`: Business services (slate nodes)

## Development Guidelines

### Logging Best Practices
- Use `get_logger(__name__)` to ensure proper module path in traces
- Include `event` field to identify operation type
- Use `extra` parameter for structured, searchable data
- Truncate large data to avoid logging full request/response bodies
- Use appropriate log levels (INFO for operations, DEBUG for details, ERROR for failures)

### Configuration
- All configuration is managed in `x-agent.yaml`
- Supports hot-reload without restart
- Includes circuit breaker for LLM failover
- Vendor-agnostic LLM support (OpenAI, Bailian, etc.)

### Error Handling
- Use `ErrorHandlerMiddleware` for consistent error responses
- Implement proper exception handling in services
- Log errors with trace context for debugging

### Memory System Compliance
When modifying memory-related functionality, ensure compliance with constitutional principles:
- Performance: Vector searches must complete in under 200ms
- Debuggability: All memory operations must be traceable with structured logs
- Composition: Memory components must be pluggable and configurable
- Separation of Concerns: Memory persistence separated from business logic