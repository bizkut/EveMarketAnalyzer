#!/bin/bash

# Wait for the Celery worker to be ready
echo "Waiting for Celery worker..."
until celery -A app.tasks.worker inspect ping; do
  >&2 echo "Celery worker not available - sleeping"
  sleep 1
done
echo "Celery worker is ready."

# Start the Uvicorn server
echo "Starting Uvicorn server..."
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload