#!/bin/bash
# X-Agent Restart Script
# Usage: ./restart.sh [--dev|--prod]

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
BACKEND_PORT=8000
FRONTEND_PORT=5173

echo -e "${GREEN}"
echo "╔═══════════════════════════════════════╗"
echo "║         X-Agent Restart               ║"
echo "╚═══════════════════════════════════════╝"
echo -e "${NC}"
echo "Mode: $MODE"
echo ""

# ============================================
# Step 1: Force kill all ports and related processes
# ============================================
echo -e "${BLUE}[1/6] Cleaning up ports $BACKEND_PORT and $FRONTEND_PORT...${NC}"

# Kill backend port
BACKEND_PIDS=$(lsof -ti:$BACKEND_PORT 2>/dev/null || true)
if [ -n "$BACKEND_PIDS" ]; then
    echo -e "${YELLOW}Killing processes on port $BACKEND_PORT: $BACKEND_PIDS${NC}"
    echo "$BACKEND_PIDS" | xargs kill -9 2>/dev/null || true
fi

# Kill frontend port
FRONTEND_PIDS=$(lsof -ti:$FRONTEND_PORT 2>/dev/null || true)
if [ -n "$FRONTEND_PIDS" ]; then
    echo -e "${YELLOW}Killing processes on port $FRONTEND_PORT: $FRONTEND_PIDS${NC}"
    echo "$FRONTEND_PIDS" | xargs kill -9 2>/dev/null || true
fi

# Also kill all node/npm/yarn/vite processes related to this project
echo -e "${YELLOW}Cleaning up node processes...${NC}"
pkill -f "vite" 2>/dev/null || true
pkill -f "npm run dev" 2>/dev/null || true
pkill -f "yarn dev" 2>/dev/null || true

# Kill Python processes running x-agent
pkill -f "python.*src.main" 2>/dev/null || true
pkill -f "uvicorn.*8000" 2>/dev/null || true

sleep 2

# Double check ports are free
REMAINING_BACKEND=$(lsof -ti:$BACKEND_PORT 2>/dev/null || true)
REMAINING_FRONTEND=$(lsof -ti:$FRONTEND_PORT 2>/dev/null || true)

if [ -n "$REMAINING_BACKEND" ] || [ -n "$REMAINING_FRONTEND" ]; then
    echo -e "${YELLOW}Force killing remaining processes...${NC}"
    [ -n "$REMAINING_BACKEND" ] && echo "$REMAINING_BACKEND" | xargs kill -9 2>/dev/null || true
    [ -n "$REMAINING_FRONTEND" ] && echo "$REMAINING_FRONTEND" | xargs kill -9 2>/dev/null || true
    sleep 2
fi

# Final check
if lsof -ti:$BACKEND_PORT 2>/dev/null || lsof -ti:$FRONTEND_PORT 2>/dev/null; then
    echo -e "${RED}Warning: Some processes still using ports${NC}"
else
    echo -e "${GREEN}All ports cleared.${NC}"
fi

# ============================================
# Step 2: Setup backend
# ============================================
echo -e "${BLUE}[2/6] Setting up backend...${NC}"
cd "$SCRIPT_DIR/backend"

# Detect Python interpreter
if [ -f "$SCRIPT_DIR/backend/.venv/bin/python" ]; then
    PYTHON="$SCRIPT_DIR/backend/.venv/bin/python"
    PIP="$SCRIPT_DIR/backend/.venv/bin/pip"
    VENV_PATH=".venv"
elif [ -f "$SCRIPT_DIR/backend/venv/bin/python" ]; then
    PYTHON="$SCRIPT_DIR/backend/venv/bin/python"
    PIP="$SCRIPT_DIR/backend/venv/bin/pip"
    VENV_PATH="venv"
else
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    python3 -m venv .venv
    VENV_PATH=".venv"
    PYTHON="$SCRIPT_DIR/backend/.venv/bin/python"
    PIP="$SCRIPT_DIR/backend/.venv/bin/pip"
fi

# Ensure pip
if ! $PYTHON -c "import pip" 2>/dev/null; then
    $PYTHON -m ensurepip --upgrade --quiet 2>/dev/null || true
fi

echo -e "${GREEN}Backend environment ready.${NC}"
echo "Using Python: $PYTHON"

# ============================================
# Step 3: Install backend dependencies
# ============================================
echo -e "${BLUE}[3/6] Installing backend dependencies...${NC}"

# Install core dependencies (with SSL workaround)
echo -e "${YELLOW}Installing core dependencies...${NC}"
$PYTHON -m pip install \
    structlog python-json-logger python-frontmatter uvicorn fastapi starlette pydantic pydantic-settings pyyaml python-dotenv websockets \
    sqlalchemy aiosqlite httpx jinja2 python-multipart apscheduler openai watchdog aiofiles filelock orjson cryptography \
    --trusted-host pypi.tuna.tsinghua.edu.cn \
    --trusted-host pypi.org \
    --trusted-host files.pythonhosted.org 2>&1 | tail -10

