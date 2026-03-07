#!/usr/bin/env python3
"""
Cron Task Scheduler Daemon
Main scheduling daemon that monitors and executes scheduled tasks
"""

import os
import sys
import json
import time
import subprocess
import threading
from datetime import datetime
from croniter import croniter
import sqlite3
import logging
from pathlib import Path

class CronScheduler:
    def __init__(self, config_file="tasks.json", db_file="scheduler.db"):
        self.config_file = config_file
        self.db_file = db_file
        self.tasks = {}
        self.running = False
        self.daemon_thread = None
        
        # Setup logging
        self.setup_logging()
        
        # Initialize database
        self.init_database()
        
        # Load tasks
        self.load_tasks()
    
    def setup_logging(self):
        """Setup logging configuration"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('scheduler.log'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def init_database(self):
        """Initialize the SQLite database for storing execution history"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS execution_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                task_name TEXT,
                scheduled_time TEXT,
                executed_time TEXT,
                status TEXT,
                output TEXT,
                error TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def load_tasks(self):
        """Load tasks from configuration file"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
                    
                    # Handle different possible structures of the config file
                    if isinstance(data, dict):
                        # Check if tasks are under a 'tasks' key (like {"tasks": [...]})
                        if 'tasks' in data and isinstance(data['tasks'], list):
                            # Convert list to dict with id as key
                            self.tasks = {task.get('id', f'task_{i}'): task for i, task in enumerate(data['tasks'])}
                        elif 'tasks' in data and isinstance(data['tasks'], dict):
                            self.tasks = data['tasks']
                        else:
                            # Assume the whole dict is the tasks dict
                            self.tasks = data
                    elif isinstance(data, list):
                        # Convert list to dict with id as key
                        self.tasks = {task.get('id', f'task_{i}'): task for i, task in enumerate(data)}
            else:
                self.logger.info(f"Configuration file {self.config_file} not found, starting with empty task list")
                self.tasks = {}
                
            self.logger.info(f"Loaded {len(self.tasks)} tasks")
        except Exception as e:
            self.logger.error(f"Error loading tasks: {str(e)}")
    
    def save_tasks(self):
        """Save tasks to configuration file"""
        try:
            with open(self.config_file, 'w') as f:
                # Save in the same format as expected by load_tasks
                json.dump({"tasks": list(self.tasks.values())}, f, indent=2)
            self.logger.info("Tasks saved successfully")
        except Exception as e:
            self.logger.error(f"Error saving tasks: {str(e)}")
    
    def validate_cron_expression(self, cron_expr):
        """Validate cron expression syntax"""
        try:
            # Test with a past date to ensure it's valid
            base_time = datetime.now()
            croniter(cron_expr, base_time)
            return True
        except:
            return False
    
    def is_due(self, task):
        """Check if a task is due for execution"""
        if not task.get('enabled', True):
            return False
            
        cron_expr = task.get('cron_expression', task.get('schedule', None))
        if not cron_expr:
            self.logger.error(f"No cron expression found for task {task['id']}")
            return False
            
        last_run = task.get('last_run')
        
        if not self.validate_cron_expression(cron_expr):
            self.logger.error(f"Invalid cron expression for task {task['id']}: {cron_expr}")
            return False
        
        now = datetime.now()
        cron = croniter(cron_expr, now)
        next_run = cron.get_next(datetime)  # Get next scheduled time
        
        # If we don't have a last run time, check if it's time to run now
        if not last_run:
            return True
            
        # Parse last run time and compare
        try:
            last_run_dt = datetime.fromisoformat(last_run.replace('Z', '+00:00')) if last_run else None
            if last_run_dt is None:
                return True  # If no last run recorded, consider it due
            return now >= next_run and last_run_dt < next_run
        except:
            return True  # If parsing fails, assume it's due
    
    def execute_task(self, task):
        """Execute a single task"""
        task_id = task['id']
        command = task.get('command', '')
        log_config = task.get('logging', {})
        
        self.logger.info(f"Executing task {task_id}: {command}")
        
        start_time = datetime.now().isoformat()
        
        try:
            # Execute the command using bash explicitly to ensure proper variable expansion
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                executable='/bin/bash',  # Use bash explicitly for better command substitution support
                timeout=300,  # 5 minute timeout
                env=os.environ  # Pass current environment to subprocess
            )
            
            end_time = datetime.now().isoformat()
            status = "SUCCESS" if result.returncode == 0 else "FAILED"
            
            # Log the result
            self.logger.info(f"Task {task_id} completed with status: {status}, return code: {result.returncode}")
            
            # Save execution history
            self.save_execution_result(
                task_id,
                task.get('name', ''),
                start_time,
                end_time,
                status,
                result.stdout,
                result.stderr
            )
            
            # Update task with last run time
            task['last_run'] = end_time
            
            return result.returncode == 0
            
        except subprocess.TimeoutExpired:
            end_time = datetime.now().isoformat()
            self.logger.error(f"Task {task_id} timed out")
            self.save_execution_result(
                task_id,
                task.get('name', ''),
                start_time,
                end_time,
                "TIMEOUT",
                "",
                "Task exceeded maximum execution time"
            )
            return False
        except Exception as e:
            end_time = datetime.now().isoformat()
            self.logger.error(f"Task {task_id} failed with exception: {str(e)}")
            self.save_execution_result(
                task_id,
                task.get('name', ''),
                start_time,
                end_time,
                "ERROR",
                "",
                str(e)
            )
            return False
    
    def save_execution_result(self, task_id, task_name, scheduled_time, executed_time, status, output, error):
        """Save execution result to database"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO execution_history 
            (task_id, task_name, scheduled_time, executed_time, status, output, error)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (task_id, task_name, scheduled_time, executed_time, status, output, error))
        
        conn.commit()
        conn.close()
    
    def run_scheduler(self):
        """Main scheduler loop"""
        self.logger.info("Starting cron scheduler daemon")
        
        while self.running:
            try:
                for task_id, task in self.tasks.items():
                    if self.is_due(task):
                        # Execute in a separate thread to avoid blocking
                        thread = threading.Thread(target=self.execute_task, args=(task,))
                        thread.start()
                
                # Sleep for a short interval before checking again
                time.sleep(30)  # Check every 30 seconds
                
            except KeyboardInterrupt:
                self.logger.info("Received interrupt signal, stopping scheduler")
                break
            except Exception as e:
                self.logger.error(f"Error in scheduler loop: {str(e)}")
                time.sleep(60)  # Wait a minute before continuing after error
        
        self.logger.info("Scheduler stopped")
    
    def start(self):
        """Start the scheduler daemon"""
        if self.running:
            self.logger.warning("Scheduler already running")
            return
        
        self.running = True
        self.daemon_thread = threading.Thread(target=self.run_scheduler)
        self.daemon_thread.daemon = True
        self.daemon_thread.start()
        self.logger.info("Scheduler started successfully")
    
    def stop(self):
        """Stop the scheduler daemon"""
        self.running = False
        if self.daemon_thread:
            self.daemon_thread.join(timeout=5)  # Wait up to 5 seconds for graceful shutdown
        self.logger.info("Scheduler stopped")
    
    def add_task(self, task):
        """Add a new task to the scheduler"""
        task_id = task.get('id')
        if not task_id:
            raise ValueError("Task must have an 'id' field")
        
        if not self.validate_cron_expression(task.get('cron_expression', task.get('schedule'))):
            raise ValueError(f"Invalid cron expression: {task.get('cron_expression', task.get('schedule'))}")
        
        self.tasks[task_id] = task
        self.save_tasks()
        self.logger.info(f"Added task {task_id}")
    
    def remove_task(self, task_id):
        """Remove a task from the scheduler"""
        if task_id in self.tasks:
            del self.tasks[task_id]
            self.save_tasks()
            self.logger.info(f"Removed task {task_id}")
        else:
            self.logger.warning(f"Task {task_id} not found")
    
    def list_tasks(self):
        """List all tasks"""
        return list(self.tasks.values())
    
    def get_execution_history(self, task_id=None, limit=100):
        """Get execution history, optionally filtered by task_id"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        if task_id:
            cursor.execute('''
                SELECT * FROM execution_history 
                WHERE task_id = ? 
                ORDER BY executed_time DESC 
                LIMIT ?
            ''', (task_id, limit))
        else:
            cursor.execute('''
                SELECT * FROM execution_history 
                ORDER BY executed_time DESC 
                LIMIT ?
            ''', (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return rows

def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Cron Task Scheduler')
    parser.add_argument('--config', '-c', default='tasks.json', help='Configuration file path')
    parser.add_argument('--db', '-d', default='scheduler.db', help='Database file path')
    parser.add_argument('action', choices=['start', 'stop', 'status', 'add-task', 'remove-task', 'list-tasks'], 
                       help='Action to perform')
    parser.add_argument('--task-file', help='Task definition file (for add-task action)')
    
    args = parser.parse_args()
    
    scheduler = CronScheduler(config_file=args.config, db_file=args.db)
    
    if args.action == 'start':
        scheduler.start()
        print("Scheduler started. Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            scheduler.stop()
    
    elif args.action == 'stop':
        scheduler.stop()
        print("Scheduler stopped")
    
    elif args.action == 'status':
        print(f"Scheduler running: {scheduler.running}")
        print(f"Number of tasks: {len(scheduler.tasks)}")
    
    elif args.action == 'add-task':
        if not args.task_file:
            print("Error: --task-file is required for add-task action")
            sys.exit(1)
        
        with open(args.task_file, 'r') as f:
            task = json.load(f)
        
        try:
            scheduler.add_task(task)
            print(f"Task {task['id']} added successfully")
        except Exception as e:
            print(f"Error adding task: {str(e)}")
            sys.exit(1)
    
    elif args.action == 'remove-task':
        if not args.task_file:
            print("Error: --task-file is required for remove-task action")
            sys.exit(1)
        
        with open(args.task_file, 'r') as f:
            task_data = json.load(f)
            task_id = task_data.get('id') or task_data  # Allow task_id to be passed directly
        
        scheduler.remove_task(task_id)
        print(f"Task {task_id} removed successfully")
    
    elif args.action == 'list-tasks':
        tasks = scheduler.list_tasks()
        print("Scheduled tasks:")
        for task in tasks:
            status = "ENABLED" if task.get('enabled', True) else "DISABLED"
            cron_expr = task.get('cron_expression', task.get('schedule', 'N/A'))
            print(f"- {task['id']}: {task['name']} [{cron_expr}] ({status})")

if __name__ == "__main__":
    main()