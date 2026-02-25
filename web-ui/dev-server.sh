#!/bin/bash
# Robust Next.js dev server startup with auto-restart

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
PORT=3010
MAX_RETRIES=3
RETRY_DELAY=2

echo -e "${GREEN}🚀 Starting Next.js dev server (port $PORT)${NC}"

# Function to check if port is in use
check_port() {
    lsof -ti:$PORT >/dev/null 2>&1
}

# Function to kill process on port
kill_port() {
    if check_port; then
        echo -e "${YELLOW}⚠️  Port $PORT is in use. Killing existing process...${NC}"
        lsof -ti:$PORT | xargs kill -9 2>/dev/null || true
        sleep 1
    fi
}

# Function to start dev server
start_server() {
    # Increase Node.js memory limit to prevent OOM crashes
    export NODE_OPTIONS="--max-old-space-size=4096"

    # Clear Next.js cache if it exists (can cause issues)
    if [ -d ".next" ]; then
        echo -e "${YELLOW}🧹 Clearing Next.js cache...${NC}"
        rm -rf .next
    fi

    # Start the dev server
    npm run dev
}

# Main execution with retry logic
attempt=1
while [ $attempt -le $MAX_RETRIES ]; do
    echo -e "${GREEN}Attempt $attempt of $MAX_RETRIES${NC}"

    # Kill any existing process on the port
    kill_port

    # Start the server
    if start_server; then
        echo -e "${GREEN}✅ Server exited cleanly${NC}"
        exit 0
    else
        exit_code=$?
        echo -e "${RED}❌ Server crashed with exit code $exit_code${NC}"

        if [ $attempt -lt $MAX_RETRIES ]; then
            echo -e "${YELLOW}⏳ Waiting ${RETRY_DELAY}s before retry...${NC}"
            sleep $RETRY_DELAY
            attempt=$((attempt + 1))
        else
            echo -e "${RED}💥 Max retries reached. Server failed to start.${NC}"
            exit 1
        fi
    fi
done
