# Architecture Guide

Technical architecture and design documentation for NOI Policy & Event Visualization.

## Table of Contents

- [System Overview](#system-overview)
- [Component Architecture](#component-architecture)
- [Data Flow](#data-flow)
- [Technology Stack](#technology-stack)
- [Performance Optimizations](#performance-optimizations)
- [Security Architecture](#security-architecture)
- [Scalability](#scalability)
- [API Design](#api-design)

---

## System Overview

The NOI Policy & Event Visualization system is a web-based application designed to provide interactive exploration and analysis of IBM Netcool Operations Insight (NOI) / Event Manager policies and their associated events.

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Web Browser                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │   Policy     │  │    Event     │  │   Pattern    │         │
│  │   Browser    │  │   Explorer   │  │   Analyzer   │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTP/HTTPS (REST API)
┌────────────────────────▼────────────────────────────────────────┐
│                    Web Interface Layer                           │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  HTTP Server (Python BaseHTTPRequestHandler)             │  │
│  │  - Request routing                                        │  │
│  │  - Authentication & session management                    │  │
│  │  - CORS handling                                          │  │
│  │  - Static file serving                                    │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────┬────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────────┐
│                   Business Logic Layer                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │   Policy     │  │    Event     │  │  Deployment  │         │
│  │  Processing  │  │  Processing  │  │   Manager    │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │   Search &   │  │    Cache     │  │    Index     │         │
│  │   Filter     │  │   Manager    │  │   Builder    │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
└────────────────────────┬────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────────┐
│                      Data Layer                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │     CSV      │  │   In-Memory  │  │     JSON     │         │
│  │    Files     │  │    Storage   │  │    Files     │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  File System / Persistent Volume                         │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### Design Principles

1. **Simplicity** - Single Python file for easy deployment
2. **Performance** - Optimized for millions of events
3. **Security** - Authentication, session management, audit logging
4. **Scalability** - Stateless design for horizontal scaling
5. **Maintainability** - Clear separation of concerns
6. **Portability** - Runs locally or in Kubernetes

---

## Component Architecture

### 1. Web Interface Layer

**File**: `web_interface.py`

**Responsibilities**:
- HTTP request handling
- Routing and endpoint management
- Authentication and authorization
- Session management
- Static file serving
- CORS handling

**Key Classes**:

```python
class Handler(BaseHTTPRequestHandler):
    """Main HTTP request handler"""
    
    def do_GET(self):
        """Handle GET requests"""
        # Route to appropriate handler based on path
        
    def do_POST(self):
        """Handle POST requests"""
        # Authentication, deployment, etc.
        
    def _check_auth(self):
        """Verify user authentication"""
        # Returns True if authenticated or auth disabled
        
    def log_message(self, format, *args):
        """Custom logging (suppressed unless ACCESS_LOG enabled)"""
```

**Request Flow**:
```
Request → Authentication → Route Matching → Handler → Response
```

### 2. Data Processing Layer

**Files**:
- `process_policies_and_events.py` - Main data processor
- `copy_policies_details_from_cassandra.sh` - Cassandra data extraction (uses cqlsh)

**Responsibilities**:
- Data extraction from source systems
- CSV processing and transformation
- Event deduplication
- Policy-event relationship mapping
- Index building for fast search

**Key Functions**:

```python
def load_data_to_memory(output_dir: str) -> bool:
    """Load processed data into memory"""
    # Read policy_summary.csv
    # Read events_detail.csv
    # Read policy_events_payload.csv
    # Parse deployed policies map
    # Build in-memory data structures
    # Returns True if successful
```

### 3. Caching Layer

**Implementation**: In-memory Python dictionaries

**Cached Data**:
- Policy summaries
- Event details
- Search indexes
- Parsed JSON payloads
- User sessions

**Global Data Structures**:
```python
# Main data storage (loaded at startup)
policy_summary_data: List[Dict[str, Any]] = []      # Policy metadata
events_detail_data: List[Dict[str, Any]] = []       # Event details
policy_events_payload_data: List[Dict[str, Any]] = [] # Event payloads
CONDSETS_BY_POLICY: Dict[str, Any] = {}             # policy_id -> condition sets

# Search indexes (built during load_data_to_memory)
SEARCH_INDEX: Dict[str, Set[str]] = {}              # search_term -> set of policy_ids
POLICY_ID_INDEX: Dict[str, List[int]] = {}          # policy_id -> list of row indices

# No reload_data() function - data loaded once at startup
# Hot-reload handled by _maybe_reload_data() which checks file timestamps
```

### 4. Authentication & Security

**Components**:
- Password hashing (PBKDF2-SHA256)
- Session management
- Audit logging
- CORS handling

**Authentication Flow**:
```
┌─────────┐
│ Browser │
└────┬────┘
     │ 1. Login request (username/password)
     ▼
┌─────────────────┐
│  Web Interface  │
└────┬────────────┘
     │ 2. Verify credentials
     ▼
┌─────────────────┐
│   users.csv     │
└────┬────────────┘
     │ 3. Password hash match
     ▼
┌─────────────────┐
│ Session Created │
└────┬────────────┘
     │ 4. Set cookie
     ▼
┌─────────┐
│ Browser │ (Authenticated)
└─────────┘
```

### 5. Frontend Layer

**Files**:
- `static/app.js` - Main JavaScript application
- `static/styles.css` - Styling
- `policy_event_viewer.html` - HTML template

**Key Components**:

```javascript
// Global table variables (line 73)
var policyTable, eventsTable, selectedPolicyId = null;

// Policy table initialization (line 919)
function initPolicies() {
    // Initialize DataTables for policies
    // Setup event handlers
    // Configure columns and sorting
}

// Event table initialization (line 1283)
function initEvents() {
    // Initialize DataTables for events
    // Setup event handlers
    // Configure server-side processing
}

// Deployment functions
async function deployPoliciesBatched(ids, cfg) {
    // Batch deployment with progress tracking (line 2606)
}

async function deployPolicies(ids, cfg, concurrency, clientTimeoutMs) {
    // Core deployment logic (line 2913)
    // Handles authentication, batching, error handling
}

// Note: Search is handled by DataTables global search, not a separate setupSearch() function
```

---

## Data Flow

### 1. Data Extraction Flow

```
┌──────────────┐
│  Cassandra   │
│   Database   │
└──────┬───────┘
       │ 1. Extract data
       ▼
┌───────────────────────────────────-─────┐
│ copy_policies_details_from_cassandra.sh │
└──────┬──────────────────────────────────┘
       │ 2. Write CSV files
       ▼
┌──────────────────────┐
│  Raw CSV Files       │
│  - policies_export   │
│  - events_export     │
└──────┬───────────────┘
       │ 3. Process & transform
       ▼
┌──────────────────────────┐
│ process_policies_*.py    │
└──────┬───────────────────┘
       │ 4. Generate output
       ▼
┌──────────────────────────┐
│  Processed Files         │
│  - policy_summary.csv    │
│  - events_detail.csv     │
│  - payloads.csv          │
│  - condition_sets.json   │
└──────────────────────────┘
```

### 2. Request Processing Flow

```
┌─────────┐
│ Browser │
└────┬────┘
     │ HTTP Request
     ▼
┌─────────────────┐
│ Authentication  │
└────┬────────────┘
     │ Authenticated?
     ├─ No → 401 Unauthorized
     │
     └─ Yes
        ▼
   ┌─────────────┐
   │   Routing   │
   └────┬────────┘
        │
        ├─ /api/policies → Load policies from cache
        ├─ /api/events → Load events for policy
        ├─ /api/payload → Load event payload
        ├─ /api/deploy → Deploy policies
        └─ /api/search → Search policies
           │
           ▼
      ┌─────────────┐
      │   Handler   │
      └────┬────────┘
           │ Process request
           ▼
      ┌─────────────┐
      │   Response  │
      └────┬────────┘
           │ JSON/HTML
           ▼
      ┌─────────┐
      │ Browser │
      └─────────┘
```

### 3. Search Flow

```
User Input: "network error"
     │
     ▼
┌─────────────────┐
│ Tokenize Input  │
└────┬────────────┘
     │ ["network", "error"]
     ▼
┌─────────────────┐
│ Search Index    │
│ word -> policy  │
└────┬────────────┘
     │ {policy-1, policy-2, ...}
     ▼
┌─────────────────┐
│ Filter Policies │
└────┬────────────┘
     │ Matching policies
     ▼
┌─────────────────┐
│ Rank Results    │
└────┬────────────┘
     │ Sorted by relevance
     ▼
┌─────────────────┐
│ Return Results  │
└─────────────────┘
```

---

## Technology Stack

### Backend

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Web Server** | Python BaseHTTPRequestHandler | HTTP request handling |
| **Data Processing** | Python csv module | CSV processing (stdlib) |
| **JSON Parsing** | orjson (optional) | Fast JSON parsing (fallback to stdlib json) |
| **Password Hashing** | hashlib (PBKDF2) | Secure password storage |
| **Data Storage** | In-Memory | Fast access with memory efficiency |
| **Logging** | Python logging | Application and audit logs |

### Frontend

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **UI Framework** | jQuery 3.6.3 | DOM manipulation |
| **CSS Framework** | Bootstrap 5.2.3 | Responsive design |
| **Data Tables** | DataTables 1.13.1 | Interactive tables |
| **Icons** | Bootstrap Icons 1.10.0 | UI icons |
| **Styling** | Custom CSS | Additional styling |

### Infrastructure

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Orchestration** | OpenShift | Container orchestration |
| **Deployment** | Kubernetes YAML | Deployment configuration |
| **Storage** | PersistentVolume (optional) | Data persistence |
| **Networking** | Service/Route | Network access |

**Note**: Docker/Dockerfile can be used for containerization but is not included in the repository. See `src/README_create_microservice.md` for instructions on creating a Dockerfile if needed.

---

## Performance Optimizations

### 1. Caching Strategy

**In-Memory Data Storage**:
```python
# All data loaded at startup (see lines 270-278 in web_interface.py)
policy_summary_data = []           # ~3.4 MB for 14K policies
events_detail_data = []            # ~15.2 MB for 70K events
policy_events_payload_data = []    # ~28.7 MB for 70K events with payloads
CONDSETS_BY_POLICY = {}            # ~0.5 MB for pattern condition sets
SEARCH_INDEX = {}                  # Built during load, minimal overhead
POLICY_ID_INDEX = {}               # Policy ID to row index mapping

# Total memory usage: ~48 MB for typical dataset (14K policies + 70K events)
```

**Benefits**:
- Sub-millisecond response times
- Reduced file I/O
- Lower CPU usage

### 2. Server-Side Processing

**DataTables Server-Side Mode**:
- Events table uses server-side processing for large datasets
- Only requested page of data is sent to client
- Filtering and sorting performed on server
- Reduces client-side memory usage and improves responsiveness

**Implementation**:
- See `_api_events_ss()` function in web_interface.py (line 2560+)
- Supports pagination, search, and sorting
- Returns only the requested slice of data

**Benefits**:
- Handles large event datasets (70K+ events)
- Fast page load times
- Lower client-side memory usage

### 3. Search Optimization

**Inverted Index Implementation**:
```python
# Build index: word -> set of policy_ids
# Indexes words from event_id, payload_resource, summary, payload_details, payload_type
SEARCH_INDEX = {
    'network': {'policy-1', 'policy-2', 'policy-5'},
    'error': {'policy-1', 'policy-3', 'policy-4'},
    'timeout': {'policy-2', 'policy-5', 'policy-6'}
}

# Search: substring matching on indexed words
def search_events(term):
    matching_ids = set()
    for word, policy_ids in SEARCH_INDEX.items():
        if term in word:  # Substring match
            matching_ids.update(policy_ids)
    
    # Fallback to full scan if no index matches
    if not matching_ids:
        # Scan all events for the term
        ...
    return matching_ids
```

**Features**:
- Indexes words 3+ characters from searchable fields
- Substring matching (e.g., "net" matches "network")
- Fallback to full scan for terms not in index
- Built during data load (line 679-703 in web_interface.py)

**Performance**:
- Search time: <10ms for 10K policies
- Memory: ~5MB for 10K policies

### 4. Optimized CSV Loading

**Implementation** (web_interface.py, line 588+):
```python
# Load entire CSV files into memory using Python's csv module
with open(events_path, "r", encoding="utf-8", buffering=8*1024*1024) as f:
    events_detail_data = list(csv.DictReader(f))

# Increased buffer size (8MB) for faster I/O
with open(payload_path, "r", encoding="utf-8", buffering=8*1024*1024) as f:
    rdr = csv.DictReader(f)
    policy_events_payload_data = []
    for row in rdr:
        # Parse JSON fields inline
        policy_events_payload_data.append(row)
```

**Optimizations**:
- Uses Python stdlib `csv` module (no pandas dependency)
- 8MB buffer size for faster file I/O
- Loads all data at startup (~48MB for 14K policies + 70K events)
- No chunking needed - dataset fits comfortably in memory

**Benefits**:
- Handles files >1GB
- Constant memory usage
- Faster processing

### 5. JSON Parsing

**Optional orjson for Data Processing**:

The data processing script (`process_policies_and_events.py`) optionally uses orjson for faster JSON parsing during CSV generation:

```python
# Try to use orjson for better performance, but fall back to standard json
jloads = json.loads
jdumps = lambda obj: json.dumps(obj, ensure_ascii=False)

try:
    import orjson
    jloads = orjson.loads
    jdumps = lambda obj: orjson.dumps(obj).decode('utf-8')
    print("[INFO] Using orjson for improved performance")
except ImportError:
    print("[INFO] Using standard json module")
```

**Web Server Uses Standard JSON**:
- `web_interface.py` uses Python's standard `json` module
- No external dependencies required for the web server
- orjson is optional and only benefits data processing phase

### 6. Memory Management

**In-Memory Data Storage**:
```python
# Data loaded on startup from CSV files
policies_data = []      # ~4.9 MB for 14K policies
events_data = []        # ~43.3 MB for 70K events
search_index = {}       # ~174K indexed search terms

# Memory usage displayed on startup
[memory] Indexed 174,834 search terms covering 13,998 policies
[memory] Data loaded successfully into memory:
[memory]   Policies:          14,002 records  (~   4.9 MB)
[memory]   Events Payload:    69,990 records  (~  43.3 MB)
[memory]   TOTAL MEMORY:    ~48.2 MB
```

**Memory Scaling Guidelines**:
| Dataset Size | Policies | Events | Estimated Memory |
|--------------|----------|--------|------------------|
| Small | 1K | 5K | ~5 MB |
| Medium | 10K | 50K | ~40 MB |
| Large | 20K | 100K | ~80 MB |
| Very Large | 50K+ | 250K+ | ~200 MB+ |

> **Note**: Ensure server has sufficient RAM. Memory usage is displayed on startup for monitoring.

---

## Security Architecture

### 1. Authentication

**Password Storage** (web_interface.py, line 1735+):
```python
# PBKDF2-SHA256 with 150,000 iterations
salt = secrets.token_hex(8)
iterations = 150000
hash_bytes = hashlib.pbkdf2_hmac(
    'sha256',
    password.encode('utf-8'),
    salt.encode('utf-8'),
    iterations
)
password_hash = f"pbkdf2:sha256:{iterations}${salt}${hash_bytes.hex()}"
```

**Session Management** (web_interface.py, line 141+):
```python
# Simple session tracking: username -> last_activity_timestamp
active_sessions = {}  # username -> timestamp

def update_session_activity(username: str):
    """Update the last activity timestamp for a user session"""
    if SESSION_TIMEOUT > 0:
        active_sessions[username] = time.time()

def check_session_expired(username: str) -> bool:
    """Check if a user's session has expired due to inactivity"""
    if SESSION_TIMEOUT <= 0:
        return False
    
    if username not in active_sessions:
        return True
    
    last_activity = active_sessions.get(username, 0)
    current_time = time.time()
    timeout_seconds = SESSION_TIMEOUT * 60
    
    if current_time - last_activity > timeout_seconds:
        active_sessions.pop(username, None)
        return True
    
    return False
```

**Features**:
- Configurable session timeout (default: 30 minutes)
- Automatic session expiration on inactivity
- Cookie-based authentication with HTTP-only flag
- Basic Auth fallback support

### 2. Authorization

**Current Implementation**:
- Single-level authentication (authenticated vs. unauthenticated)
- All authenticated users have full access
- No role-based access control (RBAC) implemented

**Future Enhancement**:
Role-based access control could be added to restrict operations by user role.

### 3. Audit Logging

**Actual Log Format** (web_interface.py, line 111+):
```
2024-01-15 10:30:45,123 - INFO - EVENT=LOGIN USER=admin IP=192.168.1.100 STATUS=success
2024-01-15 10:31:12,456 - INFO - EVENT=DEPLOY_POLICIES USER=admin IP=192.168.1.100 STATUS=success DETAILS=policies=5 success=5 failed=0
2024-01-15 10:35:20,789 - INFO - EVENT=LOGOUT USER=admin IP=192.168.1.100 STATUS=success
```

**Implementation**:
```python
def log_audit(event_type, username, client_ip="unknown", details=None, status="success"):
    """Log an audit event"""
    if not ENABLE_AUDIT:
        return
    
    message = f"EVENT={event_type} USER={username} IP={client_ip} STATUS={status}"
    if details:
        message += f" DETAILS={details}"
    audit_logger.info(message)
```

**Features**:
- Rotating file handler (10MB max, 5 backups)
- Configurable via environment variables
- Logs: LOGIN, LOGOUT, DEPLOY_POLICIES, SESSION_TIMEOUT, USER_REGISTER
- Can be disabled for development

### 4. CORS Configuration

**Implementation** (web_interface.py, line 1524+):
```python
def _add_cors_headers(self):
    """Add CORS headers to the response if enabled"""
    if ENABLE_CORS:
        self.send_header("Access-Control-Allow-Origin", CORS_ORIGINS)
        self.send_header("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
```

**Configuration**:
- Enabled by default
- Configurable origins (default: "*" for development)
- Supports preflight OPTIONS requests
- Can be restricted to specific domains in production

### 5. Security Best Practices

**Implemented**:
- Secure password hashing (PBKDF2-SHA256, 150K iterations)
- Random salt generation using `secrets` module
- Session timeout with configurable duration
- Audit logging for security events
- HTTP-only cookies to prevent XSS
- CORS headers for cross-origin control
- Security headers (CSP, X-Frame-Options, X-Content-Type-Options, HSTS)
  - Content-Security-Policy: `frame-ancestors 'self';`
  - X-Frame-Options: `SAMEORIGIN`
  - X-Content-Type-Options: `nosniff`
  - Strict-Transport-Security: `max-age=31536000; includeSubDomains`

**Not Implemented**:
- Input sanitization (relies on JSON parsing and type checking)
- Rate limiting for login attempts
- HTTPS enforcement (must be configured at deployment/infrastructure level)
- Role-based access control (RBAC)
- Comprehensive CSP (only frame-ancestors directive implemented)

---

## Scalability Considerations

### Current Limitations

**Single Instance Design**:
- In-memory session storage (`active_sessions` dict) prevents horizontal scaling
- All data loaded into memory at startup (~48MB for 14K policies + 70K events)
- No shared state mechanism between instances
- **Horizontal scaling NOT tested or supported**

### Tested Configuration

**Single Instance Performance**:
- Dataset: ~14K policies, ~70K events
- Memory usage: ~48MB data + ~200MB Python runtime = ~250MB total
- Tested on: 1 CPU core, 512MB RAM
- Concurrent users: Not formally tested (estimated 10-50 users)

**Resource Requirements** (Estimated):

| Dataset Size | Memory | CPU | Notes |
|--------------|--------|-----|-------|
| Small (1K policies, 10K events) | 256MB | 0.5 core | Tested configuration |
| Medium (14K policies, 70K events) | 512MB | 1 core | Current production use |
| Large (50K policies, 250K events) | 1GB | 1-2 cores | Extrapolated, not tested |
| X-Large (100K+ policies, 1M+ events) | 2GB+ | 2+ cores | May require optimization |

### Performance Observations

**Measured on test dataset** (14K policies, 70K events):
- Initial data load: ~2-3 seconds
- Page load time: ~1-2 seconds (first load)
- Search response: <100ms (with search index)
- Event table load: ~300ms (server-side processing)
- Policy deployment: ~20-30 seconds for batch of 5-10 policies

**Note**: Performance metrics are observational, not from formal load testing.

---

## API Design

### REST Endpoints

#### GET /api/policies
Get all policies with optional filtering.

**Query Parameters**:
- `search` - Search term
- `deployed` - Filter by deployment status
- `group_id` - Filter by group ID

**Response**:
```json
{
  "data": [
    {
      "policy_id": "policy-123",
      "ranking_score": 0.95,
      "event_count": 42,
      "policy_type": "temporal",
      "deployed": true
    }
  ]
}
```

#### GET /api/events/{policy_id}
Get events for a specific policy.

**Response**:
```json
{
  "data": [
    {
      "event_id": "event-456",
      "severity": 4,
      "summary": "Alert message",
      "timestamp": "2024-01-15T10:30:00Z"
    }
  ]
}
```

#### GET /api/payload/{event_id}
Get detailed payload for an event.

**Response**:
```json
{
  "raw": "{...}",
  "pretty": "{\n  ...\n}",
  "parsed": {...}
}
```

#### POST /api/deploy_policies
Deploy multiple policies.

**Request**:
```json
{
  "base_url": "https://policy-registry.example.com",
  "username": "admin",
  "password": "secret",
  "ids": ["policy-1", "policy-2"],
  "verify_tls": false,
  "timeout": 60,
  "concurrency": 5
}
```

**Response**:
```json
{
  "ok": ["policy-1", "policy-2"],
  "fail": [],
  "urls": {
    "policy-1": "https://...policy-1",
    "policy-2": "https://...policy-2"
  }
}
```

---

---

## References

- [Installation Guide](INSTALL.md)
- [User Guide](USER_GUIDE.md)
- [Developer Guide](DEVELOPER_GUIDE.md)
- [Auto-Update Guide](AUTO_UPDATE_GUIDE.md)
- [API Reference](API.md)