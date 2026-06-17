#!/bin/bash
#
# Copyright IBM Corp. 2024 - 2026
# SPDX-License-Identifier: Apache-2.0
#
# Wrapper script to run both web_interface.py and auto_update_visualization.py locally
# This script runs both components similar to how they run in the Kubernetes pod

# Default values
SOURCE_DIR="src"
CONFIG_FILE="web_interface_config.ini"
AUTO_UPDATE_CONFIG="auto_update_config.ini"
LOG_DIR="logs"
CASSANDRA_HOST="localhost"
CASSANDRA_PORT="9042"
CASSANDRA_USER="cassandra"
CASSANDRA_PASSWORD="cassandra"

# Function to display usage information
show_usage() {
  echo "Usage: $0 [options]"
  echo ""
  echo "Options:"
  echo "  -h, --help                 Show this help message"
  echo "  -d, --dir DIR              Source directory (default: $SOURCE_DIR)"
  echo "  -c, --config FILE          Web interface config file (default: $CONFIG_FILE)"
  echo "  -a, --auto-config FILE     Auto-update config file (default: $AUTO_UPDATE_CONFIG)"
  echo "  --cassandra-host HOST      Cassandra host (default: $CASSANDRA_HOST)"
  echo "  --cassandra-port PORT      Cassandra port (default: $CASSANDRA_PORT)"
  echo "  --cassandra-user USER      Cassandra username (default: $CASSANDRA_USER)"
  echo "  --cassandra-password PASS  Cassandra password (default: $CASSANDRA_PASSWORD)"
  echo "  --no-auto-update           Don't run the auto-update script"
  echo ""
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  key="$1"
  case $key in
    -h|--help)
      show_usage
      exit 0
      ;;
    -d|--dir)
      SOURCE_DIR="$2"
      shift 2
      ;;
    -c|--config)
      CONFIG_FILE="$2"
      shift 2
      ;;
    -a|--auto-config)
      AUTO_UPDATE_CONFIG="$2"
      shift 2
      ;;
    --cassandra-host)
      CASSANDRA_HOST="$2"
      shift 2
      ;;
    --cassandra-port)
      CASSANDRA_PORT="$2"
      shift 2
      ;;
    --cassandra-user)
      CASSANDRA_USER="$2"
      shift 2
      ;;
    --cassandra-password)
      CASSANDRA_PASSWORD="$2"
      shift 2
      ;;
    --no-auto-update)
      NO_AUTO_UPDATE=1
      shift
      ;;
    *)
      echo "Unknown option: $1"
      show_usage
      exit 1
      ;;
  esac
done

# Ensure the source directory exists
if [ ! -d "$SOURCE_DIR" ]; then
  echo "Error: Source directory '$SOURCE_DIR' not found."
  exit 1
fi

# Ensure the config files exist
if [ ! -f "$SOURCE_DIR/$CONFIG_FILE" ]; then
  echo "Error: Web interface config file '$SOURCE_DIR/$CONFIG_FILE' not found."
  exit 1
fi

if [ -z "$NO_AUTO_UPDATE" ] && [ ! -f "$SOURCE_DIR/$AUTO_UPDATE_CONFIG" ]; then
  echo "Error: Auto-update config file '$SOURCE_DIR/$AUTO_UPDATE_CONFIG' not found."
  exit 1
fi

# Create logs directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Set environment variables for Cassandra connection
export CASSANDRA_HOST="$CASSANDRA_HOST"
export CASSANDRA_PORT="$CASSANDRA_PORT"
export CASSANDRA_CLIENT_USERNAME="$CASSANDRA_USER"
export CASSANDRA_CLIENT_PASSWORD="$CASSANDRA_PASSWORD"
export PYTHONPATH="$SOURCE_DIR:$PYTHONPATH"
export ENABLE_AUTH="1"

# Change to the source directory
cd "$SOURCE_DIR" || exit 1

echo "Starting web interface and auto-update components..."
echo "======================================================="
echo "Source directory: $SOURCE_DIR"
echo "Web interface config: $CONFIG_FILE"
echo "Auto-update config: $AUTO_UPDATE_CONFIG"
echo "Cassandra host: $CASSANDRA_HOST:$CASSANDRA_PORT"
echo "Logs directory: $LOG_DIR"
echo "======================================================="

# Start the auto-update script in the background if not disabled
if [ -z "$NO_AUTO_UPDATE" ]; then
  echo "Starting auto_update_visualization.py in the background..."
  nohup python3 auto_update_visualization.py --config "$AUTO_UPDATE_CONFIG" > "../$LOG_DIR/auto_update.log" 2>&1 &
  AUTO_UPDATE_PID=$!
  echo "Auto-update process started with PID: $AUTO_UPDATE_PID"
  # Save PID to file for later cleanup
  echo $AUTO_UPDATE_PID > "../$LOG_DIR/auto_update.pid"
fi

# Start the web interface in the foreground
echo "Starting web_interface.py in the foreground..."
python3 web_interface.py --config "$CONFIG_FILE"

# This will only execute when the web interface is stopped
echo "Web interface stopped."

# Clean up the auto-update process if it was started
if [ -z "$NO_AUTO_UPDATE" ] && [ -f "../$LOG_DIR/auto_update.pid" ]; then
  AUTO_UPDATE_PID=$(cat "../$LOG_DIR/auto_update.pid")
  echo "Stopping auto-update process (PID: $AUTO_UPDATE_PID)..."
  kill $AUTO_UPDATE_PID 2>/dev/null || true
  rm -f "../$LOG_DIR/auto_update.pid"
fi

echo "All processes stopped."

