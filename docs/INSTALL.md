# Installation Guide

Complete installation instructions for NOI Policy & Event Visualization.

> **📖 After Installation**: See the [Operations Guide](OPERATIONS_GUIDE.md) for step-by-step instructions on running and operating the system.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Local Development Setup](#local-development-setup)
- [Kubernetes/OpenShift Deployment](#kubernetesopenshift-deployment)
- [Configuration](#configuration)
- [User Management](#user-management)
- [Troubleshooting](#troubleshooting)
- [Next Steps](#next-steps)

---

## Prerequisites

### All Environments

- **Python 3.9+** - Required (tested and developed on 3.9.x; 3.8+ may work but untested)
- **pip** - Python package manager
- **Git** - For cloning the repository

### Kubernetes/OpenShift Deployment

- **kubectl** or **oc** CLI - For cluster management and data extraction
- **Cluster access** - Permissions to create deployments, services, and routes
- **Namespace access** - Ability to deploy to target namespace
- **Cassandra access** - Required for extracting policy/event data using `copy_policies_details_from_cassandra.sh`
- **Policy Registry** - For policy deployment functionality (see [IBM NOI Policy Registry Setup](https://www.ibm.com/docs/en/noi/1.6.15?topic=guardrails-enabling-policy-registry-service-swagger))

**Note**: OCP deployments use the IBM NOI MIME classification service container image (`cp.icr.io/cp/noi/ea-mime-classification-service`) which provides Python 3.11 runtime. No custom Dockerfile is required.

### Optional

- **Cassandra/Scylla driver (Python)** - For automated data updates (auto-update feature only, requires scylla-driver package)
- **Additional RAM** - Memory usage scales with dataset size (~50MB for 14K policies + 70K events)

---

## Local Development Setup

### 1. Clone the Repository

```bash
git clone https://github.com/your-org/noi-policy-visualization.git
cd noi-policy-visualization/policies_and_events_visualization
```

### 2. Install Python Dependencies

```bash
cd src
pip install -r requirements.txt
```

**Dependencies:**
- **None required!** The web interface uses only Python standard library (http.server)
- All external packages are optional and only needed for Cassandra data extraction:
  - scylla-driver (Cassandra data extraction)
  - orjson (fast JSON parsing, optional)
  - psutil (performance monitoring, optional)
  - tqdm (progress bars, optional)
  - pandas (test scripts only, optional)

### 3. Configure the Application

The configuration file `web_interface_config.ini` is included in the repository.

Edit `web_interface_config.ini` if needed:

```ini
[general]
port = 5000
bind_address = 0.0.0.0  # Use 127.0.0.1 for localhost only
output_dir = output
event_instances = event_instances_export.csv

[security]
enable_auth = true
force_login_page = true
users_file = users.csv
session_timeout = 30  # minutes
enable_cors = true
cors_origins = *
```

### 4. Create Initial User (if needed)

A default admin user may already exist. If not, create one:

```bash
python manage_users.py add admin
# Enter password when prompted
```

### 5. Prepare Data Files

The application expects these files in the `src` directory:

```
src/
├── policies_export.csv          # Policy definitions
├── policies_events_export.csv   # Policy-event mappings
├── event_instances_export.csv   # Event data (optional)
└── output/
    ├── policy_summary.csv       # Processed policy data
    ├── events_detail.csv        # Processed event data
    ├── policy_events_payload.csv # Event payloads
    └── condition_sets_by_policy.json # Pattern data
```

**Extract Data from Cassandra:**

```bash
# Run the extraction script (requires oc CLI and cluster access)
./copy_policies_details_from_cassandra.sh

# Then process the extracted data
python process_policies_and_events.py
```

### 6. Start the Server

```bash
# Start with default port (5000)
python web_interface.py

# Or specify a custom port
python web_interface.py --port 8080
```

**Output:**
```
[audit] Audit logging enabled, writing to logs/audit.log
Loaded 1 users from users.csv
[config] Loaded configuration from web_interface_config.ini
[server] Configuration:
[server] - Bind address: 0.0.0.0
[server] - Port: 5000
[server] - Output directory: output
[server] - Authentication: Enabled
[server] - CORS: Enabled
[INFO] Loading data into memory...
[memory] Loading data into memory...
[memory] Loading policy_events_payload.csv...
[memory]   Loaded 69,990 payload rows total
[memory] Building search index for fast queries...
[memory]   Indexed 174,834 search terms covering 13,998 policies
[memory] ═══════════════════════════════════════════════════════
[memory] Data loaded successfully into memory:
[memory] ───────────────────────────────────────────────────────
[memory]   Policies:          14,002 records  (~   4.9 MB)
[memory]   Events Detail:          0 records  (~   0.0 MB)
[memory]   Events Payload:    69,990 records  (~  43.3 MB)
[memory]   Pattern Sets:           4 records  (~   0.0 MB)
[memory] ───────────────────────────────────────────────────────
[memory]   TOTAL MEMORY:    ~48.2 MB
[memory] ═══════════════════════════════════════════════════════
[server] Starting on http://localhost:5000 (bind=0.0.0.0)
[server] Server is accessible at: http://127.0.0.1:5000
```

### 7. Access the Application

Open your browser to:
- **Local**: http://localhost:5000
- **Network**: http://YOUR_IP:5000

**Login** with the credentials you created.

---

## Kubernetes/OpenShift Deployment

### Method 1: Automated Setup Script (Recommended)

The setup script handles everything automatically:

```bash
cd policies_and_events_visualization
./setup-web-interface.sh
```

**The script will:**
1. ✅ Check cluster connection
2. ✅ Auto-detect current namespace
3. ✅ Prompt for configuration
4. ✅ Deploy the application
5. ✅ Copy data files
6. ✅ Create route (optional)
7. ✅ Verify deployment

**Interactive Prompts:**
```
Kubernetes namespace [noi12]: <press Enter>
Deployment name [evtmanager-ibm-ea-web-interface]: <press Enter>
Source directory [src]: <press Enter>
Create route? (y/n): y
```

**Estimated Time:** 5-10 minutes

---

## Configuration

### Configuration File Reference

#### `web_interface_config.ini`

```ini
[general]
# Server settings
port = 5000                    # Port to listen on
bind_address = 0.0.0.0         # IP to bind (0.0.0.0 = all interfaces)

# Data settings
output_dir = output            # Directory with processed data
event_instances = event_instances_export.csv

# Performance
access_log = true              # Log HTTP requests
debug_timing = false           # Show timing information

[security]
# Authentication
enable_auth = true             # Require login
force_login_page = true        # Use custom login page
users_file = users.csv         # User credentials file
session_timeout = 30           # Session timeout in minutes (0 = no timeout)

# CORS
enable_cors = true             # Enable cross-origin requests
cors_origins = *               # Allowed origins (* = all)

# Audit
enable_audit = true            # Enable audit logging
audit_log_file = logs/audit.log
audit_max_bytes = 10485760     # 10MB
audit_backup_count = 5         # Keep 5 backup files

[deployment]
# Policy deployment settings
policy_registry_url = https://policy-registry.example.com
max_concurrent_deployments = 5
deployment_timeout = 60        # seconds
```


### Data Directory Structure

```
policies_and_events_visualization/
├── README.md
├── setup-web-interface.sh
├── run_local.sh
├── web-interface-deployment-modified.yaml
├── docs/
│   ├── INSTALL.md
│   ├── USER_GUIDE.md
│   ├── ARCHITECTURE.md
│   ├── DEVELOPER_GUIDE.md
│   └── AUTO_UPDATE_GUIDE.md
└── src/
    ├── web_interface.py
    ├── web_interface_config.ini
    ├── templates/
    │   └── viewer.html
    ├── policy_event_viewer.html
    ├── users.csv
    ├── manage_users.py
    ├── process_policies_and_events.py
    ├── copy_policies_details_from_cassandra.sh
    ├── requirements.txt
    ├── policies_export.csv
    ├── policies_events_export.csv
    ├── event_instances_export.csv
    ├── output/
    │   ├── policy_summary.csv
    │   ├── events_detail.csv
    │   ├── policy_events_payload.csv
    │   ├── event_instances_export.csv
    │   ├── condition_sets_by_policy.json
    │   ├── last_update.json
    │   └── data_updated.signal
    ├── logs/
    │   └── (audit.log, access.log - created at runtime)
    └── static/
        ├── app.js
        ├── styles.css
        └── config-handler.js
```

---

## User Management

### Command-Line Tool

The `manage_users.py` utility provides user management:

```bash
# Add a new user (interactive)
python manage_users.py add username

# Add user with password
python manage_users.py add username --password mypassword

# Delete a user
python manage_users.py delete username

# List all users
python manage_users.py list

# Verify password
python manage_users.py verify username

# Change password
python manage_users.py change username
```

### Users File Format

`users.csv` format:

```csv
username,password_hash
admin,pbkdf2:sha256:260000$salt$hash
operator,pbkdf2:sha256:260000$salt$hash
viewer,pbkdf2:sha256:260000$salt$hash
```

**Security Notes:**
- Passwords are hashed using PBKDF2-SHA256
- Each password has a unique salt
- 260,000 iterations for brute-force resistance
- Never store plain-text passwords

---

## Troubleshooting

### Common Issues

#### 1. Port Already in Use

**Error:** `Address already in use: 0.0.0.0:5000`

**Solution:**
```bash
# Find process using port 5000
lsof -i :5000
# or
netstat -tulpn | grep 5000

# Kill the process
kill -9 <PID>

# Or use a different port
python web_interface.py --port 8080
```

#### 2. Permission Denied

**Error:** `Permission denied: 'users.csv'`

**Solution:**
```bash
# Fix file permissions
chmod 644 users.csv
chmod 755 output/

# Fix ownership
chown -R $USER:$USER .
```

#### 3. Module Not Found

**Error:** `ModuleNotFoundError: No module named 'scylla_driver'` or similar

**Solution:**
```bash
# Install dependencies
pip install -r requirements.txt

# Or install individually
pip install scylla-driver orjson psutil tqdm
```

#### 4. Authentication Failures

**Error:** `Invalid username or password`

**Solutions:**
```bash
# Verify user exists
python manage_users.py list

# Reset password
python manage_users.py change username

# Check users.csv format
cat users.csv

# Clear browser cookies
# In browser: Settings > Privacy > Clear browsing data
```

#### 5. Data Files Not Found

**Error:** `FileNotFoundError: 'policies_export.csv'`

**Solution:**
```bash
# Check file exists
ls -la *.csv

# Extract from Cassandra
cd src/
./copy_policies_details_from_cassandra.sh
python process_policies_and_events.py
```

#### 6. Kubernetes Pod Not Starting

**Error:** Pod in `CrashLoopBackOff` state

**Diagnosis:**
```bash
# Check pod status
oc get pods

# View pod events
oc describe pod <pod-name>

# Check logs
oc logs <pod-name>

# Check previous logs
oc logs <pod-name> --previous
```

**Common Causes:**
- Missing configuration files
- Incorrect file permissions
- Missing dependencies
- Port conflicts
- Resource limits

#### 7. Route Not Accessible

**Error:** Cannot access route URL

**Solutions:**
```bash
# Verify route exists
oc get route

# Check route details
oc describe route policy-viz

# Test from inside cluster
oc exec <pod-name> -- curl http://localhost:5000

# Check service
oc get svc policy-viz
```

### Debug Mode

Enable debug mode for detailed logging:

```ini
[general]
debug_timing = true
access_log = true
```

Or via command line:
```bash
python web_interface.py --debug
```

### Log Files

Check logs for errors:

```bash
# Audit logs (enabled by default)
tail -f logs/audit.log

# Enable access logging (optional)
export ACCESS_LOG=1
python web_interface.py

# Kubernetes logs
oc logs -f deployment/policy-viz
```

### Performance Issues

If the application is slow:

1. **Ensure sufficient memory**:
   - Monitor memory usage on startup
   - Typical: ~50MB for 14K policies + 70K events
   - Scale server resources based on dataset size

2. **Reduce data size**:
   ```bash
   # Filter old events
   python process_policies_and_events.py --days 30
   ```

3. **Increase resources** (Kubernetes):
   ```yaml
   resources:
     requests:
       memory: "512Mi"
       cpu: "500m"
     limits:
       memory: "2Gi"
       cpu: "2000m"
   ```

---

## Next Steps

After installation, follow these guides to get started:

1. **[Operations Guide](OPERATIONS_GUIDE.md)** - **START HERE** - Step-by-step instructions for running the system locally or in OCP
2. **[User Guide](USER_GUIDE.md)** - Learn how to use the application features
3. **[Auto-Update Guide](AUTO_UPDATE_GUIDE.md)** - Configure automatic data updates (OCP only)
4. **[API Reference](API.md)** - REST API documentation for integration
5. **[Architecture](ARCHITECTURE.md)** - Understand the system design
6. **[Developer Guide](DEVELOPER_GUIDE.md)** - Contribute to the project

---

## Support

- **Issues**: [GitHub Issues](https://github.com/your-org/repo/issues)
