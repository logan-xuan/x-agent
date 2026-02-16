#!/bin/bash
# X-Agent Backend Restart Script
# Usage: ./restart-backend.sh [--dev|--prod]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"

# Default mode
MODE="${1:-dev}"

echo -e "${GREEN}Restarting X-Agent Backend...${NC}"
echo "Mode: $MODE"
echo "Backend directory: $BACKEND_DIR"

# Function to cleanup background processes
cleanup() {
    echo -e "${YELLOW}Stopping existing backend services if running...${NC}"
    # Kill any processes on backend port
    lsof -ti:8000 | xargs kill -9 2>/dev/null || true
    echo -e "${GREEN}Old backend services stopped.${NC}"
}

# Stop any existing backend services
cleanup

# Check if we're in the right directory
if [ ! -d "$BACKEND_DIR" ]; then
    echo -e "${RED}Error: Backend directory not found at $BACKEND_DIR${NC}"
    exit 1
fi

cd "$BACKEND_DIR"

# Check if virtual environment exists
if [ ! -d "venv" ] && [ ! -d ".venv" ]; then
    echo -e "${YELLOW}Virtual environment not found, creating one...${NC}"
    python3 -m venv venv
fi

# Activate virtual environment
if [ -d "venv" ]; then
    source venv/bin/activate
elif [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Install dependencies if needed
if [ ! -f ".dependencies_installed" ]; then
    echo -e "${YELLOW}Installing dependencies...${NC}"
    pip install -e ".[dev]" --quiet
    touch .dependencies_installed
    echo -e "${GREEN}Dependencies installed.${NC}"
fi

# Check for config file
if [ ! -f "x-agent.yaml" ]; then
    if [ -f "x-agent.yaml.example" ]; then
        echo -e "${YELLOW}Config file not found, copying from example...${NC}"
        cp x-agent.yaml.example x-agent.yaml
        echo -e "${GREEN}Config file created. Please edit x-agent.yaml with your API keys.${NC}"
    else
        echo -e "${RED}Error: No configuration file found. Please create x-agent.yaml${NC}"
        exit 1
    fi
fi

# Start the server
echo -e "${GREEN}Starting server on http://localhost:8000${NC}"
if [ "$MODE" = "prod" ]; then
    python -m uvicorn src.main:app --host 0.0.0.0 --port 8000
else
    python -m src.main
fi