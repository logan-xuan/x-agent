#!/bin/bash
# X-Agent Frontend Startup Script
# Usage: ./start-frontend.sh [--dev|--prod]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$SCRIPT_DIR/frontend"

# Default mode
MODE="${1:-dev}"
PORT=5173

echo -e "${GREEN}Starting X-Agent Frontend...${NC}"
echo "Mode: $MODE"
echo "Frontend directory: $FRONTEND_DIR"

# Check if we're in the right directory
if [ ! -d "$FRONTEND_DIR" ]; then
    echo -e "${RED}Error: Frontend directory not found at $FRONTEND_DIR${NC}"
    exit 1
fi

cd "$FRONTEND_DIR"

# Kill any process using port 5173
if lsof -ti:$PORT > /dev/null 2>&1; then
    echo -e "${YELLOW}Port $PORT is in use, killing existing process...${NC}"
    kill -9 $(lsof -ti:$PORT) 2>/dev/null || true
    sleep 1
fi

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo -e "${YELLOW}Dependencies not found, installing...${NC}"
    if command -v yarn &> /dev/null; then
        yarn install
    else
        npm install
    fi
    echo -e "${GREEN}Dependencies installed.${NC}"
fi

# Start the dev server
echo -e "${GREEN}Starting development server on http://localhost:$PORT${NC}"

if [ "$MODE" = "prod" ]; then
    if command -v yarn &> /dev/null; then
        yarn build && yarn preview --port $PORT
    else
        npm run build && npm run preview -- --port $PORT
    fi
else
    if command -v yarn &> /dev/null; then
        yarn dev --port $PORT
    else
        npm run dev -- --port $PORT
    fi
fi
