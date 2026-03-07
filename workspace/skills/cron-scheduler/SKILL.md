---
name: cron-scheduler
description: Comprehensive cron-based task scheduling framework supporting standard cron expressions, task management, logging, and monitoring. Use when Claude needs to schedule recurring tasks, automate periodic operations, or manage time-based workflows. Supports creating, modifying, deleting scheduled tasks with proper error handling and logging.
---

# Cron Task Scheduler Framework

## Overview

This skill provides a complete cron-based task scheduling framework that allows for creating, managing, and monitoring scheduled tasks using standard cron expressions.

## Cron Expression Format

Standard cron expression format (5 parts):
```
* * * * *
| | | | |
| | | | +-- Day of week (0-7, Sunday = 0 or 7)
| | | +---- Month (1-12)
| | +------ Day of month (1-31)
| +-------- Hour (0-23)
+---------- Minute (0-59)
```

### Common Cron Patterns

- `*/5 * * * *` - Every 5 minutes
- `0 */2 * * *` - Every 2 hours
- `0 9 * * *` - Daily at 9 AM
- `0 9 * * 1` - Weekly on Monday at 9 AM
- `0 0 1 * *` - Monthly on 1st day at midnight
- `@daily` - Once daily (midnight)
- `@weekly` - Once weekly (midnight Sunday)
- `@monthly` - Once monthly (midnight first day)

## Implementation Components

### 1. Task Definition Schema

Create a standardized task definition format:

```json
{
  "id": "unique_task_identifier",
  "name": "Human readable task name",
  "schedule": "cron_expression",
  "command": "shell_command_or_script_to_execute",
  "enabled": true,
  "description": "Purpose of the task",
  "logging": {
    "level": "INFO|ERROR|DEBUG",
    "file": "/path/to/log/file"
  },
  "retry_policy": {
    "max_retries": 3,
    "backoff_multiplier": 2
  }
}
```

### 2. Core Scripts

The framework includes several key scripts:

- `scheduler_daemon.py` - Main scheduling daemon
- `task_manager.py` - CRUD operations for tasks
- `executor.py` - Safe execution of scheduled commands
- `logger.py` - Structured logging for tasks
- `validator.py` - Cron expression validation

### 3. Task Management Operations

#### Adding Tasks
- Validate cron expression syntax
- Check for conflicts with existing tasks
- Store task in persistent storage
- Restart scheduler if needed

#### Updating Tasks
- Modify existing task configuration
- Preserve execution history
- Apply changes without service interruption

#### Removing Tasks
- Gracefully stop running instances
- Clean up associated resources
- Update persistent storage

#### Monitoring Tasks
- Track execution history
- Monitor performance metrics
- Alert on failures

## Usage Workflow

### Initial Setup
1. Create the task storage directory
2. Initialize the database or configuration files
3. Start the scheduler daemon
4. Verify the service is running

### Adding New Tasks
1. Define the task using the schema above
2. Validate the cron expression
3. Add the task to the scheduler
4. Confirm the task is active

### Managing Existing Tasks
1. List current scheduled tasks
2. View execution history
3. Enable/disable specific tasks
4. Modify task parameters

## Error Handling

### Common Issues
- Invalid cron expressions
- Command execution failures
- Resource constraints
- Permission issues
- Time zone complications

### Recovery Strategies
- Automatic retry with exponential backoff
- Fallback execution modes
- Detailed error logging
- Health check mechanisms

## Security Considerations

- Sanitize all command inputs
- Run tasks with minimal required privileges
- Validate file paths to prevent directory traversal
- Limit concurrent task execution
- Secure access to task management interfaces

## Logging and Monitoring

- Log all task executions with timestamps
- Record success/failure status
- Capture stdout/stderr from executed commands
- Monitor scheduler health metrics
- Generate execution reports

## Best Practices

1. Test cron expressions before deploying
2. Use descriptive names for tasks
3. Implement proper error handling in scheduled commands
4. Monitor task execution regularly
5. Plan for time zone changes and daylight saving time
6. Keep scheduled tasks lightweight and efficient
7. Implement appropriate logging in task commands
8. Plan for graceful degradation if tasks fail

## Integration Points

This framework integrates with:
- System logging (syslog/journald)
- Notification systems
- Monitoring platforms
- Configuration management tools
- Backup and recovery systems

## Usage Instructions

To implement and use this cron scheduler framework:

1. Create the necessary directory structure:
   ```bash
   mkdir -p ~/Documents/qoder-workspace/x-agent/workspace/skills/cron-scheduler/scripts
   mkdir -p ~/.cron-scheduler/config
   mkdir -p ~/.cron-scheduler/logs
   mkdir -p ~/.cron-scheduler/data
   ```

2. Create the scheduler daemon script:
   ```bash
   # This will be saved as ~/Documents/qoder-workspace/x-agent/workspace/skills/cron-scheduler/scripts/scheduler_daemon.py
   ```

3. Create the task manager script:
   ```bash
   # This will be saved as ~/Documents/qoder-workspace/x-agent/workspace/skills/cron-scheduler/scripts/task_manager.py
   ```

4. Create the validator script:
   ```bash
   # This will be saved as ~/Documents/qoder-workspace/x-agent/workspace/skills/cron-scheduler/scripts/validator.py
   ```

5. Create an installation script:
   ```bash
   # This will be saved as ~/Documents/qoder-workspace/x-agent/workspace/skills/cron-scheduler/scripts/install.sh
   ```

6. Install required dependencies:
   ```bash
   pip3 install croniter
   ```

7. Run the installation script:
   ```bash
   chmod +x ~/Documents/qoder-workspace/x-agent/workspace/skills/cron-scheduler/scripts/install.sh
   ~/Documents/qoder-workspace/x-agent/workspace/skills/cron-scheduler/scripts/install.sh
   ```

8. Define your tasks in `~/.cron-scheduler/config/tasks.json`

9. Start the scheduler:
   ```bash
   python3 ~/Documents/qoder-workspace/x-agent/workspace/skills/cron-scheduler/scripts/scheduler_daemon.py start
   ```

For detailed usage examples, refer to the examples.md file that accompanies this framework.