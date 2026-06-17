# Policies and Events Visualization System

This system provides visualization for policy and event data in OpenShift Container Platform (OCP) environments.

## Components

1. **Data Extraction**: Scripts to extract policy and event data from Cassandra
2. **Web Interface**: A web server to visualize the extracted data
3. **Auto-update**: Scheduled updates of the visualization data

## Key Features

- **Interactive Policy Browser**: View and manage temporal grouping and pattern policies
- **Event Analysis**: Detailed event tables with JSON payload inspection
- **Global Search**: Real-time text search across all policies and events
- **Advanced Filter**: Build complex queries with multiple conditions, operators, and AND/OR logic
- **Policy Deployment**: Deploy selected policies directly to Policy Registry
- **Data Export**: Export policies and events to CSV format
- **Authentication & Security**: User management with password hashing and session timeout
- **Audit Logging**: Track user activity and policy deployments
- **Auto-refresh**: Configurable automatic data updates

## Setup and Configuration

### Prerequisites

- Python 3.9+
- OpenShift Container Platform (OCP) environment
- Access to Cassandra pods in the OCP environment

**Note**: For OCP deployments, the system uses the IBM NOI MIME classification service container image (`cp.icr.io/cp/noi/ea-mime-classification-service`) which provides Python 3.11 runtime. No custom Dockerfile is needed.

### Installation

1. Clone this repository
2. Configure the system using the configuration files
3. Run the setup script to install the service

```bash
# Install the service
./setup_crontab.sh

# Start the service
./start_visualization_service.sh
```

### Accessing the Web Interface

After starting the service, you can access the web interface using a web browser:

1. **URL**:
   - Local access: http://localhost:5000
   - Remote access: http://SERVER_IP:5000 (replace SERVER_IP with your server's IP address)

2. **Authentication**:
   - You will be presented with a welcome page that includes login and account creation options
   - Use the credentials configured in users.csv or create a new account through the interface
   - Default users: admin, operator, viewer (if configured)

3. **Troubleshooting Access**:
   - Ensure the server is running (`ps aux | grep web_interface.py`)
   - Check that port 5000 is open in your firewall
   - Verify bind_address in web_interface_config.ini (0.0.0.0 for all interfaces)

### Configuration Files

#### Auto Update Configuration (`auto_update_config.ini`)

```ini
[general]
# Update interval in minutes
update_interval = 60

# Output directory for extracted data
output_dir = output

# Whether to use Python script for extraction (true) or shell script (false)
use_python_script = true

[ocp]
# OCP login credentials
username = admin
password = changeme
api_url = https://api.ocp.example.com:6443

# Namespace where Cassandra is deployed
namespace = 

# Release name for Cassandra
release_name = 
```

#### Web Interface Configuration (`web_interface_config.ini`)

```ini
[general]
# Port to listen on
port = 5000

# IP address to bind to (0.0.0.0 for all interfaces, 127.0.0.1 for localhost only)
bind_address = 0.0.0.0

# Directory with CSV files
output_dir = output

# Path to event instances export file
event_instances = event_instances_export.csv

# Enable access logging
access_log = true

# Enable debug timing
debug_timing = false

[security]
# Enable CORS (Cross-Origin Resource Sharing)
enable_cors = true

# Allowed origins for CORS (comma-separated, * for all)
cors_origins = *

# Enable basic authentication
enable_auth = true

# Force login page instead of browser popup
force_login_page = true

# Path to users CSV file (username,password_hash)
users_file = users.csv

# Session timeout in minutes (0 to disable)
session_timeout = 30

# Username and password for basic authentication (legacy, prefer users.csv)
username = admin
password = changeme
```

## Authentication System

The system includes a secure authentication mechanism with the following features:

### Audit Logging

The system includes comprehensive audit logging for security and compliance:

1. **Logged Events**:
   - User logins (successful and failed attempts)
   - User logouts
   - Session timeouts
   - User registrations
   - Policy deployments

2. **Log Format**:
   - Timestamp
   - Event type
   - Username
   - Client IP address
   - Status (success/failed)
   - Additional details when relevant

3. **Configuration**:
   - Enable/disable audit logging via `enable_audit` in web_interface_config.ini
   - Configurable log file path via `audit_log_file`
   - Log rotation with configurable maximum size and backup count
   - Default: 10MB max size with 5 backup files

4. **Security Benefits**:
   - Track user activity for compliance requirements
   - Detect suspicious login attempts
   - Monitor policy deployment actions
   - Investigate security incidents

### Authentication Methods

The system supports three authentication methods in decreasing order of security:

1. **Hashed Passwords in users.csv** (Recommended)
   - Passwords are securely hashed and stored in the users.csv file
   - Managed through the manage_users.py utility
   - Most secure option with proper password protection

2. **Multiple Users in Configuration** (Legacy)
   - Defined in web_interface_config.ini: `users = username1:password1,username2:password2`
   - Passwords stored in plain text
   - Maintained for backward compatibility

3. **Single User in Configuration** (Legacy)
   - Defined in web_interface_config.ini: `username = admin` and `password = changeme`
   - Simplest but least secure option
   - Maintained for backward compatibility

All three methods can coexist, with the more secure methods taking precedence. For best security practices, it is recommended to use the users.csv approach with hashed passwords.

### Password Hashing

When using the recommended users.csv approach, passwords are stored as secure hashes using PBKDF2 with SHA-256, which provides:
- Protection against rainbow table attacks
- Resistance to brute force attacks through multiple iterations
- Unique salt for each password

### User Management

#### Command-line Utility

