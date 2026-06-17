#!/bin/bash
#
# Copyright IBM Corp. 2024 - 2026
# SPDX-License-Identifier: Apache-2.0
#
#
# test_setup.sh
#
# Script to test the visualization service setup
# This will perform basic tests to ensure the scripts are working correctly

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_SCRIPT="${SCRIPT_DIR}/start_visualization_service.sh"
INIT_SCRIPT="${SCRIPT_DIR}/visualization-service"
CRONTAB_SCRIPT="${SCRIPT_DIR}/setup_crontab.sh"
LOG_DIR="${SCRIPT_DIR}/logs"
TEST_LOG="${LOG_DIR}/test_setup.log"

# Ensure log directory exists
mkdir -p "${LOG_DIR}"

# Logging function
log() {
  local level="$1"
  local message="$2"
  local timestamp=$(date "+%Y-%m-%d %H:%M:%S")
  echo "[${timestamp}] [${level}] ${message}" | tee -a "${TEST_LOG}"
}

# Function to check if a file exists and is executable
check_file() {
  local file="$1"
  local description="$2"
  
  if [ -f "${file}" ]; then
    if [ -x "${file}" ]; then
      log "PASS" "${description} exists and is executable"
      return 0
    else
      log "WARN" "${description} exists but is not executable"
      chmod +x "${file}"
      log "INFO" "Made ${description} executable"
      return 1
    fi
  else
    log "FAIL" "${description} does not exist"
    return 2
  fi
}

# Function to check if a Python script exists
check_python_script() {
  local file="$1"
  local description="$2"
  
  if [ -f "${file}" ]; then
    log "PASS" "${description} exists"
    
    # Check if it's a valid Python script
    if python3 -m py_compile "${file}" 2>/dev/null; then
      log "PASS" "${description} is a valid Python script"
      return 0
    else
      log "FAIL" "${description} has syntax errors"
      return 1
    fi
  else
    log "FAIL" "${description} does not exist"
    return 2
  fi
}

# Function to check if OCP credentials exist
check_ocp_credentials() {
  local kubeconfig="${1:-/root/auth/kubeconfig}"
  local password_file="${2:-/root/auth/kubeadmin-password}"
  local test_kubeconfig="${3:-/opt/root/auth/kubeconfig}"
  local test_password_file="${4:-/opt/root/auth/kubeadmin-password}"
  
  if [ -f "${kubeconfig}" ]; then
    log "PASS" "Kubeconfig found at ${kubeconfig}"
  elif [ -f "${test_kubeconfig}" ]; then
    log "PASS" "Kubeconfig found at test location ${test_kubeconfig}"
  else
    log "FAIL" "Kubeconfig not found at ${kubeconfig} or ${test_kubeconfig}"
    return 1
  fi
  
  if [ -f "${password_file}" ]; then
    log "PASS" "Kubeadmin password found at ${password_file}"
  elif [ -f "${test_password_file}" ]; then
    log "PASS" "Kubeadmin password found at test location ${test_password_file}"
  else
    log "FAIL" "Kubeadmin password not found at ${password_file} or ${test_password_file}"
    return 1
  fi
  
  return 0
}

# Function to check if oc command is available
check_oc_command() {
  if command -v oc >/dev/null 2>&1; then
    log "PASS" "oc command is available"
    
    # Check if oc is working
    if oc version >/dev/null 2>&1; then
      log "PASS" "oc command is working"
      return 0
    else
      log "WARN" "oc command is available but not working properly"
      return 1
    fi
  else
    log "FAIL" "oc command is not available"
    return 2
  fi
}

# Function to check if Python is available
check_python() {
  if command -v python3 >/dev/null 2>&1; then
    log "PASS" "Python 3 is available"
    
    # Check Python version
    python_version=$(python3 --version 2>&1)
    log "INFO" "Python version: ${python_version}"
    return 0
  else
    log "FAIL" "Python 3 is not available"
    return 1
  fi
}

# Main test function
run_tests() {
  log "INFO" "Starting visualization service setup tests"
  
  # Check script files
  check_file "${SERVICE_SCRIPT}" "Service script"
  check_file "${INIT_SCRIPT}" "Init.d script"
  check_file "${CRONTAB_SCRIPT}" "Crontab setup script"
  
  # Check Python scripts
  check_python_script "${SCRIPT_DIR}/auto_update_visualization.py" "Auto-update script"
  check_python_script "${SCRIPT_DIR}/web_interface.py" "Web interface script"
  
  # Check dependencies
  check_python
  check_oc_command
  check_ocp_credentials
  
  # Check if we can run the service script with --help
  if [ -x "${SERVICE_SCRIPT}" ]; then
    log "INFO" "Testing service script help..."
    if "${SERVICE_SCRIPT}" --help >/dev/null 2>&1; then
      log "PASS" "Service script help works"
    else
      log "WARN" "Service script help failed"
    fi
  fi
  
  log "INFO" "Tests completed"
}

# Run the tests
run_tests

# Print summary
echo ""
echo "Test Summary:"
echo "============="
passes=$(grep "PASS" "${TEST_LOG}" | wc -l)
warnings=$(grep "WARN" "${TEST_LOG}" | wc -l)
failures=$(grep "FAIL" "${TEST_LOG}" | wc -l)

echo "Passes: ${passes}"
echo "Warnings: ${warnings}"
echo "Failures: ${failures}"

if [ ${failures} -gt 0 ]; then
  echo ""
  echo "ATTENTION: There were test failures. Please check the log for details:"
  echo "${TEST_LOG}"
  exit 1
elif [ ${warnings} -gt 0 ]; then
  echo ""
  echo "ATTENTION: There were warnings. Please check the log for details:"
  echo "${TEST_LOG}"
  exit 0
else
  echo ""
  echo "All tests passed! The setup appears to be working correctly."
  exit 0
fi

