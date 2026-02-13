"""
Main entry point for the x-agent2 AI assistant system with LangChain integration.

This module orchestrates the various components of the system:
- Agent Core (planning, execution, memory)
- Tools management
- SubAgent orchestration
- API endpoints
- Heartbeat monitoring
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
from typing import Dict, Any, Optional
from datetime import datetime
import uuid
import yaml
from pydantic import BaseModel
from enum import Enum
from croniter import croniter
from datetime import datetime, timedelta
import threading
import time

# Import our core modules
from src.agent_core.planner.planner import TaskPlanner, LangChainPlanner
from src.agent_core.llm_engine.service import LLMEngineService, LLMConfig
from src.agent_core.tools_manager import ToolsManager
from src.agent_core.tools.execution_service import ToolExecutionService
from src.agent_core.security.tool_security import ToolSecurityValidator
from src.agent_core.llm_engine.tool_integration import ToolIntegrationService
from src.agent_core.config.config_service import get_config

# Create FastAPI application
app = FastAPI(
    title="x-agent2 AI Assistant System",
    description="AI assistant with LangChain integration for agent orchestration, tool management, and task planning",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize core services
# First try to load from app-config.yaml
import yaml
import os

config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "app-config.yaml")
primary_model = "qwen-max"  # default fallback
fallback_model = "qwen-plus"  # default fallback

if os.path.exists(config_path):
    with open(config_path, 'r', encoding='utf-8') as f:
        app_config_data = yaml.safe_load(f)
        primary_model = app_config_data.get('models', {}).get('primary', 'qwen-max')
        fallback_model = app_config_data.get('models', {}).get('fallback', 'qwen-plus')

llm_config = LLMConfig(
    primary_model=primary_model,
    fallback_model=fallback_model,
    temperature=0.7,  # default
    max_tokens=1024   # default
)
llm_service = LLMEngineService(config=llm_config)
tool_manager = ToolsManager()
security_validator = ToolSecurityValidator()
tool_integration_service = ToolIntegrationService(llm_service)


# Data structures for scheduled tasks
class TaskType(str, Enum):
    HEALTH_CHECK = "health_check"
    DATA_CLEANUP = "data_cleanup"
    REPORT_GENERATION = "report_generation"
    BACKUP = "backup"
    NOTIFICATION = "notification"


class ScheduledTaskStatus(str, Enum):
    CREATED = "created"
    PLANNED = "planned"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ScheduledTask(BaseModel):
    id: str = str(uuid.uuid4())
    name: str
    description: str
    schedule: str  # Cron expression
    task_type: TaskType
    enabled: bool = True
    created_at: str = datetime.utcnow().isoformat()
    updated_at: str = datetime.utcnow().isoformat()
    last_run_at: Optional[str] = None
    last_run_status: Optional[str] = None
    next_run_at: Optional[str] = None


# In-memory storage for scheduled tasks
scheduled_tasks_db: Dict[str, ScheduledTask] = {}

# Background scheduler thread
scheduler_running = True


def calculate_next_run(schedule: str) -> str:
    """Calculate the next run time based on the cron schedule."""
    try:
        cron = croniter(schedule, datetime.now())
        next_time = cron.get_next(datetime)
        return next_time.isoformat()
    except Exception:
        # If cron expression is invalid, return None
        return None


def task_scheduler():
    """Background thread to execute scheduled tasks."""
    global scheduler_running
    while scheduler_running:
        current_time = datetime.now()

        for task_id, task in scheduled_tasks_db.items():
            if task.enabled and task.next_run_at:
                next_run = datetime.fromisoformat(task.next_run_at.replace('Z', '+00:00'))

                # Check if it's time to run this task
                if current_time >= next_run:
                    print(f"Executing scheduled task: {task.name}")

                    # Update task status to in_progress
                    task.last_run_at = current_time.isoformat()
                    task.updated_at = current_time.isoformat()

                    # Execute the task - for now, just simulate execution
                    try:
                        # This is where the actual task execution would happen
                        # For demo purposes, we'll just update the status
                        task.last_run_status = "completed"
                        task.next_run_at = calculate_next_run(task.schedule)
                    except Exception as e:
                        task.last_run_status = "failed"
                        task.next_run_at = calculate_next_run(task.schedule)

                    scheduled_tasks_db[task_id] = task

        # Sleep for 60 seconds before checking again
        time.sleep(60)


# Start the scheduler in a background thread
scheduler_thread = threading.Thread(target=task_scheduler, daemon=True)
scheduler_thread.start()


@app.get("/")
async def root():
    """Root endpoint for the API."""
    return {
        "message": "Welcome to x-agent2 AI Assistant System",
        "version": "1.0.0",
        "features": [
            "AI-powered conversations",
            "Tool integration",
            "Task planning",
            "SubAgent orchestration",
            "Memory management"
        ]
    }


@app.get("/api/v1/scheduled-tasks/")
async def get_scheduled_tasks():
    """Get all scheduled tasks."""
    tasks = list(scheduled_tasks_db.values())
    # Convert to dictionary format and return
    return [task.dict() for task in tasks]


@app.post("/api/v1/scheduled-tasks/")
async def create_scheduled_task(task: ScheduledTask):
    """Create a new scheduled task."""
    # Calculate the next run time
    next_run = calculate_next_run(task.schedule)
    task.next_run_at = next_run

    # Store the task
    scheduled_tasks_db[task.id] = task

    return task


@app.put("/api/v1/scheduled-tasks/{task_id}")
async def update_scheduled_task(task_id: str, updated_task: ScheduledTask):
    """Update an existing scheduled task."""
    if task_id not in scheduled_tasks_db:
        raise HTTPException(status_code=404, detail="Task not found")

    # Calculate the next run time
    next_run = calculate_next_run(updated_task.schedule)
    updated_task.next_run_at = next_run
    updated_task.updated_at = datetime.utcnow().isoformat()

    scheduled_tasks_db[task_id] = updated_task
    return updated_task


@app.delete("/api/v1/scheduled-tasks/{task_id}")
async def delete_scheduled_task(task_id: str):
    """Delete a scheduled task."""
    if task_id not in scheduled_tasks_db:
        raise HTTPException(status_code=404, detail="Task not found")

    del scheduled_tasks_db[task_id]
    return {"message": "Task deleted successfully"}


@app.put("/api/v1/scheduled-tasks/{task_id}/enable")
async def enable_scheduled_task(task_id: str):
    """Enable a scheduled task."""
    if task_id not in scheduled_tasks_db:
        raise HTTPException(status_code=404, detail="Task not found")

    task = scheduled_tasks_db[task_id]
    task.enabled = True
    task.updated_at = datetime.utcnow().isoformat()

    # Recalculate next run if it doesn't exist
    if not task.next_run_at:
        task.next_run_at = calculate_next_run(task.schedule)

    scheduled_tasks_db[task_id] = task
    return {"message": "Task enabled successfully"}


@app.put("/api/v1/scheduled-tasks/{task_id}/disable")
async def disable_scheduled_task(task_id: str):
    """Disable a scheduled task."""
    if task_id not in scheduled_tasks_db:
        raise HTTPException(status_code=404, detail="Task not found")

    task = scheduled_tasks_db[task_id]
    task.enabled = False
    task.updated_at = datetime.utcnow().isoformat()
    scheduled_tasks_db[task_id] = task
    return {"message": "Task disabled successfully"}


@app.post("/api/v1/scheduled-tasks/{task_id}/trigger")
async def trigger_scheduled_task(task_id: str):
    """Manually trigger a scheduled task."""
    if task_id not in scheduled_tasks_db:
        raise HTTPException(status_code=404, detail="Task not found")

    task = scheduled_tasks_db[task_id]
    current_time = datetime.utcnow()

    # Update task status to in_progress
    task.last_run_at = current_time.isoformat()
    task.updated_at = current_time.isoformat()

    # Execute the task - for now, just simulate execution
    try:
        # This is where the actual task execution would happen
        # For demo purposes, we'll just update the status
        task.last_run_status = "completed"
        task.next_run_at = calculate_next_run(task.schedule)
    except Exception as e:
        task.last_run_status = "failed"
        task.next_run_at = calculate_next_run(task.schedule)

    scheduled_tasks_db[task_id] = task
    return {"message": "Task triggered successfully"}


@app.post("/api/v1/chat")
async def chat(request: Dict[str, Any]):
    """
    Initiate or continue a conversation with the AI assistant.
    Uses direct LLM service to avoid tool integration issues.
    """
    message = request.get("message", "")
    session_id = request.get("session_id", str(uuid.uuid4()))
    context = request.get("context", {})

    # Use direct LLM service to avoid any tool integration issues
    response = llm_service.generate_response(message, context.get("user_preferences", ""))

    return {
        "response": response,
        "session_id": session_id,
        "timestamp": datetime.utcnow().isoformat(),
        "usage": {
            "input_tokens": len(message.split()),
            "output_tokens": len(response.split()),
            "total_tokens": len(message.split()) + len(response.split())
        },
        "metadata": {
            "processing_time_ms": 1250,  # In real implementation, measure actual time
            "model_used": llm_config.primary_model,
            "langchain_trace_id": "optional_trace_id"  # In real implementation, use actual trace ID
        }
    }

@app.post("/api/v1/tools/execute")
async def execute_tool(request: Dict[str, Any]):
    """Execute a specific tool with provided parameters."""
    tool_name = request.get("tool_name", "")
    parameters = request.get("parameters", {})
    session_id = request.get("session_id", str(uuid.uuid4()))

    # Validate the tool parameters
    validation_result = security_validator.validate_tool_parameters(tool_name, parameters)
    if not validation_result["valid"]:
        raise HTTPException(status_code=400, detail=validation_result["message"])

    # Execute the tool using the tools manager
    result = tool_manager.execute_tool(tool_name, **parameters)

    return {
        "result": result,
        "status": "success",  # In real implementation, return actual status
        "execution_time_ms": 150,  # In real implementation, measure actual time
        "metadata": {
            "tool_used": tool_name,
            "parameters_used": parameters
        },
        "langchain_tool_call_id": "optional_tool_call_id"  # In real implementation, use actual ID
    }

@app.post("/api/v1/agents/plan")
async def plan_tasks(request: Dict[str, Any]):
    """Generate a plan for a complex task using LangChain's planning capabilities."""
    goal = request.get("goal", "")
    context = request.get("context", "")

    # Initialize the LangChain planner
    langchain_planner = LangChainPlanner()

    # For this simplified version, we'll use a basic planner instead of the full DB version
    from pydantic import BaseModel
    from enum import Enum

    class TaskType(str, Enum):
        RESEARCH = "research"
        TOOL = "tool"
        AGENT = "agent"
        MCP = "mcp"
        HUMAN_CONFIRM = "human_confirm"

    class Task(BaseModel):
        step: int
        description: str
        task_type: TaskType
        tool_name: Optional[str] = None
        agent_role: Optional[str] = None
        estimated_duration: int = 30

    class Plan(BaseModel):
        goal: str
        tasks: list[Task]

    # Create a simple plan for demonstration
    sample_tasks = [
        Task(step=1, description=f"Analyze the goal: {goal}", task_type=TaskType.RESEARCH),
        Task(step=2, description="Gather necessary information", task_type=TaskType.TOOL, tool_name="web-search"),
        Task(step=3, description="Process the gathered information", task_type=TaskType.AGENT, agent_role="researcher"),
    ]

    plan = Plan(goal=goal, tasks=sample_tasks)

    return {
        "plan": [
            {
                "step": task.step,
                "description": task.description,
                "tool_needed": task.tool_name,
                "agent_needed": task.agent_role,
                "estimated_duration": task.estimated_duration
            }
            for task in plan.tasks
        ],
        "status": "planned",
        "langchain_plan_id": str(uuid.uuid4())  # In real implementation, use actual plan ID
    }

@app.post("/api/v1/agents/run")
async def run_agent(request: Dict[str, Any]):
    """Execute an agent with a specific task using LangChain agent execution."""
    agent_role = request.get("agent_role", "")
    task = request.get("task", "")
    context = request.get("context", "")

    # In a real implementation, run the specific agent
    # For now, return a simulated response
    result = tool_integration_service.process_with_tools(task, context)

    return {
        "result": result,
        "status": "completed",
        "execution_details": {
            "steps_executed": 1,
            "tools_used": ["simulated_tool"],
            "duration_ms": 1200
        },
        "langchain_agent_run_id": str(uuid.uuid4())  # In real implementation, use actual ID
    }

if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    uvicorn.run(app, host="0.0.0.0", port=port)