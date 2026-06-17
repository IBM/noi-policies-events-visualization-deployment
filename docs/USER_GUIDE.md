# User Guide

Complete guide for using the NOI Policy & Event Visualization tool.

> **📖 Prerequisites**: Before using the application, see the [Operations Guide](OPERATIONS_GUIDE.md) for setup and deployment instructions.

## Table of Contents

- [Getting Started](#getting-started)
- [Web Interface Overview](#web-interface-overview)
- [Policy Management](#policy-management)
- [Event Analysis](#event-analysis)
- [Search and Filtering](#search-and-filtering)
- [Deployment Operations](#deployment-operations)
- [Data Export](#data-export)
- [Tips and Best Practices](#tips-and-best-practices)
- [Troubleshooting](#troubleshooting)

---

## Getting Started

### Accessing the Application

1. **Local Development**:
   ```
   http://localhost:5000
   ```

2. **Kubernetes/OpenShift**:
   
   If you used `setup-web-interface.sh`, a route is automatically created.
   
   **Option A: Use the create-route.sh script (recommended)**
   ```bash
   # Auto-detects namespace and creates route if needed
   ./create-route.sh
   
   # Or specify namespace explicitly
   ./create-route.sh noi-namespace
   ```
   
   **Option B: Manual route creation**
   ```bash
   # Create a route to expose the service
   oc expose service evtmanager-ibm-ea-web-interface -n <namespace>
   
   # Get the route URL
   oc get route evtmanager-ibm-ea-web-interface -n <namespace> -o jsonpath='{.spec.host}'
   ```
   
   **Option C: Port forwarding (for testing)**
   ```bash
   oc port-forward service/evtmanager-ibm-ea-web-interface 5000:5000 -n <namespace>
   # Access at http://localhost:5000
   ```

### First Login

**Default Credentials**:
- Username: `admin`
- Password: `changeme`

⚠️ **Important**: Change the default password immediately after first login!

**Changing Password**:
```bash
# On the server/pod
python manage_users.py change-password admin
```

---

## Web Interface Overview

### Main Layout

```
┌─────────────────────────────────────────────────────────────┐
│  Header: NOI Policy & Event Visualization                   │
│  [Search Box]                              [User: admin] [⚙] │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Policy Browser                                      │   │
│  │ [Deploy Selected] [Clear Deployed Cache] [Export Selected]                     │   │
│  │  ┌──────┬──────────┬───────┬────────┬──────────┐   │   │
│  │  │ ID   │ Score    │ Count │ Type   │ Deployed │   │   │
│  │  ├──────┼──────────┼───────┼────────┼──────────┤   │   │
│  │  │ p-1  │ 0.95     │ 42    │ temp   │ ✓        │   │   │
│  │  │ p-2  │ 0.87     │ 28    │ patt   │ ✗        │   │   │
│  │  └──────┴──────────┴───────┴────────┴──────────┘   │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Event Details: policy-123        [Export Data]  │     │
│  │  │ ID   │ Severity │ Resource │ Summary          │ │   │
│  │  ├──────┼──────────┼──────────┼──────────────────┤ │   │
│  │  │ e-1  │ Critical │ server1  │ CPU high         │ │   │
│  │  │ e-2  │ Warning  │ server2  │ Memory alert     │ │   │
│  │  └──────┴──────────┴──────────┴──────────────────┘ │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

### Key Components

1. **Header Bar**
   - Application title
   - Global search box


2. **Policy Browser Panel**
   - Interactive table of all policies
   - Sorting and filtering
   - Bulk selection
   - Deployment controls

3. **Event Details Panel**
   - Events for selected policy
   - Event details viewer
   - JSON payload inspector
   - Data export

---

## Policy Management

### Switching Between Policy Types

The application displays two types of policies in separate tabs located at the top of the interface:

**Temporal Grouping Tab** (Blue button):
- Displays temporal policies that group events based on time patterns
- Shows events occurring within specific time windows
- Useful for identifying time-based correlations
- Displays columns: Policy ID, Ranking, Events, Occurs, Deployed
- Right panel shows "Event Details" with event table and payload viewer

**Temporal Patterns Tab** (Light blue button):
- Displays pattern policies that group events based on content patterns
- Shows events matching specific field patterns or conditions
- Useful for identifying content-based correlations
- Displays columns: Policy ID, Ranking, Deployed
- Right panel shows "Pattern Details" with pattern hierarchy and condition sets

**How to Switch**:
1. Look for the two tabs at the top of the page (next to Policy Registry URL fields)
2. Click "Temporal Grouping" to view temporal policies
3. Click "Temporal Patterns" to view pattern policies
4. Note: "Click tabs to switch views (page will reload)" - the page refreshes when switching
5. Each tab maintains its own selection, sorting, and filtering state

### Viewing Policies

**Policy Table Columns**:

| Column | Description | Example |
|--------|-------------|---------|
| **Policy ID** | Unique identifier | `f7d2ad7b-5467-11f1-8719-1bc5a507a4f1100` |
| **Ranking** | Quality score (0-10) | `5` |
| **Events** | Number of events | `3` |
| **Occurs** | Occurrence count | `3` |
| **Deployed** | Deployment status | `Yes` badge or empty |

**Sorting**:
- Click column headers to sort
- Click again to reverse order
- Multi-column sorting: Shift+Click

**Pagination**:
- Default: 10 policies per page
- Options: 10, 25, 50, 100, All
- Navigate: Previous/Next buttons

### Selecting Policies

**Single Selection**:
- Click checkbox in first column
- Click anywhere on row (except links)

**Bulk Selection**:
- Click "Select All" checkbox in header
- Selects all policies on current page
- Use with filters for targeted selection

**Selection Tips**:
```
✓ Select high-scoring policies (>0.8)
✓ Select policies with many events (>20)
✓ Review before deploying
✗ Don't select all without review
```

### Policy Details

**Viewing Details**:
1. Click on Policy ID
2. Events panel updates automatically
3. Header shows: "Event Details: {policy_id}"

**Information Available**:
- Policy configuration
- Associated events
- Deployment status
- Performance metrics

---

## Event Analysis

### Event Table

**Event Columns**:

| Column | Description | Example |
|--------|-------------|---------|
| **Event ID** | Unique identifier | `evt-789` |
| **Severity** | Alert severity (1-5) | `5` (Critical) |
| **Resource** | Affected resource | `server1.example.com` |
| **Summary** | Brief description | `CPU usage above 90%` |
| **Details** | Additional info | `CPU: 95%, Duration: 5m` |
| **Type** | Event type | `Alert`, `Problem` |

**Severity Levels**:
- **5** - Critical
- **4** - Major
- **3** - Minor
- **2** - Warning
- **1** - Informational

### Viewing Event Details

**Basic Details**:
1. Click on Event ID
2. Modal popup shows details
3. View summary, resource, severity

**JSON Payload**:
1. Click "View Payload" button
2. See raw JSON data
3. Pretty-printed format
4. Copy to clipboard

**Example Payload**:
```json
{
  "event_id": "evt-789",
  "severity": 4,
  "resource": "server1.example.com",
  "summary": "CPU usage above 90%",
  "timestamp": "2024-01-15T10:30:00Z",
  "details": {
    "cpu_percent": 95,
    "duration_seconds": 300,
    "threshold": 90
  },
  "tags": ["performance", "cpu", "critical"]
}
```

### Event Filtering

The application provides real-time filtering using the search box at the top of each table:

**Global Search**:
- Type any text in the search box to filter across all columns
- Search works on policies, events, severity, resources, timestamps, etc.
- Results update instantly as you type
- Case-insensitive search

**Examples**:
- Search for `critical` - finds all events/policies with "critical" in any field
- Search for `server1` - finds all entries related to server1
- Search for `5` - finds severity 5 events and any other fields containing "5"
- Search for `cpu` - finds CPU-related policies and events

---

## Search and Filtering

### Global Search

**Search Box** (top right):
- Searches across all policy fields
- Real-time results
- Case-insensitive
- Supports partial matches

**Search Examples**:

| Query | Matches |
|-------|---------|
| `database` | Policies with "database" in any field |
| `0.9` | Policies with score ≥0.9 |
| `group-123` | Policies in group-123 |
| `deployed:true` | Only deployed policies |

### Advanced Filter

The Advanced Filter feature provides powerful, structured filtering capabilities for finding policies based on specific event criteria.

**Accessing Advanced Filter**:
1. Look for the **"Advanced Filter"** button next to the global search box (top right)
2. Click the button to open the filter builder modal

**Building Filter Conditions**:

1. **Add Conditions**:
   - Click "+ Add Condition" to create a new filter rule
   - Each condition has three parts: Column, Operator, Value

2. **Select Column**:
   - **Severity**: Event severity level (1-5)
   - **Resource**: Affected resource name
   - **Summary**: Event summary text
   - **Type**: Event type code
   - **Event ID**: Unique event identifier
   - **Details**: Additional event details

3. **Choose Operator**:
   
   For **numeric columns** (Severity, Type):
   - `=` Equals
   - `≠` Not Equals
   - `>` Greater Than
   - `≥` Greater or Equal
   - `<` Less Than
   - `≤` Less or Equal
   
   For **text columns** (Resource, Summary, Event ID, Details):
   - `Equals` - Exact match
   - `Not Equals` - Does not match exactly
   - `Contains` - Contains substring
   - `Does Not Contain` - Does not contain substring
   - `Starts With` - Begins with text
   - `Ends With` - Ends with text

4. **Enter Value**:
   - Type the value to match against
   - Numbers for numeric columns
   - Text for string columns

5. **Combine Multiple Conditions**:
   - **AND** - All conditions must match (default)
   - **OR** - Any condition can match
   - Select logic from dropdown when you have 2+ conditions

**Filter Examples**:

| Use Case | Conditions | Logic |
|----------|-----------|-------|
| Critical events only | Severity = 5 | N/A |
| Database issues | Resource Contains "database" | N/A |
| High severity on specific server | Severity > 3 AND Resource = "server1" | AND |
| Multiple resources | Resource = "server1" OR Resource = "server2" | OR |
| Complex query | Severity ≥ 4 AND Summary Contains "CPU" | AND |

**Using the Filter**:

1. **Apply Filter**:
   - Click "Apply Filter" button
   - Modal closes automatically
   - Green badge appears showing active filter
   - Policy table updates to show only policies with matching events
   - Global search box is automatically cleared

2. **View Active Filter**:
   - Green badge displays: "Filtered (X conditions)"
   - Click badge to edit filter
   - Hover over badge to see tooltip

3. **Clear Filter**:
   - Click the **✕** button on the green badge
   - Or open modal and click "Clear All"
   - Or apply filter with no conditions (shows confirmation)

4. **Edit Filter**:
   - Click the green badge text (not the ✕)
   - Modal opens with current conditions
   - Modify and click "Apply Filter"

**Filter Preview**:
- The modal shows a real-time preview of your filter
- Example: `Severity Greater Than (>) '4' AND Resource Contains 'database'`
- Helps verify your filter before applying

**Important Notes**:
- ⚠️ Advanced filter and global text search are mutually exclusive
- ⚠️ Applying advanced filter clears any text in the global search box
- ⚠️ Filter works on events, then shows policies containing matching events
- ✓ Filter persists until cleared or page is refreshed
- ✓ All filter values are case-sensitive for text comparisons

**Tips**:
- Start with one condition and test
- Use "Contains" for flexible text matching
- Combine severity with resource for targeted filtering
- Use OR logic to find events from multiple sources
- Click "Clear All" to start over if filter becomes complex

---

## Deployment Operations

### Single Policy Deployment

**Steps**:
1. Enter Policy Registry credentials in the form fields at the top of the page:
   - **Registry URL**: Policy Registry route hostname (e.g., `https://policy-registry-route-hostname`)
   - **Username**: Policy Registry username (e.g., `admin`)
   - **Password**: Policy Registry password
2. Select policy checkbox(es) to deploy
3. Click "Deploy Selected" button
4. Confirm deployment (if prompted)
5. Monitor progress in the toast notification (top-right corner)

**Progress Display**:
- Real-time progress bar showing deployment status
- Counters: Done, Failed, In-flight, Total
- Percentage complete
- Automatic table refresh after completion

### Bulk Deployment

**Steps**:
1. Filter policies (optional)
2. Select multiple policies
3. Click "Deploy Selected"
4. Configure deployment
5. Monitor progress

**Progress Tracking**:
```
Deploying 10 policies...
[████████░░] 80% (8/10)
✓ policy-1
✓ policy-2
✗ policy-3 (timeout)
...
```

**Best Practices**:
- Deploy in batches of 10-20 (maximum selection limit is 20)
- Test with one policy first
- Monitor for errors
- Review failed deployments

**Customizing Selection Limit**:
Administrators can modify the maximum number of policies that can be selected for deployment by editing the `MAX_DEPLOY_SELECTION` constant in `static/app.js`:
```javascript
const MAX_DEPLOY_SELECTION = 20;  // Change this value as needed
```
This limit prevents excessive server load and potential timeouts. The default value of 20 provides a safe limit for most deployments.

### Deployment Configuration

**Base URL**:
- Policy Registry endpoint
- Example: `https://<hostname for policyregistry route>/api/policies/user/v1/policies/activate/system`
- Must be accessible from server
- **Setup Guide**: See [IBM NOI Policy Registry Setup](https://www.ibm.com/docs/en/noi/1.6.15?topic=guardrails-enabling-policy-registry-service-swagger) for enabling and configuring the Policy Registry service

**Authentication**:
- Username and password required
- Credentials validated before deployment
- Stored in session only (not persisted)
- **Options**:
  - Use system user credentials (e.g., `admin`)
  - Use API key with Policy Registry access enabled
  - See [IBM NOI API Keys Documentation](https://www.ibm.com/docs/en/noi/1.6.15?topic=api-keys) for creating and managing API keys with Policy Registry permissions

**Internal Configuration** (hardcoded in `static/app.js`):
- **TLS Verification**: Disabled (`verify_tls: false`)
- **Request Timeout**: 2 minutes (120 seconds)
- **Concurrency**: 8 policies processed in parallel per batch
- **Max Concurrent Requests**: 3 batches can be deployed simultaneously

These values are optimized for typical deployments but can be modified by administrators in the source code if needed.

**Concurrency Guidelines**:
- Low load: 10
- Medium load: 5
- High load: 2
- Unstable network: 1

### Deployment Results

**Success**:
```
✓ Successfully deployed 8 policies
  - policy-1: https://registry.../policy-1
  - policy-2: https://registry.../policy-2
  ...
```

**Partial Success**:
```
⚠ Deployed 6 of 10 policies
✓ Success: policy-1, policy-2, ...
✗ Failed: policy-8 (timeout), policy-9 (auth error)
```

**Failure**:
```
✗ Deployment failed
Error: Connection refused
Check network connectivity and credentials
```

### Clear Deploy Cache

The application maintains a cache of successfully deployed policies to prevent redundant deployments and improve performance.

**Deploy Cache Button**:
- Located in the Policy Summary toolbar (yellow button with trash icon)
- Shows badge with number of cached policies (e.g., "30")
- Click "Clear Deploy Cache" to reset the cache

**When to Clear Cache**:
- After manually undeploying policies through Policy Registry
- When you want to re-deploy previously deployed policies
- To refresh deployment status after external changes
- Troubleshooting deployment issues

**Cache Behavior**:
- Automatically tracks successfully deployed policies
- Persists across browser sessions (stored in localStorage)
- Badge count updates in real-time as policies are deployed
- Clearing cache does NOT undeploy policies from Policy Registry

---

## Data Export

### Export Policy Data

**CSV Export**:
1. Click "Export Selected" button
2. File downloads automatically
3. Opens in Excel/Sheets

**Export Format**:
```csv
Policy ID,Ranking,Events,Occurs,Deployed
f7d2ad7b-5467-11f1-8719-1bc5a507a4f1100,5,3,3,Yes
f7d2ad79-5467-11f1-8719-1bc5a507a4f1100,5,3,3,Yes
f7d2ad78-5467-11f1-8719-1bc5a507a4f1100,5,3,3,Yes
```

**Use Cases**:
- Offline analysis
- Reporting
- Backup
- Integration with other tools

### Export Event Data

**Extract Data Button**:
1. Select policy
2. View events
3. Click "Extract Data"
4. CSV downloads

**Event Export Format**:
```csv
Event ID,Severity,Resource,Summary,Details,Type
evt-1,4,server1,CPU high,"CPU: 95%",Alert
evt-2,3,server2,Memory warning,"Mem: 85%",Alert
```

**Columns Included**:
- Event ID
- Severity
- Resource
- Summary
- Details
- Type

**Data Handling**:
- JSON objects properly escaped
- Commas in text handled
- UTF-8 encoding
- Excel-compatible

---

## Tips and Best Practices

### Performance Tips

**Large Datasets**:
- Use pagination (don't show "All")
- Apply filters before selecting
- Export in batches
- Close unused tabs

**Search Optimization**:
- Use specific terms
- Filter by type first
- Clear old searches

### Workflow Recommendations

**Daily Operations**:
1. Review new policies
2. Check high-scoring policies
3. Deploy approved policies
4. Monitor deployment status
5. Export reports

**Policy Review Process**:
```
1. Filter by score >=0.8
2. Review event counts
3. Check policy types
4. Verify not deployed
5. Select for deployment
6. Deploy in batches
7. Verify success
```

### Security Best Practices

**Credentials**:
- Change default password
- Use strong passwords
- Don't share accounts
- Log out when done

**Access Control**:
- Limit deployment access
- Review audit logs
- Monitor user activity
- Rotate passwords regularly

**Data Protection**:
- Don't export sensitive data
- Secure exported files
- Delete old exports
- Use encrypted connections

---

## Troubleshooting

### Common Issues

#### Cannot Login

**Symptoms**:
- "Invalid credentials" error
- Login page reloads

**Solutions**:
1. Verify username/password
2. Check caps lock
3. Reset password:
   ```bash
   python manage_users.py change-password admin
   ```
4. Check user exists:
   ```bash
   python manage_users.py list
   ```

#### Policies Not Loading

**Symptoms**:
- Empty policy table
- "Loading..." never completes

**Solutions**:
1. Check data files exist:
   ```bash
   ls -lh output/policy_summary.csv
   ```
2. Verify file permissions
3. Check server logs:
   ```bash
   tail -f logs/web_interface.log
   ```
4. Reload data:
   ```bash
   curl -X POST http://localhost:5000/api/reload
   ```

#### Events Not Showing

**Symptoms**:
- Click policy, no events appear
- Event panel empty

**Solutions**:
1. Verify events file:
   ```bash
   ls -lh output/events_detail.csv
   ```
2. Check policy has events
3. Clear browser cache
4. Check console for errors (F12)

#### Deployment Fails

**Symptoms**:
- "Connection refused"
- "Timeout"
- "Authentication failed"

**Solutions**:

**Connection Issues**:
```bash
# Test connectivity
curl -v https://policy-registry.example.com

# Check DNS
nslookup policy-registry.example.com

# Test from pod
oc exec policy-viz-pod -- curl https://...
```

**Authentication Issues**:
- Verify credentials
- Check user permissions
- Test with curl:
  ```bash
  curl -u admin:password https://registry.../api/policies
  ```

**Timeout Issues**:
- Increase timeout value
- Reduce concurrency
- Check network latency
- Deploy smaller batches

#### Search Not Working

**Symptoms**:
- Search returns no results
- Search box unresponsive

**Solutions**:
1. Clear search box
2. Refresh page
3. Check browser console for JavaScript errors
4. Verify DataTables is loaded correctly

#### Export Fails

**Symptoms**:
- Download doesn't start
- File is empty
- File is corrupted

**Solutions**:
1. Check browser downloads folder
2. Disable popup blocker
3. Try different browser
4. Check server logs
5. Verify data exists

### Performance Issues

#### Slow Page Load

**Causes**:
- Large dataset
- Slow network
- Server overload

**Solutions**:
1. Enable pagination
2. Reduce page size
3. Apply filters
4. Clear browser cache
5. Increase server resources

#### High Memory Usage

**Causes**:
- Too many policies loaded
- Large event payloads
- Memory leak

**Solutions**:
1. Restart server
2. Reduce dataset size
3. Increase server memory (check startup logs for current usage)
4. Monitor with:
   ```bash
   top -p $(pgrep -f web_interface.py)
   ```

### Browser Issues

#### Compatibility

**Recommended Browsers**:
- Chrome (latest)
- Firefox (latest)
- Safari (latest)
- Edge (latest)

**Note**: The application uses modern JavaScript features and may not work on older browsers. For best results, use the latest version of a modern browser.

#### Console Errors

**Check Console**:
1. Press F12
2. Click "Console" tab
3. Look for red errors
4. Copy error message

**Common Errors**:
```javascript
// CORS error
Access to fetch at '...' has been blocked by CORS policy

// Solution: Check CORS configuration

// Network error
Failed to fetch

// Solution: Check server is running

// JavaScript error
Uncaught TypeError: Cannot read property '...'

// Solution: Clear cache and reload
```

### Getting Help

**Log Files**:
```bash
# Application logs
tail -f logs/web_interface.log

# Audit logs
tail -f logs/audit.log

# Error logs
grep ERROR logs/web_interface.log
```

**Debug Mode**:
```bash
# Enable debug logging
export LOG_LEVEL=DEBUG
python web_interface.py
```

**Support Channels**:
- GitHub Issues: Report bugs
- Documentation: Check guides
- Community: Ask questions

---

## Glossary

**Policy**: A rule or pattern for grouping related events

**Event**: An alert or incident from monitoring systems

**Ranking Score**: Quality metric for policies (0-1, higher is better)

**Deployment**: Publishing a policy to the Policy Registry

**Payload**: Detailed JSON data for an event

**Group ID**: Identifier for a collection of related policies

**Temporal**: Time-based event grouping

**Pattern**: Similarity-based event grouping

---

## Next Steps

- [Installation Guide](INSTALL.md) - Setup instructions
- [Architecture Guide](ARCHITECTURE.md) - Technical details
- [Developer Guide](DEVELOPER_GUIDE.md) - Contributing
- [Auto-Update Guide](AUTO_UPDATE_GUIDE.md) - Configure automatic data updates
- [API Reference](API.md) - REST API documentation