A dedicated utility (`manage_users.py`) is provided for administrators to manage user credentials:

```bash
# Add a new user (will prompt for password)
./manage_users.py add username

# Add a user with password specified in command line
./manage_users.py add username --password mypassword

# Delete a user
./manage_users.py delete username

# List all users
./manage_users.py list

# Verify a password
./manage_users.py verify username
```

#### Self-service Registration

Users can also create their own accounts through the web interface when `force_login_page` is enabled:

1. Navigate to the welcome page
2. Click on the "Create Account" tab
3. Enter a username and password
4. Submit the form to create an account

The system will automatically:
- Check if the username is available
- Hash the password securely
- Store the credentials in the users.csv file
- Allow immediate login with the new account

### Welcome and Authentication Page

When `force_login_page` is enabled in the configuration, users will be presented with a welcome page that includes:

1. **Welcome Message**: A brief introduction to the Policies & Events Visualization system
2. **Login Form**: For existing users to authenticate
3. **Account Creation**: A tab for new users to create accounts (currently hidden but can be enabled)

This enhanced authentication experience provides:
- Better user experience compared to browser's basic authentication popup
- Custom styling consistent with the application
- More informative error messages
- Secure authentication with password hashing
- Support for both cookie-based and header-based authentication

### Authentication Flow

1. When a user accesses the system, the server checks if authentication is required
2. If authentication is required and `force_login_page` is enabled, the welcome page is displayed
3. The user can either:
   - Login with existing credentials
   - Create a new account (when enabled)
4. Upon successful authentication, the user is automatically redirected to the visualization interface
5. The browser stores the authentication token in session storage for subsequent requests
6. On future visits, if the user has a valid authentication token stored, they will be automatically logged in

#### Technical Implementation

The authentication system uses several mechanisms to ensure a smooth user experience:

1. **Cookie-based Authentication**: Credentials are securely stored in HTTP-only cookies
2. **Session Storage Backup**: For browsers that don't support cookies, credentials are stored in session storage
3. **Automatic Redirection**: After successful login, users are redirected to the main interface
4. **Secure Token Handling**: Authentication tokens are processed securely and not exposed in URLs
5. **Multiple Authentication Methods**: The system checks for credentials in:
   - HTTP Authorization header
   - Cookies
   - Session storage
   - Form submissions
6. **Session Timeout**: Automatic logout after a configurable period of inactivity
7. **Logout Button**: Allows users to manually end their session

#### Session Timeout

The system includes an automatic session timeout feature for enhanced security:

1. **Configuration**: Set the timeout duration in minutes using the `session_timeout` parameter in `web_interface_config.ini`
   - Default: 30 minutes
   - Set to 0 to disable the timeout feature

2. **Behavior**:
   - Users are automatically logged out after the specified period of inactivity
   - Activity is tracked through user interactions (clicks, keyboard input, scrolling)
   - A warning dialog appears 60 seconds before timeout, allowing users to extend their session
   - If no action is taken, the user is automatically logged out and redirected to the login page

3. **Implementation Details**:
   - Server-side session tracking with timestamp updates on each authenticated request
   - Client-side inactivity detection using JavaScript event listeners
   - Cookie max-age aligned with the session timeout setting
   - Graceful timeout handling with clear user notifications

4. **Security Benefits**:
   - Reduces risk of unauthorized access on unattended devices
   - Automatically terminates inactive sessions to free up resources
   - Provides a consistent security policy across the application

#### Testing Authentication

For testing purposes, a fallback authentication mechanism is included that allows any user to log in with the password "netcool". This feature can be disabled in production by removing the fallback code from the `_check_auth` and `do_POST` methods in `web_interface.py`.

To use the fallback authentication:
1. Enter any username (e.g., "admin", "operator", "tester")
2. Enter the password "netcool"
3. Click Login

This will bypass the normal password verification process and allow immediate access to the system.

## Environment Auto-Detection

The system automatically detects whether it's running:
1. In a pod without the `oc` command
2. In a pod with the `oc` command
3. Outside a pod

Based on this detection, it chooses the appropriate data extraction method:
- Python script for environments without `oc` command
- Shell script for environments with `oc` command

## Namespace and Release Name Auto-Detection

The system can automatically determine:
- The namespace where Cassandra is deployed
- The release name used for Cassandra

This simplifies configuration in standard deployments.

## Service Management

The system can be installed as a service that:
- Starts automatically on system boot
- Performs periodic data updates
- Provides a web interface for visualization

## Troubleshooting

### Common Issues

1. **Authentication failures**:
   - Verify user credentials in users.csv
   - Check that the password hash format is correct
   - Clear browser cookies and session storage
   - Ensure the login form is submitting correctly
   - Check server logs for authentication errors
   - Verify that the users.csv file has the correct permissions
   - If you're unexpectedly logged out, check if the session timeout is configured correctly

2. **Session timeout issues**:
   - Verify the session_timeout value in web_interface_config.ini
   - Check browser console for JavaScript errors related to session handling
   - Ensure your browser supports cookies and local storage
   - If timeout warnings don't appear, check if JavaScript is enabled in your browser
   - For testing, set a shorter timeout value (e.g., 1-2 minutes)

2. **Data extraction failures**:
   - Verify OCP credentials
   - Check connectivity to Cassandra pods
   - Ensure proper permissions to access Cassandra

3. **Web interface not accessible**:
   - Check bind address and port configuration
   - Verify firewall settings
   - Ensure the service is running

### Logs

- Service logs: `/var/log/visualization-service.log`
- Update logs: Check the output directory for `last_update.json`

## License

This software is proprietary and confidential.