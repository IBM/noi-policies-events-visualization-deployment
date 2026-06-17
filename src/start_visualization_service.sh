#!/bin/bash
#
# Copyright IBM Corp. 2024 - 2026
# SPDX-License-Identifier: Apache-2.0
#
#
# start_visualization_service.sh
# 
# Startup script for the policies and events visualization service
# This script starts both the web interface and the auto-update process
# It can be run manually or as a service from init.d
#
# Usage: ./start_visualization_service.sh [--no-web] [--no-update] [--daemon]
#   --no-web: Don't start the web interface
#   --no-update: Don't start the auto-update process
#   --daemon: Run in daemon mode (for init.d)

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${SCRIPT_DIR}/logs"
WEB_LOG="${LOG_DIR}/web_interface.log"
UPDATE_LOG="${LOG_DIR}/auto_update.log"
MAIN_LOG="${LOG_DIR}/visualization_service.log"
PID_DIR="${SCRIPT_DIR}/run"
WEB_PID="${PID_DIR}/web_interface.pid"
UPDATE_PID="${PID_DIR}/auto_update.pid"
WEB_CONFIG="${SCRIPT_DIR}/web_interface_config.ini"

# OCP configuration
KUBECONFIG_PATH="/root/auth/kubeconfig"
KUBEADMIN_PASSWORD_PATH="/root/auth/kubeadmin-password"
# Fallback paths for testing
TEST_KUBECONFIG_PATH="/opt/root/auth/kubeconfig"
TEST_KUBEADMIN_PASSWORD_PATH="/opt/root/auth/kubeadmin-password"

# Default options
START_WEB=true
START_UPDATE=true
DAEMON_MODE=false

# Process command line arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-web)
      START_WEB=false
      shift
      ;;
    --no-update)
      START_UPDATE=false
      shift
      ;;
    --daemon)
      DAEMON_MODE=true
      shift
      ;;
    *)
      echo "Unknown option: $1"
      echo "Usage: $0 [--no-web] [--no-update] [--daemon]"
      exit 1
      ;;
  esac
done

# Create log and pid directories if they don't exist
mkdir -p "${LOG_DIR}"
mkdir -p "${PID_DIR}"

# Logging function
log() {
  local level="$1"
  local message="$2"
  local timestamp=$(date "+%Y-%m-%d %H:%M:%S")
  echo "[${timestamp}] [${level}] ${message}" | tee -a "${MAIN_LOG}"
}

# Function to check if a process is running
is_running() {
  local pid_file="$1"
  if [[ -f "${pid_file}" ]]; then
    local pid=$(cat "${pid_file}")
    if ps -p "${pid}" > /dev/null 2>&1; then
      return 0  # Process is running
    fi
  fi
  return 1  # Process is not running
}

# Function to determine NOI release name
determine_release_name() {
  log "INFO" "Determining NOI release name..."
  
  local release_name=""
  
  # Try to find NOI release
  release_name=$(oc get noi 2>/dev/null | awk 'NR>1 {print $1; exit}')
  
  # If not found, try NOIHybrid
  if [[ -z "${release_name}" ]]; then
    release_name=$(oc get noihybrid 2>/dev/null | awk 'NR>1 {print $1; exit}')
  fi
  
  # If still not found, prompt user
  if [[ -z "${release_name}" ]]; then
    log "WARN" "Could not find any NOI/NOIHybrid instances"
    return 1
  fi
  
  # Clean up the release name (remove any log messages that might have been captured)
  release_name=$(echo "${release_name}" | grep -v '\[.*\]' | tr -d '[:space:]')
  
  if [[ -z "${release_name}" ]]; then
    log "WARN" "Release name was found but appears to be empty after cleanup"
    return 1
  fi
  
  log "INFO" "Found NOI release name: ${release_name}"
  echo "release name: ${release_name}"
  return 0
}

