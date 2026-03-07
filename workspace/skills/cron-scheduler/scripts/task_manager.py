#!/usr/bin/env python3
"""
Task Manager for Cron Scheduler
Handles CRUD operations for scheduled tasks
"""

import json
import os
from datetime import datetime
from croniter import croniter


class TaskManager:
    def __init__(self, config_file="tasks.json"):
        self.config_file = config_file
        self.tasks = {}
        self.load_tasks()

    def load_tasks(self):
        """Load tasks from configuration file"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self.tasks = data
                    elif isinstance(data, list):
                        # Convert list to dict with id as key
                        self.tasks = {task.get('id', f'task_{i}'): task for i, task in enumerate(data)}
            else:
                self.tasks = {}
        except Exception as e:
            print(f"Error loading tasks: {str(e)}")
            self.tasks = {}

    def save_tasks(self):
        """Save tasks to configuration file"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(list(self.tasks.values()), f, indent=2)
        except Exception as e:
            print(f"Error saving tasks: {str(e)}")

    def create_task(self, task_def):
        """Create a new task"""
        # Validate required fields
        required_fields = ['id', 'name', 'schedule', 'command']
        for field in required_fields:
            if field not in task_def:
                raise ValueError(f"Missing required field: {field}")

        # Validate cron expression
        if not self.validate_cron_expression(task_def['schedule']):
            raise ValueError(f"Invalid cron expression: {task_def['schedule']}")

        task_id = task_def['id']
        if task_id in self.tasks:
            raise ValueError(f"Task with id '{task_id}' already exists")

        # Set defaults
        task_def.setdefault('enabled', True)
        task_def.setdefault('description', '')
        task_def.setdefault('logging', {
            'level': 'INFO',
            'file': f'{task_id}.log'
        })
        task_def.setdefault('retry_policy', {
            'max_retries': 3,
            'backoff_multiplier': 2
        })

        self.tasks[task_id] = task_def
        self.save_tasks()
        return task_def

    def get_task(self, task_id):
        """Get a specific task"""
        return self.tasks.get(task_id)

    def update_task(self, task_id, updates):
        """Update an existing task"""
        if task_id not in self.tasks:
            raise ValueError(f"Task with id '{task_id}' does not exist")

        task = self.tasks[task_id]
        # Apply updates
        for key, value in updates.items():
            if key != 'id':  # Don't allow changing the ID
                task[key] = value

        # Validate cron expression if it was updated
        if 'schedule' in updates:
            if not self.validate_cron_expression(updates['schedule']):
                raise ValueError(f"Invalid cron expression: {updates['schedule']}")

        self.save_tasks()
        return task

    def delete_task(self, task_id):
        """Delete a task"""
        if task_id not in self.tasks:
            raise ValueError(f"Task with id '{task_id}' does not exist")

        del self.tasks[task_id]
        self.save_tasks()

    def list_tasks(self):
        """List all tasks"""
        return list(self.tasks.values())

    def enable_task(self, task_id):
        """Enable a task"""
        if task_id not in self.tasks:
            raise ValueError(f"Task with id '{task_id}' does not exist")
        
        self.tasks[task_id]['enabled'] = True
        self.save_tasks()

    def disable_task(self, task_id):
        """Disable a task"""
        if task_id not in self.tasks:
            raise ValueError(f"Task with id '{task_id}' does not exist")
        
        self.tasks[task_id]['enabled'] = False
        self.save_tasks()

    def validate_cron_expression(self, cron_expr):
        """Validate cron expression syntax"""
        try:
            # Test with a past date to ensure it's valid
            base_time = datetime.now()
            croniter(cron_expr, base_time)
            return True
        except:
            return False

    def get_next_run_time(self, task_id):
        """Get the next scheduled run time for a task"""
        if task_id not in self.tasks:
            return None

        task = self.tasks[task_id]
        if not task.get('enabled', True):
            return None

        try:
            cron_expr = task['schedule']
            now = datetime.now()
            cron = croniter(cron_expr, now)
            next_run = cron.get_next(datetime)
            return next_run.isoformat()
        except:
            return None

    def get_task_status(self, task_id):
        """Get status information for a task"""
        if task_id not in self.tasks:
            return None

        task = self.tasks[task_id]
        status = {
            'id': task_id,
            'name': task.get('name', ''),
            'enabled': task.get('enabled', True),
            'schedule': task.get('schedule', ''),
            'next_run': self.get_next_run_time(task_id),
            'description': task.get('description', ''),
            'last_run': task.get('last_run'),
            'command': task.get('command', '')
        }

        return status


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Task Manager for Cron Scheduler')
    parser.add_argument('--config', '-c', default='tasks.json', help='Configuration file path')

    subparsers = parser.add_subparsers(dest='action', help='Available actions')

    # Create task
    create_parser = subparsers.add_parser('create', help='Create a new task')
    create_parser.add_argument('--id', required=True, help='Task ID')
    create_parser.add_argument('--name', required=True, help='Task name')
    create_parser.add_argument('--schedule', required=True, help='Cron schedule expression')
    create_parser.add_argument('--command', required=True, help='Command to execute')
    create_parser.add_argument('--description', help='Task description')
    create_parser.add_argument('--disabled', action='store_true', help='Create task as disabled')

    # Get task
    get_parser = subparsers.add_parser('get', help='Get a specific task')
    get_parser.add_argument('--id', required=True, help='Task ID')

    # Update task
    update_parser = subparsers.add_parser('update', help='Update an existing task')
    update_parser.add_argument('--id', required=True, help='Task ID')
    update_parser.add_argument('--name', help='New task name')
    update_parser.add_argument('--schedule', help='New cron schedule expression')
    update_parser.add_argument('--command', help='New command to execute')
    update_parser.add_argument('--description', help='New task description')
    update_parser.add_argument('--enable', action='store_true', help='Enable task')
    update_parser.add_argument('--disable', action='store_true', help='Disable task')

    # Delete task
    delete_parser = subparsers.add_parser('delete', help='Delete a task')
    delete_parser.add_argument('--id', required=True, help='Task ID')

    # List tasks
    subparsers.add_parser('list', help='List all tasks')

    # Status
    status_parser = subparsers.add_parser('status', help='Get status of a task')
    status_parser.add_argument('--id', required=True, help='Task ID')

    args = parser.parse_args()
    manager = TaskManager(config_file=args.config)

    if args.action == 'create':
        try:
            task_def = {
                'id': args.id,
                'name': args.name,
                'schedule': args.schedule,
                'command': args.command
            }
            if args.description:
                task_def['description'] = args.description
            task_def['enabled'] = not args.disabled

            result = manager.create_task(task_def)
            print(f"Task {args.id} created successfully")
            print(json.dumps(result, indent=2))
        except Exception as e:
            print(f"Error creating task: {str(e)}")
            exit(1)

    elif args.action == 'get':
        task = manager.get_task(args.id)
        if task:
            print(json.dumps(task, indent=2))
        else:
            print(f"Task {args.id} not found")
            exit(1)

    elif args.action == 'update':
        updates = {}
        if args.name:
            updates['name'] = args.name
        if args.schedule:
            updates['schedule'] = args.schedule
        if args.command:
            updates['command'] = args.command
        if args.description:
            updates['description'] = args.description
        if args.enable:
            updates['enabled'] = True
        if args.disable:
            updates['enabled'] = False

        if not updates:
            print("No updates specified")
            exit(1)

        try:
            result = manager.update_task(args.id, updates)
            print(f"Task {args.id} updated successfully")
            print(json.dumps(result, indent=2))
        except Exception as e:
            print(f"Error updating task: {str(e)}")
            exit(1)

    elif args.action == 'delete':
        try:
            manager.delete_task(args.id)
            print(f"Task {args.id} deleted successfully")
        except Exception as e:
            print(f"Error deleting task: {str(e)}")
            exit(1)

    elif args.action == 'list':
        tasks = manager.list_tasks()
        print(json.dumps(tasks, indent=2))

    elif args.action == 'status':
        status = manager.get_task_status(args.id)
        if status:
            print(json.dumps(status, indent=2))
        else:
            print(f"Task {args.id} not found")
            exit(1)


if __name__ == "__main__":
    main()