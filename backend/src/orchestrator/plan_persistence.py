"""Plan persistence utility for X-Agent.

Provides JSON-based file persistence for plan states.
Supports saving and loading plans across service restarts.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ..utils.logger import get_logger

logger = get_logger(__name__)


class PlanPersistence:
    """Plan file persistence manager.
    
    Saves plan states to JSON files in workspace/.plans directory.
    Supports automatic save on plan generation/update.
    """
    
    def __init__(self, workspace_path: str):
        """Initialize plan persistence.
        
        Args:
            workspace_path: Base workspace directory path
        """
        self.workspace_path = Path(workspace_path)
        self.plans_dir = self.workspace_path / '.plans'
        self.plans_dir.mkdir(exist_ok=True)
        logger.info(
            "Plan persistence initialized",
            extra={
                "workspace": str(self.workspace_path),
                "plans_dir": str(self.plans_dir),
            }
        )
    
    def _serialize_plan_state(self, plan_state: Any) -> dict:
        """Serialize PlanState to JSON-serializable dict.
        
        Args:
            plan_state: PlanState object to serialize
            
        Returns:
            Dictionary suitable for JSON serialization
        """
        try:
            # Extract PlanState fields with safe attribute access
            data = {
                'original_plan': getattr(plan_state, 'original_plan', ''),
                'current_step': getattr(plan_state, 'current_step', 1),
                'total_steps': getattr(plan_state, 'total_steps', 0),
                'completed_steps': getattr(plan_state, 'completed_steps', []),
                'failed_count': getattr(plan_state, 'failed_count', 0),
                'last_adjustment': getattr(plan_state, 'last_adjustment'),
                'react_iteration_count': getattr(plan_state, 'react_iteration_count', 0),
                'tool_execution_count': getattr(plan_state, 'tool_execution_count', 0),
                'replan_count': getattr(plan_state, 'replan_count', 0),
                'milestones_validated': getattr(plan_state, 'milestones_validated', []),
                'allowed_tools_snapshot': getattr(plan_state, 'allowed_tools_snapshot', []),
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat(),
            }
            
            # Serialize StructuredPlan if present
            if hasattr(plan_state, 'structured_plan') and plan_state.structured_plan:
                structured_data = self._serialize_structured_plan(plan_state.structured_plan)
                data['structured_plan'] = structured_data
            
            return data
            
        except Exception as e:
            logger.error(f"Failed to serialize plan state: {e}", exc_info=True)
            return {}
    
    def _serialize_structured_plan(self, structured_plan: Any) -> dict:
        """Serialize StructuredPlan to JSON-serializable dict.
        
        Args:
            structured_plan: StructuredPlan object to serialize
            
        Returns:
            Dictionary suitable for JSON serialization
        """
        try:
            # Extract key fields from StructuredPlan
            return {
                'goal': getattr(structured_plan, 'goal', ''),
                'skill_binding': getattr(structured_plan, 'skill_binding', None),
                'tool_constraints': self._serialize_tool_constraints(structured_plan),
                'steps': self._serialize_steps(structured_plan),
                'milestones': self._serialize_milestones(structured_plan),
            }
        except Exception as e:
            logger.warning(f"Failed to serialize structured plan: {e}")
            return {}
    
    def _serialize_tool_constraints(self, structured_plan: Any) -> dict | None:
        """Serialize tool constraints."""
        try:
            tc = getattr(structured_plan, 'tool_constraints', None)
            if tc:
                return {
                    'allowed': getattr(tc, 'allowed', []),
                    'forbidden': getattr(tc, 'forbidden', []),
                    'source': getattr(tc, 'source', 'plan'),  # ✅ Serialize source
                    'priority': getattr(tc, 'priority', 10),  # ✅ Serialize priority
                }
            return None
        except Exception:
            return None
    
    def _serialize_steps(self, structured_plan: Any) -> list[dict]:
        """Serialize plan steps."""
        try:
            steps = getattr(structured_plan, 'steps', [])
            return [
                {
                    'id': getattr(step, 'id', ''),
                    'name': getattr(step, 'name', ''),  # 🔥 ADD: Serialize name
                    'description': getattr(step, 'description', ''),  # ✅ Already correct
                    'tool': getattr(step, 'tool', None),
                    'skill_command': getattr(step, 'skill_command', None),  # 🔥 ADD: Serialize skill_command
                    'expected_output': getattr(step, 'expected_output', None),  # 🔥 ADD: Serialize expected_output
                }
                for step in steps
            ]
        except Exception:
            return []
    
    def _serialize_milestones(self, structured_plan: Any) -> list[dict]:
        """Serialize plan milestones."""
        try:
            milestones = getattr(structured_plan, 'milestones', [])
            return [
                {
                    'name': getattr(m, 'name', ''),
                    'after_step': getattr(m, 'after_step', ''),
                    'check_type': getattr(m, 'check_type', ''),
                }
                for m in milestones
            ]
        except Exception:
            return []
    
    def _deserialize_to_plan_state(self, data: dict, session_id: str):
        """Deserialize JSON data back to PlanState.
        
        Args:
            data: Dictionary loaded from JSON file
            session_id: Session ID for this plan
            
        Returns:
            PlanState object or None if deserialization fails
        """
        try:
            # Lazy import to avoid circular dependency
            from .plan_context import PlanState
            
            # Reconstruct PlanState
            plan_state = PlanState(
                original_plan=data.get('original_plan', ''),
                current_step=data.get('current_step', 1),
                total_steps=data.get('total_steps', 0),
                completed_steps=data.get('completed_steps', []),
                failed_count=data.get('failed_count', 0),
                last_adjustment=data.get('last_adjustment'),
                react_iteration_count=data.get('react_iteration_count', 0),
                tool_execution_count=data.get('tool_execution_count', 0),
                replan_count=data.get('replan_count', 0),
                milestones_validated=data.get('milestones_validated', []),
                allowed_tools_snapshot=data.get('allowed_tools_snapshot', []),
            )
            
            # TODO: Reconstruct StructuredPlan if needed
            # For now, we'll skip this as it requires importing the full class
            
            return plan_state
            
        except Exception as e:
            logger.error(f"Failed to deserialize plan state: {e}")
            return None
    
    def save_plan(self, session_id: str, plan_state: Any) -> bool:
        """Save plan state to JSON file.
        
        Args:
            session_id: Unique session identifier
            plan_state: PlanState object to save
            
        Returns:
            True if save succeeded, False otherwise
        """
        try:
            plan_file = self.plans_dir / f'{session_id}.json'
            data = self._serialize_plan_state(plan_state)
            
            with open(plan_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.info(
                "Plan saved to file",
                extra={
                    "session_id": session_id,
                    "plan_file": str(plan_file),
                    "steps_count": len(data.get('completed_steps', [])),
                }
            )
            return True
            
        except Exception as e:
            logger.error(f"Failed to save plan: {e}")
            return False
    
    def load_plan(self, session_id: str) -> Any | None:
        """Load plan state from JSON file.
        
        Args:
            session_id: Unique session identifier
            
        Returns:
            PlanState object if load succeeded, None otherwise
        """
        try:
            plan_file = self.plans_dir / f'{session_id}.json'
            
            if not plan_file.exists():
                logger.debug(f"No saved plan found for session: {session_id}")
                return None
            
            with open(plan_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            plan_state = self._deserialize_to_plan_state(data, session_id)
            
            if plan_state:
                logger.info(
                    "Plan loaded from file",
                    extra={
                        "session_id": session_id,
                        "plan_file": str(plan_file),
                        "current_step": plan_state.current_step,
                    }
                )
            
            return plan_state
            
        except Exception as e:
            logger.error(f"Failed to load plan: {e}")
            return None
    
    def delete_plan(self, session_id: str) -> bool:
        """Delete saved plan file.
        
        Args:
            session_id: Unique session identifier
            
        Returns:
            True if deletion succeeded, False otherwise
        """
        try:
            plan_file = self.plans_dir / f'{session_id}.json'
            
            if plan_file.exists():
                plan_file.unlink()
                logger.info(
                    "Plan deleted",
                    extra={"session_id": session_id}
                )
                return True
            else:
                logger.debug(f"No plan file to delete: {session_id}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to delete plan: {e}")
            return False
    
    def list_saved_plans(self) -> list[str]:
        """List all saved plan session IDs.
        
        Returns:
            List of session IDs that have saved plans
        """
        try:
            if not self.plans_dir.exists():
                return []
            
            plan_files = list(self.plans_dir.glob('*.json'))
            session_ids = [f.stem for f in plan_files]
            
            logger.debug(
                "Listed saved plans",
                extra={"count": len(session_ids)}
            )
            return session_ids
            
        except Exception as e:
            logger.error(f"Failed to list plans: {e}")
            return []
