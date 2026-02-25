#!/bin/bash
# Docker Services Helper for YokeFlow Projects
# This script helps manage Docker services for generated projects

set -e

PROJECT_NAME=$1
ACTION=$2

if [ -z "$PROJECT_NAME" ] || [ -z "$ACTION" ]; then
    echo "Usage: $0 <project-name> <start|stop|status|ports>"
    exit 1
fi

PROJECT_DIR="projects/$PROJECT_NAME"

case $ACTION in
    start)
        echo "Starting Docker services for $PROJECT_NAME..."
        cd "$PROJECT_DIR"
        if [ -f docker-compose.yml ]; then
            # Check for port conflicts first
            ./scripts/docker-services-helper.sh "$PROJECT_NAME" ports

            # Start services
            docker-compose up -d
            echo "Services started. Waiting for health checks..."
            sleep 5
            docker-compose ps
        else
            echo "No docker-compose.yml found in $PROJECT_DIR"
        fi
        ;;

    stop)
        echo "Stopping Docker services for $PROJECT_NAME..."
        cd "$PROJECT_DIR"
        if [ -f docker-compose.yml ]; then
            docker-compose down
        fi
        ;;

    status)
        echo "Docker services status for $PROJECT_NAME:"
        cd "$PROJECT_DIR"
        if [ -f docker-compose.yml ]; then
            docker-compose ps
        fi
        ;;

    ports)
        echo "Checking for port conflicts..."
        # Check common ports
        PORTS=(5433 6380 9002 9003 7701)  # Shifted ports for projects
        for PORT in "${PORTS[@]}"; do
            if lsof -i :$PORT > /dev/null 2>&1; then
                echo "⚠️  Port $PORT is already in use!"
                lsof -i :$PORT | grep LISTEN
            else
                echo "✅ Port $PORT is available"
            fi
        done

        # Also check YokeFlow's ports
        echo ""
        echo "YokeFlow service ports (should be in use):"
        if lsof -i :5432 > /dev/null 2>&1; then
            echo "✅ YokeFlow PostgreSQL on 5432"
        fi
        ;;

    *)
        echo "Unknown action: $ACTION"
        echo "Use: start, stop, status, or ports"
        exit 1
        ;;
esac