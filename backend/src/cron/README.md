# APScheduler 4.0 Integration for X-Agent

This module provides a complete cron scheduling system using APScheduler 4.0.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    CronScheduler (Singleton)                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │   Triggers  │  │  DataStore  │  │   AsyncScheduler    │ │
│  │  (Interval, │  │ (SQLAlchemy │  │   (APScheduler 4.0) │ │
│  │   Cron,     │  │  /Memory)   │  │                     │ │
│  │   Date...)  │  │             │  │                     │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## 分层架构规约（必须遵守）

```
┌─────────────────────────────────────────────────┐
│           调用端 (Callers)                        │
│  ┌──────────────┐    ┌────────────────────────┐  │
│  │  api/router   │    │  tools/cron/*          │  │
│  │  api/__init__ │    │  (cron_create_task,    │  │
│  │               │    │   cron_delete_task,    │  │
│  │               │    │   cron_query_tasks,    │  │
│  │               │    │   cron_execute_now,    │  │
│  │               │    │   cron_pause_task,     │  │
│  │               │    │   cron_resume_task,    │  │
│  │               │    │   cron_get_history)    │  │
│  └──────┬───────┘    └───────────┬────────────┘  │
│         │                        │                │
│         ▼                        ▼                │
│  ┌─────────────────────────────────────────────┐  │
│  │         manager.py (SchedulerManager)       │  │
│  │         ← 唯一的公共接口层 →                  │  │
│  └──────────────────┬──────────────────────────┘  │
│                     │                             │
│                     ▼                             │
│  ┌─────────────────────────────────────────────┐  │
│  │         scheduler.py (CronScheduler)        │  │
│  │         ← 底层实现，禁止外部直接依赖 →        │  │
│  └─────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

### ⛔ 禁止直接依赖 scheduler.py

**所有调用端（router、tools、外部模块）禁止直接导入或依赖 `scheduler.py` 中的 `get_scheduler` 或 `CronScheduler`。**

- ✅ 正确：`from ..manager import get_scheduler_manager`
- ❌ 错误：`from ..scheduler import get_scheduler`

### 依赖方向

| 模块 | 允许依赖 | 禁止依赖 |
|------|---------|---------|
| `api/router.py` | `manager.py`, `config.py`, `exceptions.py` | `scheduler.py` |
| `api/__init__.py` | `manager.py`, `config.py` | `scheduler.py` |
| `tools/cron/*` | `manager.py`, `exceptions.py` | `scheduler.py` |
| `manager.py` | `scheduler.py`, `config.py`, `exceptions.py` | — |
| `scheduler.py` | APScheduler, `config.py`, `exceptions.py` | — |

### 设计原因

1. **单一职责**：`scheduler.py` 负责 APScheduler 底层封装，`manager.py` 负责业务逻辑（identity 注入、路径解析、统一错误处理）
2. **接口稳定性**：`scheduler.py` 的 API 可能随 APScheduler 版本变化，`manager.py` 作为适配层屏蔽这些变化
3. **可测试性**：调用端只需 mock `SchedulerManager`，无需关心底层调度器实现
4. **一致性**：所有调用端通过同一个 manager 接口操作，确保 identity 注入、日志记录等横切关注点的一致性

## Directory Structure

```
cron/
├── __init__.py          # Module exports
├── config.py            # Configuration models (Pydantic)
├── scheduler.py         # Core scheduler wrapper
├── exceptions.py        # Custom exceptions
├── jobs/                # Job implementations
│   ├── __init__.py
│   ├── base.py          # Base job class
│   ├── heartbeat.py     # System heartbeat
│   └── cleanup.py       # Maintenance cleanup
└── api/                 # FastAPI endpoints
    ├── __init__.py
    └── router.py        # REST API routes
```

## Configuration

Add to your `x-agent.yaml`:

```yaml
cron:
  enabled: true
  timezone: "Asia/Shanghai"
  job_store_url: "sqlite:///data/cron_jobs.db"  # or null for memory
  cleanup_interval: 3600
  jobs:
    - id: "heartbeat"
      name: "System Heartbeat"
      func: "cron.jobs.heartbeat:heartbeat_task"
      trigger_type: "interval"
      trigger_args:
        minutes: 5
      enabled: true
    
    - id: "cleanup"
      name: "System Cleanup"
      func: "cron.jobs.cleanup:cleanup_task"
      trigger_type: "cron"
      trigger_args:
        hour: 3
        minute: 0
      enabled: true
```

## API Endpoints

### Schedule Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/cron/list_schedules` | List all schedules (frontend) |
| GET | `/api/v1/cron/schedules` | List all schedules (RESTful) |
| GET | `/api/v1/cron/schedules/{id}` | Get specific schedule |
| GET | `/api/v1/cron/schedule/{id}` | Get specific schedule (with trace_id) |
| POST | `/api/v1/cron/schedules` | Create schedule |
| DELETE | `/api/v1/cron/schedules/{id}` | Remove schedule |
| POST | `/api/v1/cron/schedules/{id}/pause` | Pause schedule |
| POST | `/api/v1/cron/schedules/{id}/resume` | Resume schedule |

### Task Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/cron/tasks` | List all tasks |
| GET | `/api/v1/cron/tasks/{id}` | Get specific task |
| DELETE | `/api/v1/cron/tasks/{id}` | Delete task definition |
| POST | `/api/v1/cron/tasks/{id}/run` | Run task immediately |

### Job Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/cron/jobs` | List all jobs |
| GET | `/api/v1/cron/jobs/{id}` | Get specific job |

### Scheduler Status

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/cron/status` | Get scheduler status |

## Creating Custom Jobs

```python
from cron.jobs.base import BaseJob

class MyJob(BaseJob):
    def __init__(self):
        super().__init__("my_job", "My Custom Job")
    
    async def _run(self, **kwargs):
        # Your job logic here
        return {"status": "success"}

# Register function for scheduler
async def my_job_task(**kwargs):
    job = MyJob()
    return await job.execute()
```

## Trigger Types

- `date`: Run once at specific time
- `interval`: Run at fixed intervals
- `cron`: Run on cron schedule
- `calendar`: Run on calendar intervals

## APScheduler 4.0 Features

- Async-first design (AsyncScheduler)
- Persistent storage (SQLAlchemyDataStore)
- Event-driven architecture
- Distributed support (with event broker)
- Type-safe with full mypy support
