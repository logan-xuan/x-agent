#!/bin/bash
# X-Agent Combined Startup Script
# Usage: ./start.sh [--dev|--prod]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Default mode
MODE="${1:-dev}"

echo -e "${GREEN}"
echo "╔═══════════════════════════════════════╗"
echo "║         X-Agent Startup               ║"
echo "╚═══════════════════════════════════════╝"
echo -e "${NC}"
echo "Mode: $MODE"
echo ""

# Function to cleanup background processes on exit
cleanup() {
    echo ""
    echo -e "${YELLOW}Shutting down services...${NC}"
    if [ ! -z "$BACKEND_PID" ]; then
        kill $BACKEND_PID 2>/dev/null || true
    fi
    if [ ! -z "$FRONTEND_PID" ]; then
        kill $FRONTEND_PID 2>/dev/null || true
    fi
    # Kill any processes on our ports
    lsof -ti:8000 | xargs kill -9 2>/dev/null || true
    lsof -ti:5173 | xargs kill -9 2>/dev/null || true
    echo -e "${GREEN}Services stopped.${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM

# Kill any existing processes on our ports
echo -e "${YELLOW}Checking for existing processes...${NC}"
lsof -ti:8000 | xargs kill -9 2>/dev/null || true
lsof -ti:5173 | xargs kill -9 2>/dev/null || true

# Start backend
echo -e "${BLUE}Starting backend...${NC}"
cd "$SCRIPT_DIR/backend"

# Check for venv
if [ -d "venv" ]; then
    source venv/bin/activate
elif [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Check for config
if [ ! -f "x-agent.yaml" ] && [ -f "x-agent.yaml.example" ]; then
    cp x-agent.yaml.example x-agent.yaml
    echo -e "${YELLOW}Created x-agent.yaml from example. Please configure your API keys.${NC}"
fi

# Start backend in background
python -m src.main 2>&1 &
BACKEND_PID=$!
cd "$SCRIPT_DIR"

# Wait for backend to start
echo -e "${YELLOW}Waiting for backend to start...${NC}"
sleep 3

# Check if backend is healthy
if curl -s http://localhost:8000/api/v1/health/ > /dev/null 2>&1; then
    echo -e "${GREEN}Backend started successfully on http://localhost:8000${NC}"
else
    echo -e "${RED}Backend may not have started correctly. Check logs above.${NC}"
fi

# Start frontend
echo -e "${BLUE}Starting frontend...${NC}"
cd "$SCRIPT_DIR/frontend"

# Start frontend in background
if command -v yarn &> /dev/null; then
    yarn dev --port 5173 2>&1 &
else
    npm run dev -- --port 5173 2>&1 &
fi
FRONTEND_PID=$!
cd "$SCRIPT_DIR"

# Wait for frontend to start
sleep 2

echo ""
echo -e "${GREEN}"
echo "╔═══════════════════════════════════════╗"
echo "║   X-Agent is running!                 ║"
echo "╠═══════════════════════════════════════╣"
echo "║   Frontend:  http://localhost:5173    ║"
echo "║   Backend:   http://localhost:8000    ║"
echo "║   API Docs:  http://localhost:8000/docs (dev mode)║"
echo "╚═══════════════════════════════════════╝"
echo -e "${NC}"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"
echo ""

# Wait for either process to exit
wait $BACKEND_PID $FRONTEND_PID 2>/dev/null || true

# Cleanup on exit
cleanup