# Function to login to OCP cluster
ocp_login() {
  log "INFO" "Attempting to login to OCP cluster..."
  
  # Determine which config files to use
  local kubeconfig="${KUBECONFIG_PATH}"
  local password_file="${KUBEADMIN_PASSWORD_PATH}"
  
  if [[ ! -f "${kubeconfig}" ]]; then
    log "WARN" "Kubeconfig not found at ${kubeconfig}, trying test path..."
    kubeconfig="${TEST_KUBECONFIG_PATH}"
  fi
  
  if [[ ! -f "${password_file}" ]]; then
    log "WARN" "Kubeadmin password not found at ${password_file}, trying test path..."
    password_file="${TEST_KUBEADMIN_PASSWORD_PATH}"
  fi
  
  # Check if files exist
  if [[ ! -f "${kubeconfig}" ]]; then
    log "ERROR" "Kubeconfig file not found at ${kubeconfig} or ${TEST_KUBECONFIG_PATH}"
    return 1
  fi
  
  if [[ ! -f "${password_file}" ]]; then
    log "ERROR" "Kubeadmin password file not found at ${password_file} or ${TEST_KUBEADMIN_PASSWORD_PATH}"
    return 1
  fi
  
  # Extract server URL from kubeconfig
  local server_url=$(grep "server:" "${kubeconfig}" | head -n1 | awk '{print $2}')
  if [[ -z "${server_url}" ]]; then
    log "ERROR" "Failed to extract server URL from kubeconfig"
    return 1
  fi
  
  # Get kubeadmin password
  local password=$(cat "${password_file}")
  if [[ -z "${password}" ]]; then
    log "ERROR" "Failed to read kubeadmin password"
    return 1
  fi
  
  # Try to find the namespace where NOI is installed
  log "INFO" "Determining namespace for NOI installation..."
  local namespace=""
  
  # First check if we can get the current project
  if command -v oc >/dev/null 2>&1; then
    # Try to login first with default namespace
    if oc login "${server_url}" -u kubeadmin -p "${password}" >/dev/null 2>&1; then
      log "INFO" "Initial login successful, searching for NOI namespace..."
      
      # Look for NOI resources across all namespaces
      local noi_namespaces=$(oc get noi --all-namespaces 2>/dev/null | awk 'NR>1 {print $1}' || true)
      if [[ -n "${noi_namespaces}" ]]; then
        namespace=$(echo "${noi_namespaces}" | head -n1)
        log "INFO" "Found NOI in namespace: ${namespace}"
      else
        # Try with noihybrid
        noi_namespaces=$(oc get noihybrid --all-namespaces 2>/dev/null | awk 'NR>1 {print $1}' || true)
        if [[ -n "${noi_namespaces}" ]]; then
          namespace=$(echo "${noi_namespaces}" | head -n1)
          log "INFO" "Found NOIHybrid in namespace: ${namespace}"
        fi
      fi
    fi
  fi
  
  # If still not found, try to extract from kubeconfig
  if [[ -z "${namespace}" ]]; then
    namespace=$(grep "namespace:" "${kubeconfig}" | head -n1 | awk '{print $2}')
    if [[ -n "${namespace}" ]]; then
      log "INFO" "Using namespace from kubeconfig: ${namespace}"
    fi
  fi
  
  # If still not found, use default
  if [[ -z "${namespace}" ]]; then
    namespace="default"
    log "WARN" "Could not determine namespace, using '${namespace}'"
  fi
  
  # Login to OCP with the determined namespace
  log "INFO" "Logging in to OCP cluster at ${server_url} with namespace ${namespace}"
  if ! oc login "${server_url}" -n "${namespace}" -u kubeadmin -p "${password}"; then
    log "ERROR" "Failed to login to OCP cluster"
    return 1
  fi
  
  # Determine the release name
  local release_name=$(determine_release_name)
  if [[ -n "${release_name}" ]]; then
    log "INFO" "Using NOI release: ${release_name}"
  else
    log "WARN" "Could not determine NOI release name"
  fi
  
  log "INFO" "Successfully logged in to OCP cluster"
  return 0
}

