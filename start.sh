#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 Starting DLVideo servers...${NC}"

# Get the script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Store PIDs
BACKEND_PID=""
FRONTEND_PID=""

# Function to kill old processes
kill_old_processes() {
    echo -e "${YELLOW}🔍 Checking for old processes...${NC}"
    
    # Kill old backend (port 8000)
    OLD_BACKEND=$(lsof -ti:8000)
    if [ ! -z "$OLD_BACKEND" ]; then
        echo -e "${BLUE}   Killing old backend (PID: $OLD_BACKEND)${NC}"
        kill -9 $OLD_BACKEND 2>/dev/null
    fi
    
    # Kill old frontend (port 3000)
    OLD_FRONTEND=$(lsof -ti:3000)
    if [ ! -z "$OLD_FRONTEND" ]; then
        echo -e "${BLUE}   Killing old frontend (PID: $OLD_FRONTEND)${NC}"
        kill -9 $OLD_FRONTEND 2>/dev/null
    fi
    
    # Kill any remaining processes
    pkill -f "uvicorn server:app" 2>/dev/null
    pkill -f "craco/dist/scripts/start.js" 2>/dev/null
    pkill -f "react-scripts start" 2>/dev/null
    
    sleep 1
    echo -e "${GREEN}✅ Old processes cleaned up${NC}"
}

# Function to cleanup background processes
cleanup() {
    echo -e "\n${YELLOW}⏹️  Shutting down servers...${NC}"
    
    # Kill backend
    if [ ! -z "$BACKEND_PID" ]; then
        echo -e "${BLUE}   Stopping backend (PID: $BACKEND_PID)${NC}"
        kill -TERM $BACKEND_PID 2>/dev/null
    fi
    
    # Kill frontend and its children
    if [ ! -z "$FRONTEND_PID" ]; then
        echo -e "${BLUE}   Stopping frontend (PID: $FRONTEND_PID)${NC}"
        kill -TERM $FRONTEND_PID 2>/dev/null
        # Kill child processes (craco, webpack-dev-server, etc.)
        pkill -P $FRONTEND_PID 2>/dev/null
    fi
    
    # Force kill remaining processes on ports
    sleep 1
    lsof -ti:8000 | xargs kill -9 2>/dev/null
    lsof -ti:3000 | xargs kill -9 2>/dev/null
    
    # Kill any remaining related processes
    pkill -f "uvicorn server:app" 2>/dev/null
    pkill -f "craco/dist/scripts/start.js" 2>/dev/null
    pkill -f "react-scripts start" 2>/dev/null
    
    echo -e "${GREEN}✅ All servers stopped${NC}"
    exit 0
}

# Set up cleanup on script exit
trap cleanup SIGINT SIGTERM EXIT

# Kill old processes first
kill_old_processes

# Start backend
echo -e "${YELLOW}📡 Starting backend server...${NC}"
cd "${SCRIPT_DIR}/backend"
source venv/bin/activate
python -m uvicorn server:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

# Wait and verify backend started successfully
sleep 3
if ! kill -0 $BACKEND_PID 2>/dev/null; then
    echo -e "${RED}❌ Backend failed to start!${NC}"
    exit 1
fi

# Double check port 8000 is listening
if ! lsof -ti:8000 > /dev/null 2>&1; then
    echo -e "${RED}❌ Backend is not listening on port 8000!${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Backend is running on port 8000${NC}"

# Start frontend in new terminal or background
echo -e "${YELLOW}🌐 Starting frontend server...${NC}"
cd "${SCRIPT_DIR}/frontend"

# Check if yarn is available
if ! command -v yarn &> /dev/null; then
    echo -e "${RED}❌ Yarn not found. Please install yarn first.${NC}"
    exit 1
fi

yarn start &
FRONTEND_PID=$!

# Wait for frontend to start
sleep 3

echo ""
echo -e "${GREEN}✅ Both servers started successfully!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}🔗 Frontend: ${BLUE}http://localhost:3000${NC}"
echo -e "${GREEN}🔗 Backend:  ${BLUE}http://localhost:8000${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}📌 Backend PID:  $BACKEND_PID${NC}"
echo -e "${YELLOW}📌 Frontend PID: $FRONTEND_PID${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}⚡ Press Ctrl+C to stop both servers${NC}"
echo ""

# Wait for all background jobs
wait