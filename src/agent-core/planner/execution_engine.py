from typing import Dict, Any, List, Optional
from langchain_core.tools import BaseTool
from sqlalchemy.orm import Session
from ..llm_engine.service import LLMEngineService
from ...db.models.task import Task as TaskModel
from ...db.models.subagent import SubAgent
from ...db.models.subagent_execution import SubAgentExecution
from datetime import datetime
import asyncio


class TaskExecutionEngine:
    """
    Executes tasks as defined by the TaskPlanner, coordinating between
    tools, agents, and other resources to complete tasks.
    """

    def __init__(self, llm_service: LLMEngineService, db_session: Session):
        self.llm_service = llm_service
        self.db_session = db_session
        self.active_tasks = {}

    def execute_task(self, task: TaskModel) -> Dict[str, Any]:
        """
        Execute a single task and update its status.

        Args:
            task: The task to execute

        Returns:
            Dictionary with execution results
        """
        try:
            # Update task status to in_progress
            self._update_task_status(task.id, "in_progress")

            # Execute based on the task type
            result = None
            if task.assigned_to == "main_agent":
                result = self._execute_with_main_agent(task)
            elif task.assigned_to == "sub_agent":
                result = self._execute_with_subagent(task)
            elif task.assigned_to == "tool":
                result = self._execute_with_tool(task)
            elif task.assigned_to == "external_service":
                result = self._execute_with_external_service(task)
            else:
                # Default to main agent
                result = self._execute_with_main_agent(task)

            # Update task status to completed
            self._update_task_status(task.id, "completed", result)

            return {
                "success": True,
                "task_id": task.id,
                "result": result,
                "status": "completed"
            }

        except Exception as e:
            # Update task status to failed
            self._update_task_status(task.id, "failed", str(e))

            return {
                "success": False,
                "task_id": task.id,
                "error": str(e),
                "status": "failed"
            }

    def _execute_with_main_agent(self, task: TaskModel) -> str:
        """
        Execute a task using the main LLM agent.

        Args:
            task: The task to execute

        Returns:
            Result of the execution
        """
        # Create a prompt for the agent to complete the task
        prompt = f"""
        Please complete the following task:
        Task: {task.description}
        Type: {task.task_type}

        Provide a detailed response explaining how you completed this task.
        """

        # Call the LLM to execute the task
        result = self.llm_service.generate_response(
            user_input=prompt,
            context=task.description
        )

        return result

    def _execute_with_subagent(self, task: TaskModel) -> str:
        """
        Execute a task using a specialized subagent.

        Args:
            task: The task to execute

        Returns:
            Result of the execution
        """
        # Find the appropriate subagent based on the role
        subagent = self.db_session.query(SubAgent).filter(
            SubAgent.role == task.sub_agent_role,
            SubAgent.activated_status == True
        ).first()

        if not subagent:
            # If no active subagent exists, create one
            subagent = self._create_subagent(task.sub_agent_role)

        if not subagent:
            raise Exception(f"No subagent available for role: {task.sub_agent_role}")

        # Execute the task with the subagent
        result = self._execute_subagent_task(subagent, task)

        return result

    def _execute_with_tool(self, task: TaskModel) -> str:
        """
        Execute a task using an appropriate tool.

        Args:
            task: The task to execute

        Returns:
            Result of the execution
        """
        from ..tools_manager import ToolsManager
        tools_manager = ToolsManager()

        # Determine which tool to use based on the task description
        # In a real implementation, we'd have a more sophisticated routing system
        if "search" in task.description.lower() or "find" in task.description.lower():
            tool_name = "web-search"
            # Extract search query from task description
            query = task.description.replace("search", "").replace("find", "").strip()
            if not query:
                query = task.description
            parameters = {"query": query}
        elif "file" in task.description.lower():
            tool_name = "file-read"  # Default to file-read
            parameters = {"file_path": "placeholder.txt"}  # Would extract actual path
        elif "command" in task.description.lower() or "execute" in task.description.lower():
            tool_name = "command-exec"
            # Extract command from task description
            command = task.description.replace("execute", "").replace("command", "").strip()
            parameters = {"command": command}
        else:
            # Default to a generic tool execution
            tool_name = "web-search"
            parameters = {"query": task.description}

        # Execute the tool
        result = tools_manager.execute_tool(tool_name, **parameters)

        return result

    def _execute_with_external_service(self, task: TaskModel) -> str:
        """
        Execute a task using an external service.

        Args:
            task: The task to execute

        Returns:
            Result of the execution
        """
        # Placeholder for external service execution
        # In a real implementation, this would call external APIs or services
        return f"External service executed for task: {task.description}"

    def _update_task_status(self, task_id: str, status: str, result: Optional[str] = None):
        """
        Update the status of a task in the database.

        Args:
            task_id: ID of the task to update
            status: New status for the task
            result: Optional result to store with the task
        """
        task = self.db_session.query(TaskModel).filter(TaskModel.id == task_id).first()
        if task:
            task.status = status
            if status == "in_progress" and not task.started_at:
                task.started_at = datetime.utcnow()
            elif status in ["completed", "failed", "cancelled"]:
                task.completed_at = datetime.utcnow()

            if result:
                task.result = result

            self.db_session.commit()

    def _create_subagent(self, role: str) -> Optional[SubAgent]:
        """
        Create a new subagent with the specified role.

        Args:
            role: Role for the subagent

        Returns:
            Created SubAgent object or None if creation failed
        """
        try:
            subagent = SubAgent(
                name=f"{role}_subagent",
                role=role,
                description=f"Specialized subagent for {role} tasks",
                activated_status=True,
                activation_timestamp=datetime.utcnow(),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )

            self.db_session.add(subagent)
            self.db_session.commit()

            return subagent
        except Exception as e:
            print(f"Error creating subagent: {str(e)}")
            return None

    def _execute_subagent_task(self, subagent: SubAgent, task: TaskModel) -> str:
        """
        Execute a task with a specific subagent.

        Args:
            subagent: The subagent to use
            task: The task to execute

        Returns:
            Result of the execution
        """
        try:
            # Create a subagent execution record
            execution = SubAgentExecution(
                subagent_id=subagent.id,
                task_description=task.description,
                status="running",
                started_at=datetime.utcnow(),
                input_data={"task": task.description},
                execution_metadata={"task_type": task.task_type}
            )

            self.db_session.add(execution)
            self.db_session.commit()

            # Execute the task with the subagent
            # For now, we'll simulate different responses based on the role
            if subagent.role == "researcher":
                prompt = f"Please research the following topic: {task.description}"
            elif subagent.role == "coder":
                prompt = f"Please provide code for the following: {task.description}"
            elif subagent.role == "reviewer":
                prompt = f"Please review the following: {task.description}"
            else:
                prompt = f"Please handle this task: {task.description}"

            result = self.llm_service.generate_response(prompt)

            # Update the execution record
            execution.status = "completed"
            execution.completed_at = datetime.utcnow()
            execution.output_data = {"result": result}

            self.db_session.commit()

            return result

        except Exception as e:
            # Update the execution record with error
            execution = self.db_session.query(SubAgentExecution).filter(
                SubAgentExecution.subagent_id == subagent.id,
                SubAgentExecution.status == "running"
            ).first()

            if execution:
                execution.status = "failed"
                execution.completed_at = datetime.utcnow()
                execution.error_message = str(e)
                self.db_session.commit()

            raise e

    def execute_plan(self, tasks: List[TaskModel]) -> Dict[str, Any]:
        """
        Execute a plan consisting of multiple tasks.

        Args:
            tasks: List of tasks to execute

        Returns:
            Dictionary with execution results
        """
        results = []
        failed_tasks = []

        for task in tasks:
            # Check if this task's dependencies are met
            if not self._check_dependencies_met(task):
                print(f"Skipping task {task.id} - dependencies not met")
                continue

            result = self.execute_task(task)
            results.append(result)

            if not result["success"]:
                failed_tasks.append(result)

                # Determine if failure is critical (stops execution) or non-critical
                if self._is_critical_failure(task, result):
                    break  # Stop execution if critical task failed

        return {
            "total_tasks": len(tasks),
            "successful_tasks": len(results) - len(failed_tasks),
            "failed_tasks": len(failed_tasks),
            "results": results,
            "failed_results": failed_tasks
        }

    def _check_dependencies_met(self, task: TaskModel) -> bool:
        """
        Check if a task's dependencies have been satisfied.

        Args:
            task: The task to check

        Returns:
            True if dependencies are met, False otherwise
        """
        # In a real implementation, this would check if prerequisite tasks are completed
        # For now, we'll just return True
        return True

    def _is_critical_failure(self, task: TaskModel, result: Dict[str, Any]) -> bool:
        """
        Determine if a task failure is critical enough to stop the entire plan.

        Args:
            task: The failed task
            result: The failure result

        Returns:
            True if the failure is critical, False otherwise
        """
        # Critical tasks might include data validation, security checks, etc.
        # For now, we'll consider any task with "critical" priority as critical
        return task.priority == "critical"