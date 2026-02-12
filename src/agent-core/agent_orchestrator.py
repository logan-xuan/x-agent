"""LangChain-based agent orchestrator for the x-agent2 system."""

from typing import Dict, List, Any, Optional
from langchain_core.agents import AgentFinish
from langchain_core.tools import BaseTool
from langchain_core.callbacks import CallbackManagerForToolRun
from langchain.agents import AgentExecutor, create_openai_functions_agent, create_structured_chat_agent
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from .tools_manager import ToolsManager
from .planner.planner import Task, TaskType
import asyncio


class SubAgent:
    """Represents a specialized sub-agent for specific tasks."""
    
    def __init__(self, role: str, llm_model: str = "claude-3-5-sonnet-20241022", tools: List[BaseTool] = None):
        self.role = role
        self.tools = tools or []
        
        # Initialize the appropriate LLM based on model name
        if "claude" in llm_model.lower():
            self.llm = ChatAnthropic(model=llm_model)
        else:
            self.llm = ChatOpenAI(model=llm_model)
        
        # Set up a custom prompt based on the agent's role
        self.agent_prompt = self._create_role_specific_prompt()
        
        # Create the agent using LangChain
        self.agent = create_structured_chat_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=self.agent_prompt
        )
        
        # Create the agent executor
        self.executor = AgentExecutor.from_agent_and_tools(
            agent=self.agent,
            tools=self.tools,
            verbose=True,
            handle_parsing_errors=True
        )
    
    def _create_role_specific_prompt(self) -> ChatPromptTemplate:
        """Create a prompt specific to the agent's role."""
        if self.role == "coder":
            system_message = (
                "You are a professional code writer. Write clean, well-documented code in response to requests. "
                "Focus on implementing the requested functionality efficiently. "
                "When asked to implement a solution, provide complete code with error handling."
            )
        elif self.role == "researcher":
            system_message = (
                "You are a meticulous researcher. Gather accurate information from reliable sources. "
                "Summarize complex topics clearly and cite sources when possible. "
                "Verify facts before providing answers."
            )
        elif self.role == "reviewer":
            system_message = (
                "You are a critical reviewer. Examine code, documents, or other content for errors, "
                "best practice violations, and areas of improvement. Be thorough but constructive in your feedback."
            )
        else:
            system_message = f"You are an assistant specializing in {self.role}. Provide expert assistance in this domain."
        
        return ChatPromptTemplate.from_messages([
            ("system", system_message),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])
    
    def run(self, task_description: str) -> str:
        """Execute the agent with a specific task."""
        try:
            result = self.executor.invoke({"input": task_description})
            return result.get("output", "No output generated")
        except Exception as e:
            return f"Error executing agent {self.role}: {str(e)}"


class SubAgentOrchestrator:
    """Orchestrates multiple sub-agents for complex task execution."""
    
    def __init__(self, llm_model: str = "claude-3-5-sonnet-20241022"):
        self.llm_model = llm_model
        self.tools_manager = ToolsManager()
        self.agents: Dict[str, SubAgent] = {}
        self._initialize_agents()
    
    def _initialize_agents(self):
        """Initialize the standard sub-agents."""
        available_tools = self.tools_manager.get_available_tools()
        
        self.agents["coder"] = SubAgent(
            role="coder",
            llm_model=self.llm_model,
            tools=available_tools
        )
        
        self.agents["researcher"] = SubAgent(
            role="researcher",
            llm_model=self.llm_model,
            tools=available_tools
        )
        
        self.agents["reviewer"] = SubAgent(
            role="reviewer",
            llm_model=self.llm_model,
            tools=available_tools
        )
    
    def get_agent(self, role: str) -> Optional[SubAgent]:
        """Get a sub-agent by role."""
        return self.agents.get(role)
    
    def execute_task(self, task: Task) -> str:
        """Execute a task using the appropriate mechanism."""
        if task.task_type == TaskType.AGENT:
            # Use a specialized sub-agent
            agent = self.get_agent(task.agent_role or "coder")
            if agent:
                return agent.run(task.description)
            else:
                return f"No agent found for role: {task.agent_role}"
        elif task.task_type == TaskType.TOOL:
            # Use a tool directly
            if task.tool_name:
                tool_result = self.tools_manager.execute_tool(task.tool_name)
                return tool_result
            else:
                return "No tool specified for task"
        else:
            # Default execution with main LLM
            if "claude" in self.llm_model.lower():
                llm = ChatAnthropic(model=self.llm_model)
            else:
                llm = ChatOpenAI(model=self.llm_model)
            
            try:
                response = llm.invoke(task.description)
                return response.content
            except Exception as e:
                return f"Error executing task: {str(e)}"
    
    def run_parallel_tasks(self, tasks: List[Task]) -> Dict[int, str]:
        """Execute multiple tasks in parallel."""
        results = {}
        
        # In a real implementation, this would use proper async execution
        # For simplicity, we'll execute sequentially here
        for task in tasks:
            results[task.step] = self.execute_task(task)
        
        return results
