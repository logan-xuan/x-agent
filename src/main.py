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

# Import our core modules
from src.agent_core.planner.planner import TaskPlanner, LangChainPlanner
from src.agent_core.llm_engine.service import LLMEngineService, LLMConfig
from src.agent_core.tools_manager import ToolsManager
from src.agent_core.tools.execution_service import ToolExecutionService
from src.agent_core.security.tool_security import ToolSecurityValidator
from src.agent_core.llm_engine.tool_integration import ToolIntegrationService

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
llm_config = LLMConfig()
llm_service = LLMEngineService(config=llm_config)
tool_manager = ToolsManager()
security_validator = ToolSecurityValidator()
tool_integration_service = ToolIntegrationService(llm_service)

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

@app.post("/api/v1/chat")
async def chat(request: Dict[str, Any]):
    """
    Initiate or continue a conversation with the AI assistant.
    Utilizes LangChain agents for enhanced conversation management.
    """
    message = request.get("message", "")
    session_id = request.get("session_id", str(uuid.uuid4()))
    context = request.get("context", {})

    # Process the message using the tool integration service
    response = tool_integration_service.process_with_tools(message, context.get("user_preferences", ""))

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
    uvicorn.run(app, host="0.0.0.0", port=8000)