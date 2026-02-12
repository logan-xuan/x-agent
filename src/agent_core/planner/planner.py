"""LangChain-based task planner for the x-agent2 system."""

from typing import List, Dict, Any, Optional
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
from enum import Enum
import json
from sqlalchemy.orm import Session


class TaskType(str, Enum):
    """Types of tasks that can be planned."""
    RESEARCH = "research"
    TOOL = "tool"
    AGENT = "agent"
    MCP = "mcp"
    HUMAN_CONFIRM = "human_confirm"


class Task(BaseModel):
    """Represents a single task in a plan."""
    step: int = Field(description="The step number in the plan")
    description: str = Field(description="Description of the task")
    task_type: TaskType = Field(description="Type of the task")
    tool_name: Optional[str] = Field(default=None, description="Name of tool to use if task_type is 'tool'")
    agent_role: Optional[str] = Field(default=None, description="Role of agent to use if task_type is 'agent'")
    estimated_duration: int = Field(default=30, description="Estimated duration in seconds")


class Plan(BaseModel):
    """Represents a complete plan with multiple tasks."""
    goal: str = Field(description="The overall goal being planned")
    tasks: List[Task] = Field(description="List of tasks to accomplish the goal")


class LangChainPlanner:
    """LangChain-based task planner that decomposes complex goals into executable tasks."""

    def __init__(self, llm_model: str = "claude-3-5-sonnet-20241022"):
        self.llm_model = llm_model
        # Initialize the appropriate LLM based on model name
        if "claude" in llm_model.lower():
            self.llm = ChatAnthropic(model=llm_model)
        else:
            self.llm = ChatOpenAI(model=llm_model)

    def plan(self, goal: str, context: str, available_tools: List[BaseTool] = None) -> Plan:
        """
        Generate a plan for accomplishing a goal using LangChain.

        Args:
            goal: The goal to plan for
            context: Current context to consider
            available_tools: List of tools available to the system

        Returns:
            Plan: A plan with multiple tasks
        """
        # Create a prompt template for task planning
        prompt = PromptTemplate.from_template("""
        Please decompose the following goal into a series of executable tasks. Requirements:
        - Each task must be clear and verifiable
        - Prioritize using tools or agents to complete tasks
        - Output in JSON format following the defined schema

        Available tools: {available_tools_str}

        Example:
        Goal: Write an article about AI ethics
        → [
          {{"step": 1, "description": "Research AI ethics principles", "task_type": "research", "tool_name": "web-search"}},
          {{"step": 2, "description": "Search for Asilomar AI Principles", "task_type": "tool", "tool_name": "web-search"}},
          {{"step": 3, "description": "Write draft article", "task_type": "agent", "agent_role": "writer"}}
        ]

        Current goal: {goal}
        Context summary: {context}

        Plan:
        """)

        # Prepare available tools string
        if available_tools:
            available_tools_str = ", ".join([tool.name for tool in available_tools])
        else:
            available_tools_str = "None available"

        # Create the chain
        chain = prompt | self.llm | PydanticOutputParser(pydantic_object=Plan)

        # Execute the chain
        result = chain.invoke({
            "goal": goal,
            "context": context[:500],  # Limit context length
            "available_tools_str": available_tools_str
        })

        return result

    def refine_plan(self, plan: Plan, feedback: str) -> Plan:
        """
        Refine an existing plan based on feedback.

        Args:
            plan: The original plan
            feedback: Feedback to incorporate

        Returns:
            Plan: A refined plan
        """
        prompt = PromptTemplate.from_template("""
        Refine the following plan based on feedback:

        Original plan: {original_plan}
        Feedback: {feedback}

        Please return an improved plan that addresses the feedback while maintaining the goal.

        Refined plan:
        """)

        chain = prompt | self.llm | PydanticOutputParser(pydantic_object=Plan)
        result = chain.invoke({
            "original_plan": plan.model_dump_json(),
            "feedback": feedback
        })

        return result


class TaskPlanner:
    """
    Plans complex user requests by breaking them down into manageable subtasks.
    Uses LangChain agents to determine the best approach for each request.
    """

    def __init__(self, llm_model: str = "claude-3-5-sonnet-20241022"):
        self.langchain_planner = LangChainPlanner(llm_model)

    def plan_tasks(self, user_request: str, context: Optional[str] = None, available_tools: List[BaseTool] = None) -> Plan:
        """
        Plan tasks for a given user request.

        Args:
            user_request: The user's request to be planned
            context: Additional context for the planning
            available_tools: Available tools to consider in planning

        Returns:
            Plan: A plan with tasks to achieve the user's goal
        """
        context = context or "No additional context provided."
        return self.langchain_planner.plan(user_request, context, available_tools)

    def execute_plan(self, plan: Plan, db_session: Session):
        """
        Execute a planned set of tasks.

        Args:
            plan: The plan to execute
            db_session: Database session for tracking task execution
        """
        # In a full implementation, this would iterate through the plan and execute each task
        # For now, we just return the plan as is
        pass
