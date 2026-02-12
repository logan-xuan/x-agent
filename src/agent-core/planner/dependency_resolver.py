from typing import Dict, List, Set, Tuple
from sqlalchemy.orm import Session
from ...db.models.task import Task as TaskModel
import json


class TaskDependencyResolver:
    """
    Resolves dependencies between tasks and determines the execution order.
    Implements topological sorting to handle dependencies.
    """

    def __init__(self, db_session: Session):
        self.db_session = db_session

    def resolve_dependencies(self, session_id: str) -> List[TaskModel]:
        """
        Resolve dependencies for tasks in a session and return execution order.

        Args:
            session_id: ID of the session containing tasks

        Returns:
            List of tasks in execution order
        """
        # Get all tasks for the session
        all_tasks = self.db_session.query(TaskModel).filter(
            TaskModel.session_id == session_id
        ).all()

        # Parse dependencies from JSON strings
        task_deps = {}
        task_lookup = {task.id: task for task in all_tasks}

        for task in all_tasks:
            try:
                deps = json.loads(task.dependencies) if task.dependencies else []
                task_deps[task.id] = deps
            except json.JSONDecodeError:
                # If parsing fails, assume no dependencies
                task_deps[task.id] = []

        # Perform topological sort to get execution order
        execution_order = self._topological_sort(task_deps, task_lookup)

        return execution_order

    def _topological_sort(self, dependencies: Dict[str, List[str]],
                         task_lookup: Dict[str, TaskModel]) -> List[TaskModel]:
        """
        Perform topological sort to determine execution order of tasks.

        Args:
            dependencies: Dictionary mapping task IDs to their dependencies
            task_lookup: Dictionary mapping task IDs to task objects

        Returns:
            List of tasks in execution order
        """
        # Build adjacency list for the graph
        graph = {task_id: [] for task_id in dependencies.keys()}

        # Add reverse dependencies (what depends on this task)
        for task_id, deps in dependencies.items():
            for dep in deps:
                if dep in graph:
                    graph[dep].append(task_id)

        # Track visited nodes and the execution order
        visited: Set[str] = set()
        temp_visited: Set[str] = set()  # For cycle detection
        execution_order: List[TaskModel] = []

        def dfs(node: str):
            """
            Depth-first search to traverse the dependency graph.
            """
            if node in temp_visited:
                raise ValueError(f"Circular dependency detected involving task {node}")
            if node in visited:
                return

            temp_visited.add(node)

            # Visit all dependent tasks first
            for neighbor in graph[node]:
                dfs(neighbor)

            temp_visited.remove(node)
            visited.add(node)
            # Add this task to the execution order
            if node in task_lookup:
                execution_order.append(task_lookup[node])

        # Visit all nodes
        for task_id in dependencies:
            if task_id not in visited:
                dfs(task_id)

        # Reverse to get execution order (dependencies first)
        execution_order.reverse()
        return execution_order

    def add_dependency(self, task_id: str, dependency_task_id: str) -> bool:
        """
        Add a dependency relationship between tasks.

        Args:
            task_id: ID of the task that depends on another
            dependency_task_id: ID of the task that must be completed first

        Returns:
            True if dependency was added successfully, False otherwise
        """
        try:
            task = self.db_session.query(TaskModel).filter(TaskModel.id == task_id).first()
            if not task:
                return False

            # Parse existing dependencies
            existing_deps = json.loads(task.dependencies) if task.dependencies else []

            # Add the new dependency if it doesn't exist
            if dependency_task_id not in existing_deps:
                existing_deps.append(dependency_task_id)

            # Update the task with new dependencies
            task.dependencies = json.dumps(existing_deps)
            self.db_session.commit()

            return True
        except Exception:
            self.db_session.rollback()
            return False

    def remove_dependency(self, task_id: str, dependency_task_id: str) -> bool:
        """
        Remove a dependency relationship between tasks.

        Args:
            task_id: ID of the task that had a dependency
            dependency_task_id: ID of the dependency task to remove

        Returns:
            True if dependency was removed successfully, False otherwise
        """
        try:
            task = self.db_session.query(TaskModel).filter(TaskModel.id == task_id).first()
            if not task:
                return False

            # Parse existing dependencies
            existing_deps = json.loads(task.dependencies) if task.dependencies else []

            # Remove the dependency if it exists
            if dependency_task_id in existing_deps:
                existing_deps.remove(dependency_task_id)

            # Update the task with new dependencies
            task.dependencies = json.dumps(existing_deps)
            self.db_session.commit()

            return True
        except Exception:
            self.db_session.rollback()
            return False

    def get_dependent_tasks(self, task_id: str) -> List[TaskModel]:
        """
        Get all tasks that depend on the specified task.

        Args:
            task_id: ID of the task to check

        Returns:
            List of tasks that depend on the specified task
        """
        # Get all tasks in the system
        all_tasks = self.db_session.query(TaskModel).all()

        dependent_tasks = []

        for task in all_tasks:
            try:
                deps = json.loads(task.dependencies) if task.dependencies else []
                if task_id in deps:
                    dependent_tasks.append(task)
            except json.JSONDecodeError:
                continue

        return dependent_tasks

    def get_dependencies(self, task_id: str) -> List[TaskModel]:
        """
        Get all dependencies of the specified task.

        Args:
            task_id: ID of the task to check

        Returns:
            List of tasks that the specified task depends on
        """
        task = self.db_session.query(TaskModel).filter(TaskModel.id == task_id).first()
        if not task:
            return []

        try:
            deps = json.loads(task.dependencies) if task.dependencies else []
        except json.JSONDecodeError:
            return []

        # Get the actual task objects for the dependency IDs
        dependency_tasks = []
        for dep_id in deps:
            dep_task = self.db_session.query(TaskModel).filter(TaskModel.id == dep_id).first()
            if dep_task:
                dependency_tasks.append(dep_task)

        return dependency_tasks

    def validate_dependencies(self, session_id: str) -> Tuple[bool, List[str]]:
        """
        Validate that there are no circular dependencies in a session.

        Args:
            session_id: ID of the session to validate

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        try:
            # Get all tasks for the session
            all_tasks = self.db_session.query(TaskModel).filter(
                TaskModel.session_id == session_id
            ).all()

            # Parse dependencies
            task_deps = {}
            for task in all_tasks:
                try:
                    deps = json.loads(task.dependencies) if task.dependencies else []
                    task_deps[task.id] = deps
                except json.JSONDecodeError:
                    task_deps[task.id] = []

            # Try to perform topological sort - this will detect cycles
            task_lookup = {task.id: task for task in all_tasks}
            _ = self._topological_sort(task_deps, task_lookup)

            return (True, [])
        except ValueError as e:
            return (False, [str(e)])
        except Exception as e:
            return (False, [f"Error validating dependencies: {str(e)}"])