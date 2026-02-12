"""
Tool audit logging service for the x-agent2 AI assistant system.

This module provides comprehensive logging and auditing capabilities for
all tool executions within the system.
"""

import json
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum
import logging
from pathlib import Path
import uuid
from dataclasses import dataclass

from src.db.models.tool_execution import ToolExecution as ToolExecutionModel
from src.agent_core.config.config_service import get_config


class AuditLogLevel(Enum):
    """Levels for audit logging."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ToolExecutionStatus(Enum):
    """Status of tool execution for auditing."""
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class AuditEvent:
    """Structure for audit events."""
    id: str
    timestamp: datetime
    user_id: Optional[str]
    session_id: Optional[str]
    tool_name: str
    status: ToolExecutionStatus
    parameters: Dict[str, Any]
    result: Optional[Dict[str, Any]]
    execution_time_ms: Optional[float]
    error_message: Optional[str]
    metadata: Dict[str, Any]


class ToolAuditLogger:
    """Primary logger for tool execution audit events."""

    def __init__(self):
        self.config = get_config()
        self.logger = logging.getLogger(__name__)

        # Audit log storage path
        self.audit_log_dir = Path("logs/audit")
        self.audit_log_dir.mkdir(parents=True, exist_ok=True)

        # File-based audit logger
        self.file_handler = logging.FileHandler(self.audit_log_dir / "tool_audit.log")
        self.file_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        self.logger.addHandler(self.file_handler)
        self.logger.setLevel(logging.INFO)

    async def log_tool_execution(
        self,
        user_id: Optional[str],
        session_id: Optional[str],
        tool_name: str,
        parameters: Dict[str, Any],
        result: Optional[Dict[str, Any]] = None,
        execution_time_ms: Optional[float] = None,
        status: ToolExecutionStatus = ToolExecutionStatus.COMPLETED,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Log a tool execution event.

        Args:
            user_id: ID of the user who initiated the tool execution
            session_id: ID of the session in which the tool was executed
            tool_name: Name of the tool that was executed
            parameters: Parameters passed to the tool
            result: Result returned by the tool
            execution_time_ms: Execution time in milliseconds
            status: Status of the tool execution
            error_message: Error message if execution failed
            metadata: Additional metadata to log

        Returns:
            ID of the audit event
        """
        event_id = str(uuid.uuid4())

        # Create audit event
        audit_event = AuditEvent(
            id=event_id,
            timestamp=datetime.utcnow(),
            user_id=user_id,
            session_id=session_id,
            tool_name=tool_name,
            status=status,
            parameters=parameters,
            result=result,
            execution_time_ms=execution_time_ms,
            error_message=error_message,
            metadata=metadata or {}
        )

        # Log to file
        log_level = self._get_log_level_for_status(status)
        self.logger.log(
            log_level,
            f"AUDIT_EVENT: {json.dumps(self._event_to_dict(audit_event), default=str)}"
        )

        # Save to database
        try:
            await self._save_to_database(audit_event)
        except Exception as e:
            self.logger.error(f"Failed to save audit event to database: {e}")

        return event_id

    def _get_log_level_for_status(self, status: ToolExecutionStatus) -> int:
        """Get the appropriate log level for a given status."""
        status_to_level = {
            ToolExecutionStatus.STARTED: logging.INFO,
            ToolExecutionStatus.COMPLETED: logging.INFO,
            ToolExecutionStatus.FAILED: logging.ERROR,
            ToolExecutionStatus.TIMEOUT: logging.WARNING,
            ToolExecutionStatus.CANCELLED: logging.INFO
        }
        return status_to_level.get(status, logging.INFO)

    def _event_to_dict(self, event: AuditEvent) -> Dict[str, Any]:
        """Convert an audit event to a dictionary."""
        return {
            "id": event.id,
            "timestamp": event.timestamp.isoformat(),
            "user_id": event.user_id,
            "session_id": event.session_id,
            "tool_name": event.tool_name,
            "status": event.status.value,
            "parameters": event.parameters,
            "result": event.result,
            "execution_time_ms": event.execution_time_ms,
            "error_message": event.error_message,
            "metadata": event.metadata
        }

    async def _save_to_database(self, event: AuditEvent):
        """Save audit event to the database."""
        # Create ToolExecution record
        tool_execution = ToolExecutionModel(
            id=event.id,
            user_id=event.user_id,
            session_id=event.session_id,
            tool_name=event.tool_name,
            parameters=event.parameters,
            result=event.result,
            execution_time_ms=event.execution_time_ms,
            status=event.status.value,
            error_message=event.error_message,
            metadata=event.metadata,
            timestamp=event.timestamp
        )

        await tool_execution.save()

    async def log_tool_execution_start(
        self,
        user_id: Optional[str],
        session_id: Optional[str],
        tool_name: str,
        parameters: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Log the start of a tool execution."""
        return await self.log_tool_execution(
            user_id=user_id,
            session_id=session_id,
            tool_name=tool_name,
            parameters=parameters,
            status=ToolExecutionStatus.STARTED,
            metadata=metadata or {}
        )

    async def log_tool_execution_success(
        self,
        event_id: str,
        user_id: Optional[str],
        session_id: Optional[str],
        tool_name: str,
        parameters: Dict[str, Any],
        result: Dict[str, Any],
        execution_time_ms: float,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Log a successful tool execution."""
        return await self.log_tool_execution(
            user_id=user_id,
            session_id=session_id,
            tool_name=tool_name,
            parameters=parameters,
            result=result,
            execution_time_ms=execution_time_ms,
            status=ToolExecutionStatus.COMPLETED,
            metadata=metadata or {}
        )

    async def log_tool_execution_failure(
        self,
        user_id: Optional[str],
        session_id: Optional[str],
        tool_name: str,
        parameters: Dict[str, Any],
        error_message: str,
        execution_time_ms: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Log a failed tool execution."""
        return await self.log_tool_execution(
            user_id=user_id,
            session_id=session_id,
            tool_name=tool_name,
            parameters=parameters,
            execution_time_ms=execution_time_ms,
            status=ToolExecutionStatus.FAILED,
            error_message=error_message,
            metadata=metadata or {}
        )

    async def log_tool_execution_timeout(
        self,
        user_id: Optional[str],
        session_id: Optional[str],
        tool_name: str,
        parameters: Dict[str, Any],
        execution_time_ms: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Log a timed-out tool execution."""
        return await self.log_tool_execution(
            user_id=user_id,
            session_id=session_id,
            tool_name=tool_name,
            parameters=parameters,
            execution_time_ms=execution_time_ms,
            status=ToolExecutionStatus.TIMEOUT,
            error_message="Tool execution timed out",
            metadata=metadata or {}
        )

    async def log_tool_execution_cancelled(
        self,
        user_id: Optional[str],
        session_id: Optional[str],
        tool_name: str,
        parameters: Dict[str, Any],
        execution_time_ms: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Log a cancelled tool execution."""
        return await self.log_tool_execution(
            user_id=user_id,
            session_id=session_id,
            tool_name=tool_name,
            parameters=parameters,
            execution_time_ms=execution_time_ms,
            status=ToolExecutionStatus.CANCELLED,
            error_message="Tool execution cancelled by user",
            metadata=metadata or {}
        )


class ToolAuditService:
    """Service class for managing tool audit operations."""

    def __init__(self):
        self.audit_logger = ToolAuditLogger()
        self.logger = logging.getLogger(__name__)

    async def audit_tool_execution(
        self,
        user_id: Optional[str],
        session_id: Optional[str],
        tool_name: str,
        parameters: Dict[str, Any],
        execute_func,
        timeout_seconds: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Execute a tool with comprehensive auditing.

        Args:
            user_id: ID of the user initiating the execution
            session_id: ID of the session
            tool_name: Name of the tool to execute
            parameters: Parameters for the tool
            execute_func: Function to execute the tool
            timeout_seconds: Optional timeout for execution
            metadata: Additional metadata for auditing

        Returns:
            Result of the tool execution
        """
        # Log execution start
        event_id = await self.audit_logger.log_tool_execution_start(
            user_id, session_id, tool_name, parameters, metadata
        )

        start_time = datetime.utcnow()

        try:
            # Execute with optional timeout
            if timeout_seconds:
                # Use asyncio.wait_for for timeout
                result = await asyncio.wait_for(
                    execute_func(**parameters),
                    timeout=timeout_seconds
                )
            else:
                result = await execute_func(**parameters)

            # Calculate execution time
            execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000  # Convert to ms

            # Log successful execution
            await self.audit_logger.log_tool_execution_success(
                event_id=event_id,
                user_id=user_id,
                session_id=session_id,
                tool_name=tool_name,
                parameters=parameters,
                result=result,
                execution_time_ms=execution_time,
                metadata=metadata
            )

            return result

        except asyncio.TimeoutError:
            # Calculate execution time
            execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000  # Convert to ms

            # Log timeout
            await self.audit_logger.log_tool_execution_timeout(
                user_id=user_id,
                session_id=session_id,
                tool_name=tool_name,
                parameters=parameters,
                execution_time_ms=execution_time,
                metadata=metadata
            )

            raise Exception(f"Tool execution timed out after {timeout_seconds} seconds")

        except Exception as e:
            # Calculate execution time
            execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000  # Convert to ms

            # Log failure
            await self.audit_logger.log_tool_execution_failure(
                user_id=user_id,
                session_id=session_id,
                tool_name=tool_name,
                parameters=parameters,
                error_message=str(e),
                execution_time_ms=execution_time,
                metadata=metadata
            )

            raise e

    async def get_audit_events(
        self,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        tool_name: Optional[str] = None,
        status: Optional[ToolExecutionStatus] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Retrieve audit events with optional filters.

        Args:
            user_id: Filter by user ID
            session_id: Filter by session ID
            tool_name: Filter by tool name
            status: Filter by execution status
            start_date: Filter by start date
            end_date: Filter by end date
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of audit events
        """
        try:
            # Query database for audit events
            query_filters = {}
            if user_id:
                query_filters["user_id"] = user_id
            if session_id:
                query_filters["session_id"] = session_id
            if tool_name:
                query_filters["tool_name"] = tool_name
            if status:
                query_filters["status"] = status.value
            if start_date:
                query_filters["timestamp__gte"] = start_date
            if end_date:
                query_filters["timestamp__lte"] = end_date

            # In a real implementation, this would use the ORM's filtering capabilities
            # For now, we'll just get all events and filter in memory
            all_events = await ToolExecutionModel.get_all(limit=10000)  # Large limit for filtering

            # Apply filters
            filtered_events = []
            for event in all_events:
                match = True

                if user_id and event.user_id != user_id:
                    match = False
                if session_id and event.session_id != session_id:
                    match = False
                if tool_name and event.tool_name != tool_name:
                    match = False
                if status and event.status != status.value:
                    match = False
                if start_date and event.timestamp < start_date:
                    match = False
                if end_date and event.timestamp > end_date:
                    match = False

                if match:
                    filtered_events.append(event)

            # Apply pagination
            paginated_events = filtered_events[offset:offset + limit]

            # Convert to dictionaries
            result = []
            for event in paginated_events:
                result.append({
                    "id": event.id,
                    "timestamp": event.timestamp.isoformat(),
                    "user_id": event.user_id,
                    "session_id": event.session_id,
                    "tool_name": event.tool_name,
                    "status": event.status,
                    "parameters": event.parameters,
                    "result": event.result,
                    "execution_time_ms": event.execution_time_ms,
                    "error_message": event.error_message,
                    "metadata": event.metadata
                })

            return result
        except Exception as e:
            self.logger.error(f"Error retrieving audit events: {e}")
            return []

    async def get_tool_usage_stats(
        self,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get usage statistics for tools.

        Args:
            user_id: Filter by user ID
            session_id: Filter by session ID
            start_date: Filter by start date
            end_date: Filter by end date

        Returns:
            Dictionary with usage statistics
        """
        try:
            # Get all audit events for the specified period/filters
            all_events = await ToolExecutionModel.get_all(limit=10000)  # Large limit for analysis

            # Apply filters
            filtered_events = []
            for event in all_events:
                match = True

                if user_id and event.user_id != user_id:
                    match = False
                if session_id and event.session_id != session_id:
                    match = False
                if start_date and event.timestamp < start_date:
                    match = False
                if end_date and event.timestamp > end_date:
                    match = False

                if match:
                    filtered_events.append(event)

            # Calculate statistics
            total_executions = len(filtered_events)
            successful_executions = len([e for e in filtered_events if e.status == "completed"])
            failed_executions = len([e for e in filtered_events if e.status == "failed"])

            # Calculate tool usage counts
            tool_usage = {}
            for event in filtered_events:
                tool_name = event.tool_name
                if tool_name not in tool_usage:
                    tool_usage[tool_name] = 0
                tool_usage[tool_name] += 1

            # Calculate average execution time
            exec_times = [e.execution_time_ms for e in filtered_events if e.execution_time_ms is not None]
            avg_execution_time = sum(exec_times) / len(exec_times) if exec_times else 0

            return {
                "total_executions": total_executions,
                "successful_executions": successful_executions,
                "failed_executions": failed_executions,
                "success_rate": successful_executions / total_executions if total_executions > 0 else 0,
                "average_execution_time_ms": avg_execution_time,
                "tool_usage": tool_usage,
                "date_range": {
                    "start": start_date.isoformat() if start_date else None,
                    "end": end_date.isoformat() if end_date else None
                }
            }
        except Exception as e:
            self.logger.error(f"Error calculating tool usage stats: {e}")
            return {}

    async def get_risk_assessment(
        self,
        user_id: Optional[str] = None,
        days_back: int = 7
    ) -> Dict[str, Any]:
        """
        Perform risk assessment based on tool usage patterns.

        Args:
            user_id: Optional user ID to assess
            days_back: Number of days to look back for patterns

        Returns:
            Dictionary with risk assessment
        """
        try:
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days_back)

            # Get audit events for the time period
            events = await self.get_audit_events(
                user_id=user_id,
                start_date=start_date,
                end_date=end_date
            )

            # Assess risk factors
            total_events = len(events)
            failed_events = len([e for e in events if e.get("status") == "failed"])
            high_risk_tools = ["command_exec", "file_system", "system_access"]  # Example high-risk tools
            high_risk_events = len([e for e in events if e.get("tool_name") in high_risk_tools])

            # Calculate risk scores
            failure_rate = failed_events / total_events if total_events > 0 else 0
            high_risk_ratio = high_risk_events / total_events if total_events > 0 else 0

            # Overall risk level
            risk_level = "low"
            if high_risk_ratio > 0.5 or failure_rate > 0.3:
                risk_level = "high"
            elif high_risk_ratio > 0.2 or failure_rate > 0.15:
                risk_level = "medium"

            return {
                "risk_level": risk_level,
                "total_events": total_events,
                "failed_events": failed_events,
                "high_risk_events": high_risk_events,
                "failure_rate": failure_rate,
                "high_risk_ratio": high_risk_ratio,
                "assessment_period_days": days_back,
                "date_assessed": datetime.utcnow().isoformat()
            }
        except Exception as e:
            self.logger.error(f"Error performing risk assessment: {e}")
            return {"error": str(e)}

    async def export_audit_logs(
        self,
        output_format: str = "json",  # "json", "csv", "ndjson"
        filters: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Export audit logs in the specified format.

        Args:
            output_format: Format to export in ("json", "csv", "ndjson")
            filters: Optional filters for the export

        Returns:
            Path to the exported file
        """
        try:
            # Get audit events (possibly with filters)
            events = await ToolExecutionModel.get_all(limit=50000)  # Large limit for export

            # Apply filters if provided
            if filters:
                # This is a simplified filter implementation
                # In a real implementation, you'd want to use database-level filtering
                pass

            # Format the data according to the specified format
            if output_format.lower() == "json":
                data = [self._format_event_for_export(event) for event in events]
                output_content = json.dumps(data, indent=2, default=str)
            elif output_format.lower() == "ndjson":  # newline-delimited JSON
                lines = [json.dumps(self._format_event_for_export(event), default=str) for event in events]
                output_content = "\n".join(lines)
            elif output_format.lower() == "csv":
                # Create CSV header
                headers = ["id", "timestamp", "user_id", "session_id", "tool_name",
                          "status", "execution_time_ms", "error_message"]
                csv_lines = [",".join(headers)]

                for event in events:
                    row = [
                        event.id,
                        event.timestamp.isoformat(),
                        event.user_id or "",
                        event.session_id or "",
                        event.tool_name,
                        event.status,
                        str(event.execution_time_ms) if event.execution_time_ms else "",
                        event.error_message or ""
                    ]
                    csv_lines.append(",".join(f'"{str(item).replace(chr(34), chr(34) + chr(34))}"' for item in row))

                output_content = "\n".join(csv_lines)
            else:
                raise ValueError(f"Unsupported export format: {output_format}")

            # Write to file
            export_dir = self.audit_logger.audit_log_dir / "exports"
            export_dir.mkdir(exist_ok=True)

            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            filename = f"audit_export_{timestamp}.{output_format.lower()}"
            filepath = export_dir / filename

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(output_content)

            return str(filepath)
        except Exception as e:
            self.logger.error(f"Error exporting audit logs: {e}")
            raise e

    def _format_event_for_export(self, event) -> Dict[str, Any]:
        """Format an event for export."""
        return {
            "id": event.id,
            "timestamp": event.timestamp.isoformat(),
            "user_id": event.user_id,
            "session_id": event.session_id,
            "tool_name": event.tool_name,
            "status": event.status,
            "parameters": event.parameters,
            "result": event.result,
            "execution_time_ms": event.execution_time_ms,
            "error_message": event.error_message,
            "metadata": event.metadata
        }


class ToolSecurityMonitor:
    """Monitors tool usage for security purposes."""

    def __init__(self, audit_service: ToolAuditService):
        self.audit_service = audit_service
        self.logger = logging.getLogger(__name__)

    async def monitor_for_anomalies(
        self,
        user_id: str,
        time_window_minutes: int = 60
    ) -> List[Dict[str, Any]]:
        """
        Monitor for anomalous tool usage patterns for a user.

        Args:
            user_id: ID of the user to monitor
            time_window_minutes: Time window to analyze in minutes

        Returns:
            List of detected anomalies
        """
        try:
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(minutes=time_window_minutes)

            events = await self.audit_service.get_audit_events(
                user_id=user_id,
                start_date=start_time,
                end_date=end_time
            )

            anomalies = []

            # Check for unusual volume
            total_count = len(events)
            if total_count > 50:  # Threshold for volume anomaly
                anomalies.append({
                    "type": "volume_anomaly",
                    "severity": "medium",
                    "message": f"Unusually high tool usage: {total_count} executions in {time_window_minutes} minutes",
                    "timestamp": end_time.isoformat(),
                    "count": total_count
                })

            # Check for suspicious tools
            suspicious_tools = ["command_exec", "file_system", "network_scan"]  # Example
            suspicious_events = [e for e in events if e.get("tool_name") in suspicious_tools]
            if suspicious_events:
                anomalies.append({
                    "type": "suspicious_tool_usage",
                    "severity": "high",
                    "message": f"Detected usage of potentially risky tools: {[e['tool_name'] for e in suspicious_events][:5]}",  # Limit to first 5
                    "timestamp": end_time.isoformat(),
                    "tool_count": len(suspicious_events)
                })

            # Check for execution failures
            failed_events = [e for e in events if e.get("status") == "failed"]
            failure_rate = len(failed_events) / len(events) if events else 0
            if failure_rate > 0.5:  # More than 50% failures
                anomalies.append({
                    "type": "high_failure_rate",
                    "severity": "medium",
                    "message": f"Unusually high failure rate: {failure_rate:.2%}",
                    "timestamp": end_time.isoformat(),
                    "failure_count": len(failed_events)
                })

            return anomalies
        except Exception as e:
            self.logger.error(f"Error monitoring for anomalies: {e}")
            return []


# Global instances
tool_audit_logger = ToolAuditLogger()
tool_audit_service = ToolAuditService()
tool_security_monitor = ToolSecurityMonitor(tool_audit_service)


# Convenience functions
async def log_tool_execution(
    user_id: Optional[str],
    session_id: Optional[str],
    tool_name: str,
    parameters: Dict[str, Any],
    result: Optional[Dict[str, Any]] = None,
    execution_time_ms: Optional[float] = None,
    status: ToolExecutionStatus = ToolExecutionStatus.COMPLETED,
    error_message: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> str:
    """Log a tool execution event."""
    return await tool_audit_logger.log_tool_execution(
        user_id, session_id, tool_name, parameters, result,
        execution_time_ms, status, error_message, metadata
    )


async def audit_tool_execution(
    user_id: Optional[str],
    session_id: Optional[str],
    tool_name: str,
    parameters: Dict[str, Any],
    execute_func,
    timeout_seconds: Optional[float] = None,
    metadata: Optional[Dict[str, Any]] = None
):
    """Execute a tool with comprehensive auditing."""
    return await tool_audit_service.audit_tool_execution(
        user_id, session_id, tool_name, parameters,
        execute_func, timeout_seconds, metadata
    )


async def get_audit_events(
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    tool_name: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
) -> List[Dict[str, Any]]:
    """Get audit events with optional filters."""
    return await tool_audit_service.get_audit_events(
        user_id, session_id, tool_name, None, None, None, limit, offset
    )