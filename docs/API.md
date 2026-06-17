# API Reference

This document describes all HTTP API endpoints provided by the Policy and Event Data Visualization web interface.

> **Note:** This API documentation is generated from source code analysis. While the endpoints and their behavior are documented accurately based on the implementation in `web_interface.py`, it is recommended to test the endpoints in your environment. A test script is provided in `src/test_api_endpoints.py` to validate all endpoints.

## Base URL

```
http://<host>:<port>
```

Default port: `5000`

## Authentication

When authentication is enabled (`ENABLE_AUTH=true`), all API endpoints require HTTP Basic Authentication or a valid session cookie.

### Authentication Endpoints

#### POST /api/register
Register a new user account.

**Request Body:**
```json
{
  "username": "string",
  "password": "string"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Account created successfully!"
}
```

**Errors:**
- `400` - Invalid input or username already exists
- `500` - Registration failed

---

#### POST /api/login
Authenticate and create a session.

**Request Body:** (form-urlencoded)
```
username=<username>&password=<password>
```

**Response:**
- `302` redirect to main page with auth cookie set

**Errors:**
- `401` - Invalid credentials

---

#### POST /logout
End the current session.

**Response:**
- `302` redirect to login page with auth cookie cleared

---

## Data Endpoints

### Server-Side DataTables Endpoints

These endpoints support server-side processing for DataTables with pagination, sorting, searching, and advanced filtering.

#### GET /api/policies_ss
Get policies with server-side pagination and filtering.

**Query Parameters:**
- `draw` - DataTables draw counter
- `start` - Starting record index
- `length` - Number of records to return
- `search[value]` - Global search term
- `order[0][column]` - Column index to sort by
- `order[0][dir]` - Sort direction (`asc` or `desc`)
- `group_id` - Filter by groupId (e.g., `related-events`, `seasonality`, `analytics.temporal-patterns`)
- `advancedFilter` - JSON string with advanced filter conditions

**Response:**
```json
{
  "draw": 1,
  "recordsTotal": 1000,
  "recordsFiltered": 50,
  "data": [
    {
      "policyId": "uuid",
      "name": "Policy Name",
      "groupId": "related-events",
      "type": "correlation",
      "deployed": true,
      ...
    }
  ]
}
```

---

#### GET /api/events_ss
Get events with server-side pagination and filtering.

**Query Parameters:** (same as `/api/policies_ss`)

**Response:**
```json
{
  "draw": 1,
  "recordsTotal": 5000,
  "recordsFiltered": 100,
  "data": [
    {
      "eventId": "uuid",
      "policyId": "uuid",
      "Severity": 5,
      "Node": "server01",
      "Summary": "Event description",
      ...
    }
  ]
}
```

---

#### GET /api/event_instances_ss
**⚠️ DEPRECATED** - This endpoint requires SQLite mode which is no longer used.

Get event instances with server-side pagination and filtering.

**Query Parameters:** (same as `/api/policies_ss`)

**Response:**
```json
{
  "error": "SQLite mode required for /api/event_instances_ss"
}
```

**Status:** `400 Bad Request` - SQLite mode is deprecated and disabled

---

### Legacy Endpoints

#### GET /api/policies
Get all policies (legacy, non-paginated).

**Response:**
```json
[
  {
    "policyId": "uuid",
    "name": "Policy Name",
    ...
  }
]
```

---

#### GET /api/events
Get all events (legacy, non-paginated).

**Response:**
```json
[
  {
    "eventId": "uuid",
    "policyId": "uuid",
    ...
  }
]
```

---

#### GET /api/payloads
Get all event payloads (legacy, non-paginated).

**Response:**
```json
[
  {
    "eventId": "uuid",
    "payload": {...}
  }
]
```

---

### Pattern Configuration

#### GET /api/pattern_config/{policyId}
Get temporal pattern configuration for a specific policy.

**Path Parameters:**
- `policyId` - Policy UUID

**Response:**
```json
{
  "policyId": "uuid",
  "conditionSets": [
    {
      "conditions": [...],
      "timeWindow": 300
    }
  ]
}
```

**Errors:**
- `404` - Policy not found or no pattern config available

---

### Payload Preview and Download

#### GET /api/payload_preview/{eventId}
Get a preview of an event's payload (first 500 characters).

**Path Parameters:**
- `eventId` - Event UUID

**Response:**
```json
{
  "eventId": "uuid",
  "preview": "...",
  "truncated": true
}
```

---

#### GET /api/payload_download/{eventId}
Download the full payload for an event.

**Path Parameters:**
- `eventId` - Event UUID

**Response:**
- Content-Type: `application/json`
- Content-Disposition: `attachment; filename="payload_{eventId}.json"`

---

### Configuration

#### GET /api/config
Get runtime configuration for the web interface.

**Response:**
```javascript
// JavaScript code that sets window.APP_CONFIG
window.APP_CONFIG = {
  "enableAuth": true,
  "sessionTimeout": 30,
  "enableCors": true,
  "corsOrigins": "*",
  "forceLoginPage": true
};
```

**Content-Type:** `application/javascript`

---

#### GET /api/last_update
Get the timestamp of the last data update.

**Response:**
```json
{
  "last_update": "2024-01-01T12:00:00Z"
}
```

