#
# Copyright IBM Corp. 2024 - 2026
# SPDX-License-Identifier: Apache-2.0
#
#!/usr/bin/env python3
"""
Scalable web interface for policy & event data visualization using Python standard library.

- Pure stdlib HTTP server (ThreadingHTTPServer + BaseHTTPRequestHandler)
- Supports `analytics.temporal-patterns` (temporal patterns):
  * honors ?group_id=... in /api/policies_ss and /api/events_ss
  * loads condition_sets_by_policy.json from the chosen --output-dir
  * serves /api/pattern_config/<policy_id> with the condition set
"""

import argparse
import ast
import base64
import csv
import hashlib
import io
import json
import os
import secrets
import posixpath
import sqlite3
import ssl
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import parse_qs, quote, unquote, urlparse
from urllib.request import Request, urlopen
from datetime import datetime  # needed for ISO parsing
import logging
from logging.handlers import RotatingFileHandler

# -------------------- Config --------------------
# Set to True to enable verbose debug logging
DEBUG_VERBOSE = False

DEFAULT_EVENT_INSTANCES_FILE = "event_instances_export.csv"
DEFAULT_OUTPUT_DIR = "output"
DEFAULT_PORT = 5000
DEFAULT_BIND_ADDRESS = "0.0.0.0"
DEFAULT_CONFIG_FILE = "web_interface_config.ini"

# Write the viewer HTML *into the current working directory*
OUTPUT_HTML_NAME = "policy_event_viewer.html"
OUTPUT_HTML_DIR = os.getcwd()
OUTPUT_HTML_PATH = os.path.join(OUTPUT_HTML_DIR, OUTPUT_HTML_NAME)

# Hygiene / payload caps
MAX_REQUEST_BYTES = 16 * 1024 * 1024

# Helper function for debug logging
def debug_print(msg):
    """Print debug message only if DEBUG_VERBOSE is enabled"""
    if DEBUG_VERBOSE:
        print(msg)
STATIC_CACHE_SECS = 24 * 3600
HTML_CACHE = "no-store"
API_CACHE = "no-store"
PAYLOAD_PREVIEW_MAX = 1 * 1024 * 1024  # ~1MB

# Groups (canonical)
GROUP_PATTERNS = "analytics.temporal-patterns"
GROUP_RELATED  = "related-events"

# -------------------- Quiet/Debug toggles (default: quiet) --------------------
ACCESS_LOG = bool(int(os.environ.get("ACCESS_LOG", "0")))
DEBUG_TIMING = bool(int(os.environ.get("DEBUG_TIMING", "0")))

# -------------------- Security settings --------------------
ENABLE_AUTH = bool(int(os.environ.get("ENABLE_AUTH", "1")))
AUTH_CREDENTIALS = {}  # Will be populated with username:password pairs
USERS_FILE = os.environ.get("USERS_FILE", "users.csv")
ENABLE_CORS = bool(int(os.environ.get("ENABLE_CORS", "1")))
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*")
FORCE_LOGIN_PAGE = bool(int(os.environ.get("FORCE_LOGIN_PAGE", "1")))
SESSION_TIMEOUT = int(os.environ.get("SESSION_TIMEOUT", "30"))  # in minutes, 0 to disable

# -------------------- Audit logging --------------------
AUDIT_LOG_FILE = os.environ.get("AUDIT_LOG_FILE", "logs/audit.log")
ENABLE_AUDIT = bool(int(os.environ.get("ENABLE_AUDIT", "1")))
MAX_LOG_SIZE = int(os.environ.get("MAX_LOG_SIZE", "10485760"))  # 10MB
BACKUP_COUNT = int(os.environ.get("BACKUP_COUNT", "5"))

# Set up audit logger
audit_logger = logging.getLogger("audit")
audit_logger.setLevel(logging.INFO)
if ENABLE_AUDIT:
    try:
        # Create logs directory if it doesn't exist
        logs_dir = os.path.dirname(AUDIT_LOG_FILE)
        if logs_dir and not os.path.exists(logs_dir):
            os.makedirs(logs_dir, exist_ok=True)
            
        handler = RotatingFileHandler(
            AUDIT_LOG_FILE,
            maxBytes=MAX_LOG_SIZE,
            backupCount=BACKUP_COUNT
        )
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        audit_logger.addHandler(handler)
        print(f"[audit] Audit logging enabled, writing to {AUDIT_LOG_FILE}")
    except Exception as e:
        print(f"[audit] Error setting up audit logging: {e}")
        ENABLE_AUDIT = False

def log_audit(event_type, username, client_ip="unknown", details=None, status="success"):
    """Log an audit event"""
    if not ENABLE_AUDIT:
        return
        
    try:
        message = f"EVENT={event_type} USER={username} IP={client_ip} STATUS={status}"
        if details:
            message += f" DETAILS={details}"
        audit_logger.info(message)
    except Exception as e:
        print(f"[audit] Error logging audit event: {e}")

# Session tracking
active_sessions = {}  # username -> last_activity_timestamp

# Default credentials (for backward compatibility)
default_username = os.environ.get("AUTH_USERNAME", "admin")
default_password = os.environ.get("AUTH_PASSWORD", "changeme")
if default_username and default_password:
    AUTH_CREDENTIALS[default_username] = default_password

def parse_global_search(term: str):
    if not term:
        return "include", ""
    t = term.strip()
    if t.startswith("!"):
        return "exclude", t[1:].strip().lower()
    return "include", t.lower()

# Session management functions
def update_session_activity(username: str) -> None:
    """Update the last activity timestamp for a user session"""
    if SESSION_TIMEOUT > 0:  # Only track if timeout is enabled
        active_sessions[username] = time.time()
        if DEBUG_TIMING:
            print(f"[session] Updated activity for {username}")

def check_session_expired(username: str) -> bool:
    """Check if a user's session has expired due to inactivity"""
    if SESSION_TIMEOUT <= 0:  # Timeout disabled
        return False
        
    if username not in active_sessions:
        return True
        
    last_activity = active_sessions.get(username, 0)
    current_time = time.time()
    timeout_seconds = SESSION_TIMEOUT * 60  # Convert minutes to seconds
    
    # Check if the session has expired
    if current_time - last_activity > timeout_seconds:
        if DEBUG_TIMING:
            print(f"[session] Session expired for {username} after {SESSION_TIMEOUT} minutes of inactivity")
        # Remove the expired session
        active_sessions.pop(username, None)
        return True
        
    return False

# Load users from CSV file
def load_users_from_csv():
    global AUTH_CREDENTIALS
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, 'r', newline='') as f:
                reader = csv.reader(f)
                # Skip header
                next(reader, None)
                for row in reader:
                    if len(row) >= 2:
                        username, password_hash = row[0], row[1]
                        AUTH_CREDENTIALS[username] = password_hash
            print(f"Loaded {len(AUTH_CREDENTIALS)} users from {USERS_FILE}")
        except Exception as e:
            print(f"Error loading users from {USERS_FILE}: {e}")

# Verify password against stored hash
def verify_password(stored_hash: str, password: str) -> bool:
    """
    Verify a password against a stored hash
    
    Args:
        stored_hash: The stored hash in format pbkdf2:sha256:iterations$salt$hash
        password: The plaintext password to verify
        
    Returns:
        True if the password matches, False otherwise
    """
    try:
        if DEBUG_VERBOSE:
            print(f"[verify] Verifying password against hash: {stored_hash[:20]}...")
        
        # For backward compatibility with plain text passwords
        if not stored_hash.startswith("pbkdf2:"):
            if DEBUG_VERBOSE:
                print("[verify] Using plain text comparison")
            result = stored_hash == password
            if DEBUG_VERBOSE:
                print(f"[verify] Plain text match: {result}")
            return result
            
        # Parse the stored hash
        parts = stored_hash.split('$')
        if len(parts) != 3:
            if DEBUG_VERBOSE:
                print(f"[verify] Invalid hash format: expected 3 parts, got {len(parts)}")
            return False
            
        algorithm_parts = parts[0].split(':')
        if len(algorithm_parts) != 3:
            if DEBUG_VERBOSE:
                print(f"[verify] Invalid algorithm format: expected 3 parts, got {len(algorithm_parts)}")
            return False
            
        if algorithm_parts[0] != "pbkdf2" or algorithm_parts[1] != "sha256":
            if DEBUG_VERBOSE:
                print(f"[verify] Unsupported algorithm: {algorithm_parts[0]}:{algorithm_parts[1]}")
            return False
            
        iterations = int(algorithm_parts[2])
        salt = parts[1]
        stored_hash_value = parts[2]
        
        if DEBUG_VERBOSE:
            print(f"[verify] Algorithm: {algorithm_parts[0]}:{algorithm_parts[1]}")
            print(f"[verify] Iterations: {iterations}")
            print(f"[verify] Salt: {salt}")
            print(f"[verify] Stored hash value: {stored_hash_value[:10]}...")
        
        # Hash the provided password with the same parameters
        password_bytes = password.encode('utf-8')
        hash_bytes = hashlib.pbkdf2_hmac(
            'sha256',
            password_bytes,
            salt.encode('utf-8'),
            iterations
        )
        computed_hash = hash_bytes.hex()
        
        if DEBUG_VERBOSE:
            print(f"[verify] Computed hash value: {computed_hash[:10]}...")
        
        # Compare the hashes
        result = computed_hash == stored_hash_value
        if DEBUG_VERBOSE:
            print(f"[verify] Hash match: {result}")
        return result
    except Exception as e:
        if DEBUG_VERBOSE:
            print(f"[verify] Error verifying password: {e}")
            import traceback
            traceback.print_exc()
        return False

# Load users when module is imported
load_users_from_csv()

# -------------------- Globals --------------------
policy_summary_data: List[Dict[str, Any]] = []  # includes group_id, deployed
events_detail_data: List[Dict[str, Any]] = []
policy_events_payload_data: List[Dict[str, Any]] = []
CONDSETS_BY_POLICY: Dict[str, Any] = {}         # policy_id -> condition set object
DB_CONN: Optional[sqlite3.Connection] = None

# Search indexes for fast lookups (built during data load)
SEARCH_INDEX: Dict[str, Set[str]] = {}  # search_term -> set of policy_ids
POLICY_ID_INDEX: Dict[str, List[int]] = {}  # policy_id -> list of row indices in policy_events_payload_data

# ---- Deployed policy cache (server-side file) ----
DEPLOYED_CACHE_PATH = os.environ.get("DEPLOYED_CACHE_PATH", "deployed_cache.json")
_deployed_cache_lock = threading.Lock()
_deployed_cache_ids = set()

def _load_deployed_cache_on_startup():
    global _deployed_cache_ids
    try:
        with open(DEPLOYED_CACHE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f) or []
            _deployed_cache_ids = set(str(x) for x in data if x)
    except FileNotFoundError:
        _deployed_cache_ids = set()
    except Exception:
        _deployed_cache_ids = set()

def _save_deployed_cache():
    tmp = DEPLOYED_CACHE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(sorted(_deployed_cache_ids), f, indent=2)
    os.replace(tmp, DEPLOYED_CACHE_PATH)

def add_ids_to_deployed_cache(ids):
    if not ids:
        return
    with _deployed_cache_lock:
        for pid in ids:
            if pid:
                _deployed_cache_ids.add(str(pid))
        _save_deployed_cache()

def clear_deployed_cache():
    global _deployed_cache_ids
    with _deployed_cache_lock:
        _deployed_cache_ids.clear()
        try:
            os.remove(DEPLOYED_CACHE_PATH)
        except FileNotFoundError:
            pass

_load_deployed_cache_on_startup()

# -------------------- Utility --------------------
def _log_timing(label: str, start: float):
    if DEBUG_TIMING:
        dt = (time.perf_counter() - start) * 1000.0
        print(f"[timing] {label}: {dt:.1f} ms")

def _add_security_headers(handler):
    """Add security headers to help with iframe integration"""
    handler.send_header("Content-Security-Policy", "frame-ancestors 'self';")
    handler.send_header("X-Frame-Options", "SAMEORIGIN")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")

def _json_response(handler, obj, status=200, headers=None):
    body = json.dumps(obj).encode("utf-8")
    try:
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Cache-Control", "no-store, max-age=0")
        handler.send_header("Content-Length", str(len(body)))
        _add_security_headers(handler)
        if headers:
            for k, v in headers.items():
                handler.send_header(k, v)
        handler.end_headers()
        handler.wfile.write(body)
    except (BrokenPipeError, ConnectionResetError):
        handler.close_connection = True
    except Exception:
        handler.close_connection = True

def _send_404(handler):
    return _json_response(handler, {"error": "Not Found"}, status=404, headers={"Connection": "close"})

def _read_body_json(handler: BaseHTTPRequestHandler, max_bytes=MAX_REQUEST_BYTES) -> Dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    if length > max_bytes:
        raise ValueError("request too large")
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    try:
        return json.loads(raw.decode("utf-8") or "{}")
    except Exception:
        return {}

def _coerce(val):
    try:
        if val is None:
            return (1, None)
        if isinstance(val, (int, float)):
            return (0, val)
        s = str(val)
        if s.isdigit():
            return (0, int(s))
        return (0, float(s))
    except Exception:
        return (0, str(val))

def dt_page_mem(args: Dict[str, str], rows: List[Dict[str, Any]], columns: List[str], projector=None) -> Dict[str, Any]:
    draw = int(args.get("draw", "0") or 0)
    start = int(args.get("start", "0") or 0)
    length = int(args.get("length", "25") or 25)
    q = (args.get("search[value]", "") or "").lower().strip()
    order_col_idx = args.get("order[0][column]")
    order_dir = args.get("order[0][dir]", "asc")
    
    # Always report the total count accurately
    total_count = len(rows)
    
    # For large datasets, use a more efficient approach
    if len(rows) > 10000:
        # First apply ordering if specified
        if order_col_idx is not None:
            i = int(order_col_idx)
            key = columns[i] if i < len(columns) else columns[0]
            # Use a stable sort for consistent results
            rows = sorted(rows, key=lambda r: (_coerce(r.get(key)), r.get('policy_id', '')), reverse=(order_dir == "desc"))
        
        # Then apply filtering
        if q:
            tokens = q.split()
            # Process in chunks to avoid memory issues
            chunk_size = 1000
            filtered = []
            for i in range(0, len(rows), chunk_size):
                chunk = rows[i:i+chunk_size]
                for r in chunk:
                    hay = " ".join(str(r.get(c, "")) for c in columns).lower()
                    if all(t in hay for t in tokens):
                        filtered.append(r)
        else:
            filtered = rows
        
        # Get the requested page
        page = filtered[start:start+length]
        if projector:
            page = [projector(r) for r in page]
        
        # Add metadata to help the UI show loading status
        metadata = {
            "isLargeDataset": True,
            "totalPolicies": total_count,
            "loadedPolicies": len(filtered),
            "processingMode": "chunked"
        }
        
        return {
            "draw": draw,
            "recordsTotal": total_count,
            "recordsFiltered": len(filtered),
            "data": page,
            "metadata": metadata
        }
    else:
        # Original implementation for smaller datasets
        if q:
            tokens = q.split()
            def match(r):
                hay = " ".join(str(r.get(c, "")) for c in columns).lower()
                return all(t in hay for t in tokens)
            filtered = [r for r in rows if match(r)]
        else:
            filtered = rows

        if order_col_idx is not None:
            i = int(order_col_idx)
            key = columns[i] if i < len(columns) else columns[0]
            filtered = sorted(filtered, key=lambda r: _coerce(r.get(key)), reverse=(order_dir == "desc"))

        page = filtered[start:start+length]
        if projector:
            page = [projector(r) for r in page]

        # Add metadata for consistency
        metadata = {
            "isLargeDataset": False,
            "totalPolicies": total_count,
            "loadedPolicies": len(filtered),
            "processingMode": "standard"
        }

        return {
            "draw": draw,
            "recordsTotal": total_count,
            "recordsFiltered": len(filtered),
            "data": page,
            "metadata": metadata
        }

