#!/bin/bash

# Installation script for Cron Scheduler Framework
set -e

echo "Installing Cron Scheduler Framework..."

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is required but not installed."
    exit 1
fi

# Check if pip is installed
if ! command -v pip3 &> /dev/null; then
    echo "Error: pip3 is required but not installed."
    exit 1
fi

# Install required Python packages
echo "Installing required Python packages..."
pip3 install croniter

# Create necessary directories if they don't exist
mkdir -p ~/.cron-scheduler/config
mkdir -p ~/.cron-scheduler/logs
mkdir -p ~/.cron-scheduler/data

# Copy default configuration
if [ ! -f ~/.cron-scheduler/config/tasks.json ]; then
    echo "[]" > ~/.cron-scheduler/config/tasks.json
    echo "Created default tasks.json file"
fi

# Make scripts executable
chmod +x scheduler_daemon.py
chmod +x task_manager.py
chmod +x validator.py

echo "Installation completed!"
echo ""
echo "To get started:"
echo "1. Edit ~/.cron-scheduler/config/tasks.json to define your tasks"
echo "2. Run the scheduler: python3 scripts/scheduler_daemon.py start"
echo ""
echo "Example task definition:"
echo "{"
echo "  \"id\": \"backup-task\","
echo "  \"name\": \"Daily backup\","
echo "  \"schedule\": \"0 2 * * *\","
echo "  \"command\": \"/path/to/backup/script.sh\","
echo "  \"enabled\": true,"
echo "  \"description\": \"Daily backup at 2 AM\""
echo "}"