---

### Deployment Cache

#### GET /api/deploy_cache
Get the current deployment cache (list of deployed policy IDs).

**Response:**
```json
{
  "ids": ["uuid1", "uuid2", ...],
  "path": "/path/to/deployed_cache.json"
}
```

---

#### POST /api/deploy_cache
Update the deployment cache.

**Request Body:**
```json
{
  "ids": ["uuid1", "uuid2", ...]
}
```

**Response:**
```json
{
  "success": true
}
```

---

#### DELETE /api/deploy_cache
Clear the deployment cache.

**Response:**
```json
{
  "success": true
}
```

---

### Policy Deployment

#### POST /api/deploy_policies
Deploy selected policies to NOI/Event Manager.

**Request Body:**
```json
{
  "policyIds": ["uuid1", "uuid2", ...],
  "noiUrl": "https://noi-server",
  "username": "admin",
  "password": "password"
}
```

**Response:**
```json
{
  "success": true,
  "deployed": 5,
  "failed": 0,
  "results": [...]
}
```

**Errors:**
- `400` - Invalid request
- `500` - Deployment failed

---

## Advanced Filtering

The `/api/policies_ss` and `/api/events_ss` endpoints support advanced filtering via the `advancedFilter` query parameter.

### Filter Format

```json
{
  "conditions": [
    {
      "column": "Severity",
      "operator": ">",
      "value": "3"
    },
    {
      "column": "Node",
      "operator": "contains",
      "value": "prod"
    }
  ],
  "logic": "AND"
}
```

### Supported Operators

**Numeric columns:**
- `=` - Equal to
- `!=` - Not equal to
- `>` - Greater than
- `>=` - Greater than or equal
- `<` - Less than
- `<=` - Less than or equal

**String columns:**
- `=` - Equals (exact match)
- `!=` - Not equals
- `contains` - Contains substring
- `!contains` - Does not contain
- `starts with` - Starts with
- `ends with` - Ends with

**DateTime columns:**
- `=` - On date
- `>` - After
- `<` - Before
- `between` - Between two dates

---

## Static Assets

#### GET /static/{filename}
Serve static files (CSS, JavaScript, images).

**Examples:**
- `/static/app.js`
- `/static/styles.css`
- `/static/advanced-filter.js`
- `/static/config-handler.js`

---

## Error Responses

All endpoints may return the following error responses:

### 400 Bad Request
```json
{
  "error": "Error message"
}
```

### 401 Unauthorized
```json
{
  "error": "Authentication required"
}
```

### 404 Not Found
```json
{
  "error": "Resource not found"
}
```

### 500 Internal Server Error
```json
{
  "error": "Internal server error"
}
```

---

## CORS Support

When CORS is enabled (`ENABLE_CORS=true`), all API endpoints include the following headers:

```
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: GET,POST,DELETE,OPTIONS
Access-Control-Allow-Headers: Content-Type,Authorization
```

---

## Rate Limiting

Currently, no rate limiting is implemented. Consider adding rate limiting for production deployments.

---

## Examples

### Fetch Policies with cURL

```bash
curl -u username:password \
  "http://localhost:5000/api/policies_ss?draw=1&start=0&length=10"
```

### Advanced Filter Example

```bash
curl -u username:password \
  -G "http://localhost:5000/api/events_ss" \
  --data-urlencode 'advancedFilter={"conditions":[{"column":"Severity","operator":">","value":"3"}],"logic":"AND"}'
```

### Deploy Policies

```bash
curl -u username:password \
  -X POST "http://localhost:5000/api/deploy_policies" \
  -H "Content-Type: application/json" \
  -d '{
    "policyIds": ["uuid1", "uuid2"],
    "noiUrl": "https://noi-server",
    "username": "admin",
    "password": "password"
  }'
```

---

## Testing the API

A comprehensive test script is provided to validate all API endpoints.

**Prerequisites:** The web server must be running before testing:

```bash
# Start the web server first
cd src
python web_interface.py

# In another terminal, run the tests
python src/test_api_endpoints.py

# Test with authentication
python src/test_api_endpoints.py --username admin --password password

# Test remote server
python src/test_api_endpoints.py --host 192.168.1.100 --port 8080
```

The test script validates:
- ✅ Static asset serving
- ✅ Authentication endpoints (register, login, logout)
- ✅ Data endpoints (policies, events, event instances)
- ✅ Legacy endpoints
- ✅ Utility endpoints (config, last_update, deploy_cache)
- ✅ Advanced filtering
- ✅ Pattern configuration endpoints

**Test Output:**
```
============================================================
API Endpoint Test Suite
Testing: http://localhost:5000
Auth: Disabled
============================================================

============================================================
Static Assets
============================================================

✓ GET / (main page)
  → Status: 200
✓ GET /static/app.js
  → Status: 200
...

============================================================
Test Summary
============================================================
Passed:  25
Failed:  0
Skipped: 2
Total:   27
============================================================
```

---

## See Also

- [Architecture Documentation](ARCHITECTURE.md)
- [Auto-Update Guide](AUTO_UPDATE_GUIDE.md)
- [Main README](../README.md)
- [Test Script](../src/test_api_endpoints.py)