def _sql_like_fragment(tokens: List[str], cols: List[str]) -> Tuple[str, List[str]]:
    sql_parts, params = [], []
    for t in tokens:
        ors = []
        for c in cols:
            ors.append(f"LOWER({c}) LIKE ?")
            params.append(f"%{t}%")
        sql_parts.append("(" + " OR ".join(ors) + ")")
    return " AND ".join(sql_parts), params

def dt_page_sql(args: Dict[str, str], base_sql: str, count_sql: str, columns: List[str], orderable_cols: List[str], extra_params: Optional[List[Any]] = None):
    assert DB_CONN is not None
    extra_params = extra_params or []
    draw = int(args.get("draw", "0") or 0)
    start = int(args.get("start", "0") or 0)
    length = int(args.get("length", "25") or 25)
    q = (args.get("search[value]", "") or "").lower().strip()
    order_col_idx = args.get("order[0][column]")
    order_dir = args.get("order[0][dir]", "asc")

    cur = DB_CONN.cursor()
    total = cur.execute(count_sql, extra_params).fetchone()[0]

    where_sql = ""
    where_params: List[Any] = []
    if q:
        tokens = [t for t in q.split() if t]
        like_sql, like_params = _sql_like_fragment(tokens, columns)
        where_sql = (" WHERE " if "WHERE" not in base_sql.upper() else " AND ") + like_sql
        where_params = like_params

    filtered_count = total
    if where_sql:
        filtered_count = cur.execute(count_sql + where_sql, extra_params + where_params).fetchone()[0]

    order_sql = ""
    if order_col_idx is not None:
        i = int(order_col_idx)
        col = orderable_cols[i] if 0 <= i < len(orderable_cols) else orderable_cols[0]
        order_sql = f" ORDER BY {col} {'DESC' if order_dir == 'desc' else 'ASC'}"

    page_sql = f"{base_sql}{where_sql}{order_sql} LIMIT ? OFFSET ?"
    rows = cur.execute(page_sql, extra_params + where_params + [length, start]).fetchall()
    data = [dict(r) for r in rows]
    return {
        "draw": draw,
        "recordsTotal": total,
        "recordsFiltered": filtered_count,
        "data": data,
    }

def _maybe_float_or_int(s: str):
    try:
        if s.isdigit():
            return int(s)
        return float(s)
    except Exception:
        return s

# -------------------- Data loading --------------------
def _parse_deployed_map(output_dir: str) -> Dict[str, bool]:
    path = os.path.join("policies_export.csv")
    deployed_map: Dict[str, bool] = {}
    if not os.path.exists(path):
        return deployed_map
    with open(path, "r", encoding="utf-8") as f:
        rdr = csv.DictReader(f, delimiter=';')
        for r in rdr:
            pid = r.get("policy_id") or r.get("policyid") or r.get("policyId")
            cfg = r.get("configuration", "")
            if not pid:
                continue
            val = False
            if cfg:
                cfg = cfg.replace('\\"', '"')
                try:
                    obj = json.loads(cfg)
                except Exception:
                    try:
                        obj = ast.literal_eval(cfg)
                    except Exception:
                        obj = None
                if isinstance(obj, dict):
                    if "deployed" in obj:
                        v = obj["deployed"]
                        val = (str(v).strip().lower() in ("true","1","yes"))
                    elif "state" in obj:
                        val = (str(obj["state"]).strip().lower() in ("active","enabled","true"))
            deployed_map[pid] = val
    return deployed_map