if [ -f "pyproject.toml" ]; then
    echo -e "${YELLOW}Installing project dependencies...${NC}"
    $PYTHON -m pip install -e ".[dev]" --trusted-host pypi.tuna.tsinghua.edu.cn --trusted-host pypi.org --trusted-host files.pythonhosted.org 2>&1 | tail -5 || \
    $PYTHON -m pip install -e . --trusted-host pypi.tuna.tsinghua.edu.cn --trusted-host pypi.org --trusted-host files.pythonhosted.org 2>&1 | tail -5 || true
fi

touch .dependencies_installed

# Check for config
if [ ! -f "x-agent.yaml" ] && [ -f "x-agent.yaml.example" ]; then
    cp x-agent.yaml.example x-agent.yaml
fi

echo -e "${GREEN}Backend dependencies installed.${NC}"

# ============================================
# Step 4: Start backend
# ============================================
echo -e "${BLUE}[4/6] Starting backend server...${NC}"

if [ "$MODE" = "prod" ]; then
    $PYTHON -m uvicorn src.main:app --host 0.0.0.0 --port $BACKEND_PORT 2>&1 &
else
    $PYTHON -m src.main 2>&1 &
fi
BACKEND_PID=$!
cd "$SCRIPT_DIR"

# Wait for backend
echo -e "${YELLOW}Waiting for backend to start...${NC}"
MAX_WAIT=15
WAIT_COUNT=0
while [ $WAIT_COUNT -lt $MAX_WAIT ]; do
    if curl -s http://localhost:$BACKEND_PORT/health > /dev/null 2>&1 || \
       curl -s http://localhost:$BACKEND_PORT/api/v1/health/ > /dev/null 2>&1; then
        break
    fi
    sleep 1
    WAIT_COUNT=$((WAIT_COUNT + 1))
    printf "."
done

if [ $WAIT_COUNT -ge $MAX_WAIT ]; then
    echo -e "${RED}\nBackend failed to start within ${MAX_WAIT}s${NC}"
    exit 1
fi

echo -e "${GREEN}\nBackend started successfully on http://localhost:$BACKEND_PORT${NC}"

# ============================================
# Step 5: Start frontend
# ============================================
echo -e "${BLUE}[5/6] Starting frontend...${NC}"
cd "$SCRIPT_DIR/frontend"

if [ ! -d "node_modules" ]; then
    echo -e "${YELLOW}Installing frontend dependencies...${NC}"
    if command -v yarn &> /dev/null; then
        yarn install
    else
        npm install
    fi
fi

if command -v yarn &> /dev/null; then
    yarn dev --port $FRONTEND_PORT 2>&1 &
else
    npm run dev -- --port $FRONTEND_PORT 2>&1 &
fi
FRONTEND_PID=$!
cd "$SCRIPT_DIR"

sleep 3

# ============================================
# Step 6: Verify all services
# ============================================
echo -e "${BLUE}[6/6] Verifying services...${NC}"

BACKEND_OK=false
FRONTEND_OK=false

if curl -s http://localhost:$BACKEND_PORT/health > /dev/null 2>&1 || \
   curl -s http://localhost:$BACKEND_PORT/api/v1/health/ > /dev/null 2>&1; then
    BACKEND_OK=true
fi

if curl -s http://localhost:$FRONTEND_PORT > /dev/null 2>&1; then
    FRONTEND_OK=true
fi

echo ""
echo -e "${GREEN}"
echo "╔═══════════════════════════════════════╗"
echo "║      X-Agent Restart Summary          ║"
echo "╠═══════════════════════════════════════╣"
echo "║   Backend:  http://localhost:8000     ║"
if [ "$BACKEND_OK" = true ]; then
    echo "║            Status: ${GREEN}✓ Running${NC}          ║"
else
    echo "║            Status: ${RED}✗ Failed${NC}           ║"
fi
echo "║   Frontend: http://localhost:5173     ║"
if [ "$FRONTEND_OK" = true ]; then
    echo "║            Status: ${GREEN}✓ Running${NC}          ║"
else
    echo "║            Status: ${RED}✗ Failed${NC}           ║"
fi
echo "╚═══════════════════════════════════════╝"
echo -e "${NC}"

if [ "$BACKEND_OK" = true ] && [ "$FRONTEND_OK" = true ]; then
    echo -e "${GREEN}All services restarted successfully!${NC}"
    echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"
else
    echo -e "${YELLOW}Some services may not have started correctly.${NC}"
    echo -e "${YELLOW}Check logs at: $SCRIPT_DIR/backend/logs/x-agent.log${NC}"
fi