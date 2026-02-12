"""Main entry point for the x-agent2 system with LangChain integration."""

from .agent-core.planner.planner import LangChainPlanner, Task, Plan
from .agent-core.agent_orchestrator import SubAgentOrchestrator
from .agent-core.tools_manager import ToolsManager
from langchain_core.callbacks import CallbackManager, BaseCallbackHandler
from typing import Dict, Any, List


class LangChainAgentCore:
    """Main class that integrates all LangChain components for the AI agent system."""
    
    def __init__(self, llm_model: str = "claude-3-5-sonnet-20241022"):
        self.planner = LangChainPlanner(llm_model=llm_model)
        self.orchestrator = SubAgentOrchestrator(llm_model=llm_model)
        self.tools_manager = ToolsManager()
        self.llm_model = llm_model
    
    def process_user_request(self, user_input: str, session_id: str = None) -> str:
        """Process a user request using the full LangChain-based pipeline."""
        # 1. Plan the task based on user input
        context_summary = self._get_context_summary(session_id) if session_id else ""
        available_tools = self.tools_manager.get_available_tools()
        
        plan = self.planner.plan(
            goal=user_input,
            context=context_summary,
            available_tools=available_tools
        )
        
        # 2. Execute the plan using the orchestrator
        results = self.orchestrator.run_parallel_tasks(plan.tasks)
        
        # 3. Aggregate results
        final_result = self._aggregate_results(results, plan)
        
        # 4. Store results in memory if session exists
        if session_id:
            self._store_in_memory(session_id, user_input, final_result)
        
        return final_result
    
    def _get_context_summary(self, session_id: str) -> str:
        """Get a summary of the context for the given session."""
        # In a real implementation, this would fetch from memory system
        return f"Session {session_id}: Context summary would be retrieved here"
    
    def _aggregate_results(self, results: Dict[int, str], plan: Plan) -> str:
        """Aggregate results from all tasks in the plan."""
        aggregated = f"Original goal: {plan.goal}\n\n"
        for task in plan.tasks:
            result = results.get(task.step, "No result")
            aggregated += f"Step {task.step}: {task.description}\nResult: {result}\n\n"
        
        return aggregated
    
    def _store_in_memory(self, session_id: str, input_text: str, result: str):
        """Store the conversation in the memory system."""
        # In a real implementation, this would store in the memory system
        print(f"Storing in session {session_id}: {input_text} -> {result}")
    
    def run_single_task(self, task: Task) -> str:
        """Run a single task using the appropriate component."""
        return self.orchestrator.execute_task(task)


# Example usage
def main():
    """Example usage of the LangChain-integrated agent core."""
    agent_core = LangChainAgentCore(llm_model="claude-3-5-sonnet-20241022")
    
    # Example user request
    user_request = "Help me write a Python function that analyzes a CSV file and calculates the average of a specified column."
    
    print(f"Processing request: {user_request}\n")
    result = agent_core.process_user_request(user_request, session_id="session-123")
    
    print("Final result:")
    print(result)


if __name__ == "__main__":
    main()
