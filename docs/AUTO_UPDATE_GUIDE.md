# Auto-Update Guide

Complete guide for the automated data pipeline and update system.

> **📖 Prerequisites**: This guide assumes you have already deployed the system. See the [Operations Guide](OPERATIONS_GUIDE.md) for deployment instructions.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Scripts Overview](#scripts-overview)
- [Configuration](#configuration)
- [Deployment Scenarios](#deployment-scenarios)
- [Scheduling Options](#scheduling-options)
- [Monitoring and Logging](#monitoring-and-logging)
- [Troubleshooting](#troubleshooting)
- [Advanced Usage](#advanced-usage)

---

## Overview

The auto-update system provides automated data pipeline functionality that keeps the visualization up-to-date with the latest data from Cassandra. It consists of three main components:

1. **Data Extraction** - Pulls data from Cassandra database
2. **Data Processing** - Transforms and prepares data for visualization
3. **Distribution** - Updates the web interface (and optionally pods)

### Key Features

- ✅ **Automated Pipeline** - Complete end-to-end data refresh
- ✅ **Flexible Scheduling** - Run once, scheduled, or via cron
- ✅ **Environment Detection** - Auto-detects Kubernetes/local environment
- ✅ **Retry Logic** - Resilient to transient failures
- ✅ **Pod Distribution** - Automatically updates multiple pods
- ✅ **Monitoring** - Comprehensive logging and notifications
- ✅ **Configurable** - INI file or command-line configuration

---

## Architecture

### Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    Auto-Update Pipeline                      │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 1: Data Extraction                                     │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Cassandra Database                                     │ │
│  │  ├─ policies table                                      │ │
│  │  ├─ events table                                        │ │
│  │  └─ relationships                                       │ │
│  └────────────────────────────────────────────────────────┘ │
│                            │                                 │
│                            ▼                                 │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Extraction Script                                      │ │
│  │  └─ Shell script (copy_policies_details_*.sh)          │ │
│  └────────────────────────────────────────────────────────┘ │
│                            │                                 │
│                            ▼                                 │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Raw CSV Files                                          │ │
│  │  ├─ policies_export.csv                                │ │
│  │  ├─ policies_events_export.csv                         │ │
│  │  └─ event_instances_export.csv                         │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 2: Data Processing                                    │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  process_policies_and_events.py                         │ │
│  │  ├─ Parse CSV files                                     │ │
│  │  ├─ Deduplicate events                                  │ │
│  │  ├─ Build relationships                                 │ │
│  │  ├─ Create search indexes                               │ │
│  │  └─ Generate summaries                                  │ │
│  └────────────────────────────────────────────────────────┘ │
│                            │                                 │
│                            ▼                                 │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Processed Files (output/)                              │ │
│  │  ├─ policy_summary.csv                                  │ │
│  │  ├─ events_detail.csv                                   │ │
│  │  ├─ policy_events_payload.csv                           │ │
│  │  ├─ condition_sets_by_policy.json                       │ │
│  │  └─ last_update.json                                    │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 3: Distribution (Optional)                            │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Local Mode: Files ready for web interface             │ │
│  └────────────────────────────────────────────────────────┘ │
│                     OR                                       │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Pod Mode: Copy files to Kubernetes pod                │ │
│  │  ├─ Discover pod via kubectl/oc                        │ │
│  │  ├─ Copy to pod                                         │ │
│  │  └─ Verify successful copy                              │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Web Interface Auto-Reload                                   │
│  ├─ Detects data_updated.signal                             │
│  ├─ Reloads data in memory                                  │
│  └─ Updates UI                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## Scripts Overview

### 1. auto_update_visualization.py

**Purpose**: Basic auto-update for local or single-instance deployments

**Features**:
- Extracts data from Cassandra
- Processes data
- Updates local files
- Suitable for development or single-server deployments

**Usage**:
```bash
# Run once
python auto_update_visualization.py --run-once

# Run on schedule (every 60 minutes by default)
python auto_update_visualization.py --schedule

# Use Python script for extraction
python auto_update_visualization.py --run-once --use-python-script true

# Custom config file
python auto_update_visualization.py --config my_config.ini --run-once
```

### 2. auto_update_visualization_copy_to_pod.py

**Purpose**: Advanced auto-update with Kubernetes pod distribution

**Features**:
- All features of basic auto-update
- Discovers visualization pod automatically
- Copies files to the visualization pod
- Suitable for Kubernetes/OpenShift deployments

**Usage**:
```bash
# Run once with pod updates
python auto_update_visualization_copy_to_pod.py --run-once --namespace noi

# Scheduled updates with pod distribution
python auto_update_visualization_copy_to_pod.py --schedule --namespace noi

# Custom deployment name
python auto_update_visualization_copy_to_pod.py \
  --run-once \
  --namespace noi \
  --deployment-name my-web-interface

# Full configuration
python auto_update_visualization_copy_to_pod.py \
  --schedule \
  --namespace noi \
  --deployment-name evtmanager-ea-web-interface \
  --container-name web-interface \
  --use-python-script auto
```

### 3. setup_crontab.sh

**Purpose**: Configure cron jobs for automatic service management

**Features**:
- Sets up cron entries
- Configures service monitoring
- Creates service check script
- Ensures service runs after reboot

**Usage**:
```bash
# Set up cron jobs
./setup_crontab.sh

# This creates:
# - @reboot entry to start service
# - */15 * * * * entry to check service every 15 minutes
# - check_service_running.sh script
```

---

## Configuration

### Configuration File Format

**File**: `auto_update_config.ini`

```ini
[general]
# Update interval in minutes (for scheduled mode)
update_interval_minutes = 60

# Output directory for processed files
output_dir = output

# Timestamp file to track updates
timestamp_file = last_update.json

# Retry configuration
max_retries = 3
retry_delay_seconds = 30

[cassandra]
# Local mode: use local CSV files instead of extracting from Cassandra
local_mode = false

# Reuse existing CSV files (skip extraction)
reuse_csv = false

# Script selection: auto, true, or false
# auto: Auto-detect based on environment
# true: Always use Python script
# false: Always use shell script
force_python_script = auto

[ocp]
# Kubernetes/OpenShift namespace (leave empty for auto-detection)
namespace = 

# Release name (leave empty for auto-detection)
release_name = 

# Deployment name for pod distribution
deployment_name = evtmanager-ea-web-interface

# Container name in pods
container_name = web-interface
```

### Configuration Options Explained

#### General Section

| Option | Default | Description |
|--------|---------|-------------|
| `update_interval_minutes` | 60 | How often to run updates in scheduled mode |
| `output_dir` | output | Directory for processed files |
| `timestamp_file` | last_update.json | File to track update history |
| `max_retries` | 3 | Number of retry attempts on failure |
| `retry_delay_seconds` | 30 | Delay between retry attempts |

#### Cassandra Section

| Option | Default | Description |
|--------|---------|-------------|
| `local_mode` | false | Use local CSV files instead of Cassandra |
| `reuse_csv` | false | Skip extraction, use existing CSV files |
| `force_python_script` | auto | Script selection strategy |

**Script Selection**:
- `auto` - Detects if running in pod without `oc` command
- `true` - Always use Python script (good for pods)
- `false` - Always use shell script (good for local with `oc`)

#### OCP Section

| Option | Default | Description |
|--------|---------|-------------|
| `namespace` | (empty) | Kubernetes namespace |
| `release_name` | (empty) | Release name for Cassandra |
| `deployment_name` | evtmanager-ea-web-interface | Deployment to update |
| `container_name` | web-interface | Container name in pods |

### Command-Line Overrides

Command-line arguments override configuration file settings:

```bash
python auto_update_visualization_copy_to_pod.py \
  --config custom.ini \              # Use custom config file
  --run-once \                       # Run once instead of scheduled
  --use-python-script true \         # Override script selection
  --namespace my-namespace \         # Override namespace
  --deployment-name my-deployment \  # Override deployment name
  --container-name my-container      # Override container name
```

---

## Deployment Scenarios

### Scenario 1: Local Development

**Setup**:
```bash
# Create config file
cat > auto_update_config.ini << EOF
[general]
update_interval_minutes = 30
output_dir = output

[cassandra]
local_mode = false
force_python_script = false

[ocp]
namespace = noi
release_name = evtmanager
EOF

# Run once
python auto_update_visualization.py --run-once
```

**Use Case**: Development environment with local `oc` access

### Scenario 2: Kubernetes Pod (Single Instance)

**Setup**:
```bash
# Config file
cat > auto_update_config.ini << EOF
[general]
update_interval_minutes = 60

[cassandra]
force_python_script = true

[ocp]
namespace = noi
release_name = evtmanager
EOF

# Run scheduled
python auto_update_visualization.py --schedule
```

**Use Case**: Running inside a Kubernetes pod without `oc` command

### Scenario 3: Cron-Based Service Management

**Setup**:
```bash
# Set up cron jobs for service management
./setup_crontab.sh
```

**What it does**:
- Adds crontab entry to start service at system reboot
- Adds crontab entry to check service health every 15 minutes
- Creates `check_service_running.sh` script that:
  - Monitors web interface process
  - Monitors auto-update process (if enabled)
  - Automatically restarts failed processes
  - Logs all checks to `logs/service_check.log`

**Note**: This manages service availability, NOT data update scheduling. For automatic data updates, use Scenario 1 or 2 with built-in scheduler.

**Use Case**: Production environment requiring high availability and automatic service recovery

---

## Scheduling Options

### Option 1: Built-in Scheduler

**Advantages**:
- Simple configuration
- Integrated logging
- Automatic retry logic

**Usage**:
```bash
# Start scheduled updates
python auto_update_visualization.py --schedule

# Runs continuously, updating every N minutes
```

**Configuration**:
```ini
[general]
update_interval_minutes = 60
```

### Option 2: Cron Jobs

**Advantages**:
- System-level scheduling
- Survives script crashes
- Standard Unix tool

**Setup**:
```bash
# Edit crontab
crontab -e

# Add entry (every hour)
0 * * * * cd /path/to/scripts && python auto_update_visualization.py --run-once >> logs/cron.log 2>&1

# Or every 30 minutes
*/30 * * * * cd /path/to/scripts && python auto_update_visualization.py --run-once >> logs/cron.log 2>&1
```

**Cron Schedule Examples**:
```bash
# Every hour at minute 0
0 * * * * command

# Every 30 minutes
*/30 * * * * command

# Every day at 2 AM
0 2 * * * command

# Every Monday at 3 AM
0 3 * * 1 command

# Every 15 minutes during business hours (9 AM - 5 PM)
*/15 9-17 * * * command
```

### Option 3: Kubernetes CronJob

> **⚠️ UNTESTED**: This option has not been tested in production. It may be useful if you want to try it, but use at your own risk.

**Advantages**:
- Native Kubernetes scheduling
- Automatic pod management
- Scalable

**YAML Example**:
```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: policy-viz-update
  namespace: noi
spec:
  schedule: "0 * * * *"  # Every hour
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: updater
            image: policy-viz-updater:latest
            command:
            - python
            - auto_update_visualization_copy_to_pod.py
            - --run-once
            - --namespace
            - noi
            env:
            - name: OCP_NAMESPACE
              value: noi
          restartPolicy: OnFailure
```

**Deploy**:
```bash
kubectl apply -f cronjob.yaml
```

### Option 4: Systemd Timer

> **⚠️ UNTESTED**: This option has not been tested in production. It may be useful if you want to try it, but use at your own risk.

**Advantages**:
- Modern Linux scheduling
- Better than cron for services
- Integrated with systemd

**Timer File** (`/etc/systemd/system/policy-viz-update.timer`):
```ini
[Unit]
Description=Policy Visualization Update Timer
Requires=policy-viz-update.service

[Timer]
OnBootSec=5min
OnUnitActiveSec=1h
Unit=policy-viz-update.service

[Install]
WantedBy=timers.target
```

**Service File** (`/etc/systemd/system/policy-viz-update.service`):
```ini
[Unit]
Description=Policy Visualization Update Service

[Service]
Type=oneshot
WorkingDirectory=/opt/policy-viz
ExecStart=/usr/bin/python3 auto_update_visualization.py --run-once
User=policyuser
StandardOutput=journal
StandardError=journal
```

**Enable**:
```bash
sudo systemctl daemon-reload
sudo systemctl enable policy-viz-update.timer
sudo systemctl start policy-viz-update.timer
```

---

## Monitoring and Logging

### Log Files

**Location**: `logs/` directory

| File | Purpose |
|------|---------|
| `auto_update_visualization.log` | Main update process log |
| `auto_update_visualization_copy_to_pod.log` | Pod distribution log |
| `web_interface.log` | Web server log |
| `service_check.log` | Service monitoring log |
| `cron_service_check.log` | Cron job log |

### Log Format

```
2024-01-15 10:30:45 - auto_update_visualization - INFO - Starting data extraction from Cassandra
2024-01-15 10:31:12 - auto_update_visualization - INFO - Data extraction completed successfully
2024-01-15 10:31:15 - auto_update_visualization - INFO - Starting data processing
2024-01-15 10:32:30 - auto_update_visualization - INFO - Data processing completed successfully
2024-01-15 10:32:31 - auto_update_visualization - INFO - Visualization updated successfully
```

### Monitoring Update Status

**Check Last Update**:
```bash
# View timestamp file
cat output/last_update.json
```

**Output**:
```json
{
  "last_update": "2024-01-15T10:32:31.123456",
  "update_count": 42,
  "last_status": "success"
}
```

**Status Values**:
- `success` - Update completed successfully
- `extraction_failed` - Data extraction failed
- `processing_failed` - Data processing failed
- `pod_copy_failed` - Pod distribution failed
- `none` - No updates yet

### Notification System

**Notification File**: `output/notification.json`

```json
{
  "level": "success",
  "message": "Visualization updated successfully",
  "timestamp": "2024-01-15T10:32:31.123456"
}
```

**Levels**:
- `success` - Update successful
- `error` - Update failed
- `warning` - Partial success

**Extending Notifications**:

> **⚠️ UNTESTED**: The following notification integrations have not been tested. They may be useful if you want to try them, but use at your own risk.

The `send_notification()` function can be extended to send alerts via:
- Email (SMTP)
- Slack webhooks
- PagerDuty
- Custom webhooks

**Example Email Integration** (untested):
```python
def send_notification(config, level, message):
    logger.info(f"Notification [{level}]: {message}")
    
    # Send email for errors
    if level == 'error':
        import smtplib
        from email.mime.text import MIMEText
        
        msg = MIMEText(message)
        msg['Subject'] = f'Policy Viz Update {level.upper()}'
        msg['From'] = 'noreply@example.com'
        msg['To'] = 'admin@example.com'
        
        with smtplib.SMTP('localhost') as s:
            s.send_message(msg)
```

### Health Checks

**Manual Check**:
```bash
# Check if processes are running
ps aux | grep auto_update

# Check recent logs
tail -f logs/auto_update_visualization.log

# Check last update time
cat output/last_update.json | jq '.last_update'
```

**Automated Check** (via `check_service_running.sh`):

> **Note**: The `check_service_running.sh` script is automatically created when you run `./setup_crontab.sh`

```bash
# Run service check manually
./check_service_running.sh

# View check log
tail logs/service_check.log
```

---

## Troubleshooting

### Common Issues

#### Issue 1: Data Extraction Fails

**Symptoms**:
```
ERROR - Data extraction failed
ERROR - STDERR: Connection refused
```

**Solutions**:

1. **Check Cassandra connectivity**:
   ```bash
   # Test connection
   cqlsh cassandra-host 9042
   ```

2. **Verify credentials**:
   ```bash
   # Check environment variables
   echo $CASSANDRA_HOST
   echo $CASSANDRA_USER
   ```

3. **Check namespace/release**:
   ```bash
   # Verify Cassandra pod
   oc get pods -n noi | grep cassandra
   ```

4. **Use local mode for testing**:
   ```ini
   [cassandra]
   local_mode = true
   reuse_csv = true
   ```

#### Issue 2: Script Selection Problems

**Symptoms**:
```
ERROR - oc: command not found
ERROR - Failed to execute shell script
```

**Solutions**:

1. **Force Python script**:
   ```bash
   python auto_update_visualization.py --run-once --use-python-script true
   ```

2. **Or in config**:
   ```ini
   [cassandra]
   force_python_script = true
   ```

3. **Check environment**:
   ```bash
   # Check if in pod
   ls /var/run/secrets/kubernetes.io/serviceaccount
   
   # Check if oc available
   which oc
   ```

#### Issue 3: Pod Copy Fails

**Symptoms**:
```
ERROR - No pod found to copy files to
ERROR - Failed to copy file to pod
```

**Solutions**:

1. **Verify namespace**:
   ```bash
   oc get pods -n noi
   ```

2. **Check deployment name**:
   ```bash
   oc get deployment -n noi
   ```

3. **Verify kubectl/oc access**:
   ```bash
   oc whoami
   kubectl cluster-info
   ```

4. **Check pod labels**:
   ```bash
   oc get pods -n noi --show-labels
   ```

5. **Manual test**:
   ```bash
   oc cp test.txt noi/pod-name:/tmp/test.txt
   ```

#### Issue 4: Permission Denied

**Symptoms**:
```
ERROR - Permission denied: 'output/policy_summary.csv'
ERROR - Cannot create directory
```

**Solutions**:

1. **Check file permissions**:
   ```bash
   ls -la output/
   chmod 755 output/
   ```

2. **Check user**:
   ```bash
   whoami
   id
   ```

3. **Run as correct user**:
   ```bash
   sudo -u policyuser python auto_update_visualization.py --run-once
   ```

#### Issue 5: Memory Issues

**Symptoms**:
```
ERROR - MemoryError
ERROR - Killed
```

**Solutions**:

1. **Increase pod memory**:
   ```yaml
   resources:
     limits:
       memory: 2Gi
     requests:
       memory: 1Gi
   ```

2. **Process in chunks**:
   ```python
   # Modify process_policies_and_events.py
   chunk_size = 10000
   for chunk in pd.read_csv('file.csv', chunksize=chunk_size):
       process_chunk(chunk)
   ```

3. **Use local mode**:
   ```ini
   [cassandra]
   local_mode = true
   ```

### Debug Mode

**Enable Debug Logging**:
```python
# In script
logging.basicConfig(level=logging.DEBUG)
```

**Or via environment**:
```bash
export LOG_LEVEL=DEBUG
python auto_update_visualization.py --run-once
```

**Verbose Output**:
```bash
# Run with verbose output
python auto_update_visualization.py --run-once 2>&1 | tee debug.log
```

---

## Advanced Usage

### Custom Data Pipeline

**Extend the Pipeline**:
```python
# custom_pipeline.py
from auto_update_visualization import run_update_process, load_config

def custom_post_processing():
    """Custom processing after update"""
    # Add custom logic here
    pass

def main():
    config = load_config('auto_update_config.ini')
    
    # Run standard update
    if run_update_process(config):
        # Run custom processing
        custom_post_processing()

if __name__ == "__main__":
    main()
```

### Conditional Updates

**Update Only If Data Changed**:
```python
import hashlib

def get_data_hash():
    """Calculate hash of source data"""
    with open('policies_export.csv', 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()

def should_update():
    """Check if update is needed"""
    current_hash = get_data_hash()
    
    try:
        with open('last_hash.txt', 'r') as f:
            last_hash = f.read().strip()
    except FileNotFoundError:
        last_hash = None
    
    if current_hash != last_hash:
        with open('last_hash.txt', 'w') as f:
            f.write(current_hash)
        return True
    
    return False

if should_update():
    run_update_process(config)
else:
    logger.info("No changes detected, skipping update")
```

---

## Best Practices

### 1. Configuration Management

- ✅ Use separate config files for dev/staging/prod
- ✅ Store configs in version control (without secrets)
- ✅ Use environment variables for sensitive data
- ✅ Document all configuration options

### 2. Scheduling

- ✅ Choose appropriate update frequency (hourly is typical)
- ✅ Avoid peak usage times
- ✅ Use cron for production reliability
- ✅ Monitor update duration

### 3. Error Handling

- ✅ Enable retry logic (3 retries recommended)
- ✅ Set appropriate timeouts
- ✅ Log all errors with context
- ✅ Set up alerting for failures

### 4. Performance

- ✅ Use local mode for testing
- ✅ Reuse CSV files when possible
- ✅ Monitor memory usage
- ✅ Optimize for large datasets

### 5. Monitoring

- ✅ Check logs regularly
- ✅ Monitor update timestamps
- ✅ Set up health checks
- ✅ Track update success rate

---

## References

- [Installation Guide](INSTALL.md)
- [Architecture Guide](ARCHITECTURE.md)
- [User Guide](USER_GUIDE.md)
- [Developer Guide](DEVELOPER_GUIDE.md)