def _load_condition_sets(output_dir: str) -> Dict[str, Any]:
    path = os.path.join(output_dir, "condition_sets_by_policy.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
            if isinstance(obj, dict):
                return obj
    except Exception:
        pass
    return {}

def _get_size_mb(obj) -> float:
    """Calculate approximate memory size of an object in MB"""
    import sys
    try:
        size_bytes = sys.getsizeof(obj)
        # For lists/dicts, recursively calculate size of contents
        if isinstance(obj, dict):
            size_bytes += sum(sys.getsizeof(k) + sys.getsizeof(v) for k, v in obj.items())
        elif isinstance(obj, (list, tuple)):
            size_bytes += sum(sys.getsizeof(item) for item in obj)
        return size_bytes / (1024 * 1024)  # Convert to MB
    except Exception:
        return 0.0

def load_data_to_memory(output_dir: str) -> bool:
    global policy_summary_data, events_detail_data, policy_events_payload_data, CONDSETS_BY_POLICY
    summary_path = os.path.join(output_dir, "policy_summary.csv")
    events_path = os.path.join(output_dir, "events_detail.csv")
    payload_path = os.path.join(output_dir, "policy_events_payload.csv")

    if not os.path.exists(summary_path):
        print(f"[load_data] Missing: {summary_path}")
        return False
    if not os.path.exists(events_path):
        print(f"[load_data] Missing: {events_path}")
        return False
    if not os.path.exists(payload_path):
        print(f"[load_data] Missing: {payload_path}")
        return False

    print(f"[memory] Loading data into memory...")
    t0 = time.perf_counter()
    try:
        dep_map = _parse_deployed_map(output_dir)
        rows_by_policy = {}

        with open(summary_path, "r", encoding="utf-8") as f:
            rdr = csv.DictReader(f)
            for r in rdr:
                pid = r.get("policy_id")
                if not pid:
                    continue

                rs  = _maybe_float_or_int(r.get("ranking_score", "") or "")
                ec  = _maybe_float_or_int(r.get("event_count", "") or "")
                eo  = _maybe_float_or_int(r.get("event_occurrences", "") or "")
                dep = 1 if dep_map.get(pid, False) else 0
                gid = r.get("group_id") or ""

                # keep last occurrence (or first — either is fine)
                rows_by_policy[pid] = (pid, rs, ec, eo, dep, gid)

        rows = list(rows_by_policy.values())
        
        # Convert tuples to dictionaries for policy_summary_data
        policy_summary_data = []
        for pid, rs, ec, eo, dep, gid in rows:
            policy_summary_data.append({
                "policy_id": pid,
                "ranking_score": rs,
                "event_count": ec,
                "event_occurrences": eo,
                "deployed": bool(dep),
                "group_id": gid
            })

        # Load events_detail (faster with list comprehension)
        print(f"[memory] Loading events_detail.csv...")
        with open(events_path, "r", encoding="utf-8", buffering=8*1024*1024) as f:
            events_detail_data = list(csv.DictReader(f))
        print(f"[memory]   Loaded {len(events_detail_data):,} events detail rows")

        # Load policy_events_payload with optimized JSON parsing
        print(f"[memory] Loading policy_events_payload.csv...")
        with open(payload_path, "r", encoding="utf-8", buffering=8*1024*1024) as f:
            rdr = csv.DictReader(f)
            policy_events_payload_data = []
            
            # Process in batches for progress indication
            batch = []
            batch_size = 50000
            row_count = 0
            
            for row in rdr:
                if "full_payload" in row:
                    try:
                        row["full_payload"] = json.loads(row["full_payload"])
                    except Exception:
                        pass
                batch.append(row)
                row_count += 1
                
                if len(batch) >= batch_size:
                    policy_events_payload_data.extend(batch)
                    batch = []
                    if row_count % 250000 == 0:
                        print(f"[memory]   Loaded {row_count:,} payload rows...")
            
            # Add remaining rows
            if batch:
                policy_events_payload_data.extend(batch)
        
        print(f"[memory]   Loaded {len(policy_events_payload_data):,} payload rows total")
        
        # Build search index for fast lookups
        print(f"[memory] Building search index for fast queries...")
        global SEARCH_INDEX, POLICY_ID_INDEX
        SEARCH_INDEX = {}
        POLICY_ID_INDEX = {}
        
        for idx, row in enumerate(policy_events_payload_data):
            policy_id = row.get("policy_id")
            if policy_id:
                if policy_id not in POLICY_ID_INDEX:
                    POLICY_ID_INDEX[policy_id] = []
                POLICY_ID_INDEX[policy_id].append(idx)
            
            # Index searchable fields
            for field in ("event_id", "payload_resource", "summary", "payload_details", "payload_type"):
                value = row.get(field)
                if value:
                    # Tokenize and index each word (lowercase)
                    words = str(value).lower().split()
                    for word in words:
                        if len(word) >= 3:  # Only index words 3+ chars
                            if word not in SEARCH_INDEX:
                                SEARCH_INDEX[word] = set()
                            SEARCH_INDEX[word].add(policy_id)
        
        print(f"[memory]   Indexed {len(SEARCH_INDEX):,} search terms covering {len(POLICY_ID_INDEX):,} policies")

        CONDSETS_BY_POLICY = _load_condition_sets(output_dir)

        # Calculate memory usage
        policy_size = _get_size_mb(policy_summary_data)
        events_size = _get_size_mb(events_detail_data)
        payload_size = _get_size_mb(policy_events_payload_data)
        patterns_size = _get_size_mb(CONDSETS_BY_POLICY)
        total_size = policy_size + events_size + payload_size + patterns_size
        
        # Display memory usage summary
        print(f"[memory] ═══════════════════════════════════════════════════════")
        print(f"[memory] Data loaded successfully into memory:")
        print(f"[memory] ───────────────────────────────────────────────────────")
        print(f"[memory]   Policies:        {len(policy_summary_data):>8,} records  (~{policy_size:>6.1f} MB)")
        print(f"[memory]   Events Detail:   {len(events_detail_data):>8,} records  (~{events_size:>6.1f} MB)")
        print(f"[memory]   Events Payload:  {len(policy_events_payload_data):>8,} records  (~{payload_size:>6.1f} MB)")
        print(f"[memory]   Pattern Sets:    {len(CONDSETS_BY_POLICY):>8,} records  (~{patterns_size:>6.1f} MB)")
        print(f"[memory] ───────────────────────────────────────────────────────")
        print(f"[memory]   TOTAL MEMORY:    ~{total_size:.1f} MB")
        print(f"[memory] ═══════════════════════════════════════════════════════")
        
        # Warn if memory usage is high
        if total_size > 1000:
            print(f"[memory] ⚠️  CRITICAL: Very high memory usage ({total_size:.1f} MB)")
            print(f"[memory]     System may experience performance issues or crashes")
            print(f"[memory]     Recommendations:")
            print(f"[memory]     - Reduce dataset size by filtering policies/events")
            print(f"[memory]     - Increase system RAM")
            print(f"[memory]     - Process data in smaller batches")
        elif total_size > 500:
            print(f"[memory] ⚠️  WARNING: High memory usage detected ({total_size:.1f} MB)")
            print(f"[memory]     Monitor system performance closely")
            print(f"[memory]     Consider reducing dataset size if issues occur")
        
        _log_timing("load_data(memory)", t0)
        return True
    except Exception as e:
        print(f"[load_data] Error: {e}")
        return False

def _to_int(x: str, default: Optional[int] = None) -> Optional[int]:
    try:
        return int(x)
    except Exception:
        return default

def ingest_event_instances_to_sqlite(csv_path: str, conn: sqlite3.Connection, batch_size: int = 100_000) -> None:
    t0 = time.perf_counter()
    cur = conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL;")
    cur.execute("PRAGMA synchronous=OFF;")
    cur.execute("PRAGMA temp_store=MEMORY;")
    try:
        cur.execute("PRAGMA mmap_size=30000000000;")
    except Exception:
        pass

    cur.executescript("""
        DROP TABLE IF EXISTS event_instances;
        CREATE TABLE event_instances (
            event_id TEXT,
            policy_id TEXT,
            severity INTEGER,
            summary TEXT,
            first_seen_ts INTEGER,
            last_seen_ts  INTEGER,
            full_payload  TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_ei_policy ON event_instances(policy_id);
        CREATE INDEX IF NOT EXISTS idx_ei_event  ON event_instances(event_id);
        CREATE INDEX IF NOT EXISTS idx_ei_sev    ON event_instances(severity);
    """)

    inserted = 0
    if not os.path.exists(csv_path):
        if DEBUG_TIMING:
            print(f"[sqlite] (optional) event_instances not found at {csv_path}; skipping.")
        return

    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        rdr = csv.DictReader(f, delimiter=";")
        batch: List[Tuple] = []
        for row in rdr:
            ev_id = row.get("event_id") or row.get("eventid") or row.get("Identifier") or row.get("id")
            pol_id = row.get("policy_id") or row.get("policyid") or row.get("policyId")
            sev   = _to_int(row.get("severity", "") or row.get("Severity", ""), None)
            summ  = row.get("summary") or row.get("Summary")
            first_ms = _to_int(row.get("first_seen_ts", "") or row.get("firstSeen", "") or row.get("timestamp", "") or row.get("Time", ""))
            last_ms  = _to_int(row.get("last_seen_ts", "") or row.get("lastSeen", "") or row.get("timestamp", "") or row.get("Time", ""))
            full_payload = json.dumps(row, ensure_ascii=False)

            batch.append((ev_id, pol_id, sev, summ, first_ms, last_ms, full_payload))
            if len(batch) >= batch_size:
                cur.executemany(
                    "INSERT INTO event_instances (event_id, policy_id, severity, summary, first_seen_ts, last_seen_ts, full_payload) VALUES (?,?,?,?,?,?,?)",
                    batch
                )
                conn.commit()
                inserted += len(batch)
                batch.clear()
                if DEBUG_TIMING:
                    print(f"[sqlite] inserted ~{inserted:,} rows...")

        if batch:
            cur.executemany(
                "INSERT INTO event_instances (event_id, policy_id, severity, summary, first_seen_ts, last_seen_ts, full_payload) VALUES (?,?,?,?,?,?,?)",
                batch
            )
            conn.commit()
            inserted += len(batch)

    if DEBUG_TIMING:
        print(f"[sqlite] event_instances ingested: {inserted:,} rows in {time.perf_counter()-t0:.2f}s")

def load_data_to_sqlite(output_dir: str, sqlite_path: str, event_instances: Optional[str]) -> bool:
    """
    Load data from CSV files into SQLite database.
    
    Args:
        output_dir: Directory containing CSV files
        sqlite_path: Path to SQLite database file
        event_instances: Optional path to event instances CSV file
        
    Returns:
        True if data was loaded successfully, False otherwise
    """
    global DB_CONN, CONDSETS_BY_POLICY
    summary_path = os.path.join(output_dir, "policy_summary.csv")
    events_path = os.path.join(output_dir, "events_detail.csv")
    payload_path = os.path.join(output_dir, "policy_events_payload.csv")

    if not os.path.exists(summary_path):
        print(f"[sqlite] Missing: {summary_path}")
        return False
    if not os.path.exists(events_path):
        print(f"[sqlite] Missing: {events_path}")
        return False
    if not os.path.exists(payload_path):
        print(f"[sqlite] Missing: {payload_path}")
        return False

    t0 = time.perf_counter()
    
    try:
        # Enable thread-safe mode with timeout and WAL mode for better concurrent access
        # Use DEFERRED isolation level instead of None for better stability
        DB_CONN = sqlite3.connect(sqlite_path, check_same_thread=False, timeout=30.0, isolation_level='DEFERRED')
        DB_CONN.row_factory = sqlite3.Row
        # Enable WAL mode for better concurrent read/write performance
        DB_CONN.execute("PRAGMA journal_mode=WAL")
        DB_CONN.execute("PRAGMA synchronous=NORMAL")
        DB_CONN.execute("PRAGMA cache_size=10000")
        DB_CONN.execute("PRAGMA busy_timeout=30000")  # 30 second timeout for locks
        c = DB_CONN.cursor()

        c.executescript("""
            DROP TABLE IF EXISTS policies;
            DROP TABLE IF EXISTS events;
        """)

        c.executescript("""
            CREATE TABLE policies (
                policy_id TEXT PRIMARY KEY,
                ranking_score REAL,
                event_count INTEGER,
                event_occurrences INTEGER,
                deployed INTEGER,
                group_id TEXT
            );
            CREATE TABLE events (
                policy_id TEXT,
                event_id TEXT,
                severity TEXT,
                payload_resource TEXT,
                summary TEXT,
                payload_details TEXT,
                payload_type TEXT,
                full_payload TEXT,
                PRIMARY KEY (event_id, policy_id)
            );
            CREATE INDEX IF NOT EXISTS idx_events_policy ON events(policy_id);
            CREATE INDEX IF NOT EXISTS idx_events_eventid ON events(event_id);
            CREATE INDEX IF NOT EXISTS idx_policies_group ON policies(group_id);
        """)

        dep_map = _parse_deployed_map(output_dir)

        rows = []
        rows_by_policy = {}

        with open(summary_path, "r", encoding="utf-8") as f:
            rdr = csv.DictReader(f)
            for r in rdr:
                pid = r.get("policy_id")
                if not pid:
                    continue

                rs  = _maybe_float_or_int(r.get("ranking_score", "") or "")
                ec  = _maybe_float_or_int(r.get("event_count", "") or "")
                eo  = _maybe_float_or_int(r.get("event_occurrences", "") or "")
                dep = 1 if dep_map.get(pid, False) else 0
                gid = r.get("group_id") or ""

                # last-write-wins (same as memory mode)
                rows_by_policy[pid] = (pid, rs, ec, eo, dep, gid)

        rows = list(rows_by_policy.values())
        print(f"[sqlite] inserting {len(rows)} policies")
        c.executemany(
            """
            INSERT INTO policies
            (policy_id, ranking_score, event_count, event_occurrences, deployed, group_id)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(policy_id) DO UPDATE SET
            ranking_score      = excluded.ranking_score,
            event_count        = excluded.event_count,
            event_occurrences  = excluded.event_occurrences,
            deployed           = excluded.deployed,
            group_id           = excluded.group_id
            """,
            rows
        )

        rows = []
        with open(payload_path, "r", encoding="utf-8") as f:
            rdr = csv.DictReader(f)
            for r in rdr:
                fp = r.get("full_payload", "")
                rows.append((
                    r.get("policy_id"),
                    r.get("event_id"),
                    r.get("severity"),
                    r.get("payload_resource"),
                    r.get("summary"),
                    r.get("payload_details"),
                    r.get("payload_type"),
                    fp
                ))
        print(f"[sqlite] inserting {len(rows)} events")                
        c.executemany("""
            INSERT INTO events
            (policy_id, event_id, severity, payload_resource, summary, payload_details, payload_type, full_payload)
            VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT(event_id, policy_id) DO UPDATE SET
            severity          = excluded.severity,
            payload_resource  = excluded.payload_resource,
            summary           = excluded.summary,
            payload_details   = excluded.payload_details,
            payload_type      = excluded.payload_type,
            full_payload      = excluded.full_payload
        """, rows)

        DB_CONN.commit()
        
        # Force WAL checkpoint to ensure data is written to main database file
        try:
            DB_CONN.execute("PRAGMA wal_checkpoint(FULL)")
        except Exception as e:
            print(f"[sqlite] Warning: WAL checkpoint failed: {e}")
        
        # Load condition sets
        CONDSETS_BY_POLICY = _load_condition_sets(output_dir)
        
        # Ingest event instances if provided
        if event_instances:
            ei_path = os.path.join(output_dir, event_instances)
            if os.path.exists(ei_path):
                ingest_event_instances_to_sqlite(ei_path, DB_CONN)
            else:
                print(f"[sqlite] Warning: Event instances file not found at {ei_path}")
        
        _log_timing("load_data_to_sqlite", t0)
        return True
        
    except Exception as e:
        print(f"[sqlite] Error loading data: {e}")
        import traceback
        traceback.print_exc()
        if DB_CONN is not None:
            try:
                DB_CONN.close()
            except Exception:
                pass
            DB_CONN = None
        return False

# -------------------- Hot-reload support (no deps) --------------------
# These are set in start_web_server() based on CLI args
SERVER_OUTPUT_DIR: Optional[str] = None
SERVER_SQLITE_PATH: Optional[str] = None
SERVER_EVENT_INSTANCES: Optional[str] = None
SERVER_USE_SQLITE: bool = False

_DATA_LOCK = threading.RLock()
_DATA_VERSION = 0                 # version we've loaded into memory/SQLite
_LAST_CHECK = 0.0
_CHECK_COOLDOWN = 2.0            # don't stat more than once every 2s

def _signal_file_path() -> Path:
    base = SERVER_OUTPUT_DIR or DEFAULT_OUTPUT_DIR
    return Path(base) / "data_updated.signal"

def _timestamp_file_path() -> Path:
    base = SERVER_OUTPUT_DIR or DEFAULT_OUTPUT_DIR
    return Path(base) / "last_update.json"

def _version_from_disk() -> int:
    """
    Compute a monotonic-ish version from:
      - mtime of data_updated.signal (if present)
      - fields in last_update.json (version | last_update(_iso) | update_count)
      - mtime of last_update.json (fallback)
    """
    v = 0
    # signal mtime
    try:
        v = max(v, int(_signal_file_path().stat().st_mtime))
    except FileNotFoundError:
        pass

    ts_path = _timestamp_file_path()
    try:
        with open(ts_path, "r", encoding="utf-8") as f:
            d = json.load(f)
        ver = int(d.get("version") or 0)
        if not ver:
            iso = d.get("last_update_iso") or d.get("last_update")
            if iso:
                try:
                    ver = int(datetime.fromisoformat(iso).timestamp())
                except Exception:
                    ver = 0
        if not ver and "update_count" in d:
            try:
                ver = int(d["update_count"]) or 0
            except Exception:
                ver = 0
        v = max(v, ver)
    except FileNotFoundError:
        pass
    except Exception:
        try:
            v = max(v, int(ts_path.stat().st_mtime))
        except Exception:
            pass
    return int(v or 0)

def _reload_all():
    """
    Rebuild the data snapshot from files under SERVER_OUTPUT_DIR.
    Chooses SQLite vs memory based on startup mode. Zero new deps.
    """
    global DB_CONN, SERVER_USE_SQLITE
    print(f"[DEBUG] _reload_all: START")
    out = SERVER_OUTPUT_DIR or DEFAULT_OUTPUT_DIR
    if SERVER_USE_SQLITE:
        print(f"[DEBUG] _reload_all: using SQLite mode")
        # Recreate SQLite DB from CSVs (close existing if any)
        try:
            if DB_CONN is not None:
                print(f"[DEBUG] _reload_all: closing existing DB connection")
                # Force checkpoint before closing to flush WAL
                try:
                    DB_CONN.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                except Exception:
                    pass
                DB_CONN.close()
        except Exception as e:
            print(f"[DEBUG] _reload_all: error closing DB: {e}")
            pass
        DB_CONN = None
        
        # Give OS time to release file handles
        import time
        time.sleep(0.5)
        
        # Delete corrupted database if it exists (including WAL files)
        db_path = SERVER_SQLITE_PATH or os.path.join(out, "policy_events.db")
        try:
            if os.path.exists(db_path):
                print(f"[DEBUG] _reload_all: removing existing database at {db_path}")
                os.remove(db_path)
            # Also remove WAL and SHM files if they exist
            for ext in ['-wal', '-shm']:
                wal_file = db_path + ext
                if os.path.exists(wal_file):
                    print(f"[DEBUG] _reload_all: removing {wal_file}")
                    os.remove(wal_file)
        except Exception as e:
            print(f"[WARNING] _reload_all: could not remove database files: {e}")
        
        print(f"[DEBUG] _reload_all: calling load_data_to_sqlite")
        try:
            load_data_to_sqlite(out, db_path, SERVER_EVENT_INSTANCES)
            print(f"[DEBUG] _reload_all: SQLite load complete")
        except Exception as e:
            print(f"[ERROR] _reload_all: SQLite load failed: {e}")
            print(f"[INFO] _reload_all: falling back to memory mode")
            SERVER_USE_SQLITE = False
            DB_CONN = None
            load_data_to_memory(out)
            print(f"[DEBUG] _reload_all: memory mode fallback complete")
    else:
        print(f"[DEBUG] _reload_all: using memory mode")
        # Rebuild in-memory lists/dicts
        load_data_to_memory(out)
        print(f"[DEBUG] _reload_all: memory load complete")
    print(f"[DEBUG] _reload_all: END")

def _maybe_reload_data(force: bool = False):
    """
    Cheap guard: checks disk version at most once per 2s.
    If version increases, reloads data under a lock.
    """
    global _LAST_CHECK, _DATA_VERSION
    now = time.time()
    debug_print(f"[DEBUG] _maybe_reload_data: called, force={force}")
    if not force and (now - _LAST_CHECK) < _CHECK_COOLDOWN:
        debug_print(f"[DEBUG] _maybe_reload_data: skipping check (cooldown)")
        return
    _LAST_CHECK = now

    disk_ver = _version_from_disk()
    debug_print(f"[DEBUG] _maybe_reload_data: disk_ver={disk_ver}, current_ver={_DATA_VERSION}")
    if disk_ver and disk_ver > _DATA_VERSION:
        print(f"[DEBUG] _maybe_reload_data: acquiring lock for reload")
        with _DATA_LOCK:
            # double-check under lock
            disk_ver2 = _version_from_disk()
            if disk_ver2 <= _DATA_VERSION:
                print(f"[DEBUG] _maybe_reload_data: version already loaded, skipping")
                return
            print(f"[DEBUG] _maybe_reload_data: calling _reload_all()")
            _reload_all()
            _DATA_VERSION = disk_ver2
            print(f"[DEBUG] _maybe_reload_data: reload complete, version = {_DATA_VERSION}")
            if DEBUG_TIMING:
                print(f"[hot-reload] Reloaded data version = {_DATA_VERSION}")

def read_last_update() -> Dict[str, Any]:
    """
    Best-effort reader for last_update.json + signal mtime.
    Returns a stable 'version' so the UI can detect changes.
    """
    resp = {
        "last_update_iso": None,
        "update_count": None,
        "last_status": None,
        "version": 0,
    }
    ts_path = _timestamp_file_path()
    # base on file mtime
    try:
        resp["version"] = int(ts_path.stat().st_mtime)
    except FileNotFoundError:
        pass

    # contents
    try:
        with open(ts_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            resp["last_status"] = data.get("last_status")
            if "update_count" in data:
                resp["update_count"] = data["update_count"]
                try:
                    resp["version"] = max(resp["version"], int(data["update_count"]) or 0)
                except Exception:
                    pass
            iso = data.get("last_update_iso") or data.get("last_update")
            if iso:
                resp["last_update_iso"] = iso
                try:
                    resp["version"] = max(resp["version"], int(datetime.fromisoformat(iso).timestamp()))
                except Exception:
                    pass
    except FileNotFoundError:
        pass
    except Exception:
        pass

    # also fold in signal mtime
    try:
        resp["version"] = max(resp["version"], int(_signal_file_path().stat().st_mtime))
    except Exception:
        pass

    return resp

# -------------------- Viewer HTML --------------------
def write_viewer_html() -> str:
    """
    Copy the HTML template from templates/viewer.html to the output directory.
    The template is now separate from Python code for better maintainability.
    Dynamic configuration is loaded via /api/config endpoint.
    """
    Path(OUTPUT_HTML_DIR).mkdir(parents=True, exist_ok=True)
    
    # Remove existing HTML file to force regeneration
    if os.path.exists(OUTPUT_HTML_PATH):
        try:
            os.remove(OUTPUT_HTML_PATH)
            if DEBUG_TIMING:
                print(f"[viewer] Removed existing HTML file: {OUTPUT_HTML_PATH}")
        except Exception as e:
            print(f"[WARNING] Could not remove existing HTML file: {e}")
    
    # Read template file
    template_path = os.path.join(os.path.dirname(__file__), "templates", "viewer.html")
    try:
        with open(template_path, "r", encoding="utf-8") as f:
            html = f.read()
    except FileNotFoundError:
        print(f"[ERROR] Template file not found: {template_path}")
        print(f"[ERROR] Falling back to legacy inline HTML generation")
        # Fallback to legacy behavior if template doesn't exist
        html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Policy and Event Data Visualization</title>
  <link rel="stylesheet" href="/static/styles.css" />
</head>
<body>
  <h1>Template Error</h1>
  <p>The HTML template file is missing. Please ensure templates/viewer.html exists.</p>
</body>
</html>
"""
    
    # Write to output directory
    with open(OUTPUT_HTML_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    if DEBUG_TIMING:
        print(f"[viewer] Wrote {OUTPUT_HTML_PATH}")
    return OUTPUT_HTML_PATH

# -------------------- HTTP Handler --------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "PolicyEventStdlibHTTP/1.1"

    # Suppress default access logs unless ACCESS_LOG enabled
    def log_message(self, format, *args):
        if ACCESS_LOG:
            x = 1
            # sys.stderr.write("%s - - [%s] %s\n" %
            #                  (self.client_address[0],
            #                   self.log_date_time_string(),
            #                   format % args))
        else:
            return
    
    def _check_auth(self) -> bool:
        """Check if the request has valid authentication credentials"""
        if not ENABLE_AUTH:
            return True
            
        # Check Authorization header
        auth_header = self.headers.get('Authorization')
        if auth_header:
            try:
                auth_type, auth_data = auth_header.split(' ', 1)
                if auth_type.lower() == 'basic':
                    decoded = base64.b64decode(auth_data).decode('utf-8')
                    username, password = decoded.split(':', 1)
                    
                    # Check for session timeout if enabled
                    if SESSION_TIMEOUT > 0 and check_session_expired(username):
                        print(f"[auth] Session expired for {username}")
                        # Log session timeout
                        client_ip = self.client_address[0]
                        log_audit("SESSION_TIMEOUT", username, client_ip=client_ip)
                        return False
                    
                    # Check if username exists and password matches using secure verification
                    if username in AUTH_CREDENTIALS:
                        stored_hash = AUTH_CREDENTIALS[username]
                        if verify_password(stored_hash, password):
                            # Update session activity
                            update_session_activity(username)
                            return True
            except Exception as e:
                print(f"[auth] Error checking Authorization header: {e}")
                import traceback
                traceback.print_exc()
        
        # Check for auth cookie
        cookie_header = self.headers.get('Cookie')
        if cookie_header:
            try:
                cookies = {}
                for cookie in cookie_header.split(';'):
                    if '=' in cookie:
                        name, value = cookie.strip().split('=', 1)
                        cookies[name] = value
                
                auth_token = cookies.get('auth_token')
                if auth_token:
                    decoded = base64.b64decode(auth_token).decode('utf-8')
                    username, password = decoded.split(':', 1)
                    
                    # Check for session timeout if enabled
                    if SESSION_TIMEOUT > 0 and check_session_expired(username):
                        print(f"[auth] Session expired for {username} (cookie)")
                        # Log session timeout
                        client_ip = self.client_address[0]
                        log_audit("SESSION_TIMEOUT", username, client_ip=client_ip, details="cookie-based")
                        return False
                    
                    # No fallback authentication - use configured credentials only
                        # Set the Authorization header for this request
                        self.headers['Authorization'] = f'Basic {auth_token}'
                        # Update session activity
                        update_session_activity(username)
                        return True
                    
                    # Check if username exists and password matches using secure verification
                    if username in AUTH_CREDENTIALS:
                        stored_hash = AUTH_CREDENTIALS[username]
                        if verify_password(stored_hash, password):
                            # Set the Authorization header for this request
                            self.headers['Authorization'] = f'Basic {auth_token}'
                            # Update session activity
                            update_session_activity(username)
                            return True
            except Exception as e:
                print(f"[auth] Error checking auth cookie: {e}")
                import traceback
                traceback.print_exc()
                    
        return False
    
    def _send_auth_required(self):
        """Send a 401 Unauthorized response"""
        self.send_response(401)
        self.send_header('WWW-Authenticate', 'Basic realm="Policy Visualization"')
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(b'Authentication required')

    # -------- helpers --------
    def _parse_args(self):
        parsed = urlparse(self.path)
        return parsed, parse_qs(parsed.query)
    
    def _evaluate_advanced_filter(self, record, conditions, logic):
        """
        Evaluate advanced filter conditions against a record.
        
        Args:
            record: Dictionary containing event data
            conditions: List of filter conditions
            logic: 'AND' or 'OR' - how to combine conditions
            
        Returns:
            Boolean indicating if record matches the filter
        """
        if not conditions:
            return True
        
        results = []
        for condition in conditions:
            column = condition.get("column", "")
            operator = condition.get("operator", "=")
            value = condition.get("value", "")
            
            # Get the field value from the record
            field_value = record.get(column)
            
            # Handle None values
            if field_value is None:
                results.append(False)
                continue
            
            # Convert to string for string operations
            field_str = str(field_value).lower()
            value_str = str(value).lower()
            
            # Evaluate based on operator
            try:
                # Handle timestamp comparisons
                if column == "timestamp":
                    # Parse timestamp value - support multiple formats
                    import re
                    from datetime import datetime
                    
                    # Convert field value to comparable format
                    # Timestamps can be in various formats: epoch ms, ISO string, etc.
                    try:
                        # Try parsing as epoch milliseconds
                        if isinstance(field_value, (int, float)):
                            field_ts = float(field_value)
                        elif field_value.isdigit():
                            field_ts = float(field_value)
                        else:
                            # Try parsing as ISO datetime string
                            dt = datetime.fromisoformat(field_value.replace('Z', '+00:00'))
                            field_ts = dt.timestamp() * 1000  # Convert to milliseconds
                    except (ValueError, AttributeError):
                        # If parsing fails, treat as string comparison
                        field_ts = None
                    
                    # Parse user input value
                    try:
                        # User input from datetime-local is in format: YYYY-MM-DDTHH:MM
                        if 'T' in value:
                            # Parse as ISO datetime
                            dt = datetime.fromisoformat(value)
                            value_ts = dt.timestamp() * 1000  # Convert to milliseconds
                        elif value.isdigit():
                            # Direct epoch milliseconds
                            value_ts = float(value)
                        else:
                            # Try parsing as date string
                            dt = datetime.fromisoformat(value)
                            value_ts = dt.timestamp() * 1000
                    except (ValueError, AttributeError):
                        value_ts = None
                    
                    # Perform comparison if both values are valid timestamps
                    if field_ts is not None and value_ts is not None:
                        if operator == "=":
                            # For equality, check if within same minute (60000 ms)
                            match = abs(field_ts - value_ts) < 60000
                        elif operator == "!=":
                            match = abs(field_ts - value_ts) >= 60000
                        elif operator == ">":
                            match = field_ts > value_ts
                        elif operator == ">=":
                            match = field_ts >= value_ts
                        elif operator == "<":
                            match = field_ts < value_ts
                        elif operator == "<=":
                            match = field_ts <= value_ts
                        elif operator == "contains":
                            # For contains, fall back to string comparison
                            match = value_str in field_str
                        else:
                            match = False
                    else:
                        # Fall back to string comparison if timestamp parsing fails
                        if operator == "contains":
                            match = value_str in field_str
                        else:
                            match = False
                
                elif operator == "=":
                    # For numeric fields, try numeric comparison
                    if column in ["severity", "payload_type"]:
                        match = float(field_value) == float(value)
                    else:
                        match = field_str == value_str
                elif operator == "!=":
                    if column in ["severity", "payload_type"]:
                        match = float(field_value) != float(value)
                    else:
                        match = field_str != value_str
                elif operator == ">":
                    match = float(field_value) > float(value)
                elif operator == ">=":
                    match = float(field_value) >= float(value)
                elif operator == "<":
                    match = float(field_value) < float(value)
                elif operator == "<=":
                    match = float(field_value) <= float(value)
                elif operator == "contains":
                    match = value_str in field_str
                elif operator == "!contains":
                    match = value_str not in field_str
                elif operator == "starts":
                    match = field_str.startswith(value_str)
                elif operator == "ends":
                    match = field_str.endswith(value_str)
                else:
                    # Unknown operator, default to false
                    match = False
                
                results.append(match)
            except (ValueError, TypeError) as e:
                # If comparison fails (e.g., non-numeric comparison), treat as no match
                print(f"[DEBUG] Filter evaluation error for {column} {operator} {value}: {e}")
                results.append(False)
        
        # Combine results based on logic
        if logic == "OR":
            return any(results)
        else:  # AND
            return all(results)

    def _route(self, method: str, path: str):
        if path == "/":
            return self._get_index
        if path == "/regenerate" and method in ("GET", "POST"):
            return self._regenerate
        if path == "/logout" and method == "POST":
            return self._handle_logout
        if path.startswith("/static/") and method == "GET":
            return self._static

        if path == "/api/policies_ss" and method == "GET":
            return self._api_policies_ss
        if path == "/api/events_ss" and method == "GET":
            return self._api_events_ss
        if path == "/api/event_instances_ss" and method == "GET":
            return self._api_event_instances_ss

        if path.startswith("/api/payload_preview/") and method == "GET":
            return self._api_payload_preview
        if path.startswith("/api/payload_download/") and method == "GET":
            return self._api_payload_download

        if path == "/api/policies" and method == "GET":
            return self._api_policies_legacy
        if path == "/api/events" and method == "GET":
            return self._api_events_legacy
        if path == "/api/payloads" and method == "GET":
            return self._api_payloads_legacy

        if path == "/api/deploy_cache":
            if method == "GET":
                return self._api_get_deploy_cache
            if method == "POST":
                return self._api_post_deploy_cache
            if method == "DELETE":
                return self._api_delete_deploy_cache

        if path == "/api/deploy_policies" and method == "POST":
            return self._api_deploy_policies

        if path.startswith("/api/pattern_config/") and method == "GET":
            return self._api_pattern_config

        if path.startswith("/api/last_update") and method == "GET":
            return self._api_last_update
        
        if path == "/api/config" and method == "GET":
            return self._api_config
            
        if path == "/api/register" and method == "POST":
            return self._api_register
            
        if path == "/api/login" and method == "POST":
            return self._api_login

        return None

    def _apply_cache_headers(self, is_api: bool, is_html: bool):
        if is_api:
            self.send_header("Cache-Control", API_CACHE)
        elif is_html:
            self.send_header("Cache-Control", HTML_CACHE)
        else:
            self.send_header("Cache-Control", f"public, max-age={STATIC_CACHE_SECS}")
        
        # Add CORS headers if enabled
        self._add_cors_headers()

    def _add_cors_headers(self):
        """Add CORS headers to the response if enabled"""
        if ENABLE_CORS:
            self.send_header("Access-Control-Allow-Origin", CORS_ORIGINS)
            self.send_header("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
    
    # -------- verbs --------
    def do_GET(self):
        parsed, query_params = self._parse_args()
        
        # Check if there's an auth parameter in the URL (from login redirect)
        auth_param = query_params.get('auth', [''])[0]
        if auth_param:
            try:
                # Extract credentials from the auth parameter
                auth_data = auth_param
                decoded = base64.b64decode(auth_data).decode('utf-8')
                username, password = decoded.split(':', 1)
                
                # Verify credentials
                if username in AUTH_CREDENTIALS:
                    stored_hash = AUTH_CREDENTIALS[username]
                    if verify_password(stored_hash, password):
                        # Set the Authorization header for this request
                        self.headers['Authorization'] = f'Basic {auth_data}'
                        
                        # Redirect to clean URL without auth parameter to avoid showing credentials in URL
                        if parsed.path == '/':
                            self.send_response(302)
                            self.send_header('Location', '/')
                            self.end_headers()
                            return
            except Exception as e:
                if DEBUG_TIMING:
                    print(f"[auth] Error processing auth parameter: {e}")
        
        # Check authentication
        if not self._check_auth():
            # If force login page is enabled, show the login page instead of 401
            if FORCE_LOGIN_PAGE:
                return self._send_login_page()
            else:
                return self._send_auth_required()
            
        fn = self._route("GET", parsed.path)
        if not fn:
            return _send_404(self)
        return fn()

    def do_POST(self):
        parsed, _ = self._parse_args()
        
        # Handle direct form submission from login page
        if parsed.path == "/" and FORCE_LOGIN_PAGE:
            # Get form data
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length).decode('utf-8')
            
            # Parse form data
            form_data = {}
            for item in post_data.split('&'):
                if '=' in item:
                    key, value = item.split('=', 1)
                    form_data[key] = value
            
            username = form_data.get('username', '')
            password = form_data.get('password', '')
            
            # Debug logging
            print(f"[auth] Login attempt for user: {username}")
            print(f"[auth] Available users: {list(AUTH_CREDENTIALS.keys())}")
            
            # Check credentials
            if username in AUTH_CREDENTIALS:
                stored_hash = AUTH_CREDENTIALS[username]
                print(f"[auth] Found stored hash for {username}: {stored_hash[:20]}...")
                
                # Try verification
                if verify_password(stored_hash, password):
                    print(f"[auth] Password verification successful for {username}")
                    # Set Authorization header for this request
                    auth_data = base64.b64encode(f"{username}:{password}".encode('utf-8')).decode('utf-8')
                    self.headers['Authorization'] = f'Basic {auth_data}'
                    
                    # Initialize session activity
                    update_session_activity(username)
                    
                    # Set cookie max-age based on session timeout
                    cookie_max_age = ""
                    if SESSION_TIMEOUT > 0:
                        cookie_max_age = f"; Max-Age={SESSION_TIMEOUT * 60}"
                    
                    # Log successful login
                    client_ip = self.client_address[0]
                    log_audit("LOGIN", username, client_ip=client_ip, status="success")
                    
                    # Redirect to main page
                    self.send_response(302)
                    self.send_header('Location', '/')
                    self.send_header('Set-Cookie', f'auth_token={auth_data}; Path=/; HttpOnly{cookie_max_age}')
                    self.end_headers()
                    return
                else:
                    print(f"[auth] Password verification failed for {username}")
                    # Log failed login attempt
                    client_ip = self.client_address[0]
                    log_audit("LOGIN", username, client_ip=client_ip, status="failed", details="Invalid password")
            else:
                print(f"[auth] User not found: {username}")
                # Log failed login attempt
                client_ip = self.client_address[0]
                log_audit("LOGIN", username, client_ip=client_ip, status="failed", details="User not found")
            
            # If authentication failed, redirect to login page with error
            self.send_response(302)
            self.send_header('Location', '/?error=1')
            self.end_headers()
            return
        
        # Allow access to registration endpoint without authentication
        if parsed.path == "/api/register":
            fn = self._route("POST", parsed.path)
            if fn:
                return fn()
            return _send_404(self)
        
        # Check authentication for all other endpoints
        if not self._check_auth():
            # If force login page is enabled, show the login page instead of 401
            if FORCE_LOGIN_PAGE:
                return self._send_login_page()
            else:
                return self._send_auth_required()
            
        fn = self._route("POST", parsed.path)
        if not fn:
            return _send_404(self)
        return fn()

    def do_DELETE(self):
        # Check authentication
        if not self._check_auth():
            # If force login page is enabled, show the login page instead of 401
            if FORCE_LOGIN_PAGE:
                return self._send_login_page()
            else:
                return self._send_auth_required()
            
        parsed, _ = self._parse_args()
        fn = self._route("DELETE", parsed.path)
        if not fn:
            return _send_404(self)
        return fn()

    def do_OPTIONS(self):
        self.send_response(204)
        self._add_cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    # -------- route impls --------
    def _get_index(self):
        """
        Serve the main HTML page from the template file.
        The template loads dynamic configuration via /api/config endpoint.
        """
        # Remove any auth parameter from the URL to avoid it being visible in the browser
        parsed, query_params = self._parse_args()
        if 'auth' in query_params:
            # We've already processed the auth parameter in do_GET, so we can remove it now
            # This is just to clean up the URL
            clean_path = parsed.path
            self.path = clean_path
        
        # Serve directly from template file
        template_path = os.path.join(os.path.dirname(__file__), "templates", "viewer.html")
        
        try:
            with open(template_path, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self._apply_cache_headers(is_api=False, is_html=True)
            self.send_header("Content-Length", str(len(data)))
            _add_security_headers(self)
            self.end_headers()
            self.wfile.write(data)
        except FileNotFoundError:
            # Fallback: try to generate HTML if template doesn't exist
            if not os.path.exists(OUTPUT_HTML_PATH):
                write_viewer_html()
            try:
                with open(OUTPUT_HTML_PATH, "rb") as f:
                    data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self._apply_cache_headers(is_api=False, is_html=True)
                self.send_header("Content-Length", str(len(data)))
                _add_security_headers(self)
                self.end_headers()
                self.wfile.write(data)
            except Exception:
                _send_404(self)
        except Exception:
            _send_404(self)

    def _regenerate(self):
        path = write_viewer_html()
        _json_response(self, {"ok": True, "generated": path})
        
    def _api_register(self):
        """Handle user registration requests"""
        if not ENABLE_AUTH:
            return _json_response(self, {"error": "Authentication is disabled"}, status=400)
            
        try:
            data = _read_body_json(self)
            username = data.get("username", "").strip()
            password = data.get("password", "")
            
            # Validate input
            if not username or not password:
                return _json_response(self, {"error": "Username and password are required"}, status=400)
                
            if len(password) < 6:
                return _json_response(self, {"error": "Password must be at least 6 characters"}, status=400)
                
            # Check if username already exists
            if username in AUTH_CREDENTIALS:
                return _json_response(self, {"error": "Username already exists"}, status=400)
                
            # Generate secure password hash
            salt = secrets.token_hex(8)
            iterations = 150000
            hash_bytes = hashlib.pbkdf2_hmac(
                'sha256',
                password.encode('utf-8'),
                salt.encode('utf-8'),
                iterations
            )
            password_hash = f"pbkdf2:sha256:{iterations}${salt}${hash_bytes.hex()}"
            
            # Add user to credentials dictionary
            AUTH_CREDENTIALS[username] = password_hash
            
            # Save to users.csv file
            with open(USERS_FILE, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([username, password_hash])
            
            # Log user registration
            client_ip = self.client_address[0]
            log_audit("USER_REGISTER", username, client_ip=client_ip)
                
            return _json_response(self, {
                "success": True,
                "message": "Account created successfully!"
            })
        except Exception as e:
            if DEBUG_TIMING:
                print(f"[register] Error: {e}")
            return _json_response(self, {"error": "Registration failed"}, status=500)
            
    def _handle_logout(self):
        """Handle logout requests and redirect to login page"""
        # Get username from Authorization header or cookie
        username = "unknown"
        auth_header = self.headers.get('Authorization')
        if auth_header:
            try:
                auth_type, auth_data = auth_header.split(' ', 1)
                if auth_type.lower() == 'basic':
                    decoded = base64.b64decode(auth_data).decode('utf-8')
                    username, _ = decoded.split(':', 1)
            except Exception:
                pass
                
        # Log logout event
        client_ip = self.client_address[0]
        log_audit("LOGOUT", username, client_ip=client_ip)
        
        # Clear the auth cookie
        self.send_response(302)
        self.send_header('Set-Cookie', 'auth_token=; Path=/; Expires=Thu, 01 Jan 1970 00:00:01 GMT; HttpOnly')
        self.send_header('Location', '/?logout=1')
        self.end_headers()
        return
        
    def _api_login(self):
        """Handle login requests and redirect to main page"""
        try:
            # Get form data
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length).decode('utf-8')
            
            # Parse form data
            form_data = {}
            for item in post_data.split('&'):
                if '=' in item:
                    key, value = item.split('=', 1)
                    form_data[key] = value
            
            auth_data = form_data.get('auth', '')
            
            # Return a simple HTML page with JavaScript to set the cookie and redirect
            html = """
            <!DOCTYPE html>
            <html>
            <head>
                <title>Login Successful</title>
                <script>
                    // Set the auth cookie
                    document.cookie = "auth_token=AUTH_TOKEN_VALUE; path=/; max-age=86400";
                    
                    // Store in session storage as backup
                    sessionStorage.setItem('auth', 'AUTH_TOKEN_VALUE');
                    
                    // Redirect to main page
                    window.location.href = '/';
                </script>
            </head>
            <body>
                <h1>Login Successful</h1>
                <p>Redirecting to main page...</p>
            </body>
            </html>
            """.replace('AUTH_TOKEN_VALUE', auth_data)
            
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', str(len(html)))
            self.end_headers()
            self.wfile.write(html.encode('utf-8'))
            
        except Exception as e:
            if DEBUG_TIMING:
                print(f"[login] Error: {e}")
            self.send_response(302)
            self.send_header('Location', '/')
            self.end_headers()
        
    def _send_login_page(self):
        """Send a login page instead of 401 when FORCE_LOGIN_PAGE is enabled"""
        # Check if there's an error message to display
        error_class = "d-none"
        timeout_class = "d-none"
        logout_class = "d-none"
        parsed, query_params = self._parse_args()
        
        if 'error' in query_params:
            error_class = ""
        
        if 'timeout' in query_params:
            timeout_class = ""
            
        if 'logout' in query_params:
            logout_class = ""
            
        # Create the login HTML with proper string formatting
        login_html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Welcome - Policy and Event Data Visualization</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.2.3/dist/css/bootstrap.min.css">
    <style>
        body {
            background-color: #f8f9fa;
            height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .login-container {
            max-width: 450px;
            width: 100%;
            padding: 15px;
            margin: auto;
        }
        .card {
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }
        .card-header {
            background-color: #343a40;
            color: white;
            border-radius: 10px 10px 0 0 !important;
        }
        .btn-primary {
            background-color: #0d6efd;
            border-color: #0d6efd;
        }
        .btn-primary:hover {
            background-color: #0b5ed7;
            border-color: #0b5ed7;
        }
        .btn-outline-secondary {
            color: #6c757d;
            border-color: #6c757d;
        }
        .welcome-text {
            font-size: 1.1rem;
            line-height: 1.6;
            margin-bottom: 20px;
        }
        .nav-tabs {
            margin-bottom: 20px;
        }
        .tab-content {
            padding-top: 10px;
        }
    </style>
</head>
<body>
    <div class="login-container">
        <div class="card">
            <div class="card-header text-center py-3">
                <h3 class="mb-0">Policy and Event Data Visualization</h3>
            </div>
            <div class="card-body p-4">
                <div class="welcome-text text-center">
                    Welcome to the Policies & Events Visualization system. Please login to access the visualization interface or create a new account.
                </div>
                
                <ul class="nav nav-tabs" id="authTabs" role="tablist">
                    <li class="nav-item" role="presentation">
                        <button class="nav-link active" id="login-tab" data-bs-toggle="tab" data-bs-target="#login-pane" type="button" role="tab" aria-controls="login-pane" aria-selected="true">Login</button>
                    </li>
                    <!-- Hide Create Account tab for now
                    <li class="nav-item" role="presentation">
                        <button class="nav-link" id="register-tab" data-bs-toggle="tab" data-bs-target="#register-pane" type="button" role="tab" aria-controls="register-pane" aria-selected="false">Create Account</button>
                    </li>
                    -->
                </ul>
                
                <!-- Hide the Create Account tab in the UI -->
                <style>
                    #register-tab, #register-pane {
                        display: none !important;
                    }
                </style>
                
                <div class="tab-content" id="authTabsContent">
                    <!-- Login Tab -->
                    <div class="tab-pane fade show active" id="login-pane" role="tabpanel" aria-labelledby="login-tab">
                        <div id="login-error" class="alert alert-danger """ + error_class + """">
                            Invalid username or password
                        </div>
                        <div id="timeout-message" class="alert alert-warning """ + timeout_class + """">
                            Your session has expired due to inactivity. Please log in again.
                        </div>
                        <div id="logout-message" class="alert alert-success """ + logout_class + """">
                            You have been successfully logged out.
                        </div>
                        <form id="login-form" action="/" method="post">
                            <div class="mb-3">
                                <label for="username" class="form-label">Username</label>
                                <input type="text" class="form-control" id="username" name="username" required>
                            </div>
                            <div class="mb-3">
                                <label for="password" class="form-label">Password</label>
                                <input type="password" class="form-control" id="password" name="password" required>
                            </div>
                            <div class="d-grid gap-2">
                                <button type="submit" class="btn btn-primary">Login</button>
                            </div>
                        </form>
                    </div>
                    
                    <!-- Register Tab (hidden for now) -->
                    <div class="tab-pane fade" id="register-pane" role="tabpanel" aria-labelledby="register-tab" style="display: none;">
                        <div id="register-error" class="alert alert-danger d-none">
                            Error creating account
                        </div>
                        <div id="register-success" class="alert alert-success d-none">
                            Account created successfully! You can now login.
                        </div>
                        <form id="register-form">
                            <div class="mb-3">
                                <label for="new-username" class="form-label">Username</label>
                                <input type="text" class="form-control" id="new-username" name="new-username" required>
                            </div>
                            <div class="mb-3">
                                <label for="new-password" class="form-label">Password</label>
                                <input type="password" class="form-control" id="new-password" name="new-password" required>
                            </div>
                            <div class="mb-3">
                                <label for="confirm-password" class="form-label">Confirm Password</label>
                                <input type="password" class="form-control" id="confirm-password" name="confirm-password" required>
                            </div>
                            <div class="d-grid gap-2">
                                <button type="submit" class="btn btn-outline-secondary">Create Account</button>
                            </div>
                        </form>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.2.3/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        // Simple login form handling
        document.getElementById('login-form').addEventListener('submit', function(e) {
            // Don't prevent default - let the form submit normally
            
            // Store username in session storage for later use
            const username = document.getElementById('username').value;
            const password = document.getElementById('password').value;
            
            // Create Basic Auth header
            const credentials = btoa(username + ':' + password);
            sessionStorage.setItem('auth', credentials);
        });
        
        // Session timeout handling
        const SESSION_TIMEOUT = """ + str(SESSION_TIMEOUT) + """ || 0;
        if (SESSION_TIMEOUT > 0) {
            // Add session timeout warning to the page
            document.addEventListener('DOMContentLoaded', function() {
                const body = document.querySelector('body');
                const timeoutDialog = document.createElement('div');
                timeoutDialog.id = 'timeout-warning';
                timeoutDialog.style.display = 'none';
                timeoutDialog.style.position = 'fixed';
                timeoutDialog.style.top = '50%';
                timeoutDialog.style.left = '50%';
                timeoutDialog.style.transform = 'translate(-50%, -50%)';
                timeoutDialog.style.zIndex = '1000';
                timeoutDialog.style.backgroundColor = 'white';
                timeoutDialog.style.padding = '20px';
                timeoutDialog.style.borderRadius = '5px';
                timeoutDialog.style.boxShadow = '0 0 10px rgba(0,0,0,0.5)';
                timeoutDialog.style.maxWidth = '400px';
                timeoutDialog.style.width = '100%';
                
                timeoutDialog.innerHTML = `
                    <h4>Session Timeout Warning</h4>
                    <p>Your session will expire in <span id="timeout-countdown">60</span> seconds due to inactivity.</p>
                    <div class="d-grid gap-2">
                        <button id="extend-session" class="btn btn-primary">Extend Session</button>
                        <button id="logout-now" class="btn btn-outline-secondary">Logout Now</button>
                    </div>
                `;
                
                body.appendChild(timeoutDialog);
                
                // Add overlay
                const overlay = document.createElement('div');
                overlay.id = 'timeout-overlay';
                overlay.style.display = 'none';
                overlay.style.position = 'fixed';
                overlay.style.top = '0';
                overlay.style.left = '0';
                overlay.style.width = '100%';
                overlay.style.height = '100%';
                overlay.style.backgroundColor = 'rgba(0,0,0,0.5)';
                overlay.style.zIndex = '999';
                body.appendChild(overlay);
            });
        }
        
        // Register form handling
        document.getElementById('register-form').addEventListener('submit', function(e) {
            e.preventDefault();
            
            const username = document.getElementById('new-username').value;
            const password = document.getElementById('new-password').value;
            const confirmPassword = document.getElementById('confirm-password').value;
            
            // Check if passwords match
            if (password !== confirmPassword) {
                document.getElementById('register-error').textContent = "Passwords do not match";
                document.getElementById('register-error').classList.remove('d-none');
                document.getElementById('register-success').classList.add('d-none');
                return;
            }
            
            // Send registration request to the server
            fetch('/api/register', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    username: username,
                    password: password
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // Show success message
                    document.getElementById('register-error').classList.add('d-none');
                    document.getElementById('register-success').classList.remove('d-none');
                    document.getElementById('register-success').textContent = data.message || "Account created successfully! You can now login.";
                    
                    // Clear the form
                    document.getElementById('register-form').reset();
                    
                    // Switch to login tab after a delay
                    setTimeout(() => {
                        document.getElementById('login-tab').click();
                    }, 2000);
                } else {
                    // Show error message
                    document.getElementById('register-error').textContent = data.error || "Registration failed";
                    document.getElementById('register-error').classList.remove('d-none');
                    document.getElementById('register-success').classList.add('d-none');
                }
            })
            .catch(error => {
                console.error('Registration error:', error);
                document.getElementById('register-error').textContent = "Registration failed. Please try again.";
                document.getElementById('register-error').classList.remove('d-none');
                document.getElementById('register-success').classList.add('d-none');
            });
        });
        
        // Session timeout handling for the main application
        if (SESSION_TIMEOUT > 0) {
            let inactivityTimer;
            let warningTimer;
            let countdownInterval;
            let lastActivity = Date.now();
            const warningTime = 60; // Show warning 60 seconds before timeout
            
            // Function to reset the inactivity timer
            function resetInactivityTimer() {
                lastActivity = Date.now();
                clearTimeout(inactivityTimer);
                clearTimeout(warningTimer);
                clearInterval(countdownInterval);
                document.getElementById('timeout-warning')?.style.display = 'none';
                document.getElementById('timeout-overlay')?.style.display = 'none';
                
                // Set new timers
                inactivityTimer = setTimeout(logout, SESSION_TIMEOUT * 60 * 1000);
                warningTimer = setTimeout(showWarning, (SESSION_TIMEOUT * 60 - warningTime) * 1000);
            }
            
            // Function to show the warning dialog
            function showWarning() {
                const warningDialog = document.getElementById('timeout-warning');
                const overlay = document.getElementById('timeout-overlay');
                if (warningDialog && overlay) {
                    warningDialog.style.display = 'block';
                    overlay.style.display = 'block';
                    
                    let countdown = warningTime;
                    document.getElementById('timeout-countdown').textContent = countdown;
                    
                    countdownInterval = setInterval(() => {
                        countdown--;
                        if (countdown <= 0) {
                            clearInterval(countdownInterval);
                            logout();
                        } else {
                            document.getElementById('timeout-countdown').textContent = countdown;
                        }
                    }, 1000);
                }
            }
            
            // Function to logout
            function logout() {
                // Clear cookies and session storage
                document.cookie = "auth_token=; Path=/; Expires=Thu, 01 Jan 1970 00:00:01 GMT;";
                sessionStorage.removeItem('auth');
                
                // Redirect to login page
                window.location.href = '/?timeout=1';
            }
            
            // Track user activity
            ['mousedown', 'mousemove', 'keypress', 'scroll', 'touchstart'].forEach(event => {
                document.addEventListener(event, resetInactivityTimer, true);
            });
            
            // Setup extend session button
            document.addEventListener('DOMContentLoaded', function() {
                const extendButton = document.getElementById('extend-session');
                const logoutButton = document.getElementById('logout-now');
                
                if (extendButton) {
                    extendButton.addEventListener('click', function() {
                        resetInactivityTimer();
                    });
                }
                
                if (logoutButton) {
                    logoutButton.addEventListener('click', function() {
                        logout();
                    });
                }
                
                // Initialize the timer
                resetInactivityTimer();
            });
        }
    </script>
</body>
</html>
"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(login_html.encode('utf-8'))))
        self.end_headers()
        self.wfile.write(login_html.encode('utf-8'))

    def _static(self):
        parsed = urlparse(self.path)
        rel = parsed.path[len("/static/"):]
        import posixpath as _pp
        safe = _pp.normpath(rel).lstrip("/")
        full = os.path.join("static", safe)
        if not os.path.isfile(full):
            return _send_404(self)

        ctype = "text/plain; charset=utf-8"
        if full.endswith(".css"):
            ctype = "text/css; charset=utf-8"
        elif full.endswith(".js"):
            ctype = "application/javascript; charset=utf-8"
        elif full.endswith(".json"):
            ctype = "application/json; charset=utf-8"
        elif full.endswith(".png"):
            ctype = "image/png"
        elif full.endswith(".jpg") or full.endswith(".jpeg"):
            ctype = "image/jpeg"

        with open(full, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self._apply_cache_headers(is_api=False, is_html=False)
        self.send_header("Content-Length", str(len(data)))
        _add_security_headers(self)
        self.end_headers()
        self.wfile.write(data)

    def _api_last_update(self):
        # Just emit the single JSON object; no fall-through.
        data = read_last_update()
        return _json_response(self, data)

    def _api_config(self):
        """
        Serve dynamic configuration as JavaScript.
        This allows the HTML template to access runtime settings.
        """
        timestamp_range_hint = None
        try:
            hint_path = os.path.join(SERVER_OUTPUT_DIR or DEFAULT_OUTPUT_DIR, "timestamp_range_hint.json")
            if os.path.exists(hint_path):
                with open(hint_path, "r", encoding="utf-8") as f:
                    timestamp_range_hint = json.load(f)
        except Exception as e:
            print(f"[WARNING] Failed to load timestamp range hint: {e}")

        config = {
            "enableAuth": ENABLE_AUTH,
            "sessionTimeout": SESSION_TIMEOUT,
            "enableCors": ENABLE_CORS,
            "debugTiming": DEBUG_TIMING,
            "timestampRangeHint": timestamp_range_hint,
        }
        
        # Generate JavaScript that sets window.APP_CONFIG
        js_content = f"window.APP_CONFIG = {json.dumps(config, indent=2)};\n"
        
        self.send_response(200)
        self.send_header("Content-Type", "application/javascript; charset=utf-8")
        self.send_header("Content-Length", str(len(js_content.encode("utf-8"))))
        self._apply_cache_headers(is_api=True, is_html=False)
        _add_security_headers(self)
        self.end_headers()
        self.wfile.write(js_content.encode("utf-8"))

    def _api_policies_ss(self):
        """
        Server-side DataTables for policies.

        - related-events: rows come from policy_summary.csv (or SQLite table)
        - analytics.temporal-patterns: rows come from condition_sets_by_policy.json
        """
        global SERVER_USE_SQLITE, DB_CONN
        debug_print(f"[DEBUG] _api_policies_ss: START")
        try:
            _maybe_reload_data()  # hot-reload guard
            debug_print(f"[DEBUG] _api_policies_ss: after _maybe_reload_data")
            t0 = time.perf_counter()
            parsed, qd = self._parse_args()
            args = {k: v[0] for k, v in qd.items()}
            global_search = (args.get("global_search") or "").strip()
            group_id = (args.get("group_id") or "").strip()
            advanced_filter_json = (args.get("advancedFilter") or "").strip()
            debug_print(f"[DEBUG] _api_policies_ss: group_id={group_id}, global_search={global_search}, advancedFilter={advanced_filter_json}")

            # ---- Patterns mode: serve from CONDSETS_BY_POLICY ----
            if group_id == GROUP_PATTERNS:
                rows: List[Dict[str, Any]] = []
                if global_search:
                    gs = global_search.lower()

                    def match(pid: str, obj: Any) -> bool:
                        try:
                            blob = json.dumps(obj, ensure_ascii=False)
                        except Exception:
                            blob = str(obj)
                        return (gs in pid.lower()) or (gs in blob.lower())

                    for pid, obj in CONDSETS_BY_POLICY.items():
                        if match(pid, obj):
                            rows.append({
                                "policy_id": pid,
                                "ranking_score": None,   # not used for patterns
                                "event_count": None,
                                "event_occurrences": None,
                                "deployed": bool(obj.get("deployed", False)) if isinstance(obj, dict) else False
                            })
                else:
                    for pid, obj in CONDSETS_BY_POLICY.items():
                        rows.append({
                            "policy_id": pid,
                            "ranking_score": None,
                            "event_count": None,
                            "event_occurrences": None,
                            "deployed": bool(obj.get("deployed", False)) if isinstance(obj, dict) else False
                        })

                cols = ["policy_id", "ranking_score", "event_count", "event_occurrences", "deployed"]
                res = dt_page_mem(args, rows, cols, projector=lambda r: r)
                _log_timing("policies_ss(patterns)", t0)
                return _json_response(self, res)
            # ---- Related-events mode ----
            if SERVER_USE_SQLITE and DB_CONN is not None:
                base_sql  = "SELECT policy_id, ranking_score, event_count, event_occurrences, deployed, group_id FROM policies"
                count_sql = "SELECT COUNT(*) FROM policies"
                cols_filter = ["policy_id", "CAST(ranking_score AS TEXT)", "CAST(event_count AS TEXT)"]
                cols_order  = ["policy_id", "ranking_score", "event_count", "event_occurrences", "deployed"]
                params: List[Any] = []
                where_clauses: List[str] = []

                if group_id:
                    where_clauses.append("group_id = ?")
                    params.append(group_id)
                if global_search:
                    mode, needle = parse_global_search(global_search)

                    if needle:
                        like_cols = ["event_id", "payload_resource", "summary", "payload_details", "payload_type"]
                        like_expr = " OR ".join([f"e.{c} LIKE ?" for c in like_cols])
                        if mode == "include":
                            where_clauses.append(f"""
                                EXISTS (
                                    SELECT 1 FROM events e
                                    WHERE e.policy_id = policies.policy_id
                                    AND ({like_expr})
                                )
                            """)
                        else:  # exclude
                            where_clauses.append(f"""
                                NOT EXISTS (
                                    SELECT 1 FROM events e
                                    WHERE e.policy_id = policies.policy_id
                                    AND ({like_expr})
                                )
                            """)


                        params.extend([f"%{needle}%"] * len(like_cols))


                if where_clauses:
                    where_sql = " WHERE " + " AND ".join(where_clauses)
                    base_sql  += where_sql
                    count_sql += where_sql

                try:
                    res = dt_page_sql(args, base_sql, count_sql, cols_filter, cols_order, extra_params=params)

                    def projector(r: Dict[str, Any]) -> Dict[str, Any]:
                        return {
                            "policy_id": r.get("policy_id"),
                            "ranking_score": r.get("ranking_score"),
                            "event_count": r.get("event_count"),
                            "event_occurrences": r.get("event_occurrences"),
                            "deployed": bool(r.get("deployed", 0)),
                        }
                    res["data"] = [projector(x) for x in res["data"]]
                    _log_timing("policies_ss(sqlite)", t0)
                    return _json_response(self, res)
                except (sqlite3.DatabaseError, sqlite3.OperationalError) as e:
                    print(f"[ERROR] Database error in policies_ss: {e}")
                    print("[CRITICAL] SQLite corruption detected - permanently switching to memory mode")
                    # Permanently disable SQLite mode to prevent repeated corruption
                    SERVER_USE_SQLITE = False
                    # DON'T try to close corrupted connection - it may cause segfault
                    # Just set to None and let garbage collector handle it
                    DB_CONN = None
                    # Force garbage collection to clean up any lingering SQLite objects
                    import gc
                    gc.collect()
                    # Try to remove corrupted database file so it gets recreated on next restart
                    try:
                        if SERVER_SQLITE_PATH and os.path.exists(SERVER_SQLITE_PATH):
                            print(f"[INFO] Removing corrupted database file: {SERVER_SQLITE_PATH}")
                            os.remove(SERVER_SQLITE_PATH)
                            # Also remove WAL and SHM files if they exist
                            for ext in ['-wal', '-shm']:
                                wal_file = SERVER_SQLITE_PATH + ext
                                if os.path.exists(wal_file):
                                    os.remove(wal_file)
                    except Exception as cleanup_err:
                        print(f"[WARNING] Could not remove corrupted database: {cleanup_err}")
                    # Don't reload data here - just use existing memory data
                    # (data was already loaded at startup into policy_summary_data, etc.)
                    print("[INFO] Switched to memory mode - using existing in-memory data")
                    # Fall through to memory mode below
            
            # Memory mode (also used as fallback for database errors)
            if not SERVER_USE_SQLITE or DB_CONN is None:
                policies = policy_summary_data
                print(f"[DEBUG] _api_policies_ss: memory mode, total policies={len(policies)}")
                if group_id:
                    print(f"[DEBUG] _api_policies_ss: filtering by group_id={group_id}")
                    policies = [p for p in policies if (p.get("group_id") or "") == group_id]
                    print(f"[DEBUG] _api_policies_ss: after group filter, policies={len(policies)}")

                if global_search:
                    term = global_search.lower()
                    
                    # Use search index for fast lookups
                    if SEARCH_INDEX:
                        # Find all policy IDs that match any indexed word containing the search term
                        matching_ids = set()
                        for word, policy_ids in SEARCH_INDEX.items():
                            if term in word:
                                matching_ids.update(policy_ids)
                        
                        if not matching_ids:
                            # No index matches, do full scan as fallback
                            print(f"[DEBUG] No index matches for '{term}', doing full scan")
                            def event_matches(e: Dict[str, Any]) -> bool:
                                for k in ("event_id", "payload_resource", "summary", "payload_details", "payload_type"):
                                    v = e.get(k)
                                    if v is not None and term in str(v).lower():
                                        return True
                                return False
                            matching_ids = {e.get("policy_id") for e in policy_events_payload_data if event_matches(e)}
                    else:
                        # No index available, do full scan
                        def event_matches(e: Dict[str, Any]) -> bool:
                            for k in ("event_id", "payload_resource", "summary", "payload_details", "payload_type"):
                                v = e.get(k)
                                if v is not None and term in str(v).lower():
                                    return True
                            return False
                        matching_ids = {e.get("policy_id") for e in policy_events_payload_data if event_matches(e)}
                    
                    policies = [p for p in policies if p.get("policy_id") in matching_ids]
                
                # Apply advanced filter if specified
                if advanced_filter_json:
                    print(f"[DEBUG] _api_policies_ss: applying advanced filter to find matching policies")
                    try:
                        import json
                        filter_obj = json.loads(advanced_filter_json)
                        conditions = filter_obj.get("conditions", [])
                        logic = filter_obj.get("logic", "AND")
                        print(f"[DEBUG] _api_policies_ss: filter conditions={conditions}, logic={logic}")
                        
                        if conditions:
                            # Find all policy IDs that have events matching the filter
                            matching_policy_ids = set()
                            for event in policy_events_payload_data:
                                if self._evaluate_advanced_filter(event, conditions, logic):
                                    policy_id = event.get("policy_id")
                                    if policy_id:
                                        matching_policy_ids.add(policy_id)
                            
                            print(f"[DEBUG] _api_policies_ss: found {len(matching_policy_ids)} policies with matching events")
                            policies = [p for p in policies if p.get("policy_id") in matching_policy_ids]
                            print(f"[DEBUG] _api_policies_ss: after advanced filter, policies={len(policies)}")
                    except Exception as e:
                        print(f"[ERROR] _api_policies_ss: failed to apply advanced filter: {e}")
                        import traceback
                        traceback.print_exc()

                cols = ["policy_id", "ranking_score", "event_count", "event_occurrences", "deployed"]
                def proj(r: Dict[str, Any]) -> Dict[str, Any]:
                    return {
                        "policy_id": r.get("policy_id"),
                        "ranking_score": r.get("ranking_score"),
                        "event_count": r.get("event_count"),
                        "event_occurrences": r.get("event_occurrences"),
                        "deployed": r.get("deployed", False),
                    }
                res = dt_page_mem(args, policies, cols, projector=proj)
                _log_timing("policies_ss(memory)", t0)
                print(f"[DEBUG] _api_policies_ss: returning response, data_len={len(res.get('data', []))}")
                return _json_response(self, res)
        except Exception as e:
            print(f"[ERROR] _api_policies_ss: Exception occurred: {e}")
            import traceback
            traceback.print_exc()
            return _json_response(self, {"error": str(e)}, status=500)

    def _api_event_instances_ss(self):
        if DB_CONN is None:
            return _json_response(self, {"error": "SQLite mode required for /api/event_instances_ss"}, status=400)
        _maybe_reload_data()  # hot-reload guard
        t0 = time.perf_counter()
        parsed, qd = self._parse_args()
        args = {k: v[0] for k, v in qd.items()}
        policy_filter = (args.get("policy_id") or "").strip()
        cols_filter = ["event_id", "policy_id", "CAST(severity AS TEXT)", "summary", "CAST(first_seen_ts AS TEXT)", "CAST(last_seen_ts AS TEXT)"]
        cols_order  = ["event_id", "policy_id", "severity", "summary", "first_seen_ts", "last_seen_ts"]
        base_sql = "SELECT event_id, policy_id, severity, summary, first_seen_ts, last_seen_ts FROM event_instances"
        count_sql = "SELECT COUNT(*) FROM event_instances"
        extra_params: List[Any] = []
        if policy_filter:
            base_sql += " WHERE policy_id = ?"
            count_sql += " WHERE policy_id = ?"
            extra_params.append(policy_filter)
        res = dt_page_sql(args, base_sql, count_sql, cols_filter, cols_order, extra_params)
        _log_timing("event_instances_ss(sqlite)", t0)
        return _json_response(self, res)

    def _api_events_ss(self):
        """
        Server-side DataTables for events.

        - related-events: rows from policy_events_payload.csv (or SQLite)
        - analytics.temporal-patterns: no rows (UI shows condition set via /api/pattern_config)
        """
        global SERVER_USE_SQLITE, DB_CONN
        debug_print(f"[DEBUG] _api_events_ss: START")
        try:
            _maybe_reload_data()  # hot-reload guard
            debug_print(f"[DEBUG] _api_events_ss: after _maybe_reload_data")
            t0 = time.perf_counter()
            parsed, qd = self._parse_args()
            args = {k: v[0] for k, v in qd.items()}
            policy_id = (args.get("policy_id") or "").strip()
            global_search = (args.get("global_search") or "").strip()
            group_id = (args.get("group_id") or "").strip()
            advanced_filter_json = (args.get("advancedFilter") or "").strip()
            debug_print(f"[DEBUG] _api_events_ss: group_id={group_id}, policy_id={policy_id}, global_search={global_search}, advancedFilter={advanced_filter_json}")

            # ---- Patterns mode: return empty (UI uses /api/pattern_config) ----
            if group_id == GROUP_PATTERNS:
                debug_print(f"[DEBUG] _api_events_ss: returning empty for patterns mode")
                return _json_response(self, {
                    "draw": int(args.get("draw","0") or 0),
                    "recordsTotal": 0,
                    "recordsFiltered": 0,
                    "data": []
                })

            # ---- Related-events mode ----
            debug_print(f"[DEBUG] _api_events_ss: entering related-events mode, acquiring lock")
            # Acquire lock to prevent data corruption during concurrent access
            with _DATA_LOCK:
                debug_print(f"[DEBUG] _api_events_ss: lock acquired")
                debug_print(f"[DEBUG] _api_events_ss: checking DB_CONN, value={DB_CONN is not None}")
                if SERVER_USE_SQLITE and DB_CONN is not None:
                    debug_print(f"[DEBUG] _api_events_ss: using SQLite mode")
                    base_sql  = "SELECT event_id, severity, payload_resource, summary, payload_details, payload_type FROM events"
                    count_sql = "SELECT COUNT(*) FROM events"
                    params: List[Any] = []
                    search_cols = ["event_id", "payload_resource", "summary", "payload_details", "payload_type"]
                    where: List[str] = []

                    if global_search:
                        mode, needle = parse_global_search(global_search)
                        if needle:
                            like_clause = " OR ".join([f"{c} LIKE ?" for c in search_cols])

                            if mode == "include":
                                where.append(f"({like_clause})")
                            else:  # exclude
                                where.append(f"NOT ({like_clause})")

                            params.extend([f"%{needle}%"] * len(search_cols))
                    elif policy_id:
                        where.append("policy_id = ?")
                        params.append(policy_id)


                    if where:
                        wsql = " WHERE " + " AND ".join(where)
                        base_sql += wsql
                        count_sql += wsql

                    cols_filter = ["event_id", "severity", "payload_resource", "summary", "payload_details", "payload_type"]
                    cols_order  = ["event_id", "severity", "payload_resource", "summary", "payload_details", "payload_type"]
                    
                    try:
                        res = dt_page_sql(args, base_sql, count_sql, cols_filter, cols_order, extra_params=params)
                        _log_timing("events_ss(sqlite)", t0)
                        return _json_response(self, res)
                    except (sqlite3.DatabaseError, sqlite3.OperationalError) as e:
                        print(f"[ERROR] Database error in events_ss: {e}")
                        print("[CRITICAL] SQLite corruption detected - permanently switching to memory mode")
                        # Permanently disable SQLite mode to prevent repeated corruption
                        SERVER_USE_SQLITE = False
                        # DON'T try to close corrupted connection - it may cause segfault
                        # Just set to None and let garbage collector handle it
                        DB_CONN = None
                        # Force garbage collection to clean up any lingering SQLite objects
                        import gc
                        gc.collect()
                        # Try to remove corrupted database file so it gets recreated on next restart
                        try:
                            if SERVER_SQLITE_PATH and os.path.exists(SERVER_SQLITE_PATH):
                                print(f"[INFO] Removing corrupted database file: {SERVER_SQLITE_PATH}")
                                os.remove(SERVER_SQLITE_PATH)
                                # Also remove WAL and SHM files if they exist
                                for ext in ['-wal', '-shm']:
                                    wal_file = SERVER_SQLITE_PATH + ext
                                    if os.path.exists(wal_file):
                                        os.remove(wal_file)
                        except Exception as cleanup_err:
                            print(f"[WARNING] Could not remove corrupted database: {cleanup_err}")
                        # Don't reload data here - just use existing memory data
                        # (data was already loaded at startup into policy_summary_data, etc.)
                        print("[INFO] Switched to memory mode - using existing in-memory data")
                        # Fall through to memory mode below
                
                # Memory mode (also used as fallback for database errors)
                print(f"[DEBUG] _api_events_ss: using memory mode")
                # For large datasets, use a more memory-efficient approach
                start = int(args.get("start", "0") or 0)
                length = int(args.get("length", "25") or 25)
                draw = int(args.get("draw", "0") or 0)
                print(f"[DEBUG] _api_events_ss: start={start}, length={length}, draw={draw}")
                
                print(f"[DEBUG] _api_events_ss: policy_events_payload_data length={len(policy_events_payload_data)}")
            
                # First filter by policy_id if specified (most common case)
                if policy_id:
                    print(f"[DEBUG] _api_events_ss: filtering by policy_id={policy_id}")
                    # Process in batches to reduce memory pressure
                    filtered = []
                    batch_size = 1000
                    total_count = len(policy_events_payload_data)
                    
                    for i in range(0, total_count, batch_size):
                        batch = policy_events_payload_data[i:i+batch_size]
                        for r in batch:
                            if r.get("policy_id") == policy_id:
                                filtered.append(r)
                    
                    base = filtered
                    print(f"[DEBUG] _api_events_ss: filtered to {len(base)} events")
                else:
                    print(f"[DEBUG] _api_events_ss: no policy filter, using all data")
                    base = policy_events_payload_data
                
                # Then apply global search if specified
                if global_search:
                    print(f"[DEBUG] _api_events_ss: applying global search")
                    gs = global_search.lower()
                    filtered = []
                    batch_size = 1000
                    total_count = len(base)
                    
                    for i in range(0, total_count, batch_size):
                        batch = base[i:i+batch_size]
                        for r in batch:
                            fields = [r.get("event_id"), r.get("payload_resource"), r.get("summary"),
                                     r.get("payload_details"), r.get("payload_type")]
                            for v in fields:
                                if v is not None and gs in str(v).lower():
                                    filtered.append(r)
                                    break
                    
                    base = filtered
                    print(f"[DEBUG] _api_events_ss: after global search, {len(base)} events")
                
                # Apply advanced filter if specified
                if advanced_filter_json:
                    print(f"[DEBUG] _api_events_ss: applying advanced filter, JSON={advanced_filter_json}")
                    try:
                        import json
                        filter_obj = json.loads(advanced_filter_json)
                        conditions = filter_obj.get("conditions", [])
                        logic = filter_obj.get("logic", "AND")
                        print(f"[DEBUG] _api_events_ss: parsed filter - conditions={conditions}, logic={logic}")
                        
                        if conditions:
                            filtered = []
                            batch_size = 1000
                            total_count = len(base)
                            print(f"[DEBUG] _api_events_ss: filtering {total_count} events with {len(conditions)} condition(s)")
                            
                            for i in range(0, total_count, batch_size):
                                batch = base[i:i+batch_size]
                                for r in batch:
                                    match = self._evaluate_advanced_filter(r, conditions, logic)
                                    if match:
                                        filtered.append(r)
                            
                            base = filtered
                            print(f"[DEBUG] _api_events_ss: after advanced filter, {len(base)} events (filtered from {total_count})")
                        else:
                            print(f"[DEBUG] _api_events_ss: no conditions in filter, skipping")
                    except Exception as e:
                        print(f"[ERROR] _api_events_ss: failed to parse advanced filter: {e}")
                        import traceback
                        traceback.print_exc()
                else:
                    print(f"[DEBUG] _api_events_ss: no advanced filter specified")
                
                print(f"[DEBUG] _api_events_ss: applying sorting")
                # Apply sorting if specified
                order_col_idx = args.get("order[0][column]")
                order_dir = args.get("order[0][dir]", "asc")
                cols = ["event_id", "severity", "payload_resource", "summary", "payload_details", "payload_type"]
                
                if order_col_idx is not None:
                    print(f"[DEBUG] _api_events_ss: sorting by column {order_col_idx}, direction {order_dir}")
                    i = int(order_col_idx)
                    key = cols[i] if i < len(cols) else cols[0]
                    base = sorted(base, key=lambda r: (_coerce(r.get(key)), r.get('event_id', '')),
                                 reverse=(order_dir == "desc"))
                    print(f"[DEBUG] _api_events_ss: sorting complete")
                
                print(f"[DEBUG] _api_events_ss: getting page")
                # Get the page
                total_count = len(policy_events_payload_data)
                filtered_count = len(base)
                page = base[start:start+length]
                print(f"[DEBUG] _api_events_ss: page extracted, length={len(page)}")
                
                print(f"[DEBUG] _api_events_ss: projecting results")
                # Project the results
                def proj(r: Dict[str, Any]) -> Dict[str, Any]:
                    return {
                        "event_id": r.get("event_id"),
                        "severity": r.get("severity"),
                        "payload_resource": r.get("payload_resource"),
                        "summary": r.get("summary"),
                        "payload_details": r.get("payload_details"),
                        "payload_type": r.get("payload_type"),
                    }
                
                print(f"[DEBUG] _api_events_ss: creating result_data list")
                result_data = [proj(r) for r in page]
                print(f"[DEBUG] _api_events_ss: result_data created, length={len(result_data)}")
                
                print(f"[DEBUG] _api_events_ss: building response dict")
                res = {
                    "draw": draw,
                    "recordsTotal": total_count,
                    "recordsFiltered": filtered_count,
                    "data": result_data,
                }
                print(f"[DEBUG] _api_events_ss: response dict built")
                
                _log_timing("events_ss(memory-optimized)", t0)
                print(f"[DEBUG] _api_events_ss: returning response, data_len={len(result_data)}")
                return _json_response(self, res)
        except Exception as e:
            print(f"[ERROR] _api_events_ss: Exception occurred: {e}")
            import traceback
            traceback.print_exc()
            return _json_response(self, {"error": str(e)}, status=500)

    def _api_pattern_config(self):
        _maybe_reload_data()  # hot-reload guard
        parsed = urlparse(self.path)
        policy_id = unquote(parsed.path.rsplit("/", 1)[-1])
        cs = CONDSETS_BY_POLICY.get(policy_id)
        if cs is None:
            return _json_response(self, {"error": "not found", "policy_id": policy_id}, status=404)
        return _json_response(self, {"condition_set": cs})

    def _api_payload_preview(self):
        _maybe_reload_data()  # hot-reload guard
        parsed = urlparse(self.path)
        event_id = unquote(parsed.path.rsplit("/", 1)[-1])
        t0 = time.perf_counter()

        # Synthetic pattern event id support (not used now, but harmless)
        if event_id.endswith("-pattern"):
            pid = event_id[:-8]
            cond = CONDSETS_BY_POLICY.get(pid)
            if cond is not None:
                s = json.dumps(cond, separators=(",", ":"), ensure_ascii=False)
                truncated = False
                if len(s.encode("utf-8", "ignore")) > PAYLOAD_PREVIEW_MAX:
                    truncated = True
                    s = s[:PAYLOAD_PREVIEW_MAX]
                return _json_response(self, {
                    "event_id": event_id,
                    "preview": True,
                    "truncated": truncated,
                    "bytes": len(s.encode("utf-8", "ignore")),
                    "text": s,
                    "download_url": f"/api/payload_download/{event_id}"
                })

        # related-events fallback
        if DB_CONN is not None:
            cur = DB_CONN.cursor()
            row = cur.execute("SELECT full_payload FROM events WHERE event_id = ?", (event_id,)).fetchone()
            raw = row["full_payload"] if row else None
        else:
            hit = next((e for e in policy_events_payload_data if e.get("event_id") == event_id), None)
            raw = hit.get("full_payload") if hit else None

        if raw is None:
            return _json_response(self, {"event_id": event_id, "preview": True, "truncated": False, "bytes": 0, "text": "", "download_url": f"/api/payload_download/{event_id}"})

        if not isinstance(raw, str):
            try:
                raw = json.dumps(raw, separators=(",", ":"))
            except Exception:
                raw = str(raw)

        s = raw
        truncated = False
        if len(s.encode("utf-8", "ignore")) > PAYLOAD_PREVIEW_MAX:
            truncated = True
            s = s[:PAYLOAD_PREVIEW_MAX]

        _log_timing("payload_preview", t0)
        return _json_response(self, {
            "event_id": event_id,
            "preview": True,
            "truncated": truncated,
            "bytes": len(s.encode("utf-8", "ignore")),
            "text": s,
            "download_url": f"/api/payload_download/{event_id}"
        })

    def _api_payload_download(self):
        _maybe_reload_data()  # hot-reload guard
        parsed = urlparse(self.path)
        event_id = unquote(parsed.path.rsplit("/", 1)[-1])

        if event_id.endswith("-pattern"):
            pid = event_id[:-8]
            cond = CONDSETS_BY_POLICY.get(pid)
            if cond is None:
                return _send_404(self)
            raw = json.dumps(cond, ensure_ascii=False)
            body = raw.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Disposition", f'attachment; filename="{event_id}.json"')
            self.send_header("Content-Length", str(len(body)))
            self._apply_cache_headers(is_api=True, is_html=False)
            self.end_headers()
            self.wfile.write(body)
            return

        # related-events
        if DB_CONN is not None:
            cur = DB_CONN.cursor()
            row = cur.execute("SELECT full_payload FROM events WHERE event_id = ?", (event_id,)).fetchone()
            raw = row["full_payload"] if row else None
        else:
            hit = next((e for e in policy_events_payload_data if e.get("event_id") == event_id), None)
            raw = hit.get("full_payload") if hit else None

        if raw is None:
            return _send_404(self)

        if not isinstance(raw, str):
            try:
                raw = json.dumps(raw)
            except Exception:
                raw = str(raw)

        body = raw.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Disposition", f'attachment; filename="{event_id}.json"')
        self.send_header("Content-Length", str(len(body)))
        self._apply_cache_headers(is_api=True, is_html=False)
        self.end_headers()
        self.wfile.write(body)

    def _api_policies_legacy(self):
        _maybe_reload_data()  # hot-reload guard
        _json_response(self, policy_summary_data)

    def _api_events_legacy(self):
        _maybe_reload_data()  # hot-reload guard
        _json_response(self, events_detail_data)

    def _api_payloads_legacy(self):
        _maybe_reload_data()  # hot-reload guard
        _json_response(self, policy_events_payload_data)

    def _api_get_deploy_cache(self):
        with _deployed_cache_lock:
            return _json_response(self, {"ids": sorted(_deployed_cache_ids), "path": DEPLOYED_CACHE_PATH})

    def _api_post_deploy_cache(self):
        data = _read_body_json(self)
        ids = [str(x) for x in (data.get("ids") or []) if x]
        add_ids_to_deployed_cache(ids)
        return _json_response(self, {"ok": True, "added": ids, "path": DEPLOYED_CACHE_PATH})

    def _api_delete_deploy_cache(self):
        clear_deployed_cache()
        return _json_response(self, {"ok": True, "path": DEPLOYED_CACHE_PATH})

    def _api_deploy_policies(self):
        """
        PATCH proxy. Body:
        {
          "base_url": ".../policies/activate/system",
          "username": "...",
          "password": "...",
          "ids": ["..."],
          "verify_tls": true,
          "ca_bundle": null,
          "concurrency": 4,
          "connect_timeout": 10,
          "read_timeout": 25,
          "overall_timeout": 120
        }
        """
        data = _read_body_json(self)
        base_url   = (data.get("base_url") or "").strip().rstrip("/")
        username   = data.get("username") or ""
        password   = data.get("password") or ""
        ids        = [str(x) for x in (data.get("ids") or []) if x]
        verify_tls = bool(data.get("verify_tls", True))
        ca_bundle  = data.get("ca_bundle") or None
        connect_to = float(data.get("connect_timeout", 10.0))
        read_to    = float(data.get("read_timeout", 25.0))
        overall_timeout = float(data.get("overall_timeout", max(30.0, 5.0 * len(ids))))
        try:
            concurrency = int(data.get("concurrency", 4))
        except Exception:
            concurrency = 4
        max_workers = max(1, min(concurrency, len(ids) or 1))

        if not base_url:
            return _json_response(self, {"error": "Missing base_url"}, status=400)
        if not ids:
            return _json_response(self, {"ok": [], "fail": [], "urls": {}, "cache_path": None})

        def build_url(pid: str) -> str:
            return f"{base_url}/{quote(pid, safe='')}?policystate=active&policylocked=false"

        # SSL context
        context = None
        if base_url.lower().startswith("https"):
            if not verify_tls:
                context = ssl._create_unverified_context()
            elif ca_bundle:
                context = ssl.create_default_context(cafile=ca_bundle)
            else:
                context = ssl.create_default_context()

        # Basic Auth header if provided
        auth_header = None
        if username or password:
            import base64 as _b64
            token = _b64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
            auth_header = f"Basic {token}"

        ok, fail, urls = [], [], {}
        def worker(pid: str):
            url = build_url(pid)
            headers = {"Accept": "*/*", "Connection": "close"}
            if auth_header:
                headers["Authorization"] = auth_header
            req = Request(url, data=b"", headers=headers, method="PATCH")
            try:
                with urlopen(req, timeout=connect_to + read_to, context=context) as resp:
                    status = resp.status
                    body = (resp.read(400) or b"").decode("utf-8", "ignore")
                if 200 <= status < 300:
                    return ("ok", pid, status, "", url)
                else:
                    return ("fail", pid, status, body, url)
            except Exception as e:
                return ("fail", pid, 0, str(e)[:400], url)

        done = []
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            fut_to_id = {ex.submit(worker, pid): pid for pid in ids}
            try:
                for fut in as_completed(fut_to_id, timeout=overall_timeout):
                    done.append(fut)
                    kind, pid, status, info, url = fut.result()
                    urls[pid] = url
                    if kind == "ok":
                        ok.append(pid)
                    else:
                        fail.append({"id": pid, "status": status, "error": info, "url": url})
            except Exception:
                pass
            unfinished = [f for f in fut_to_id if f not in done]
            for f in unfinished:
                pid = fut_to_id[f]
                try:
                    f.cancel()
                except Exception:
                    pass
                url = urls.get(pid) or build_url(pid)
                fail.append({"id": pid, "status": 0, "error": "overall timeout", "url": url})

        # Log deployment action
        username = "unknown"
        auth_header = self.headers.get('Authorization')
        if auth_header:
            try:
                auth_type, auth_data = auth_header.split(' ', 1)
                if auth_type.lower() == 'basic':
                    decoded = base64.b64decode(auth_data).decode('utf-8')
                    username, _ = decoded.split(':', 1)
            except Exception:
                pass
                
        client_ip = self.client_address[0]
        details = f"policies={len(ids)} success={len(ok)} failed={len(fail)}"
        log_audit("DEPLOY_POLICIES", username, client_ip=client_ip, details=details)
        
        return _json_response(self, {"ok": ok, "fail": fail, "urls": urls})

# -------------------- Server bootstrap --------------------
def start_web_server(output_dir: str, port: int, use_sqlite: bool = False, sqlite_path: Optional[str] = None,
                    event_instances: Optional[str] = None, bind_address: str = DEFAULT_BIND_ADDRESS,
                    enable_auth: bool = False, auth_credentials: Optional[Dict[str, str]] = None,
                    enable_cors: bool = True, cors_origins: str = "*",
                    enable_https: bool = False, ssl_cert_file: Optional[str] = None, ssl_key_file: Optional[str] = None) -> None:
    global DB_CONN, CONDSETS_BY_POLICY
    global SERVER_OUTPUT_DIR, SERVER_SQLITE_PATH, SERVER_EVENT_INSTANCES, SERVER_USE_SQLITE, _DATA_VERSION
    global ENABLE_AUTH, AUTH_CREDENTIALS, ENABLE_CORS, CORS_ORIGINS
    
    # Apply security settings
    ENABLE_AUTH = enable_auth
    
    # Update credentials dictionary
    if auth_credentials:
        AUTH_CREDENTIALS.update(auth_credentials)
    
    # For backward compatibility, if no credentials provided but auth is enabled,
    # ensure we have at least the default admin user
    if ENABLE_AUTH and not AUTH_CREDENTIALS:
        AUTH_CREDENTIALS["admin"] = "changeme"
        
    ENABLE_CORS = enable_cors
    CORS_ORIGINS = cors_origins

    Path("static").mkdir(parents=True, exist_ok=True)

    # Remember startup parameters for hot-reload
    SERVER_OUTPUT_DIR = output_dir or DEFAULT_OUTPUT_DIR
    SERVER_SQLITE_PATH = sqlite_path
    SERVER_EVENT_INSTANCES = event_instances
    SERVER_USE_SQLITE = bool(use_sqlite)

    # Initial load - ALWAYS load into memory for fallback capability
    ok = False
    
    # Always load data into memory first (needed for fallback from SQLite corruption)
    print("[INFO] Loading data into memory (for fallback capability)...")
    ok_memory = load_data_to_memory(output_dir)
    
    if use_sqlite:
        print("[WARNING] SQLite mode is currently disabled due to persistent corruption issues")
        print("[INFO] Using memory-only mode for stability")
        SERVER_USE_SQLITE = False
        ok = ok_memory
    else:
        ok = ok_memory

    if not ok:
        print("Error: Failed to load data. Ensure CSVs exist in the output directory., but will continue anyway for later refresh.")
        # sys.exit(1)

    # Ensure condition sets are loaded (already done in loaders, but safe)
    if not CONDSETS_BY_POLICY:
        try:
            cond_path = os.path.join(output_dir, "condition_sets_by_policy.json")
            with open(cond_path, "r", encoding="utf-8") as f:
                CONDSETS_BY_POLICY = json.load(f) or {}
        except Exception:
            CONDSETS_BY_POLICY = {}

    # Initialize our in-memory version marker to whatever is on disk now
    _DATA_VERSION = _version_from_disk()

    write_viewer_html()

    # Use the specified bind address instead of hardcoded 0.0.0.0
    srv = ThreadingHTTPServer((bind_address, port), Handler)
    
    # Configure HTTPS if enabled
    protocol = "http"
    if enable_https:
        if not ssl_cert_file or not ssl_key_file:
            print("[server] Warning: HTTPS is enabled but certificate or key file path is not specified.")
            print("[server] Falling back to HTTP. To enable HTTPS, specify both ssl_cert_file and ssl_key_file.")
        else:
            try:
                cert_exists = os.path.exists(ssl_cert_file)
                key_exists = os.path.exists(ssl_key_file)
                
                # Auto-generate certificates if they don't exist
                if not cert_exists or not key_exists:
                    print(f"[server] SSL certificate or key file not found. Attempting to generate them automatically.")
                    try:
                        # Use the generate_ssl_cert.py script to create certificates
                        import subprocess
                        from subprocess import Popen, PIPE
                        
                        # Create directories for cert and key files if they don't exist
                        cert_dir = os.path.dirname(ssl_cert_file)
                        if cert_dir and not os.path.exists(cert_dir):
                            os.makedirs(cert_dir, exist_ok=True)
                            
                        key_dir = os.path.dirname(ssl_key_file)
                        if key_dir and not os.path.exists(key_dir):
                            os.makedirs(key_dir, exist_ok=True)
                        
                        # Create a configuration file for OpenSSL
                        config_content = """[req]
distinguished_name = req_distinguished_name
x509_extensions = v3_req
prompt = no

[req_distinguished_name]
C = US
ST = CA
L = San Francisco
O = Policy Visualization
CN = localhost

[v3_req]
keyUsage = keyEncipherment, dataEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @alt_names

[alt_names]
DNS.1 = localhost
IP.1 = 127.0.0.1
"""
                        
                        config_file = "openssl_config.cnf"
                        with open(config_file, "w") as f:
                            f.write(config_content)
                        
                        # Generate private key and certificate using OpenSSL
                        cmd = f"openssl req -x509 -newkey rsa:2048 -nodes -keyout {ssl_key_file} -out {ssl_cert_file} -days 365 -config {config_file}"
                        process = Popen(cmd, shell=True, stdout=PIPE, stderr=PIPE)
                        stdout, stderr = process.communicate()
                        
                        if process.returncode != 0:
                            print(f"[server] Error generating certificates: {stderr.decode('utf-8')}")
                            print("[server] Falling back to HTTP.")
                        else:
                            print(f"[server] Successfully generated self-signed certificate and key")
                            cert_exists = key_exists = True
                            
                        # Clean up the temporary config file
                        if os.path.exists(config_file):
                            os.remove(config_file)
                            
                    except Exception as e:
                        print(f"[server] Error generating certificates: {e}")
                        print("[server] Falling back to HTTP.")
                
                if cert_exists and key_exists:
                    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                    ssl_context.load_cert_chain(ssl_cert_file, ssl_key_file)
                    srv.socket = ssl_context.wrap_socket(srv.socket, server_side=True)
                    protocol = "https"
                    print(f"[server] HTTPS enabled with certificate: {ssl_cert_file}")
            except Exception as e:
                print(f"[server] Error enabling HTTPS: {e}")
                print("[server] Falling back to HTTP.")
    
    # Show the actual bind address in the startup message
    local_url = f"{protocol}://localhost:{port}" if bind_address in ("0.0.0.0", "127.0.0.1") else f"{protocol}://{bind_address}:{port}"
    print(f"[server] Starting on {local_url} (bind={bind_address}, sqlite={use_sqlite}, access_log={ACCESS_LOG}, timing={DEBUG_TIMING})")
    
    # Try to show the server's IP address for remote access if binding to all interfaces
    if bind_address == "0.0.0.0":
        try:
            import socket
            hostname = socket.gethostname()
            ip_address = socket.gethostbyname(hostname)
            print(f"[server] Server is accessible at: {protocol}://{ip_address}:{port}")
        except Exception:
            pass
    
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
        if DB_CONN is not None:
            DB_CONN.close()

def load_config_file(config_path: str) -> Dict[str, Any]:
    """Load configuration from file or return defaults if file doesn't exist"""
    config = {
        'port': DEFAULT_PORT,
        'bind_address': DEFAULT_BIND_ADDRESS,
        'output_dir': DEFAULT_OUTPUT_DIR,
        'use_sqlite': True,
        'sqlite_path': None,
        'event_instances': DEFAULT_EVENT_INSTANCES_FILE,
        'access_log': False,
        'debug_timing': False,
        'enable_cors': True,
        'cors_origins': '*',
        'enable_auth': False,
        'username': 'admin',
        'password': 'changeme',
        'session_timeout': 30,
        'enable_audit': True,
        'audit_log_file': 'audit.log',
        'max_log_size': 10485760,
        'backup_count': 5,
        'enable_https': False,
        'ssl_cert_file': 'cert.pem',
        'ssl_key_file': 'key.pem'
    }
    
    if not os.path.exists(config_path):
        print(f"[config] No configuration file found at {config_path}, using defaults")
        return config
    
    try:
        import configparser
        cfg = configparser.ConfigParser()
        cfg.read(config_path)
        
        # General section
        if 'general' in cfg:
            if 'port' in cfg['general']:
                config['port'] = cfg.getint('general', 'port')
            if 'bind_address' in cfg['general']:
                config['bind_address'] = cfg['general']['bind_address']
            if 'output_dir' in cfg['general']:
                config['output_dir'] = cfg['general']['output_dir']
            if 'use_sqlite' in cfg['general']:
                config['use_sqlite'] = cfg.getboolean('general', 'use_sqlite')
            if 'sqlite_path' in cfg['general']:
                config['sqlite_path'] = cfg['general']['sqlite_path']
            if 'event_instances' in cfg['general']:
                config['event_instances'] = cfg['general']['event_instances']
            if 'access_log' in cfg['general']:
                config['access_log'] = cfg.getboolean('general', 'access_log')
            if 'debug_timing' in cfg['general']:
                config['debug_timing'] = cfg.getboolean('general', 'debug_timing')
        
        # Security section
        if 'security' in cfg:
            if 'enable_cors' in cfg['security']:
                config['enable_cors'] = cfg.getboolean('security', 'enable_cors')
            if 'cors_origins' in cfg['security']:
                config['cors_origins'] = cfg['security']['cors_origins']
            if 'enable_auth' in cfg['security']:
                config['enable_auth'] = cfg.getboolean('security', 'enable_auth')
            if 'username' in cfg['security']:
                config['username'] = cfg['security']['username']
            if 'password' in cfg['security']:
                config['password'] = cfg['security']['password']
            # HTTPS configuration
            if 'enable_https' in cfg['security']:
                config['enable_https'] = cfg.getboolean('security', 'enable_https')
            if 'ssl_cert_file' in cfg['security']:
                config['ssl_cert_file'] = cfg['security']['ssl_cert_file']
            if 'ssl_key_file' in cfg['security']:
                config['ssl_key_file'] = cfg['security']['ssl_key_file']
        
        print(f"[config] Loaded configuration from {config_path}")
    except Exception as e:
        print(f"[config] Error loading configuration: {e}")
    
    return config

def main():
    global ACCESS_LOG, DEBUG_TIMING
    parser = argparse.ArgumentParser(description="Scalable Policy & Event Web UI (stdlib server, quiet by default)")
    parser.add_argument("--config", default=DEFAULT_CONFIG_FILE, help=f"Path to configuration file (default: {DEFAULT_CONFIG_FILE})")
    parser.add_argument("--output-dir", default=None, help=f"Directory with CSVs (default: {DEFAULT_OUTPUT_DIR})")
    parser.add_argument("--port", type=int, default=None, help=f"Port (default: {DEFAULT_PORT})")
    parser.add_argument("--bind", default=None, help=f"IP address to bind to (default: {DEFAULT_BIND_ADDRESS})")
    parser.add_argument("--use-sqlite", action="store_true", help="Load CSVs into a SQLite DB and serve from it")
    parser.add_argument("--sqlite-path", default=None, help="Path to SQLite DB file (default: <output-dir>/policy_events.db)")
    parser.add_argument("--event-instances", default=None, help="Path to event_instances_export.csv (semicolon-delimited, HEADER=true)")
    parser.add_argument("--access-log", action="store_true", help="Enable per-request access logging")
    parser.add_argument("--debug-timing", action="store_true", help="Enable timing prints")
    
    # HTTPS options
    parser.add_argument("--enable-https", action="store_true", help="Enable HTTPS")
    parser.add_argument("--ssl-cert", default=None, help="Path to SSL certificate file")
    parser.add_argument("--ssl-key", default=None, help="Path to SSL key file")
    args = parser.parse_args()
    
    # Load configuration from file
    config = load_config_file(args.config)
    
    # Command line arguments override configuration file
    output_dir = args.output_dir or config['output_dir']
    port = args.port or config['port']
    bind_address = args.bind or config['bind_address']
    use_sqlite = args.use_sqlite or config['use_sqlite']
    sqlite_path = args.sqlite_path or config['sqlite_path']
    event_instances = args.event_instances or config['event_instances']
    
    # HTTPS options from command line override config file
    enable_https = args.enable_https or config.get('enable_https', False)
    ssl_cert_file = args.ssl_cert or config.get('ssl_cert_file')
    ssl_key_file = args.ssl_key or config.get('ssl_key_file')
    
    # Set global flags
    if args.access_log or config['access_log']:
        ACCESS_LOG = True
    if args.debug_timing or config['debug_timing']:
        DEBUG_TIMING = True
    
    # Print configuration summary
    print(f"[server] Configuration:")
    print(f"[server] - Bind address: {bind_address}")
    print(f"[server] - Port: {port}")
    print(f"[server] - Output directory: {output_dir}")
    print(f"[server] - Use SQLite: {use_sqlite}")
    print(f"[server] - Access log: {ACCESS_LOG}")
    print(f"[server] - Debug timing: {DEBUG_TIMING}")
    
    # Get security settings from config
    enable_auth = config.get('enable_auth', False)
    enable_cors = config.get('enable_cors', True)
    cors_origins = config.get('cors_origins', '*')
    
    # Process credentials
    auth_credentials = {}
    
    try:
        import configparser
        cfg = configparser.ConfigParser()
        cfg.read(args.config)
        
        if 'security' in cfg and enable_auth:
            # Check for multiple users in the config
            if 'users' in cfg['security']:
                # Format: username1:password1,username2:password2
                users_str = cfg['security']['users']
                for user_entry in users_str.split(','):
                    if ':' in user_entry:
                        username, password = user_entry.strip().split(':', 1)
                        if username and password:
                            auth_credentials[username] = password
            
            # For backward compatibility, also check for single username/password
            if 'username' in cfg['security'] and 'password' in cfg['security']:
                username = cfg['security']['username']
                password = cfg['security']['password']
                if username and password:
                    auth_credentials[username] = password
                    
            # Load audit logging configuration
            if 'enable_audit' in cfg['security']:
                config['enable_audit'] = cfg.getboolean('security', 'enable_audit')
            if 'audit_log_file' in cfg['security']:
                config['audit_log_file'] = cfg['security']['audit_log_file']
            if 'max_log_size' in cfg['security']:
                config['max_log_size'] = cfg.getint('security', 'max_log_size')
            if 'backup_count' in cfg['security']:
                config['backup_count'] = cfg.getint('security', 'backup_count')
    except Exception as e:
        print(f"[config] Error processing authentication credentials: {e}")
        # Fallback to default credentials
        if enable_auth:
            auth_credentials = {"admin": "changeme"}
    
    # Print security configuration
    print(f"[server] - Authentication: {'Enabled' if enable_auth else 'Disabled'}")
    if enable_auth:
        print(f"[server] - Users configured: {len(auth_credentials)}")
    print(f"[server] - CORS: {'Enabled' if enable_cors else 'Disabled'}")
    print(f"[server] - Audit logging: {'Enabled' if config['enable_audit'] else 'Disabled'}")
    if config['enable_audit']:
        print(f"[server] - Audit log file: {config['audit_log_file']}")
    
    # HTTPS configuration
    enable_https = config.get('enable_https', False)
    ssl_cert_file = config.get('ssl_cert_file')
    ssl_key_file = config.get('ssl_key_file')
    if enable_https:
        print(f"[server] - HTTPS: Enabled")
        print(f"[server] - SSL Certificate: {ssl_cert_file}")
        print(f"[server] - SSL Key: {ssl_key_file}")
    else:
        print(f"[server] - HTTPS: Disabled")
    
    # Update global audit settings
    global ENABLE_AUDIT, AUDIT_LOG_FILE, MAX_LOG_SIZE, BACKUP_COUNT
    ENABLE_AUDIT = config['enable_audit']
    AUDIT_LOG_FILE = config['audit_log_file']
    MAX_LOG_SIZE = config['max_log_size']
    BACKUP_COUNT = config['backup_count']
    
    # Start the web server with all configuration options
    start_web_server(
        output_dir=output_dir,
        port=port,
        use_sqlite=use_sqlite,
        sqlite_path=sqlite_path,
        event_instances=event_instances,
        bind_address=bind_address,
        enable_auth=enable_auth,
        auth_credentials=auth_credentials,
        enable_cors=enable_cors,
        cors_origins=cors_origins,
        enable_https=enable_https,
        ssl_cert_file=ssl_cert_file,
        ssl_key_file=ssl_key_file
    )

if __name__ == "__main__":
    main()
