#!/usr/bin/env python3
#
# Copyright IBM Corp. 2024 - 2026
# SPDX-License-Identifier: Apache-2.0
#
"""
Process policy and event data from CSVs and generate reports/artefacts
for BOTH:
  - related-events (events + payloads)
  - analytics.correlation-patterns (no events; condition sets only)

This version is robust to header/column order and groupid formatting.
Performance optimized for large datasets.
"""

import csv
import json
import re
import ast
import os
import sys
import time
import argparse
from pathlib import Path
from typing import Dict, List, Set, Optional, Any, Union, Tuple
from collections import defaultdict, Counter
from datetime import datetime
import shutil
# Optional: Try to import tqdm for progress bars
try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False
    # Fallback: simple progress indicator
    class tqdm:
        def __init__(self, iterable=None, desc=None, total=None, disable=False):
            self.iterable = iterable
            self.desc = desc
            self.total = total
            self.n = 0
            self.disable = disable
            if desc and not disable:
                print(f"[INFO] {desc}...")
        
        def __iter__(self):
            for item in self.iterable:
                self.n += 1
                if not self.disable and self.total and self.n % max(1, self.total // 20) == 0:
                    pct = (self.n / self.total) * 100
                    print(f"[INFO] {self.desc}: {self.n}/{self.total} ({pct:.1f}%)")
                yield item
        
        def update(self, n=1):
            self.n += n
        
        def close(self):
            if not self.disable and self.desc:
                print(f"[INFO] {self.desc}: Complete ({self.n} items)")

# File paths
DEFAULT_POLICIES_FILE = "policies_export.csv"
DEFAULT_EVENTS_FILE = "policies_events_export.csv"
DEFAULT_EVENT_INSTANCES_FILE = "event_instances_export.csv"
DEFAULT_OUTPUT_DIR = "output"

GROUP_RELATED = "related-events"
GROUP_PATTERNS = "analytics.correlation-patterns"

# Performance optimizations: Pre-compiled regex patterns
RANKING_SCORE_PATTERN = re.compile(r'"rankingScore"\s*:\s*(\d+)')
EVENT_ID_PATTERN = re.compile(r'"eventid"\s*:\s*"([^"]+)"')
OCCURRENCES_PATTERN = re.compile(r'"occurrences"\s*:\s*(\d+)')

# JSON parsing cache to avoid re-parsing same strings
_JSON_CACHE: Dict[str, Any] = {}
_CACHE_MAX_SIZE = 10000  # Limit cache size to prevent memory issues

def ensure_output_dir(output_dir: str) -> None:
    Path(output_dir).mkdir(parents=True, exist_ok=True)

def _parse_json_cached(json_str: str) -> Optional[Dict]:
    """Parse JSON with caching to avoid re-parsing same strings"""
    if not json_str:
        return None
    
    # Check cache first
    if json_str in _JSON_CACHE:
        return _JSON_CACHE[json_str]
    
    # Clean escaped quotes
    if json_str.startswith('{\\\"'):
        json_str = json_str.replace('\\\"', '"')
    
    try:
        result = json.loads(json_str)
        # Add to cache if not too large
        if len(_JSON_CACHE) < _CACHE_MAX_SIZE:
            _JSON_CACHE[json_str] = result
        return result
    except json.JSONDecodeError:
        return None

def extract_ranking_score(metrics_str: str) -> Optional[int]:
    """Extract ranking score from metrics JSON string (optimized with caching and compiled regex)"""
    try:
        if not metrics_str:
            return None
        
        # Try cached JSON parsing first
        metrics_dict = _parse_json_cached(metrics_str)
        if metrics_dict and isinstance(metrics_dict, dict) and "rankingScore" in metrics_dict:
            return metrics_dict["rankingScore"]
        
        # Fallback to regex with pre-compiled pattern
        m = RANKING_SCORE_PATTERN.search(metrics_str)
        if m:
            return int(m.group(1))
        
        return None
    except Exception:
        return None

def extract_event_ids_from_config(config_str: str) -> List[str]:
    """Extract event IDs from configuration JSON (optimized with caching and compiled regex)"""
    try:
        if not config_str:
            return []
        
        # Try cached JSON parsing first
        cfg = _parse_json_cached(config_str)
        if cfg and "group" in cfg and isinstance(cfg["group"], list):
            return [item.get("eventid") for item in cfg["group"] if "eventid" in item]
        
        # Fallback to regex with pre-compiled pattern
        return EVENT_ID_PATTERN.findall(config_str)
    except Exception:
        return []

def extract_event_occurrences_from_metrics(metrics_str: str) -> Optional[int]:
    """Extract event occurrences from metrics JSON (optimized with caching and compiled regex)"""
    try:
        if not metrics_str:
            return None
        
        # Try cached JSON parsing first
        metrics_dict = _parse_json_cached(metrics_str)
        if metrics_dict and isinstance(metrics_dict, dict) and "col1" in metrics_dict:
            col1 = metrics_dict["col1"]
            if isinstance(col1, dict) and "occurrences" in col1:
                return col1["occurrences"]
        
        # Fallback to regex with pre-compiled pattern
        m = OCCURRENCES_PATTERN.search(metrics_str)
        if m:
            return int(m.group(1))
        
        return None
    except Exception:
        return None

def parse_policy_ids(policy_ids_str: str) -> Set[str]:
    try:
        if policy_ids_str.startswith('{') and policy_ids_str.endswith('}'):
            return ast.literal_eval(policy_ids_str)
        return set()
    except Exception:
        return set()

def normalize_group_id(s: Optional[str]) -> str:
    if s is None:
        return ""
    val = str(s).strip().strip('"').strip("'").lower()
    # Accept common variants / typos
    if "analytics.correlation-pattern" in val or "analytics.temporal-patterns" in val:
        return GROUP_PATTERNS
    if val == "related events":  # seen occasionally
        return GROUP_RELATED
    return val

def guess_indices_by_header(header_row: List[str]) -> Dict[str, int]:
    """
    Map canonical column names -> index, robust to casing/quotes.
    Falls back to positions if header is missing.
    Cassandra COPY order (reference):
      tenantid(0), partitionid(1), policyset(2), policyid(3), type(4),
      configuration(5), dynamic(6), groupid(7), issystem(8), isuser(9),
      metadata(10), metrics(11), resolver(12)
    """
    if not header_row:
        return {
            "tenantid": 0,
            "partitionid": 1,
            "policyset": 2,
            "policyid": 3,
            "type": 4,
            "configuration": 5,
            "groupid": 7,
            "metrics": 11
        }
    norm = [str(h).strip().strip('"').strip("'").lower() for h in header_row]
    idx = {}
    def find(name, default):
        try:
            return norm.index(name)
        except ValueError:
            return default
    # Try to detect whether this is actually a header row
    looks_like_header = any(x in norm for x in ("tenantid","policyid","groupid","configuration"))
    if not looks_like_header:
        # It's actually data; return defaults and the caller will treat this row as data
        return {
            "tenantid": 0, "partitionid": 1, "policyset": 2, "policyid": 3, "type": 4,
            "configuration": 5, "groupid": 7, "metrics": 11, "_has_header": 0
        }
    idx = {
        "tenantid": find("tenantid", 0),
        "partitionid": find("partitionid", 1),
        "policyset": find("policyset", 2),
        "policyid": find("policyid", 3),
        "type": find("type", 4),
        "configuration": find("configuration", 5),
        "groupid": find("groupid", 7),
        "metrics": find("metrics", 11),
        "_has_header": 1
    }
    return idx

def build_event_to_policies(events_data):
    m = defaultdict(list)
    for _, _, event_id, policy_ids in events_data:
        for pid in policy_ids:
            m[event_id].append(pid)
    return m

def write_csv(data: List[Dict[str, Any]], filename: str, fieldnames: Optional[List[str]] = None) -> None:
    if not fieldnames and data:
        fieldnames = list(data[0].keys())
    if not fieldnames:
        fieldnames = ["No data"]
        data = []
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(data)

def _parse_timestamp_hint_value(value: Any) -> Tuple[Optional[int], Optional[str]]:
    """Return comparable epoch-ms value plus display string for timestamp hints."""
    if value is None:
        return None, None

    text = str(value).strip()
    if not text:
        return None, None

    if text.isdigit():
        try:
            raw_num = int(text)
            epoch_ms = raw_num if raw_num > 10**12 else raw_num * 1000
            display = datetime.utcfromtimestamp(epoch_ms / 1000.0).strftime("%Y-%m-%d %H:%M:%S")
            return epoch_ms, display
        except Exception:
            return None, text

    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%SZ",
    ):
        try:
            dt = datetime.strptime(text, fmt)
            epoch_ms = int(dt.timestamp() * 1000)
            display = dt.strftime("%Y-%m-%d %H:%M:%S")
            return epoch_ms, display
        except Exception:
            continue

    return None, text

