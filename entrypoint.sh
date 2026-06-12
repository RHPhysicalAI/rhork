#!/bin/bash
set -e

export PYTHONUNBUFFERED=1

# Validate required environment variables
if [ -z "$GENESIS_MODE" ]; then
    echo "ERROR: GENESIS_MODE not set (must be 'viewer' or 'streaming')"
    exit 1
fi

if [ -z "$STREAM_PREFIX" ]; then
    echo "ERROR: STREAM_PREFIX not set"
    exit 1
fi

if [ -z "$MEDIAMTX_HOST" ]; then
    echo "WARNING: MEDIAMTX_HOST not set, defaulting to 'mediamtx:554'"
    export MEDIAMTX_HOST="mediamtx:554"
fi

# Set defaults for encoding parameters
export SIM_STEP_FREQ=${SIM_STEP_FREQ:-100}
export ENCODING_BITRATE=${ENCODING_BITRATE:-4000000}
export ENCODING_FPS=${ENCODING_FPS:-30}
export WORLD_FILE=${WORLD_FILE:-/worlds/headless_camera.gen}

if [ "$GENESIS_MODE" = "viewer" ]; then
    echo "Starting Genesis with interactive viewer..."
    python3.11 /app/genesis_streamer.py --mode viewer
elif [ "$GENESIS_MODE" = "streaming" ]; then
    echo "Starting Genesis in headless streaming mode..."
    python3.11 /app/genesis_streamer.py --mode streaming
else
    echo "ERROR: GENESIS_MODE must be 'viewer' or 'streaming', got '$GENESIS_MODE'"
    exit 1
fi
