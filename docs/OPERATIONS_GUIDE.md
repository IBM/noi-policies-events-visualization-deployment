# Operations Guide

This guide provides step-by-step instructions for operating the Policy and Event Visualization system in both local and OpenShift environments.

> 📸 **Visual Guide**: For screenshots and visual documentation of all operations, see the [Screenshots Documentation](images/README.md).

## Table of Contents

- [Prerequisites](#prerequisites)
- [Local Operation](#local-operation)
- [OpenShift Operation](#openshift-operation)
- [User Management](#user-management)
- [Troubleshooting](#troubleshooting)
- [Screenshots](#screenshots)

---

## Prerequisites

### Authentication
The system comes with a default admin user:
- **Username**: `admin`
- **Password**: `changeme`

⚠️ **Security Note**: Change the default password immediately after first login using the user management tools.

### Required Access
- OpenShift cluster access with `oc` CLI configured
- Permissions to access Cassandra pods
- Permissions to create/manage deployments (for OCP deployment)

---

## Local Operation

Follow these steps to run the visualization system locally on your machine.

### Step 1: Login to OpenShift Cluster

```bash
# Login to your OpenShift cluster
oc login --server=https://your-cluster-api:6443 --token=your-token

# Verify you're in the correct namespace
oc project your-namespace
```

### Step 2: Extract Policies from Cassandra

```bash
# Navigate to the source directory
cd policies_and_events_visualization/src

# Run the Cassandra extraction script
./copy_policies_details_from_cassandra.sh

# This will create 3 CSV files in the current directory:
# - policies_export.csv
# - policies_events_export.csv
# - event_instances_export.csv
```

**Expected Output**:
```
Extracting policies from Cassandra...
Found 11 policies
Extracting events...
Found 483 events
Extraction complete!
```

### Step 3: Process the Extracted Data

```bash
# Process the CSV files into the format needed by the web interface
python3 process_policies_and_events.py

# This creates/updates files in the output/ directory:
# - output/condition_sets_by_policy.json
# - output/data_updated.signal
# - output/event_instances_export.csv
# - output/events_detail.csv
# - output/last_update.json
# - output/policy_events_payload.csv
# - output/policy_summary.csv
# - output/timestamp_range_hint.json
```

**Expected Output**:
```
Processing policies and events...
Loaded 11 policies
Loaded 483 events
Processing complete!
```

### Step 4: Start the Web Interface

```bash
# Start the web server (default port 5000)
python3 web_interface.py

# Or specify a custom port
python3 web_interface.py --port 8080
```

**Expected Output**:
```
Starting Policy and Event Visualization Service...
Server running on http://0.0.0.0:5000
Authentication: Enabled
Press Ctrl+C to stop
```

### Step 5: Access the Web Interface

1. Open your browser to: **http://localhost:5000**

2. You will see the login page:

   ![Login Page](images/login-page.png)

3. Login with credentials:
   - Username: `admin`
   - Password: `changeme` (or your custom password)

4. After successful login, you will see the policy and event visualization interface

### Step 6: (Optional) Change Default Password

```bash
# Change the admin password
python3 manage_users.py change-password admin

# Follow the prompts to enter new password
```

---

## OpenShift Operation

Follow these steps to deploy and operate the visualization system in OpenShift.

### Step 1: Login to OpenShift Cluster

```bash
# Login to your OpenShift cluster
oc login --server=https://your-cluster-api:6443 --token=your-token

# Switch to the target namespace
oc project your-namespace
```

### Step 2: Deploy the Visualization Service

```bash
# Navigate to the project root
cd policies_and_events_visualization

# Run the interactive setup script
./setup-web-interface.sh

# Follow the prompts:
# 1. Enter namespace (default: current namespace)
# 2. Confirm deployment
# 3. Wait for pods to be ready
```

**Expected Output**:
```
🚀 Policy and Event Visualization Setup
========================================
Namespace: your-namespace
Creating deployment...
✓ Deployment created
✓ Service created
✓ Route created
✓ Pods ready

Access URL: https://policy-viz-your-namespace.apps.your-cluster.com
```

### Step 3: Verify Deployment

```bash
# Check pod status
oc get pods | grep policy-viz

# Check logs
oc logs -f deployment/policy-viz

# Verify route
oc get route policy-viz
```

### Step 4: Access the Web Interface

1. Get the route URL:
   ```bash
   oc get route policy-viz -o jsonpath='{.spec.host}'
   ```

2. Open the URL in your browser

3. You will see the login page:

   ![Login Page](images/login-page.png)

4. Login with default credentials:
   - Username: `admin`
   - Password: `changeme`

### Step 5: Configure Auto-Update (Optional)

For automatic data refresh from Cassandra, see the [Auto-Update Guide](AUTO_UPDATE_GUIDE.md).

**Quick Start**:
```bash
# The auto-update container is already configured in the deployment
# It will automatically refresh data every 5 minutes (configurable)

# Check auto-update logs
oc logs -f deployment/policy-viz -c auto-update
```

---

## User Management

### Adding Users Locally

When running locally, use the `manage_users.py` script:

```bash
cd policies_and_events_visualization/src

# Add a new user
python3 manage_users.py add-user john.doe

# Enter password when prompted
# User will be added to users.csv
```

### Adding Users in OpenShift

To add users to the OCP deployment, you need to update the users.csv file in the pod:

#### Method 1: Add User Locally, Then Copy to Pod

```bash
# Step 1: Add user locally
cd policies_and_events_visualization/src
python3 manage_users.py add-user jane.smith
# Enter password when prompted

# Step 2: Copy updated users.csv to the pod
POD_NAME=$(oc get pods -l app=policy-viz -o jsonpath='{.items[0].metadata.name}')
oc cp users.csv ${POD_NAME}:/opt/app/users.csv

# Step 3: Restart the web interface container to pick up changes
oc rollout restart deployment/policy-viz
```

#### Method 2: Add User Directly in Pod

```bash
# Step 1: Get pod name
POD_NAME=$(oc get pods -l app=policy-viz -o jsonpath='{.items[0].metadata.name}')

# Step 2: Execute manage_users.py in the pod
oc exec -it ${POD_NAME} -- python3 manage_users.py add-user jane.smith

# Step 3: Restart to pick up changes
oc rollout restart deployment/policy-viz
```

### Listing Users

```bash
# Local
python3 manage_users.py list-users

# OpenShift
oc exec -it ${POD_NAME} -- python3 manage_users.py list-users
```

### Changing Passwords

```bash
# Local
python3 manage_users.py change-password username

# OpenShift
oc exec -it ${POD_NAME} -- python3 manage_users.py change-password username
```

### Deleting Users

```bash
# Local
python3 manage_users.py delete-user username

# OpenShift
oc exec -it ${POD_NAME} -- python3 manage_users.py delete-user username
```

---

## Troubleshooting

### Local Operation Issues

#### Issue: "Connection refused" when accessing localhost:5000

**Solution**:
```bash
# Check if the service is running
ps aux | grep web_interface.py

# Check if port 5000 is in use
lsof -i :5000

# Try a different port
python3 web_interface.py --port 5001
```

#### Issue: "No data available" in the web interface

**Solution**:
```bash
# Verify CSV files exist
ls -lh output/*.csv

# Re-run the extraction
./copy_policies_details_from_cassandra.sh

# Re-run the processing
python3 process_policies_and_events.py
```

#### Issue: "Authentication failed" with default credentials

**Solution**:
```bash
# Reset to default admin user
python3 manage_users.py reset-admin

# This creates admin/changeme
```

### OpenShift Operation Issues

#### Issue: Pods not starting

**Solution**:
```bash
# Check pod status
oc get pods

# Check pod events
oc describe pod <pod-name>

# Check logs
oc logs <pod-name>

# Common issues:
# - Image pull errors: Check image registry access
# - Resource limits: Check cluster resources
# - ConfigMap missing: Re-run setup script
```

#### Issue: Route not accessible

**Solution**:
```bash
# Verify route exists
oc get route policy-viz

# Check route configuration
oc describe route policy-viz

# Test from within cluster
oc run test-pod --image=curlimages/curl --rm -it -- curl http://policy-viz:8080
```

#### Issue: Auto-update not working

**Solution**:
```bash
# Check auto-update container logs
oc logs -f deployment/policy-viz -c auto-update

# Verify Cassandra connectivity
oc exec -it <pod-name> -c auto-update -- python3 -c "from cassandra.cluster import Cluster; print('OK')"

# Check configuration
oc exec -it <pod-name> -c auto-update -- cat auto_update_config.ini
```

### User Management Issues

#### Issue: Cannot add users - "Permission denied"

**Solution**:
```bash
# Check file permissions
ls -l users.csv

# Fix permissions
chmod 644 users.csv

# In OCP, ensure the pod has write access to /opt/app
```

#### Issue: Users.csv not found

**Solution**:
```bash
# Create users.csv with default admin
python3 manage_users.py reset-admin

# Or copy from template
cp users.csv.template users.csv
```

---

## Quick Reference

### Local Operation Commands
```bash
# Full workflow
oc login --server=<cluster> --token=<token>
cd policies_and_events_visualization/src
./copy_policies_details_from_cassandra.sh  # Creates 3 CSV files in current dir
python3 process_policies_and_events.py      # Processes CSVs into output/ dir
python3 web_interface.py                    # Start server (default port 5000)
python3 web_interface.py --port 8080        # Or use custom port
```

### OpenShift Operation Commands
```bash
# Deployment
oc login --server=<cluster> --token=<token>
cd policies_and_events_visualization
./setup-web-interface.sh

# Management
oc get pods
oc logs -f deployment/policy-viz
oc rollout restart deployment/policy-viz
```

### User Management Commands
```bash
# Add user
python3 manage_users.py add-user <username>

# Copy to OCP
oc cp users.csv <pod-name>:/opt/app/users.csv
oc rollout restart deployment/policy-viz
```

---

## Next Steps

- **Configure Auto-Update**: See [Auto-Update Guide](AUTO_UPDATE_GUIDE.md)
- **Learn Features**: See [User Guide](USER_GUIDE.md)
- **API Integration**: See [API Documentation](API.md)
- **Development**: See [Developer Guide](DEVELOPER_GUIDE.md)

---

## Screenshots

For detailed visual documentation of all operations covered in this guide, see the [Screenshots Documentation](images/README.md).

The screenshots include:
- **Login Page** - Authentication interface
- **Main Viewer** - Policy and event visualization with filtering
- **Deployment Workflow** - Step-by-step policy deployment process
- **Advanced Filtering** - Complex query builder and results
- **Pattern Analysis** - Temporal pattern policy visualization
- **Data Extraction** - Cassandra export process (copy-policies-cassandra.png)
- **Data Processing** - Transformation pipeline (processing-policies-events.png)
- **OpenShift Setup** - Deployment setup process (setup-ocp-image1.png, setup-ocp-image2.png)

---

## Support

For issues or questions:
1. Check the [Troubleshooting](#troubleshooting) section above
2. Review the [Architecture Documentation](ARCHITECTURE.md)
3. Check application logs for error messages
4. Review the [Screenshots Documentation](images/README.md) for visual guidance
5. Contact your system administrator