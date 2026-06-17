# Changelog

All notable changes to the Policy and Events Visualization Tool will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security
- Updated Python dependencies to address 21 vulnerabilities (4 high, 16 moderate, 1 low)
- Updated scylla-driver from >=3.25.0 to >=3.29.1,<4.0.0
- Updated orjson from >=3.6.0 to >=3.10.7,<4.0.0
- Updated psutil from >=5.9.0 to >=6.1.0,<7.0.0
- Updated tqdm from >=4.65.0 to >=4.67.1,<5.0.0
- Updated pandas from >=1.3.0 to >=2.2.3,<3.0.0
- Added version constraints to prevent breaking changes
- Created SECURITY_UPDATES.md to track vulnerability fixes

### Added
- IBM open source template compliance
- CONTRIBUTING.md with contribution guidelines
- CODE_OF_CONDUCT.md (Contributor Covenant 3.0)
- SECURITY.md with security policy
- MAINTAINERS.md with project maintainers
- CHANGELOG.md for tracking changes
- SPDX license headers to all source files
- HTML template refactoring: separated presentation from Python logic
- Created src/templates/ directory for HTML templates
- Created src/static/config-handler.js for dynamic configuration
- Added /api/config endpoint for runtime configuration
- .github/dco.yml for DCO bot configuration

### Changed
- Updated documentation for open source release
- Removed proprietary and confidential information
- Improved documentation accuracy
- Updated README.md with IBM template structure

## [1.0.0] - 2024-12-01

### Added
- Initial open source release
- Web-based visualization interface for NOI policies and events
- Policy summary table with search and filtering
- Events detail table with advanced filtering
- Payload inspection capability
- User authentication and session management
- Auto-update functionality for data refresh
- Cassandra data extraction scripts
- Docker containerization support
- OpenShift/Kubernetes deployment support
- Comprehensive documentation suite:
  - README.md - Project overview
  - docs/INSTALL.md - Installation guide
  - docs/ARCHITECTURE.md - Technical architecture
  - docs/USER_GUIDE.md - End-user guide
  - docs/DEVELOPER_GUIDE.md - Developer guide
  - docs/AUTO_UPDATE_GUIDE.md - Auto-update configuration

### Features
- **Data Visualization**: Interactive tables for policies and events
- **Search & Filter**: Advanced search across all data fields
- **Export**: CSV export functionality
- **Authentication**: Secure user login with password hashing
- **Responsive Design**: Mobile-friendly interface
- **Real-time Updates**: Auto-refresh capability
- **Data Processing**: Efficient handling of large datasets
- **Deployment Options**: Local, Docker, and Kubernetes deployment

### Security
- PBKDF2 password hashing with 150,000 iterations
- Session-based authentication
- Security headers (CSP, X-Frame-Options, HSTS)
- Input validation and sanitization

### Performance
- Server-side processing for large datasets
- Efficient CSV parsing with 8MB buffer
- Optional orjson for faster JSON processing
- In-memory data caching

## [0.1.0] - 2024-06-01

### Added
- Initial internal development version
- Basic web interface
- Policy and event data loading
- Simple authentication

---

## Release Notes

### Version 1.0.0

This is the first official open source release of the Policy and Events Visualization Tool. The tool provides a web-based interface for visualizing and analyzing IBM Netcool Operations Insight (NOI) policies and events data extracted from Cassandra.

**Key Highlights**:
- Production-ready web interface
- Comprehensive documentation
- Multiple deployment options
- Security best practices implemented
- Open source under Apache 2.0 license

**Known Limitations**:
- Single-pod deployment only (no horizontal scaling)
- In-memory session storage (sessions don't persist across restarts)
- Requires manual data extraction from Cassandra

**Upgrade Notes**:
- This is the first release, no upgrade path needed

---

## Links

- [Repository](https://github.ibm.com/hdm/noi-aiops-helping-tools-scripts/tree/main/policies_and_events_visualization)
- [Issues](https://github.ibm.com/hdm/noi-aiops-helping-tools-scripts/issues)
- [Pull Requests](https://github.ibm.com/hdm/noi-aiops-helping-tools-scripts/pulls)

[unreleased]: https://github.ibm.com/hdm/noi-aiops-helping-tools-scripts/compare/v1.0.0...HEAD
[1.0.0]: https://github.ibm.com/hdm/noi-aiops-helping-tools-scripts/releases/tag/v1.0.0
[0.1.0]: https://github.ibm.com/hdm/noi-aiops-helping-tools-scripts/releases/tag/v0.1.0