# Function to start the web interface
start_web_interface() {
  if is_running "${WEB_PID}"; then
    log "WARN" "Web interface is already running with PID $(cat ${WEB_PID})"
    return 0
  fi
  
  log "INFO" "Starting web interface..."
  cd "${SCRIPT_DIR}"
  
  # Create default config file if it doesn't exist
  if [ ! -f "${WEB_CONFIG}" ]; then
    log "INFO" "Creating default web interface configuration file"
    cat > "${WEB_CONFIG}" << 'EOF'
[general]
port = 5000
bind_address = 0.0.0.0
output_dir = output
use_sqlite = false
sqlite_path = output/policy_events.db
event_instances = event_instances_export.csv
access_log = true
debug_timing = false

[security]
enable_cors = true
cors_origins = *
enable_auth = false
username = admin
password = changeme
EOF
  fi
  
  # Extract port from config file
  local port=$(grep "^port" "${WEB_CONFIG}" | cut -d'=' -f2 | tr -d ' ')
  local bind_address=$(grep "^bind_address" "${WEB_CONFIG}" | cut -d'=' -f2 | tr -d ' ')
  local output_dir=$(grep "^output_dir" "${WEB_CONFIG}" | cut -d'=' -f2 | tr -d ' ')
  
  # Use default values if not found in config
  port=${port:-5000}
  bind_address=${bind_address:-0.0.0.0}
  output_dir=${output_dir:-output}
  
  log "INFO" "Web interface will listen on ${bind_address}:${port}"
  
  # Start the web interface in the background with config parameters
  nohup python3 web_interface.py --port "${port}" --output-dir "${output_dir}" --access-log > "${WEB_LOG}" 2>&1 &
  local pid=$!
  
  # Check if process started successfully
  if ps -p "${pid}" > /dev/null 2>&1; then
    echo "${pid}" > "${WEB_PID}"
    log "INFO" "Web interface started with PID ${pid} on ${bind_address}:${port}"
    
    # Get the server's IP address for remote access
    # Use a more portable way to get the IP address
    local ip_address=""
    if command -v ip >/dev/null 2>&1; then
      ip_address=$(ip addr show | grep 'inet ' | grep -v '127.0.0.1' | head -n1 | awk '{print $2}' | cut -d/ -f1)
    elif command -v ifconfig >/dev/null 2>&1; then
      ip_address=$(ifconfig | grep 'inet ' | grep -v '127.0.0.1' | head -n1 | awk '{print $2}')
    fi
    
    if [ -n "${ip_address}" ]; then
      log "INFO" "Web interface is accessible at: http://${ip_address}:${port}"
    fi
    
    return 0
  else
    log "ERROR" "Failed to start web interface"
    return 1
  fi
}

