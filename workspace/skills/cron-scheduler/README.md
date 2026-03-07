# Cron Scheduler Skill

A comprehensive cron-based task scheduler skill that enables reliable task automation with cron expression support.

## Features

- **Cron Expression Support**: Full support for standard cron expressions (e.g., "0 9 * * *" for daily at 9 AM)
- **Task Management**: Create, update, delete, and list scheduled tasks
- **Persistent Storage**: Tasks stored in JSON format with automatic persistence
- **Error Handling**: Comprehensive error handling and logging
- **Task Execution**: Reliable execution of scheduled commands/scripts
- **Validation**: Built-in cron expression validation

## Installation

1. Ensure Python 3.6+ is installed
2. Install required dependencies:
   ```bash
   pip install croniter
   ```

3. The scheduler creates necessary directories automatically on first run:
   - `~/.cron-scheduler/config/` - Configuration files
   - `~/.cron-scheduler/logs/` - Log files
   - `~/.cron-scheduler/data/` - Task data

## Usage

### Adding a New Task

To schedule a task using a cron expression:

```bash
python scheduler_daemon.py add --expression="0 9 * * *" --command="echo 'Good morning!'" --name="morning_greeting"
```

### Listing Scheduled Tasks

View all currently scheduled tasks:

```bash
python scheduler_daemon.py list
```

### Removing a Task

Remove a scheduled task by name:

```bash
python scheduler_daemon.py remove --name="morning_greeting"
```

### Starting the Scheduler

Start the scheduler daemon to begin executing tasks:

```bash
python scheduler_daemon.py start
```

### Stopping the Scheduler

Stop the scheduler daemon:

```bash
python scheduler_daemon.py stop
```

## Cron Expression Format

The scheduler supports standard cron expressions with five fields:

```
* * * * *
│ │ │ │ │
│ │ │ │ └── Day of week (0-7, where 0 and 7 are Sunday)
│ │ │ └──── Month (1-12)
│ │ └────── Day of month (1-31)
│ └──────── Hour (0-23)
└────────── Minute (0-59)
```

### Supported Special Characters

- `*` - Any value
- `,` - List of values (e.g., "1,5,10")
- `-` - Range of values (e.g., "1-5")
- `/` - Step values (e.g., "*/5" for every 5 units)
- `?` - Not specified (for day/month fields)

### Examples

- `0 9 * * *` - Daily at 9:00 AM
- `30 18 * * *` - Daily at 6:30 PM
- `0 9 * * 1-5` - Weekdays at 9:00 AM
- `0 0 1 * *` - First day of each month at midnight
- `*/15 * * * *` - Every 15 minutes
- `0 */2 * * *` - Every 2 hours

## Task Definition Schema

Tasks are stored in JSON format with the following schema:

```json
{
  "name": "task_name",
  "cron_expression": "0 9 * * *",
  "command": "command to execute",
  "enabled": true,
  "created_at": "2023-01-01T00:00:00Z",
  "last_run": null,
  "next_run": "2023-01-01T09:00:00Z"
}
```

## Configuration

The scheduler uses the following configuration files:

- `~/.cron-scheduler/config/tasks.json` - Stores all scheduled tasks
- `~/.cron-scheduler/logs/scheduler.log` - Execution logs
- `~/.cron-scheduler/data/pid.txt` - Process ID when running

## Error Handling

- Failed tasks are logged with detailed error messages
- Scheduler continues running even if individual tasks fail
- Invalid cron expressions are rejected during task creation
- Automatic recovery from temporary errors

## Security Considerations

- Commands are executed with the same permissions as the scheduler process
- Only allow trusted commands to be scheduled
- Regularly review and audit scheduled tasks
- Monitor logs for unexpected activity

## Troubleshooting

### Scheduler won't start
- Check that all required directories exist
- Verify that the PID file isn't locked (`~/.cron-scheduler/data/pid.txt`)
- Review logs in `~/.cron-scheduler/logs/`

### Tasks aren't executing
- Verify cron expression format is correct
- Check that the command exists and is executable
- Review logs for error messages
- Ensure the scheduler daemon is running

### Performance issues
- Limit the number of frequently-executing tasks
- Optimize command execution times
- Monitor system resources