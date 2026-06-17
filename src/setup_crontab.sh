#!/bin/bash
#
# Copyright IBM Corp. 2024 - 2026
# SPDX-License-Identifier: Apache-2.0
#
#
# setup_crontab.sh
#
# Script to set up crontab entries for the visualization service
# This will add entries to the root crontab to ensure the service
# starts automatically after system reboot and checks periodically
# that the service is running.

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_SCRIPT="${SCRIPT_DIR}/start_visualization_service.sh"
LOG_DIR="${SCRIPT_DIR}/logs"
CRON_LOG="${LOG_DIR}/cron_service_check.log"

# Ensure log directory exists
mkdir -p "${LOG_DIR}"

# Make scripts executable
chmod +x "${SERVICE_SCRIPT}"
if [ -f "${SCRIPT_DIR}/visualization-service" ]; then
    chmod +x "${SCRIPT_DIR}/visualization-service"
fi

# Function to check if a crontab entry exists
crontab_entry_exists() {
    local entry="$1"
    crontab -l 2>/dev/null | grep -F "${entry}" >/dev/null
}

# Function to add a crontab entry if it doesn't exist
add_crontab_entry() {
    local entry="$1"
    local description="$2"
    
    if crontab_entry_exists "${entry}"; then
        echo "Crontab entry for ${description} already exists."
    else
        echo "Adding crontab entry for ${description}..."
        (crontab -l 2>/dev/null; echo "${entry}") | crontab -
    fi
}

echo "Setting up crontab entries for visualization service..."

# Add entry to start service at reboot
add_crontab_entry "@reboot ${SERVICE_SCRIPT} --daemon >> ${CRON_LOG} 2>&1" "service startup at reboot"

# Add entry to check service every 15 minutes
add_crontab_entry "*/15 * * * * ${SCRIPT_DIR}/check_service_running.sh >> ${CRON_LOG} 2>&1" "service monitoring"

# Create the service check script if it doesn't exist
if [ ! -f "${SCRIPT_DIR}/check_service_running.sh" ]; then
    cat > "${SCRIPT_DIR}/check_service_running.sh" << 'EOF'
#!/bin/bash
#
# check_service_running.sh
#
# Script to check if the visualization service is running
# and restart it if necessary

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_SCRIPT="${SCRIPT_DIR}/start_visualization_service.sh"
PID_DIR="${SCRIPT_DIR}/run"
WEB_PID="${PID_DIR}/web_interface.pid"
UPDATE_PID="${PID_DIR}/auto_update.pid"
LOG_DIR="${SCRIPT_DIR}/logs"
CHECK_LOG="${LOG_DIR}/service_check.log"

# Ensure directories exist
mkdir -p "${PID_DIR}"
mkdir -p "${LOG_DIR}"

# Logging function
log() {
    local level="$1"
    local message="$2"
    local timestamp=$(date "+%Y-%m-%d %H:%M:%S")
    echo "[${timestamp}] [${level}] ${message}" >> "${CHECK_LOG}"
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

log "INFO" "Checking visualization service status..."

# Check web interface
if ! is_running "${WEB_PID}"; then
    log "WARN" "Web interface is not running, restarting..."
    ${SERVICE_SCRIPT} --no-update --daemon
    sleep 5
    if is_running "${WEB_PID}"; then
        log "INFO" "Web interface restarted successfully"
    else
        log "ERROR" "Failed to restart web interface"
    fi
else
    log "INFO" "Web interface is running"
fi

# Check auto-update process
if ! is_running "${UPDATE_PID}"; then
    log "WARN" "Auto-update process is not running, restarting..."
    ${SERVICE_SCRIPT} --no-web --daemon
    sleep 5
    if is_running "${UPDATE_PID}"; then
        log "INFO" "Auto-update process restarted successfully"
    else
        log "ERROR" "Failed to restart auto-update process"
    fi
else
    log "INFO" "Auto-update process is running"
fi

log "INFO" "Service check completed"
EOF
    chmod +x "${SCRIPT_DIR}/check_service_running.sh"
    echo "Created service check script: ${SCRIPT_DIR}/check_service_running.sh"
fi

# Create a README file with installation instructions
if [ ! -f "${SCRIPT_DIR}/INSTALL.md" ]; then
    cat > "${SCRIPT_DIR}/INSTALL.md" << 'EOF'
# Visualization Service Installation Guide

This guide explains how to install and configure the Policies and Events Visualization Service.

## Manual Installation

1. Make the scripts executable:
   ```
   chmod +x start_visualization_service.sh
   chmod +x check_service_running.sh
   ```

2. Set up crontab entries:
   ```
   ./setup_crontab.sh
   ```

3. Start the service manually:
   ```
   ./start_visualization_service.sh
   ```

## System Service Installation (init.d)

1. Copy the service script to init.d:
   ```
   sudo cp visualization-service /etc/init.d/
   sudo chmod +x /etc/init.d/visualization-service
   ```

2. Configure the service to start on boot:
   ```
   sudo chkconfig --add visualization-service
   sudo chkconfig visualization-service on
   ```

3. Start the service:
   ```
   sudo service visualization-service start
   ```

4. Check service status:
   ```
   sudo service visualization-service status
   ```

## Configuration

The service uses the following configuration files:
- `auto_update_config.ini`: Configuration for the auto-update process
- OpenShift credentials are read from:
  - `/root/auth/kubeconfig` (or `/opt/root/auth/kubeconfig` for testing)
  - `/root/auth/kubeadmin-password` (or `/opt/root/auth/kubeadmin-password` for testing)

## Logs

Logs are stored in the `logs` directory:
- `web_interface.log`: Web interface logs
- `auto_update.log`: Auto-update process logs
- `visualization_service.log`: Main service logs
- `service_check.log`: Service monitoring logs
- `cron_service_check.log`: Cron job logs

## Troubleshooting

If the service fails to start:
1. Check the log files for errors
2. Ensure the OpenShift credentials are correct
3. Verify that the Python scripts are executable
4. Check that the required Python packages are installed
EOF
    echo "Created installation guide: ${SCRIPT_DIR}/INSTALL.md"
fi

echo "Crontab setup completed."
echo "To manually start the service, run: ${SERVICE_SCRIPT}"
echo "For installation instructions, see: ${SCRIPT_DIR}/INSTALL.md"