# Function to start the auto-update process
start_auto_update() {
  if is_running "${UPDATE_PID}"; then
    log "WARN" "Auto-update process is already running with PID $(cat ${UPDATE_PID})"
    return 0
  fi
  
  log "INFO" "Starting auto-update process..."
  cd "${SCRIPT_DIR}"
  
  # Get namespace and release name from current context
  local namespace=$(oc project -q 2>/dev/null || echo "")
  
  # Get release name and clean it up
  local release_name=""
  local raw_release=$(determine_release_name 2>/dev/null || echo "")
  if [[ -n "${raw_release}" ]]; then
    # Clean up the release name (remove any log messages and whitespace)
    release_name=$(echo "${raw_release}" | grep -v '\[.*\]' | tr -d '[:space:]')
    log "INFO" "Using cleaned release name: ${release_name}"
  fi
  
  # Create or update config file with namespace and release name
  local config_file="auto_update_config.ini"
  if [ ! -f "${config_file}" ]; then
    log "INFO" "Creating default auto-update configuration file"
    cat > "${config_file}" << EOF
[general]
update_interval_minutes = 60
output_dir = output
timestamp_file = last_update.json
max_retries = 3
retry_delay_seconds = 30

[cassandra]
local_mode = false
reuse_csv = false
force_python_script = auto

[ocp]
namespace = ${namespace}
release_name = ${release_name}
EOF
  else
    # Update existing config file with namespace and release name
    log "INFO" "Updating auto-update configuration with namespace and release name"
    
    # Create a temporary file for the updates
    local temp_file="${config_file}.tmp"
    
    if grep -q "^\[ocp\]" "${config_file}"; then
      # Section exists, update the file with awk instead of sed
      awk -v ns="${namespace}" -v rel="${release_name}" '
        BEGIN { in_ocp = 0; ns_done = 0; rel_done = 0; }
        /^\[ocp\]/ { in_ocp = 1; }
        /^\[/ && !/^\[ocp\]/ { in_ocp = 0; }
        in_ocp && /^namespace/ { print "namespace = " ns; ns_done = 1; next; }
        in_ocp && /^release_name/ { print "release_name = " rel; rel_done = 1; next; }
        { print; }
        END {
          if (in_ocp && !ns_done) print "namespace = " ns;
          if (in_ocp && !rel_done) print "release_name = " rel;
        }
      ' "${config_file}" > "${temp_file}" && mv "${temp_file}" "${config_file}"
    else
      # Section doesn't exist, add it
      cat >> "${config_file}" << EOF

[ocp]
namespace = ${namespace}
release_name = ${release_name}
EOF
    fi
  fi
  
  # Start the auto-update process in the background
  log "INFO" "Starting auto-update process with namespace '${namespace}' and release '${release_name}'"
  nohup python3 auto_update_visualization.py --schedule > "${UPDATE_LOG}" 2>&1 &
  local pid=$!
  
  # Check if process started successfully
  if ps -p "${pid}" > /dev/null 2>&1; then
    echo "${pid}" > "${UPDATE_PID}"
    log "INFO" "Auto-update process started with PID ${pid}"
    return 0
  else
    log "ERROR" "Failed to start auto-update process"
    return 1
  fi
}

# Function to stop processes
stop_process() {
  local pid_file="$1"
  local process_name="$2"
  
  if [[ -f "${pid_file}" ]]; then
    local pid=$(cat "${pid_file}")
    if ps -p "${pid}" > /dev/null 2>&1; then
      log "INFO" "Stopping ${process_name} (PID: ${pid})..."
      kill "${pid}"
      
      # Wait for process to terminate
      local count=0
      while ps -p "${pid}" > /dev/null 2>&1 && [[ ${count} -lt 10 ]]; do
        sleep 1
        ((count++))
      done
      
      # Force kill if still running
      if ps -p "${pid}" > /dev/null 2>&1; then
        log "WARN" "${process_name} did not terminate gracefully, force killing..."
        kill -9 "${pid}" > /dev/null 2>&1
      fi
      
      log "INFO" "${process_name} stopped"
    else
      log "WARN" "${process_name} is not running but PID file exists"
    fi
    rm -f "${pid_file}"
  else
    log "INFO" "${process_name} is not running"
  fi
}

# Function to stop all processes
stop_all() {
  stop_process "${WEB_PID}" "Web interface"
  stop_process "${UPDATE_PID}" "Auto-update process"
}

# Function to check status of all processes
check_status() {
  local web_status="stopped"
  local update_status="stopped"
  
  if is_running "${WEB_PID}"; then
    web_status="running (PID: $(cat ${WEB_PID}))"
  fi
  
  if is_running "${UPDATE_PID}"; then
    update_status="running (PID: $(cat ${UPDATE_PID}))"
  fi
  
  log "INFO" "Web interface: ${web_status}"
  log "INFO" "Auto-update process: ${update_status}"
}

# Main execution
log "INFO" "Starting visualization service..."

# Login to OCP cluster
if ! ocp_login; then
  log "ERROR" "Failed to login to OCP cluster, exiting"
  exit 1
fi

# Start processes based on options
if ${START_WEB}; then
  start_web_interface
fi

if ${START_UPDATE}; then
  start_auto_update
fi

# Check status
check_status

# If running in daemon mode, exit now
if ${DAEMON_MODE}; then
  log "INFO" "Running in daemon mode, exiting script"
  exit 0
fi

# If not in daemon mode, wait for Ctrl+C
log "INFO" "Press Ctrl+C to stop the service"
trap stop_all EXIT
while true; do
  sleep 1
done