def write_timestamp_range_hint(
    output_dir: str,
    min_timestamp_ms: Optional[int],
    max_timestamp_ms: Optional[int],
    min_timestamp_display: Optional[str],
    max_timestamp_display: Optional[str]
) -> None:
    hint_path = os.path.join(output_dir, "timestamp_range_hint.json")
    payload = {
        "min": min_timestamp_display,
        "max": max_timestamp_display,
        "minEpochMs": min_timestamp_ms,
        "maxEpochMs": max_timestamp_ms,
        "generated_at": datetime.now().isoformat()
    }
    with open(hint_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(
        f"[INFO] Wrote timestamp range hint: {hint_path} "
        f"min={payload['min']} ({payload['minEpochMs']}) "
        f"max={payload['max']} ({payload['maxEpochMs']})"
    )

# --- streamed writer for event payloads (unchanged behavior for related-events) ---
def write_policy_events_payload_streamed(event_instances_file, needed_event_ids, event_to_policies, policies_map, out_csv_path):
    import re
    DEF_IDX_EVENTID = 2
    DEF_IDX_TIMESTAMP = 1
    DEF_IDX_PAYLOAD = 6
    DEF_IDX_SEVERITY = 7

    def normalize(col: str) -> str:
        return col.strip().strip('"').strip("'").lower()

    def get_indices(header_row):
        if not header_row:
            return (False, DEF_IDX_EVENTID, DEF_IDX_TIMESTAMP, DEF_IDX_PAYLOAD, DEF_IDX_SEVERITY)
        norm = [normalize(h) for h in header_row]
        known = {'tenantid', 'timestamp', 'eventid', 'createtime', 'id', 'lastmodified', 'payload', 'severity'}
        is_header = any(c in known for c in norm)
        if not is_header:
            return (False, DEF_IDX_EVENTID, DEF_IDX_TIMESTAMP, DEF_IDX_PAYLOAD, DEF_IDX_SEVERITY)

        def idx(name, default):
            try: return norm.index(name)
            except ValueError: return default

        return (
            True,
            idx('eventid', DEF_IDX_EVENTID),
            idx('timestamp', DEF_IDX_TIMESTAMP),
            idx('payload', DEF_IDX_PAYLOAD),
            idx('severity', DEF_IDX_SEVERITY),
        )

    # Try to use orjson for better performance, but fall back to standard json
    jloads = json.loads
    jdumps = lambda obj: json.dumps(obj, ensure_ascii=False)
    
    try:
        import orjson
        jloads = orjson.loads
        jdumps = lambda obj: orjson.dumps(obj).decode('utf-8')
        print("[INFO] Using orjson for improved performance")
    except ImportError:
        print("[INFO] orjson not available, using standard json module")

    def safe_load_json(payload_json: str):
        if not payload_json:
            return None
        try:
            return jloads(payload_json)
        except Exception:
            pass
        try:
            if payload_json.startswith('{\\\"'):
                s = payload_json.replace('\\\"', '"').replace('\\\\', '\\')
                return jloads(s)
        except Exception:
            pass
        try:
            if '"' not in payload_json and "'" in payload_json:
                return jloads(payload_json.replace("'", '"'))
        except Exception:
            pass
        try:
            s = re.sub(r'\\(?!["\\/bfnrt]|u[0-9a-fA-F]{4})', '', payload_json)
            return jloads(s)
        except Exception:
            return None

    def fallback_from_event_id(ev_id: str):
        parts = ev_id.split('-')
        resource = parts[1] if len(parts) >= 2 else ''
        ptype    = parts[2] if len(parts) >= 3 else ''
        details  = ' '.join(parts[3:]) if len(parts) >= 4 else ''
        return resource, ptype, details

    fieldnames = [
        'policy_id','ranking_score','event_id','timestamp',
        'payload_details','payload_resource','payload_type',
        'severity','summary','full_payload','note'
    ]

    # Use larger buffer sizes for better I/O performance
    with open(out_csv_path, 'w', newline='', encoding='utf-8', buffering=8*1024*1024) as f_out, \
         open(event_instances_file, 'r', encoding='utf-8', newline='', buffering=8*1024*1024) as f_in:

        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()

        reader = csv.reader(f_in, delimiter=';')
        first = next(reader, None)
        has_header, idx_eventid, idx_timestamp, idx_payload, idx_severity = get_indices(first)

        # Process in batches with optimized size for performance
        batch_size = 5000  # Increased batch size for better performance
        row_count = 0
        batch_count = 0
        
        min_timestamp_ms = None
        max_timestamp_ms = None
        min_timestamp_display = None
        max_timestamp_display = None

        def process_batch(batch):
            nonlocal row_count, min_timestamp_ms, max_timestamp_ms, min_timestamp_display, max_timestamp_display
            rows_processed = 0
            
            # Accumulate rows for batch writing (much faster than individual writes)
            write_buffer = []
            write_buffer_size = 2000  # Increased for better performance
            
            # Process all rows in batch directly (no sub-batching overhead)
            for row in batch:
                if len(row) <= max(idx_eventid, idx_timestamp, idx_payload, idx_severity):
                    continue
                    
                ev_id = row[idx_eventid]
                if ev_id not in needed_event_ids:
                    continue

                ts = row[idx_timestamp] if len(row) > idx_timestamp else ''
                payload_json = row[idx_payload] if len(row) > idx_payload else ''
                ts_epoch_ms, ts_display = _parse_timestamp_hint_value(ts)
                if ts_epoch_ms is not None:
                    if min_timestamp_ms is None or ts_epoch_ms < min_timestamp_ms:
                        min_timestamp_ms = ts_epoch_ms
                        min_timestamp_display = ts_display
                    if max_timestamp_ms is None or ts_epoch_ms > max_timestamp_ms:
                        max_timestamp_ms = ts_epoch_ms
                        max_timestamp_display = ts_display
                severity_col = row[idx_severity] if len(row) > idx_severity else ''
                
                # Use cached JSON parser for better performance
                obj = _parse_json_cached(payload_json)

                if obj is None:
                    resource, ptype, details = fallback_from_event_id(ev_id)
                    summary = ''
                    sev_val = str(severity_col)
                    full_payload_out = payload_json or '{}'
                else:
                    details  = obj.get('details', '')
                    resource = obj.get('resource', '')
                    ptype    = obj.get('type', '')
                    summary  = obj.get('summary', '')
                    sev_val  = str(obj.get('severity', '')) or str(severity_col)
                    full_payload_out = jdumps(obj)

                # Accumulate rows for batch writing
                for pid in event_to_policies.get(ev_id, []):
                    write_buffer.append({
                        'policy_id': pid,
                        'ranking_score': policies_map.get(pid),
                        'event_id': ev_id,
                        'timestamp': ts,
                        'payload_details': details,
                        'payload_resource': resource,
                        'payload_type': ptype,
                        'severity': sev_val,
                        'summary': summary,
                        'full_payload': full_payload_out,
                        'note': ''
                    })
                    
                    # Write buffer when it reaches threshold
                    if len(write_buffer) >= write_buffer_size:
                        writer.writerows(write_buffer)
                        write_buffer = []
                
                rows_processed += 1
            
            # Write any remaining buffered rows
            if write_buffer:
                writer.writerows(write_buffer)
            
            return rows_processed

        # Process the first row if it's not a header
        if first and not has_header:
            current_batch = [first]
        else:
            current_batch = []
        
        # Process rows in batches - optimized for speed
        for row in reader:
            current_batch.append(row)
            
            if len(current_batch) >= batch_size:
                processed = process_batch(current_batch)
                row_count += processed
                batch_count += 1
                print(f"[INFO][{datetime.now().strftime('%H:%M:%S')}] Processed payload batch {batch_count}, total rows: {row_count}")
                
                current_batch = []
                
                # Periodically flush file to ensure data is written
                if batch_count % 10 == 0:
                    f_out.flush()
        
        # Process any remaining rows
        if current_batch:
            processed = process_batch(current_batch)
            row_count += processed
            print(f"[INFO][{datetime.now().strftime('%H:%M:%S')}] Processed final payload batch, total rows: {row_count}")

    return min_timestamp_ms, max_timestamp_ms, min_timestamp_display, max_timestamp_display

def deduplicate_event_instances(input_file: str, output_file: str, needed_event_ids: Set[str]) -> None:
    """
    Deduplicate event_instances_export.csv and filter to only needed event IDs.
    Keeps only unique events that are referenced in the policies.
    """
    print(f"[INFO] Deduplicating event instances from {input_file}...")
    print(f"[INFO] Filtering to {len(needed_event_ids)} needed event IDs...")
    
    seen_events = set()
    kept_count = 0
    duplicate_count = 0
    filtered_count = 0
    
    # Retry logic to handle file locks
    max_retries = 5
    retry_delay = 1.0
    
    for attempt in range(max_retries):
        try:
            with open(output_file, 'w', newline='', encoding='utf-8') as out_f:
                writer = csv.writer(out_f, delimiter=';')
                
                with open(input_file, 'r', newline='', encoding='utf-8') as in_f:
                    reader = csv.DictReader(in_f, delimiter=';')
                    
                    # Write header
                    if reader.fieldnames:
                        writer.writerow(reader.fieldnames)
                    
                    for row in reader:
                        # Try both column name variations
                        event_id = row.get('event_id', '') or row.get('eventid', '')
                        event_id = event_id.strip()
                        
                        if not event_id:
                            continue
                        
                        # Filter: only keep events that are needed
                        if event_id not in needed_event_ids:
                            filtered_count += 1
                            continue
                        
                        # Deduplicate: skip if already seen
                        if event_id in seen_events:
                            duplicate_count += 1
                            continue
                        
                        seen_events.add(event_id)
                        kept_count += 1
                        
                        # Write the row
                        writer.writerow([row.get(field, '') for field in reader.fieldnames])
            
            print(f"[INFO] Deduplication complete:")
            print(f"[INFO]   Kept: {kept_count:,} unique events")
            print(f"[INFO]   Filtered out (not needed): {filtered_count:,}")
            print(f"[INFO]   Duplicates removed: {duplicate_count:,}")
            return
            
        except PermissionError as e:
            if attempt < max_retries - 1:
                print(f"[WARNING] File locked, retrying in {retry_delay}s (attempt {attempt + 1}/{max_retries})...")
                time.sleep(retry_delay)
                retry_delay *= 1.5
            else:
                print(f"[ERROR] Could not write {output_file} after {max_retries} attempts")
                raise

def generate_event_instances_from_events(events_file: str, output_file: str, needed_event_ids: Set[str]) -> None:
    """
    Generate event_instances_export.csv from policies_events_export.csv
    This creates a minimal event instances file with event IDs so the visualization works.
    """
    print(f"[INFO] Generating event instances from {events_file}...")
    
    # Filter to only needed event IDs
    event_ids_to_write = needed_event_ids
    
    print(f"[INFO] Writing {len(event_ids_to_write)} event instances to {output_file}...")
    
    # Retry logic to handle file locks from web interface
    max_retries = 5
    retry_delay = 1.0
    
    for attempt in range(max_retries):
        try:
            with open(output_file, 'w', newline='', encoding='utf-8') as f:
                _write_event_instances(f, event_ids_to_write)
            print(f"[INFO] Successfully created {output_file} with {len(event_ids_to_write)} events")
            return
        except PermissionError as e:
            if attempt < max_retries - 1:
                print(f"[WARNING] File locked, retrying in {retry_delay}s (attempt {attempt + 1}/{max_retries})...")
                time.sleep(retry_delay)
                retry_delay *= 1.5  # Exponential backoff
            else:
                print(f"[ERROR] Could not write {output_file} after {max_retries} attempts")
                raise

def _write_event_instances(f, event_ids_to_write: Set[str]) -> None:
    """Helper function to write event instances to an open file"""
    writer = csv.writer(f, delimiter=';')
    # Write header
    writer.writerow(['tenantid', 'timestamp', 'eventid', 'createtime', 'id', 'lastmodified', 'payload', 'severity'])
    
    # Write minimal event data
    for event_id in sorted(event_ids_to_write):
        # Extract parts from event_id for basic info
        parts = event_id.split('-')
        resource = parts[1] if len(parts) >= 2 else 'unknown'
        event_type = parts[2] if len(parts) >= 3 else 'unknown'
        details = ' '.join(parts[3:]) if len(parts) >= 4 else event_id
        
        # Create minimal payload
        payload = {
            "eventid": event_id,
            "resource": resource,
            "type": event_type,
            "details": details,
            "summary": details,
            "severity": "3"
        }
        
        payload_json = json.dumps(payload)
        
        writer.writerow([
            'default-tenant',  # tenantid
            '1577836800',      # timestamp (2020-01-01)
            event_id,          # eventid
            '1577836800',      # createtime
            event_id,          # id
            '1577836800',      # lastmodified
            payload_json,      # payload
            '3'                # severity
        ])

def generate_static_files(args, output_dir):
    from pathlib import Path
    import importlib
    print("[INFO] Generating static HTML interface...")
    try:
        swi = importlib.import_module("static_web_interface")
    except Exception as e:
        raise RuntimeError(f"Could not import static_web_interface: {e}")
    swi.write_files(Path(output_dir))
    print("[OK] Wrote static UI:",
          Path(output_dir) / 'static_index.html',
          Path(output_dir) / 'static_app.js',
          Path(output_dir) / 'static_styles.css', sep="\n     ")

def main() -> None:
    parser = argparse.ArgumentParser(description="Process policy and event data")
    parser.add_argument("--excel", action="store_true")
    parser.add_argument("--csv", action="store_true")
    parser.add_argument("--web", action="store_true")
    parser.add_argument("--static-web", action="store_true")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--html-file", default="policy_event_viewer.html")
    parser.add_argument("--policies-file", default=DEFAULT_POLICIES_FILE)
    parser.add_argument("--events-file", default=DEFAULT_EVENTS_FILE)
    parser.add_argument("--event-instances-file", default=DEFAULT_EVENT_INSTANCES_FILE)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    if not (args.excel or args.csv or args.web or args.static_web):
        args.csv = True

    policies_file = args.policies_file
    events_file = args.events_file
    event_instances_file = args.event_instances_file
    output_dir = args.output_dir
    ensure_output_dir(output_dir)

    if not os.path.exists(policies_file):
        print(f"Error: Policies file {policies_file} not found.")
        return
    if not os.path.exists(events_file):
        print(f"Error: Events file {events_file} not found.")
        return

    print('[INFO][', datetime.now(), '] Loading policies from:', policies_file)
    start_time = time.time()
    policies_data: List[Dict[str, Any]] = []
    condition_sets_by_policy: Dict[str, Any] = {}

    # ---- Read policies with header/position robustness ----
    with open(policies_file, 'r', encoding='utf-8', buffering=8*1024*1024) as f:  # Increased buffer size
        rdr = csv.reader(f, delimiter=';')
        first = next(rdr, None)
        if not first or len(first) < 6:
            print("Error: policies_export.csv unexpected format.")
            return

        idx = guess_indices_by_header(first)
        has_header = bool(idx.get("_has_header", 0))
        rows_list = list(rdr) if has_header else [first] + list(rdr)
        
        print(f"[INFO] Processing {len(rows_list):,} policy rows...")
        
        group_counter = Counter()
        processed_count = 0
        skipped_count = 0
        
        # Wrap iterator with progress bar
        rows_iter = tqdm(rows_list, desc="Processing policies", disable=False)
        
        for row in rows_iter:
            # Guard for short rows
            if len(row) <= max(idx["policyid"], idx["configuration"], idx["groupid"], idx["type"], idx["metrics"]):
                continue

            tenant_id     = row[idx["tenantid"]]     if idx["tenantid"]     < len(row) else ""
            partition_id  = row[idx["partitionid"]]  if idx["partitionid"]  < len(row) else ""
            policy_set    = row[idx["policyset"]]    if idx["policyset"]    < len(row) else ""
            policy_id     = row[idx["policyid"]]     if idx["policyid"]     < len(row) else ""
            policy_type   = row[idx["type"]]         if idx["type"]         < len(row) else ""
            configuration = row[idx["configuration"]]if idx["configuration"]< len(row) else ""
            group_id_raw  = row[idx["groupid"]]      if idx["groupid"]      < len(row) else ""
            metrics       = row[idx["metrics"]]      if idx["metrics"]      < len(row) else ""

            if not policy_id:
                skipped_count += 1
                continue

            ptype = (policy_type or "").strip().lower()
            g     = normalize_group_id(group_id_raw) or GROUP_RELATED

            # keep:
            # - related-events only when type == correlation (old pipeline)
            # - patterns when type in {correlation, v2policy}
            is_related  = (g == GROUP_RELATED     and ptype == "correlation")
            is_patterns = (g == GROUP_PATTERNS    and ptype in ("correlation", "v2policy"))

            if not (is_related or is_patterns):
                skipped_count += 1
                continue
            
            processed_count += 1

            group_norm = normalize_group_id(group_id_raw) or GROUP_RELATED
            group_counter[group_norm] += 1

            ranking_score     = extract_ranking_score(metrics)
            event_occurrences = extract_event_occurrences_from_metrics(metrics)
            if group_norm == GROUP_RELATED:
                event_ids = extract_event_ids_from_config(configuration)
                policies_data.append({
                    'tenant_id': tenant_id,
                    'partition_id': partition_id,
                    'policy_set': policy_set,
                    'policy_id': policy_id,
                    'policy_type': policy_type,
                    'configuration': configuration,
                    'group_id': group_norm,
                    'ranking_score': round((ranking_score or 0), 0),
                    'event_occurrences': event_occurrences,
                    'event_ids': event_ids
                })

            elif group_norm == GROUP_PATTERNS:
                cfg_str = configuration or ""
                cond_obj: Any
                try:
                    if cfg_str.startswith('{\\\"'):
                        cfg_str = cfg_str.replace('\\\"', '"')
                    cond = json.loads(cfg_str)
                    if isinstance(cond, dict):
                        if "configuration" in cond:
                            cond_obj = cond["configuration"]
                        elif "conditionSets" in cond:
                            cond_obj = cond["conditionSets"]
                        else:
                            cond_obj = cond
                    else:
                        cond_obj = cond
                except Exception:
                    cond_obj = cfg_str or {}

                condition_sets_by_policy[policy_id] = cond_obj
                policies_data.append({
                    'tenant_id': tenant_id,
                    'partition_id': partition_id,
                    'policy_set': policy_set,
                    'policy_id': policy_id,
                    'policy_type': policy_type,
                    'configuration': configuration,
                    'group_id': group_norm,
                    'ranking_score': round((ranking_score or 0), 0),
                    'event_occurrences': event_occurrences,
                    'event_ids': []
                })
            
    # Processing complete - show summary
    elapsed_time = time.time() - start_time
    print(f"\n[INFO] ═══════════════════════════════════════════════════════")
    print(f"[INFO] Policy Processing Complete")
    print(f"[INFO] ───────────────────────────────────────────────────────")
    print(f"[INFO]   Total rows read:      {len(rows_list):>8,}")
    print(f"[INFO]   Policies processed:   {processed_count:>8,}")
    print(f"[INFO]   Rows skipped:         {skipped_count:>8,}")
    print(f"[INFO]   Processing time:      {elapsed_time:>8.1f}s")
    print(f"[INFO]   Rate:                 {len(rows_list)/elapsed_time:>8.0f} rows/sec")
    print(f"[INFO] ═══════════════════════════════════════════════════════\n")
    
    print("[INFO] Group distribution (correlation policies):")
    for g, c in group_counter.most_common():
        print(f"       - {g or '<empty>'}: {c}")

    print('[INFO][', datetime.now(), f'] Loaded {len(policies_data)} policies (both groups).')

    # ---- Events (only for related-events) ----
    print('[INFO][', datetime.now(), '] Loading events from:', events_file)
    start_time = time.time()  # Track event processing time
    related_policy_ids: Set[str] = {p['policy_id'] for p in policies_data if p['group_id'] == GROUP_RELATED}

    # Use dictionary to deduplicate events by event_id (merge policy_ids for same event)
    events_dict: Dict[str, Tuple[str, str, Set[str]]] = {}  # event_id -> (tenant_id, policyset, policy_ids)
    
    with open(events_file, 'r', encoding='utf-8', buffering=8*1024*1024) as f:  # Increased buffer size
        rdr = csv.reader(f, delimiter=';')
        first = next(rdr, None)
        if not first or len(first) < 3:
            print("Error: policies_events_export.csv unexpected format.")
            return
        # header?
        norm = [str(h).strip().strip('"').strip("'").lower() for h in first]
        is_header = any(x in norm for x in ("tenantid","eventid","policies","policyset"))
        
        # Process in batches with optimized size for performance
        batch_size = 20000  # Significantly increased batch size for better performance
        row_count = 0
        batch_count = 0
        
        # Convert to set for O(1) lookups instead of O(n) intersection
        related_policy_ids_set = set(related_policy_ids) if not isinstance(related_policy_ids, set) else related_policy_ids
        
        # Process the first row if it's not a header
        if not is_header and len(first) >= 4:
            tenant_id = first[0]
            policyset = first[1]
            event_id = first[2]
            policy_ids = parse_policy_ids(first[3])
            # Use set intersection - much faster
            policy_ids = policy_ids & related_policy_ids_set
            if policy_ids:
                if event_id in events_dict:
                    # Merge policy_ids for duplicate event
                    events_dict[event_id] = (tenant_id, policyset, events_dict[event_id][2] | policy_ids)
                else:
                    events_dict[event_id] = (tenant_id, policyset, policy_ids)
            row_count += 1
        
        # Process rows directly without intermediate batch list
        print_interval = 50000  # Print every 50K rows instead of every 20K
        for row in rdr:
            if len(row) < 4:
                continue
            
            tenant_id = row[0]
            policyset = row[1]
            event_id = row[2]
            policy_ids = parse_policy_ids(row[3])
            # Use set intersection - much faster
            policy_ids = policy_ids & related_policy_ids_set
            if policy_ids:
                if event_id in events_dict:
                    # Merge policy_ids for duplicate event
                    events_dict[event_id] = (tenant_id, policyset, events_dict[event_id][2] | policy_ids)
                else:
                    events_dict[event_id] = (tenant_id, policyset, policy_ids)
            
            row_count += 1
            
            # Print progress less frequently
            if row_count % print_interval == 0:
                batch_count += 1
                elapsed = time.time() - start_time if 'start_time' in locals() else 0
                rate = row_count / elapsed if elapsed > 0 else 0
                print(f"[INFO][{datetime.now().strftime('%H:%M:%S')}] Processed {row_count:,} event rows ({len(events_dict):,} unique events) - {rate:,.0f} rows/sec")
        
    # Convert deduplicated dictionary to list
    events_data: List[Tuple[str, str, str, Set[str]]] = [
        (tenant_id, policyset, event_id, policy_ids)
        for event_id, (tenant_id, policyset, policy_ids) in events_dict.items()
    ]
    
    print(f"[INFO][{datetime.now().strftime('%H:%M:%S')}] Deduplication complete:")
    print(f"[INFO]   Total rows processed: {row_count:,}")
    print(f"[INFO]   Unique events kept: {len(events_data):,}")
    print(f"[INFO]   Duplicates removed: {row_count - len(events_data):,}")

    print('[INFO][', datetime.now(), f'] Events rows kept (related-events): {len(events_data)}')

    # Build helpers for payload CSV
    needed_event_ids: Set[str] = {e for _, _, e, _ in events_data}
    event_to_policies = defaultdict(list)
    for _, _, event_id, pids in events_data:
        for pid in pids:
            event_to_policies[event_id].append(pid)

    # Write policy_events_payload.csv (related-events only)
    ensure_output_dir(output_dir)
    
    # Clean up existing output files before processing
    # NOTE: Do NOT delete event_instances_export.csv - it may contain real data
    print('[INFO][', datetime.now(), '] Cleaning up existing output files...')
    output_files = [
        "policy_events_payload.csv",
        "policy_summary.csv",
        "events_detail.csv",
        # "event_instances_export.csv",  # KEEP THIS - may have real event data
        "condition_sets_by_policy.json",
        "timestamp_range_hint.json",
        "last_update.json",
        "data_updated.signal",
        "policy_events.db",
        "policy_events.db-wal",
        "policy_events.db-shm"
    ]
    
    for filename in output_files:
        filepath = os.path.join(output_dir, filename)
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
                print(f'[INFO]   Removed: {filename}')
            except Exception as e:
                print(f'[WARNING]   Could not remove {filename}: {e}')
    os.makedirs(output_dir,exist_ok=True)
    
    policy_events_payload_csv = os.path.join(output_dir, "policy_events_payload.csv")
    event_instances_file = os.path.join(output_dir, "event_instances_export.csv")
    print('[INFO][', datetime.now(), '] Writing policies events payload to:', policy_events_payload_csv)
    
    # Check for real event_instances_export.csv in root directory first
    root_event_instances = "event_instances_export.csv"
    if os.path.exists(root_event_instances):
        print(f'[INFO] Found real event instances file in root directory')
        print(f'[INFO] Deduplicating and filtering to needed events...')
        deduplicate_event_instances(root_event_instances, event_instances_file, needed_event_ids)
    elif not os.path.exists(event_instances_file):
        print(f'[INFO] Event instances file not found, auto-generating minimal data from events...')
        generate_event_instances_from_events(events_file, event_instances_file, needed_event_ids)
    
    if os.path.exists(event_instances_file):
        min_timestamp_ms, max_timestamp_ms, min_timestamp_display, max_timestamp_display = write_policy_events_payload_streamed(
            event_instances_file,
            needed_event_ids,
            event_to_policies,
            {p['policy_id']: p['ranking_score'] for p in policies_data},
            policy_events_payload_csv
        )
    else:
        print('[ERROR] Failed to generate or find event instances file')
        min_timestamp_ms, max_timestamp_ms = None, None
        min_timestamp_display, max_timestamp_display = None, None
        write_csv([{
            'policy_id': p['policy_id'], 'ranking_score': p['ranking_score'],'event_occurrences':p['event_occurrences'],
            'event_id':'','timestamp':'','payload_details':'','payload_resource':'',
            'payload_type':'','severity':'','summary':'','full_payload':'{}','note':'No event_instances file'
        } for p in policies_data if p['group_id']==GROUP_RELATED], policy_events_payload_csv)

    write_timestamp_range_hint(
        output_dir,
        min_timestamp_ms,
        max_timestamp_ms,
        min_timestamp_display,
        max_timestamp_display
    )

    # ----- policy_summary.csv (both groups) -----
    print('[INFO][', datetime.now(), '] Building policy summary...')
    policy_summary: List[Dict[str, Any]] = []
    events_per_policy = defaultdict(int)
    for _, _, _, pids in events_data:
        for pid in pids:
            events_per_policy[pid] += 1

    for p in policies_data:
        pid = p['policy_id']
        policy_summary.append({
            'policy_id': pid,
            'ranking_score': p['ranking_score'],
            'event_count': events_per_policy.get(pid, 0),
            'event_occurrences': p['event_occurrences'],
            'policy_type': p['policy_type'],
            'policy_set': p['policy_set'],
            'group_id': p['group_id'],
            'event_ids_in_config': ", ".join(p['event_ids']) if p['event_ids'] else ""
        })

    policy_summary.sort(key=lambda x: (x['ranking_score'] or 0), reverse=True)

    policy_summary_csv = os.path.join(output_dir, "policy_summary.csv")
    events_detail_csv  = os.path.join(output_dir, "events_detail.csv")

    # Write policy summary first
    print('[INFO][', datetime.now(), '] Writing policy summary to', output_dir)
    write_csv(policy_summary, policy_summary_csv)

    # Stream events_detail directly to CSV to avoid memory issues with large datasets
    # Use deduplicated events from event_instances_export.csv instead of raw events_data
    print('[INFO][', datetime.now(), '] Writing events detail from deduplicated event instances (streaming for memory efficiency)...')
    policy_ranking_map = {p['policy_id']: p['ranking_score'] for p in policies_data}
    
    # Read event IDs from event_instances_export.csv (deduplicated)
    deduplicated_event_ids = set()
    if os.path.exists(event_instances_file):
        print(f'[INFO] Reading deduplicated event IDs from {event_instances_file}...')
        with open(event_instances_file, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f, delimiter=';')
            for row in reader:
                event_id = row.get('eventid', '').strip()
                if event_id:
                    deduplicated_event_ids.add(event_id)
        print(f'[INFO] Found {len(deduplicated_event_ids)} deduplicated events')
    else:
        print('[WARNING] event_instances_export.csv not found, using all events from events_data')
        deduplicated_event_ids = {e for _, _, e, _ in events_data}
    
    with open(events_detail_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['event_id', 'policy_id', 'ranking_score'])
        writer.writeheader()
        
        # Write in batches to reduce memory usage
        batch = []
        batch_size = 10000
        row_count = 0
        
        # Only write events that exist in the deduplicated event_instances file
        for _, _, event_id, pids in events_data:
            if event_id in deduplicated_event_ids:
                for pid in pids:
                    rs = policy_ranking_map.get(pid)
                    batch.append({'event_id': event_id, 'policy_id': pid, 'ranking_score': rs})
                    row_count += 1
                    
                    if len(batch) >= batch_size:
                        writer.writerows(batch)
                        batch = []
                        
                        # Progress indicator for large datasets
                        if row_count % 100000 == 0:
                            print(f'[INFO][{datetime.now().strftime("%H:%M:%S")}] Written {row_count} events detail rows...')
        
        # Write remaining rows
        if batch:
            writer.writerows(batch)
        
        print(f'[INFO][{datetime.now().strftime("%H:%M:%S")}] Completed events detail: {row_count} total rows (from {len(deduplicated_event_ids)} deduplicated events)')

    # NEW: write patterns map for the UIs
    cond_path = os.path.join(output_dir, "condition_sets_by_policy.json")
    with open(cond_path, "w", encoding="utf-8") as f:
        json.dump(condition_sets_by_policy, f, ensure_ascii=False, indent=2)
    print("[INFO] Wrote condition sets:", cond_path, f"({len(condition_sets_by_policy)} policies)")

    # Write signal files for auto-refresh detection
    print('[INFO][', datetime.now(), '] Writing signal files for auto-refresh...')
    
    # Create last_update.json with version info
    last_update_path = os.path.join(output_dir, "last_update.json")
    update_info = {
        "last_update_iso": datetime.now().isoformat(),
        "version": int(datetime.now().timestamp()),
        "update_count": int(datetime.now().timestamp()),
        "policies_count": len(policy_summary),
        "events_count": len(events_data),
        "events_detail_count": row_count
    }
    with open(last_update_path, "w", encoding="utf-8") as f:
        json.dump(update_info, f, indent=2)
    print(f"[INFO] Wrote last_update.json: version={update_info['version']}")
    
    # Touch signal file to trigger reload
    signal_path = os.path.join(output_dir, "data_updated.signal")
    Path(signal_path).touch()
    print(f"[INFO] Touched signal file: {signal_path}")

    if args.web:
        try:
            import web_interface
            print("\nLaunching web interface...")
            web_interface.start_web_server(output_dir, args.port)
        except ImportError as e:
            print(f"\nError: Could not launch web interface: {e}. Ensure web_interface.py is available.")

    if args.static_web:
        generate_static_files(args, output_dir)

if __name__ == "__main__":
    main()
