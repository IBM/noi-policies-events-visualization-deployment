# NOI Policy & Event Visualization Tool

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![OpenShift](https://img.shields.io/badge/OpenShift-4.x-red.svg)](https://www.openshift.com/)

## Scope

The purpose of this project is to provide a powerful web-based visualization tool for analyzing IBM Netcool Operations Insight (NOI) / Event Manager policies and events. It enables interactive exploration of temporal grouping policies, pattern analysis, and event correlation with deployment management capabilities.

## Usage

This tool provides:

- **Interactive Policy Visualization** - Browse and analyze policies with real-time filtering and search
- **Event Analysis** - Explore events associated with policies, view detailed payloads
- **Temporal Grouping** - Visualize time-based event correlation patterns
- **Pattern Analysis** - Analyze event patterns and condition sets
- **Deployment Management** - Deploy policies directly from the UI
- **Performance Optimized** - Handles millions of events with caching and indexing
- **Secure Authentication** - Multi-user support with password hashing and session management

## 🌟 Features

- **📊 Interactive Policy Visualization** - Browse and analyze policies with real-time filtering and search
- **🔍 Event Analysis** - Explore events associated with policies, view detailed payloads
- **⏱️ Temporal Grouping** - Visualize time-based event correlation patterns
- **🎯 Pattern Analysis** - Analyze event patterns and condition sets
- **🚀 Deployment Management** - Deploy policies directly from the UI (up to 20 at once)
- **📈 Performance Optimized** - Handles millions of events with caching and indexing
- **🔐 Secure Authentication** - Multi-user support with password hashing and session management
- **📱 Responsive UI** - Modern, intuitive interface with DataTables integration
- **🔄 Auto-Refresh** - Hot-reload capability for real-time data updates
- **📤 Data Export** - Export filtered data to CSV for further analysis

## 🚀 Quick Start

### Local Development (5 minutes)

```bash
# Clone the repository
git clone <repository-url>
cd policies_and_events_visualization

# Install dependencies
pip install -r src/requirements.txt

# Configure (edit src/web_interface_config.ini)
cp src/web_interface_config.ini.example src/web_interface_config.ini

# Create a user (will prompt for password)
cd src
python manage_users.py add admin
# Enter password when prompted: e.g., "SecurePass123!"

# Start the server
python web_interface.py

# Access at http://localhost:5000
```

### Kubernetes/OpenShift Deployment (10 minutes)

```bash
# Log in to your cluster
oc login <cluster-url>

# Run the setup script
cd policies_and_events_visualization
./setup-web-interface.sh

# Follow the interactive prompts
# Access via the route URL provided
```

**Automated/Unattended Deployment:**
```bash
# Deploy without prompts (uses defaults, auto-creates route)
./setup-web-interface.sh --yes

# Useful for CI/CD pipelines and automation
```

**Cleanup/Remove Deployment:**
```bash
# Remove all deployment resources (with confirmation)
./setup-web-interface.sh --cleanup

# Remove without confirmation (automated)
./setup-web-interface.sh --cleanup --yes

# This will delete:
# - Deployment and pods
# - Service
# - Route (if exists)
# - ConfigMap
```

**Get Help:**
```bash
./setup-web-interface.sh --help
```

## 🧪 Synthetic Data Generation

The `generate_synthetic_policy_data.py` script creates realistic test data for development and testing. It generates policies, events, and event instances with proper relationships and structure.

### Quick Start

```bash
# Generate 100 policies with default settings (includes 10% pattern policies)
cd src
python generate_synthetic_policy_data.py --num-policies 100

# Output files:
# - generated_policies_export.csv
# - generated_policies_events_export.csv
# - generated_event_instances_export.csv
```

### Features

- **Zero Configuration** - Works without any template files
- **Built-in Templates** - Includes realistic policy structures
- **Pattern Policies** - Automatically generates seasonality and temporal-pattern policies (10% by default)
- **Event Instances** - Creates detailed event payloads with timestamps
- **Scalable** - Generate from 10 to millions of policies
- **Customizable** - Control event counts, pattern ratios, and more

### Usage Examples

```bash
# Basic usage (10 policies + 1 pattern policy + event instances)
python generate_synthetic_policy_data.py

# Large dataset (50K policies + 5K pattern policies)
python generate_synthetic_policy_data.py --num-policies 50000

# Custom event range per policy
python generate_synthetic_policy_data.py --num-policies 1000 --min-events 5 --max-events 50

# Adjust pattern policy ratio (20% instead of default 10%)
python generate_synthetic_policy_data.py --num-policies 100 --pattern-policy-ratio 0.2

# Disable pattern policies
python generate_synthetic_policy_data.py --num-policies 100 --pattern-policy-ratio 0

# Skip event instances generation (faster)
python generate_synthetic_policy_data.py --num-policies 1000 --no-event-instances

# Use custom templates from policies_templates directory (optional)
python generate_synthetic_policy_data.py \
  --policies-template policies_templates/policies_export.txt \
  --events-template policies_templates/policies_events_export.txt \
  --event-instances-template policies_templates/event_instances_export.txt \
  --num-policies 10000

# Custom output prefix
python generate_synthetic_policy_data.py --num-policies 500 --output-prefix test_data
```

### Generated Policy Types

The script generates three types of policies matching real NOI/Event Manager structures:

1. **Standard Correlation Policies** (90% by default)
   - Type: `correlation`
   - GroupID: `related-events`
   - Contains event groups with correlation logic

2. **Seasonality Pattern Policies** (~5% by default)
   - Type: `enrich`
   - GroupID: `seasonality`
   - Includes resolver configuration

3. **Temporal Pattern Policies** (~5% by default)
   - Type: `v2policy`
   - GroupID: `analytics.temporal-patterns`
   - Full v2policy structure with triggers and actions

### Command-Line Options

```
--num-policies N          Number of standard policies (default: 10)
--min-events N            Minimum events per policy (default: 3)
--max-events N            Maximum events per policy (default: 100)
--pattern-policy-ratio F  Pattern policies as ratio (default: 0.1 = 10%)
--pattern-policy-count N  Additional pattern policies to generate
--output-prefix PREFIX    Output file prefix (default: "generated")
--seed N                  Random seed for reproducibility
--no-event-instances      Skip event instances generation
--policies-template FILE  Optional custom policy template
--events-template FILE    Optional custom events template
--pattern-policies-template FILE  Optional pattern policy template
--event-instances-template FILE   Optional event instances template
```

### Performance

- **Fast Generation**: ~5,000 policies/second
- **Memory Efficient**: Streams output for large datasets
- **Progress Tracking**: Real-time progress updates for large generations

## 📁 Key Files

### Root Directory
- **`setup-web-interface.sh`** - Interactive deployment script for Kubernetes/OpenShift
- **`run_local.sh`** - Quick start script for local development
- **`create-route.sh`** - Utility to create/verify OpenShift routes
- **`web-interface-deployment-modified.yaml`** - Kubernetes deployment manifest (uses MIME classification service image for Python 3.11 runtime)

### Source Directory (`src/`)
- **`web_interface.py`** - Main web server application
- **`process_policies_and_events.py`** - Data processing and transformation
- **`manage_users.py`** - User management CLI tool
- **`generate_synthetic_policy_data.py`** - Generate synthetic policy/event data for testing
- **`copy_policies_details_from_cassandra.sh`** - Data extraction from Cassandra
- **`auto_update_visualization.py`** - Automated data refresh service
- **`templates/viewer.html`** - Main UI template (primary)
- **`policy_event_viewer.html`** - Legacy UI template (for compatibility)
- **`static/app.js`** - Frontend JavaScript logic
- **`static/styles.css`** - UI styling
- **`static/config-handler.js`** - Dynamic configuration handler

### Documentation (`docs/`)
- **`INSTALL.md`** - Installation and setup guide
- **`OPERATIONS_GUIDE.md`** - Step-by-step operational procedures for local and OCP environments
- **`USER_GUIDE.md`** - Feature walkthrough and usage
- **`ARCHITECTURE.md`** - Technical design documentation
- **`DEVELOPER_GUIDE.md`** - Development and contribution guide
- **`AUTO_UPDATE_GUIDE.md`** - Automated pipeline documentation
- **`API.md`** - Complete API endpoint reference
- **`images/README.md`** - UI screenshots and visual documentation

## 📸 Screenshots

For detailed visual documentation of the system's user interface and workflows, see the [Screenshots Documentation](docs/images/README.md).

**Quick Preview:**
- [Login Page](docs/images/login-page.png) - Authentication interface
- [Main Viewer](docs/images/policies-events-viewer.png) - Policy and event visualization
- [Advanced Filter](docs/images/advanced-filter.png) - Complex query builder
- [Pattern Policies](docs/images/patterns-policies.png) - Temporal pattern analysis
- [Deployment Workflow](docs/images/policies-deployment.png) - Policy deployment process

The screenshots documentation includes 13 comprehensive images covering:
- User interface and navigation
- Policy deployment workflows
- Advanced filtering and search
- Event payload inspection
- Data extraction and processing
- OpenShift deployment setup

## 📚 Documentation

### Project Documentation

- **[Installation Guide](docs/INSTALL.md)** - Detailed setup instructions for all environments
- **[User Guide](docs/USER_GUIDE.md)** - Complete walkthrough of features and workflows
- **[Architecture](docs/ARCHITECTURE.md)** - Technical design and component overview
- **[Developer Guide](docs/DEVELOPER_GUIDE.md)** - Contributing and development setup
- **[Auto-Update Guide](docs/AUTO_UPDATE_GUIDE.md)** - Automated data pipeline documentation
- **[API Reference](docs/API.md)** - REST API endpoints and usage

### External Resources

- **[IBM NOI Policy Registry Setup](https://www.ibm.com/docs/en/noi/1.6.15?topic=guardrails-enabling-policy-registry-service-swagger)** - Official IBM documentation for enabling and configuring the Policy Registry service and Swagger UI

## 🏗️ Architecture

```
┌─────────────────┐
│   Web Browser   │
└────────┬────────┘
         │ HTTP/HTTPS
┌────────▼────────────────────────────────┐
│     Web Interface (Python)              │
│  - Authentication & Session Management  │
│  - REST API Endpoints                   │
│  - Data Processing & Caching            │
└────────┬────────────────────────────────┘
         │
┌────────▼────────────────────────────────┐
│     Data Layer                          │
│  - CSV Files (policies, events)         │
│  - In-Memory Storage (fast access)      │
│  - JSON (condition sets, metadata)      │
└─────────────────────────────────────────┘
```

**Memory Usage Example** (14K policies, 70K events):
```
[memory] Indexed 174,834 search terms covering 13,998 policies
[memory] Data loaded successfully into memory:
[memory]   Policies:          14,002 records  (~   4.9 MB)
[memory]   Events Detail:          0 records  (~   0.0 MB)
[memory]   Events Payload:    69,990 records  (~  43.3 MB)
[memory]   Pattern Sets:           4 records  (~   0.0 MB)
[memory]   TOTAL MEMORY:    ~48.2 MB
```

> **Note**: Memory usage scales with dataset size. Larger policy/event sets require proportionally more RAM. The application displays memory statistics on startup.

## 🔧 Configuration

Key configuration options in `web_interface_config.ini`:

```ini
[general]
port = 5000
bind_address = 0.0.0.0
output_dir = output

[security]
enable_auth = true
force_login_page = true
session_timeout = 30
users_file = users.csv
```

See [Installation Guide](docs/INSTALL.md) for complete configuration reference.

## 🔐 Security Features

- **Password Hashing** - PBKDF2-SHA256 with unique salts
- **Session Management** - Configurable timeout with activity tracking
- **Audit Logging** - Comprehensive logging of user actions
- **CORS Support** - Configurable cross-origin resource sharing
- **Multi-User** - Role-based access with user management CLI

## 📊 Performance

- **Handles 2M+ events** with optimized caching
- **Sub-second search** with inverted indexing
- **Lazy loading** for large datasets
- **Memory efficient** with streaming CSV processing
- **Concurrent requests** with thread-safe operations

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details on:

- How to submit pull requests
- Coding standards and guidelines
- Development setup
- Testing requirements

For questions or discussions, please open an issue in the [issue tracker](https://github.ibm.com/hdm/noi-aiops-helping-tools-scripts/issues).

Pull requests are very welcome! Make sure your patches are well tested. Ideally create a topic branch for every separate change you make. For example:

1. Fork the repo
2. Create your feature branch (`git checkout -b my-new-feature`)
3. Commit your changes with DCO sign-off (`git commit -s -m 'Add some feature'`)
4. Push to the branch (`git push origin my-new-feature`)
5. Create new Pull Request

## 📝 License

All source files must include a Copyright and License header. The SPDX license header is preferred because it can be easily scanned.

If you would like to see the detailed LICENSE click [here](LICENSE).

```text
#
# Copyright IBM Corp. 2024 - 2026
# SPDX-License-Identifier: Apache-2.0
#
```

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## 📚 Additional Resources

This repository contains the following documentation:

* [LICENSE](LICENSE) - Apache 2.0 License
* [README.md](README.md) - This file
* [CONTRIBUTING.md](CONTRIBUTING.md) - Contribution guidelines
* [MAINTAINERS.md](MAINTAINERS.md) - Project maintainers
* [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) - Community code of conduct
* [SECURITY.md](SECURITY.md) - Security policy and vulnerability reporting
* [CHANGELOG.md](CHANGELOG.md) - Version history and changes

## Notes

**NOTE: This repository has been configured with the [DCO bot](https://github.com/probot/dco).
When you set up a new repository that uses the Apache license, you should
use the DCO to manage contributions. The DCO bot will help enforce that.**

## 🙏 Acknowledgments

- Built for IBM NOI/Event Manager policy analysis
- Designed for Kubernetes/OpenShift environments
- Optimized for Cassandra data sources

## Authors

- Yasser Abduallah - yassera@us.ibm.com

For a complete list of contributors, see [MAINTAINERS.md](MAINTAINERS.md).

---

**Built for the NOI/Event Manager community**
