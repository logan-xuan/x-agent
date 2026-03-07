#!/usr/bin/env python3
"""
Script to check the status of the cron scheduler
"""

import psutil
import subprocess
import sys
import os
from pathlib import Path

def find_scheduler_processes():
    """Find all scheduler processes"""
    scheduler_processes = []
    
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            # Look for Python processes running scheduler_daemon.py
            cmdline_list = proc.info['cmdline']
            if cmdline_list:  # Check if cmdline is not None or empty
                cmdline = ' '.join(cmdline_list)
                if ('python' in proc.info['name'].lower() and 
                    'scheduler_daemon.py' in cmdline and 
                    'start' in cmdline):
                    scheduler_processes.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    
    return scheduler_processes

def check_scheduler_status():
    """Check the status of the scheduler"""
    scheduler_processes = find_scheduler_processes()
    
    if not scheduler_processes:
        print("Scheduler is not running")
        return False
    
    print(f"Scheduler is running with {len(scheduler_processes)} process(es):")
    for proc in scheduler_processes:
        try:
            print(f"  - PID: {proc.pid}, Status: {proc.status()}")
        except psutil.NoSuchProcess:
            print(f"  - PID: {proc.pid}, Status: Terminated")
    
    return True

if __name__ == "__main__":
    is_running = check_scheduler_status()
    sys.exit(0 if is_running else 1)