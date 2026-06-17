# Developer Guide

Guide for developers contributing to the NOI Policy & Event Visualization project.

## Table of Contents

- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [Code Style](#code-style)
- [Development Workflow](#development-workflow)
- [Testing](#testing)
- [Adding Features](#adding-features)
- [API Development](#api-development)
- [Frontend Development](#frontend-development)
- [Database Integration](#database-integration)
- [Debugging](#debugging)
- [Contributing](#contributing)

---

## Development Setup

### Prerequisites

**Required**:
- Python 3.9+ (tested on 3.9.x; 3.8+ may work but untested)
- Git
- Text editor/IDE (VS Code, PyCharm, etc.)

**Optional**:
- Docker Desktop
- Kubernetes/OpenShift CLI
- Cassandra/Scylla access (for data extraction)

### Clone Repository

```bash
git clone https://github.com/your-org/noi-policy-visualization.git
cd noi-policy-visualization
```

### Virtual Environment

```bash
# Create virtual environment
python -m venv venv

# Activate (Linux/Mac)
source venv/bin/activate

# Activate (Windows)
venv\Scripts\activate
```

### Install Dependencies

```bash
# Install required packages
pip install -r requirements.txt

```

**requirements.txt**:
```
scylla-driver>=3.25.0
orjson>=3.6.0
cassandra-driver>=3.25.0
```

### IDE Setup

**VS Code** (`.vscode/settings.json`):
```json
{
  "python.linting.enabled": true,
  "python.linting.flake8Enabled": true,
  "python.formatting.provider": "black",
  "editor.formatOnSave": true,
  "python.testing.pytestEnabled": true
}
```

**PyCharm**:
- Enable Black formatter
- Configure pytest as test runner
- Enable type checking

---

## Project Structure

```
policies_and_events_visualization/
├── src/                              # Source code
│   ├── web_interface.py              # Main web server
│   ├── process_policies_and_events.py # Data processing
│   ├── manage_users.py               # User management
│   ├── copy_policies_details_from_cassandra.sh # Cassandra data extraction
│   ├── mime_cassandra_util.py        # Cassandra utilities (for auto-update)
│   ├── read_cassandra_agg_noi.py     # Cassandra instance generator
│   ├── auto_update_visualization.py  # Auto-update service
│   ├── auto_update_visualization_copy_to_pod.py # Pod copy utility
│   ├── setup_crontab.sh              # Cron setup script
│   ├── start_visualization_service.sh # Service startup script
│   ├── test_setup.sh                 # Test setup script
│   ├── deploy_policies_events_viz.sh # Deployment script
│   ├── Dockerfile                    # Container definition
│   ├── templates/                    # HTML templates
│   │   └── viewer.html               # Main HTML template (primary)
│   ├── static/                       # Frontend assets
│   │   ├── app.js                    # Main JavaScript
│   │   ├── styles.css                # Styling
│   │   └── config-handler.js         # Dynamic configuration handler
│   ├── policy_event_viewer.html      # HTML template (legacy, for compatibility)
│   ├── users.csv                     # User credentials
│   ├── requirements.txt              # Python dependencies
│   └── README.md                     # Source documentation
├── docs/                             # Documentation
│   ├── README.md                     # Main documentation
│   ├── INSTALL.md                    # Installation guide
│   ├── ARCHITECTURE.md               # Architecture details
│   ├── USER_GUIDE.md                 # User guide
│   ├── DEVELOPER_GUIDE.md            # Developer guide
│   └── AUTO_UPDATE_GUIDE.md          # Auto-update guide
├── output/                           # Generated data (created at runtime)
│   ├── policy_summary.csv
│   ├── events_detail.csv
│   └── payloads.csv
├── logs/                             # Log files (created at runtime)
│   ├── web_interface.log
│   └── auto_update_visualization.log
└── .gitignore                        # Git ignore rules
```

### Key Files

**Backend**:
- `web_interface.py` - HTTP server, routing, authentication
- `process_policies_and_events.py` - Data transformation
- `manage_users.py` - User CRUD operations
- `copy_policies_details_from_cassandra.sh` - Cassandra data extraction script
- `mime_cassandra_util.py` - Cassandra utilities for auto-update
- `read_cassandra_agg_noi.py` - Cassandra aggregation reader
- `auto_update_visualization.py` - Auto-update service
- `auto_update_visualization_copy_to_pod.py` - Pod copy utility

**Frontend**:
- `static/app.js` - UI logic, AJAX calls, DataTables
- `static/styles.css` - Custom styling
- `policy_event_viewer.html` - HTML structure

**Configuration**:
- `users.csv` - User credentials

---

## Code Style

### Python Style Guide

Follow [PEP 8](https://pep8.org/) with these specifics:

**Formatting**:
```python
# Use Black formatter (line length: 88)
black src/

# Check with flake8
flake8 src/ --max-line-length=88
```

**Naming Conventions**:
```python
# Variables and functions: snake_case
user_name = "admin"
def process_data():
    pass

# Classes: PascalCase
class PolicyHandler:
    pass

# Constants: UPPER_CASE
MAX_RETRIES = 3
DEFAULT_PORT = 5000

# Private: _leading_underscore
def _internal_function():
    pass
```

**Type Hints**:
```python
from typing import List, Dict, Optional

def get_policies(
    filter_type: Optional[str] = None
) -> List[Dict[str, any]]:
    """Get policies with optional filtering."""
    pass
```

**Docstrings**:
```python
def deploy_policy(policy_id: str, base_url: str) -> bool:
    """
    Deploy a policy to the registry.
    
    Args:
        policy_id: Unique policy identifier
        base_url: Registry base URL
        
    Returns:
        True if successful, False otherwise
        
    Raises:
        ConnectionError: If registry is unreachable
        AuthenticationError: If credentials are invalid
    """
    pass
```

### JavaScript Style Guide

**Formatting**:
```javascript
// Use 2-space indentation
function loadPolicies() {
  $.ajax({
    url: '/api/policies',
    success: function(data) {
      // Process data
    }
  });
}

// Use semicolons
const x = 5;

// Use const/let, not var
const API_URL = '/api';
let currentPolicy = null;
```

**Naming**:
```javascript
// Variables and functions: camelCase
let policyTable = null;
function initializeTables() {}

// Constants: UPPER_CASE
const MAX_POLICIES = 1000;

// Classes: PascalCase
class PolicyManager {}
```

### CSS Style Guide

```css
/* Use kebab-case for classes */
.policy-table {
  width: 100%;
}

/* Group related properties */
.card {
  /* Layout */
  display: flex;
  flex-direction: column;
  
  /* Spacing */
  margin: 10px;
  padding: 15px;
  
  /* Visual */
  background: white;
  border: 1px solid #ddd;
  border-radius: 4px;
}

/* Use comments for sections */
/* ===== Policy Browser ===== */
```

---

## Development Workflow

### Branch Strategy

```
main (production)
  ├── develop (integration)
  │   ├── feature/add-search
  │   ├── feature/improve-ui
  │   └── bugfix/fix-login
  └── hotfix/critical-bug
```

**Branch Naming**:
- `feature/description` - New features
- `bugfix/description` - Bug fixes
- `hotfix/description` - Critical fixes
- `refactor/description` - Code refactoring
- `docs/description` - Documentation

### Development Process

1. **Create Branch**:
   ```bash
   git checkout -b feature/add-export
   ```

2. **Make Changes**:
   ```bash
   # Edit files
   vim src/web_interface.py
   
   # Format code
   black src/
   
   # Check style
   flake8 src/
   ```

3. **Test Changes**:
   ```bash
   # Run tests
   pytest tests/
   
   # Check coverage
   pytest --cov=src tests/
   ```

4. **Commit**:
   ```bash
   git add .
   git commit -m "feat: add CSV export functionality"
   ```

5. **Push**:
   ```bash
   git push origin feature/add-export
   ```

6. **Create Pull Request**:
   - Go to GitHub
   - Create PR from feature branch to develop
   - Fill in PR template
   - Request review

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

**Types**:
- `feat` - New feature
- `fix` - Bug fix
- `docs` - Documentation
- `style` - Formatting
- `refactor` - Code restructuring
- `test` - Tests
- `chore` - Maintenance

**Examples**:
```bash
feat(api): add policy search endpoint
fix(ui): correct event table sorting
docs(readme): update installation steps
refactor(auth): simplify session management
test(api): add deployment tests
```

---

## Testing

> ⚠️ **NOT IMPLEMENTED**: The project does not currently include automated tests. This section provides recommendations for future testing implementation.

### Recommended Test Structure

```
tests/
├── unit/                    # Unit tests
│   ├── test_auth.py
│   ├── test_data.py
│   └── test_utils.py
├── integration/             # Integration tests
│   ├── test_api.py
│   └── test_deployment.py
├── e2e/                     # End-to-end tests
│   └── test_workflow.py
└── conftest.py              # Pytest fixtures
```

### Recommended Testing Approach

**Unit Test Example**:
```python
# tests/unit/test_auth.py
import pytest
from src.web_interface import hash_password, verify_password

def test_password_hashing():
    """Test password hashing and verification."""
    password = "test123"
    hashed = hash_password(password)
    
    assert hashed != password
    assert verify_password(password, hashed)
    assert not verify_password("wrong", hashed)

def test_password_salt():
    """Test that same password produces different hashes."""
    password = "test123"
    hash1 = hash_password(password)
    hash2 = hash_password(password)
    
    assert hash1 != hash2
```

**Integration Test Example**:
```python
# tests/integration/test_api.py
import pytest
import requests

@pytest.fixture
def api_url():
    return "http://localhost:5000"

@pytest.fixture
def auth_token(api_url):
    """Get authentication token."""
    response = requests.post(
        f"{api_url}/api/login",
        json={"username": "admin", "password": "admin123"}
    )
    return response.cookies.get("session_id")

def test_get_policies(api_url, auth_token):
    """Test getting policies."""
    response = requests.get(
        f"{api_url}/api/policies",
        cookies={"session_id": auth_token}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert isinstance(data["data"], list)
```

### Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/unit/test_auth.py

# Run specific test
pytest tests/unit/test_auth.py::test_password_hashing

# Run with coverage
pytest --cov=src --cov-report=html

# Run with verbose output
pytest -v

# Run and stop on first failure
pytest -x
```

### Test Coverage

**Target**: 80%+ coverage

```bash
# Generate coverage report
pytest --cov=src --cov-report=term-missing

# View HTML report
pytest --cov=src --cov-report=html
open htmlcov/index.html
```

### Mocking

```python
from unittest.mock import Mock, patch

def test_api_call_with_mock():
    """Test API call with mocked response."""
    with patch('requests.get') as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"data": []}
        
        result = fetch_policies()
        
        assert result == []
        mock_get.assert_called_once()
```

---

## Adding Features

### Feature Development Checklist

- [ ] Design feature
- [ ] Write tests (TDD)
- [ ] Implement feature
- [ ] Update documentation
- [ ] Test manually
- [ ] Create PR
- [ ] Code review
- [ ] Merge to develop

### Example: Adding New API Endpoint

**1. Define Endpoint**:
```python
# src/web_interface.py

def do_GET(self):
    """Handle GET requests."""
    if self.path == '/api/statistics':
        self._handle_statistics()
    # ... other routes
```

**2. Implement Handler**:
```python
def _handle_statistics(self):
    """Get policy statistics."""
    try:
        stats = {
            'total_policies': len(policy_cache),
            'deployed_policies': sum(
                1 for p in policy_cache.values() 
                if p.get('deployed')
            ),
            'total_events': len(event_cache),
            'avg_score': sum(
                p.get('ranking_score', 0) 
                for p in policy_cache.values()
            ) / len(policy_cache)
        }
        self._send_json(stats)
    except Exception as e:
        self._send_error(500, str(e))
```

**3. Add Tests**:
```python
# tests/integration/test_api.py

def test_get_statistics(api_url, auth_token):
    """Test statistics endpoint."""
    response = requests.get(
        f"{api_url}/api/statistics",
        cookies={"session_id": auth_token}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert 'total_policies' in data
    assert 'deployed_policies' in data
    assert data['total_policies'] >= 0
```

**4. Update Frontend**:
```javascript
// static/app.js

function loadStatistics() {
  $.ajax({
    url: '/api/statistics',
    method: 'GET',
    success: function(data) {
      $('#total-policies').text(data.total_policies);
      $('#deployed-policies').text(data.deployed_policies);
      $('#avg-score').text(data.avg_score.toFixed(2));
    },
    error: function(xhr) {
      console.error('Failed to load statistics:', xhr);
    }
  });
}
```

**5. Update Documentation**:
```markdown
# docs/API.md

## GET /api/statistics

Get policy statistics.

**Response**:
```json
{
  "total_policies": 100,
  "deployed_policies": 75,
  "total_events": 1000,
  "avg_score": 0.85
}
```
```

---

## API Development

### REST API Guidelines

**URL Structure**:
```
/api/resource              # Collection
/api/resource/{id}         # Single item
/api/resource/{id}/action  # Action on item
```

**HTTP Methods**:
- `GET` - Retrieve data
- `POST` - Create or action
- `PUT` - Update (full)
- `PATCH` - Update (partial)
- `DELETE` - Remove

**Response Format**:
```python
# Success
{
    "data": [...],
    "meta": {
        "count": 100,
        "page": 1
    }
}

# Error
{
    "error": {
        "code": "INVALID_INPUT",
        "message": "Policy ID is required",
        "details": {...}
    }
}
```

### Error Handling

```python
class APIError(Exception):
    """Base API error."""
    def __init__(self, code, message, status=400):
        self.code = code
        self.message = message
        self.status = status

def _handle_api_error(self, error):
    """Send error response."""
    self.send_response(error.status)
    self.send_header('Content-Type', 'application/json')
    self.end_headers()
    
    response = {
        'error': {
            'code': error.code,
            'message': error.message
        }
    }
    self.wfile.write(json.dumps(response).encode())
```

### Authentication

```python
def _check_auth(self):
    """Verify authentication."""
    session_id = self._get_cookie('session_id')
    
    if not session_id:
        raise APIError('AUTH_REQUIRED', 'Authentication required', 401)
    
    if session_id not in session_cache:
        raise APIError('INVALID_SESSION', 'Invalid session', 401)
    
    session = session_cache[session_id]
    
    # Check timeout
    if time.time() - session['last_activity'] > SESSION_TIMEOUT:
        del session_cache[session_id]
        raise APIError('SESSION_EXPIRED', 'Session expired', 401)
    
    # Update activity
    session['last_activity'] = time.time()
    
    return session['username']
```

---

## Frontend Development

### JavaScript Architecture

```javascript
// Module pattern
const PolicyViewer = (function() {
  // Private variables
  let policyTable = null;
  let eventsTable = null;
  
  // Private functions
  function initTables() {
    // Initialize DataTables
  }
  
  function loadPolicies() {
    // Load policy data
  }
  
  // Public API
  return {
    init: function() {
      initTables();
      loadPolicies();
    },
    refresh: function() {
      loadPolicies();
    }
  };
})();

// Initialize on page load
$(document).ready(function() {
  PolicyViewer.init();
});
```

### AJAX Patterns

```javascript
// Reusable AJAX function
function apiCall(endpoint, options = {}) {
  return $.ajax({
    url: `/api/${endpoint}`,
    method: options.method || 'GET',
    data: options.data,
    contentType: options.contentType || 'application/json',
    dataType: 'json',
    beforeSend: function() {
      if (options.showLoader) {
        showLoader();
      }
    },
    success: function(data) {
      if (options.success) {
        options.success(data);
      }
    },
    error: function(xhr) {
      handleError(xhr);
      if (options.error) {
        options.error(xhr);
      }
    },
    complete: function() {
      if (options.showLoader) {
        hideLoader();
      }
    }
  });
}

// Usage
apiCall('policies', {
  showLoader: true,
  success: function(data) {
    updateTable(data);
  }
});
```

### DataTables Integration

```javascript
// Initialize DataTable
policyTable = $('#policy-table').DataTable({
  data: [],
  columns: [
    { data: 'policy_id' },
    { data: 'ranking_score' },
    { data: 'event_count' }
  ],
  order: [[1, 'desc']],
  pageLength: 25,
  responsive: true,
  dom: 'Bfrtip',
  buttons: ['copy', 'csv', 'excel']
});

// Update data
function updatePolicies(data) {
  policyTable.clear();
  policyTable.rows.add(data);
  policyTable.draw();
}

// Get selected rows
function getSelectedPolicies() {
  return policyTable.rows('.selected').data().toArray();
}
```

---

## Data Storage

### In-Memory Storage

The application uses in-memory storage for fast data access:

**Data Structures**:
```python
# Global data structures loaded on startup
policies_data = []          # List of policy dictionaries
events_data = []            # List of event dictionaries
search_index = {}           # Inverted index for search
pattern_sets = []           # Pattern set definitions

# Memory usage tracking
def calculate_memory_usage():
    """Calculate approximate memory usage."""
    import sys
    
    policies_size = sys.getsizeof(policies_data) / (1024 * 1024)
    events_size = sys.getsizeof(events_data) / (1024 * 1024)
    index_size = sys.getsizeof(search_index) / (1024 * 1024)
    
    return {
        'policies_mb': round(policies_size, 1),
        'events_mb': round(events_size, 1),
        'index_mb': round(index_size, 1),
        'total_mb': round(policies_size + events_size + index_size, 1)
    }
```

**Loading Data**:
```python
def load_data_into_memory():
    """Load CSV data into memory structures."""
    global policies_data, events_data, search_index
    
    # Load policies
    with open('policies_export.csv', 'r') as f:
        reader = csv.DictReader(f)
        policies_data = list(reader)
    
    # Load events
    with open('events_export.csv', 'r') as f:
        reader = csv.DictReader(f)
        events_data = list(reader)
    
    # Build search index
    search_index = build_inverted_index(policies_data)
    
    # Display memory usage
    usage = calculate_memory_usage()
    print(f"[memory] Policies: {len(policies_data):,} records (~{usage['policies_mb']:>6} MB)")
    print(f"[memory] Events:   {len(events_data):,} records (~{usage['events_mb']:>6} MB)")
    print(f"[memory] TOTAL MEMORY: ~{usage['total_mb']} MB")
```

**Performance Considerations**:
- Data loaded once on startup
- Fast in-memory lookups (O(1) for indexed fields)
- Memory usage scales linearly with dataset size
- Typical: ~50MB for 14K policies + 70K events

---

## Debugging

### Logging

```python
import logging

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/debug.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Use in code
logger.debug('Processing policy: %s', policy_id)
logger.info('Deployed %d policies', count)
logger.warning('Slow response: %dms', duration)
logger.error('Failed to connect: %s', error)
```

### Python Debugger

```python
# Add breakpoint
import pdb; pdb.set_trace()

# Or use built-in breakpoint() (Python 3.7+)
breakpoint()

# Commands:
# n - next line
# s - step into
# c - continue
# p variable - print variable
# l - list code
# q - quit
```

### Browser DevTools

**Console**:
```javascript
// Debug AJAX calls
console.log('Loading policies...');
console.table(policies);
console.error('Failed:', error);

// Inspect objects
console.dir(policyTable);

// Performance timing
console.time('load');
loadPolicies();
console.timeEnd('load');
```

**Network Tab**:
- Monitor API calls
- Check request/response
- Identify slow requests
- Debug CORS issues

**Sources Tab**:
- Set breakpoints
- Step through code
- Watch variables
- Debug minified code

---

## Contributing

### Pull Request Process

1. **Fork Repository**
2. **Create Branch**
3. **Make Changes**
4. **Run Tests**
5. **Update Docs**
6. **Submit PR**

### PR Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Manual testing completed

## Checklist
- [ ] Code follows style guide
- [ ] Self-review completed
- [ ] Comments added
- [ ] Documentation updated
- [ ] No new warnings
```

### Code Review Guidelines

**Reviewers Check**:
- Code quality
- Test coverage
- Documentation
- Performance
- Security

**Author Responsibilities**:
- Respond to feedback
- Make requested changes
- Keep PR updated
- Resolve conflicts

---

## Resources

- [Python Documentation](https://docs.python.org/)
- [Python http.server Documentation](https://docs.python.org/3/library/http.server.html)
- [DataTables Documentation](https://datatables.net/)
- [jQuery Documentation](https://api.jquery.com/)
- [Pytest Documentation](https://docs.pytest.org/)

---

## Getting Help

- **Issues**: GitHub Issues


---

## License

This project is licensed under the Apache License 2.0 - see [LICENSE](../LICENSE) file.