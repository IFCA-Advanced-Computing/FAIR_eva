#!/bin/bash

# Entrypoint script for FAIR_eva Docker container
# This script handles environment variables and launches the fair-eva application

# Set default values for environment variables
FAIR_EVA_HOST=${FAIR_EVA_HOST:-0.0.0.0}
FAIR_EVA_PORT=${FAIR_EVA_PORT:-9090}
FAIR_EVA_LOGLEVEL=${FAIR_EVA_LOGLEVEL:-info}
START_CMD=${START_CMD:-fair-eva}

# Build the command to run fair-eva
CMD="$START_CMD --host $FAIR_EVA_HOST --port $FAIR_EVA_PORT"

# Transform FAIR_EVA_LOGLEVEL to boolean for --debug flag
# If FAIR_EVA_LOGLEVEL is set to "debug", enable the --debug option
if [ "$FAIR_EVA_LOGLEVEL" = "debug" ]; then
    CMD="$CMD --debug"
fi

# Execute the command
echo "Starting FAIR_eva with command: $CMD"
exec $CMD
