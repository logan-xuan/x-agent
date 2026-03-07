#!/usr/bin/env python3
"""
Script to start the cron scheduler in the background
"""

import subprocess
import sys
import os
from pathlib import Path

def start_scheduler(config_file="tasks.json", db_file="scheduler.db"):
    """Start the scheduler in the background"""
    try:
        # Get the directory where this script is located
        script_dir = Path(__file__).parent.absolute()
        scheduler_script = script_dir / "scheduler_daemon.py"
        
        # Change to the parent directory of the script (the project root)
        project_dir = script_dir.parent
        os.chdir(project_dir)
        
        # Start the scheduler in the background
        cmd = [
            sys.executable, str(scheduler_script),
            '--config', config_file,
            '--db', db_file,
            'start'
        ]
        
        # Use subprocess.Popen to start in background
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid  # Create new session so it's independent
        )
        
        print(f"Scheduler started with PID: {process.pid}")
        return process.pid
        
    except Exception as e:
        print(f"Error starting scheduler: {str(e)}")
        return None

if __name__ == "__main__":
    pid = start_scheduler()
    if pid:
        print(f"Scheduler started successfully with PID {pid}")
    else:
        print("Failed to start scheduler")
        sys.exit(1)