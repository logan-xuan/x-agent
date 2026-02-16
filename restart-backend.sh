#!/bin/bash
# X-Agent Backend Restart Script
# Usage: ./restart-backend.sh [--dev|--prod]

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
BACKEND_PORT=8000

echo -e "${GREEN}"
echo "╔═══════════════════════════════════════╗"
echo "║      X-Agent Backend Restart          ║"
echo "╚═══════════════════════════════════════╝"
echo -e "${NC}"
echo "Mode: $MODE"
echo ""

# ============================================
# Step 1: Force kill port 8000 and related processes
# ============================================
echo -e "${BLUE}[1/5] Cleaning up port $BACKEND_PORT...${NC}"

# Kill by port
PORT_PIDS=$(lsof -ti:$BACKEND_PORT 2>/dev/null || true)
if [ -n "$PORT_PIDS" ]; then
    echo -e "${YELLOW}Found processes on port $BACKEND_PORT: $PORT_PIDS${NC}"
    echo "$PORT_PIDS" | xargs kill -9 2>/dev/null || true
    sleep 1
fi

# Also kill Python processes related to x-agent
pkill -f "python.*src.main" 2>/dev/null || true
pkill -f "uvicorn.*8000" 2>/dev/null || true

# Double check
REMAINING=$(lsof -ti:$BACKEND_PORT 2>/dev/null || true)
if [ -n "$REMAINING" ]; then
    echo -e "${RED}Warning: Port $BACKEND_PORT still occupied, force killing...${NC}"
    echo "$REMAINING" | xargs kill -9 2>/dev/null || true
    sleep 2
fi

# Final check
if lsof -ti:$BACKEND_PORT 2>/dev/null; then
    echo -e "${RED}Error: Port $BACKEND_PORT still occupied after cleanup${NC}"
else
    echo -e "${GREEN}Port $BACKEND_PORT cleared.${NC}"
fi

# ============================================
# Step 2: Check backend directory
# ============================================
echo -e "${BLUE}[2/5] Checking backend directory...${NC}"
if [ ! -d "$BACKEND_DIR" ]; then
    echo -e "${RED}Error: Backend directory not found at $BACKEND_DIR${NC}"
    exit 1
fi
cd "$BACKEND_DIR"
echo -e "${GREEN}Backend directory OK.${NC}"

# ============================================
# Step 3: Setup virtual environment
# ============================================
echo -e "${BLUE}[3/5] Setting up virtual environment...${NC}"
if [ ! -d ".venv" ] && [ ! -d "venv" ]; then
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    python3 -m venv .venv
fi

# Determine venv path
if [ -d ".venv" ]; then
    VENV_PATH=".venv"
elif [ -d "venv" ]; then
    VENV_PATH="venv"
fi

# Activate and ensure pip exists
source "$VENV_PATH/bin/activate"

# Ensure pip is available
if ! command -v pip &> /dev/null; then
    echo -e "${YELLOW}Installing pip...${NC}"
    python -m ensurepip --upgrade --quiet 2>/dev/null || curl -sS https://bootstrap.pypa.io/get-pip.py | python
fi

echo -e "${GREEN}Virtual environment activated: $VENV_PATH${NC}"

# ============================================
# Step 4: Install dependencies
# ============================================
echo -e "${BLUE}[4/5] Installing dependencies...${NC}"

# Ensure pip is available
if ! python -c "import pip" 2>/dev/null; then
    python -m ensurepip --upgrade --quiet 2>/dev/null || true
fi

# Always ensure core dependencies are installed (with SSL workaround)
python -m pip install \
    uvicorn fastapi starlette pydantic pydantic-settings pyyaml python-dotenv websockets \
    sqlalchemy aiosqlite httpx jinja2 python-multipart apscheduler \
    --trusted-host pypi.tuna.tsinghua.edu.cn \
    --trusted-host pypi.org \
    --trusted-host files.pythonhosted.org \
    -q 2>/dev/null || true

# Install project dependencies if pyproject.toml exists
if [ -f "pyproject.toml" ]; then
    python -m pip install -e ".[dev]" --trusted-host pypi.tuna.tsinghua.edu.cn --trusted-host pypi.org --trusted-host files.pythonhosted.org -q 2>/dev/null || \
    python -m pip install -e . --trusted-host pypi.tuna.tsinghua.edu.cn --trusted-host pypi.org --trusted-host files.pythonhosted.org -q 2>/dev/null || true
fi

# Mark dependencies as installed
touch .dependencies_installed
echo -e "${GREEN}Dependencies installed.${NC}"

# Check for config file
if [ ! -f "x-agent.yaml" ]; then
    if [ -f "x-agent.yaml.example" ]; then
        echo -e "${YELLOW}Copying x-agent.yaml from example...${NC}"
        cp x-agent.yaml.example x-agent.yaml
    fi
fi

# ============================================
# Step 5: Start server and verify
# ============================================
echo -e "${BLUE}[5/5] Starting backend server...${NC}"

# Start server in background
if [ "$MODE" = "prod" ]; then
    python -m uvicorn src.main:app --host 0.0.0.0 --port $BACKEND_PORT 2>&1 &
else
    python -m src.main 2>&1 &
fi
SERVER_PID=$!

# Wait for server to start
echo -e "${YELLOW}Waiting for server to start...${NC}"
MAX_WAIT=15
WAIT_COUNT=0
while [ $WAIT_COUNT -lt $MAX_WAIT ]; do
    if curl -s http://localhost:$BACKEND_PORT/health > /dev/null 2>&1 || \
       curl -s http://localhost:$BACKEND_PORT/api/v1/health/ > /dev/null 2>&1; then
        echo ""
        echo -e "${GREEN}"
        echo "╔═══════════════════════════════════════╗"
        echo "║   Backend restarted successfully!     ║"
        echo "╠═══════════════════════════════════════╣"
        echo "║   URL:      http://localhost:8000     ║"
        echo "║   API Docs: http://localhost:8000/docs║"
        echo "║   PID:      $SERVER_PID"
        echo "╚═══════════════════════════════════════╝"
        echo -e "${NC}"
        exit 0
    fi
    sleep 1
    WAIT_COUNT=$((WAIT_COUNT + 1))
    printf "."
done

echo ""
echo -e "${RED}Backend failed to start within ${MAX_WAIT}s${NC}"
echo -e "${YELLOW}Check logs at: $BACKEND_DIR/logs/x-agent.log${NC}"
exit 1