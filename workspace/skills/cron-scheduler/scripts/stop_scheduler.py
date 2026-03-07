#!/usr/bin/env python3
"""
Script to stop the cron scheduler
"""

import subprocess
import sys
import os
import signal
import psutil
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

def stop_scheduler():
    """Stop the scheduler by finding and terminating the process"""
    scheduler_processes = find_scheduler_processes()
    
    if not scheduler_processes:
        print("No scheduler processes found")
        return True
    
    success = True
    for proc in scheduler_processes:
        try:
            print(f"Stopping scheduler process with PID: {proc.pid}")
            proc.terminate()  # Try graceful termination first
            proc.wait(timeout=5)  # Wait up to 5 seconds for graceful shutdown
            print(f"Scheduler process {proc.pid} stopped gracefully")
        except psutil.TimeoutExpired:
            try:
                print(f"Force killing scheduler process {proc.pid}")
                proc.kill()  # Force kill if it doesn't terminate gracefully
                print(f"Scheduler process {proc.pid} killed")
            except psutil.NoSuchProcess:
                print(f"Process {proc.pid} already terminated")
            except Exception as e:
                print(f"Error killing process {proc.pid}: {str(e)}")
                success = False
        except Exception as e:
            print(f"Error stopping process {proc.pid}: {str(e)}")
            success = False
    
    return success

if __name__ == "__main__":
    if stop_scheduler():
        print("Scheduler stopped successfully")
    else:
        print("Some errors occurred while stopping the scheduler")
        sys.exit(1)