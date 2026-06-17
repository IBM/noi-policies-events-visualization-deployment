#!/usr/bin/env python3
#
# Copyright IBM Corp. 2024 - 2026
# SPDX-License-Identifier: Apache-2.0
#
"""
Generate synthetic policy export CSVs that mimic policies_export.csv and
policies_events_export.csv while preserving policy -> event relationships.

New:
  --pattern-policies-template  Optional policy export containing pattern policy examples.
  --pattern-policy-count       Add this many pattern-style policies.
  --pattern-policy-ratio       Add pattern-style policies as a ratio of --num-policies.
  --event-instances-template   Generate a matching event details/instances export.

Defaults:
  --num-policies 10
  --min-events 3
  --max-events 100

Example:
  python generate_policy_exports.py \
    --num-policies 50000 \
    --max-events 100 \
    --pattern-policies-template "policies_export(2).csv" \
    --pattern-policy-ratio 0.10 \
    --output-prefix policies_export_test
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
import time
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import pandas as pd


def log(message: str) -> None:
    print(message, flush=True)


def read_export_csv(path: Path) -> pd.DataFrame:
    """Read the semicolon export files with backslash-escaped JSON fields."""
    return pd.read_csv(
        path,
        sep=";",
        dtype=str,
        keep_default_na=False,
        escapechar="\\",
        quoting=csv.QUOTE_NONE,
        engine="python",
    )


def write_export_csv(df: pd.DataFrame, path: Path) -> None:
    """Write files in the same semicolon + backslash-escaped style."""
    def clean(value: object) -> str:
        text = "" if value is None else str(value)
        return text.replace('"', r'\"')

    with path.open("w", encoding="utf-8", newline="") as fh:
        fh.write(";".join(df.columns) + "\n")
        total = len(df)
        start = time.time()
        for idx, (_, row) in enumerate(df.iterrows(), start=1):
            fh.write(";".join(clean(row.get(col, "")) for col in df.columns) + "\n")
            if total >= 10000 and (idx == 1 or idx % 50000 == 0 or idx == total):
                elapsed = time.time() - start
                rate = idx / elapsed if elapsed > 0 else 0
                log(f"Writing {path.name}: {idx:,}/{total:,} ({idx / total:.0%}) | {rate:,.1f} rows/sec")


def json_loads_safe(value: str) -> dict:
    if not value:
        return {}
    try:
        loaded = json.loads(value)
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        return {}


def parse_event_ids_from_policy_config(configuration: str) -> List[str]:
    obj = json_loads_safe(configuration)
    return [item.get("eventid", "") for item in obj.get("group", []) if isinstance(item, dict) and item.get("eventid")]


def format_policy_set(policy_ids: List[str]) -> str:
    """Return the policy set string in the same style as the sample export."""
    if not policy_ids:
        return ""
    return "{" + ", ".join(f"'{pid}'" for pid in sorted(set(policy_ids))) + "}"


def make_event_id(index: int, style: str, seed_text: str) -> str:
    """Create event IDs that resemble the observed formats."""
    digest = hashlib.sha1(f"{seed_text}-{index}".encode()).hexdigest()
    if style == "finalised":
        base_ts = int(time.time()) - random.randint(10_000, 2_000_000)
        ckey_ts = base_ts - random.randint(60, 600)
        circuit = random.randint(1, 8)
        return f"FINALISED:{base_ts}CKEYP:{ckey_ts}:S:[{digest}]:CustomParent:Circuit{circuit}"

    if style == "pattern_text":
        summaries = [
            "Disk space high usage of critical level",
            "Weekly BackUp Started on hr server",
            "Temperature High on Db2 rack",
            "Temperature Critical on Db2 rack",
            "Fan failed in datacentre rack",
            "CPU utilization above threshold",
            "Memory usage high on application server",
            "Interface down on core router",
            "Packet loss detected on transport circuit",
        ]
        nodes = [
            "ibmdbserver01", "ibmdbserver02", "ibmdbserver03",
            "rack99z.ldn.ibm.com", "regionalstorage", "remotestorage",
            "core-router-01", "app-server-04",
        ]
        return f"{random.choice(summaries)} {random.choice(nodes)} {digest[:8]}"

    # Compact NOI-like synthetic id.
    a = random.randint(1, 99)
    b = random.randint(1, 99)
    suffix = random.choice(["g", "g-c", "g-11", "t-g-c", "z-g-c", "l-g"])
    return f"NOI_ID_pc_{a}-{b}-{digest[:1]}-{suffix}"


def pick_template_dict(template_rows: List[dict], prefer_group: bool = True) -> dict:
    if prefer_group:
        candidates = [r for r in template_rows if parse_event_ids_from_policy_config(r.get("configuration", ""))]
        if candidates:
            return random.choice(candidates).copy()
    return random.choice(template_rows).copy()


def update_configuration(template_config: str, event_ids: List[str], deployed: bool = True) -> str:
    obj = json_loads_safe(template_config)
    obj["deployed"] = deployed
    obj["group"] = [{"eventid": eid} for eid in event_ids]
    obj["ghash"] = hashlib.sha1("|".join(event_ids).encode()).hexdigest()
    return json.dumps(obj, separators=(",", ":"))


def update_metadata(template_metadata: str) -> str:
    now_sec = int(time.time())
    now_ms = now_sec * 1000
    obj = json_loads_safe(template_metadata)

    obj.setdefault("model", {})
    obj["model"].setdefault("analytic", "related-events")
    obj["model"].setdefault("version", "1.0")
    obj["model"]["trainingTimestamp"] = now_sec
    obj["model"]["trainingWindowEnd"] = now_ms
    obj["model"]["trainingWindowStart"] = now_ms - 90 * 24 * 60 * 60 * 1000

    obj.setdefault("statedata", {})
    obj["statedata"].setdefault("state", "hidden")
    obj["statedata"].setdefault("locked", False)
    obj["statedata"].setdefault("userId", "smadmin")
    obj["statedata"]["timestamp"] = now_ms
    return json.dumps(obj, separators=(",", ":"))


def update_metrics(template_metrics: str, event_count: int) -> str:
    obj = json_loads_safe(template_metrics)

    severity = random.choice([30, 40, 50, 60])
    occurrences = random.randint(1, max(1, min(10, event_count)))
    age = round(random.uniform(0, 30), 6)
    obj["col1"] = {"occurrences": occurrences, "maxOccurrences": max(occurrences, random.randint(5, 15))}
    obj["col2"] = {"age": age, "maxAge": max(age, round(random.uniform(age, age + 25), 6))}
    obj["col3"] = {"severity": severity, "maxSeverity": max(severity, 60)}
    obj["col4"] = {"size": event_count, "maxSize": max(event_count, random.randint(event_count, max(event_count, 100)))}
    obj["rankingScore"] = round(random.uniform(35, 95), 4)
    obj["lastOccurrence"] = int(time.time()) - random.randint(0, 30 * 24 * 60 * 60)
    return json.dumps(obj, separators=(",", ":"))


def update_pattern_configuration(template_config: str, event_ids: List[str], groupid: str, deployed: bool = True) -> str:
    """Update pattern policy configuration while preserving the template shape."""
    obj = json_loads_safe(template_config)
    if not obj:
        # Fallback pattern config.
        obj = {"deployed": deployed}
    else:
        obj["deployed"] = deployed

    # Classic pattern/enrich exports have a group list.
    if "group" in obj or groupid in {"seasonality", "related-events"}:
        obj["group"] = [{"eventid": eid} for eid in event_ids]
        obj["ghash"] = hashlib.sha1("|".join(event_ids).encode()).hexdigest()

    # v2 temporal-pattern policies have nested actions with patternId values.
    # Keep the structure but randomize patternId values so the generated rows are distinct.
    config_text = json.dumps(obj, separators=(",", ":"))
    for old_id in set(re.findall(r'"patternId":"([^"]+)"', config_text)):
        new_id = str(random.randint(-2_000_000_000, 2_000_000_000))
        config_text = config_text.replace(f'"patternId":"{old_id}"', f'"patternId":"{new_id}"')
    return config_text


def update_pattern_metadata(template_metadata: str, groupid: str) -> str:
    """Keep pattern metadata shape when parseable; otherwise build a valid metadata object."""
    now_sec = int(time.time())
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now_sec))
    obj = json_loads_safe(template_metadata)

    if not obj:
        analytic = "seasonality" if groupid == "seasonality" else groupid
        obj = {
            "createdBy": {
                "entityType": "analytics",
                "entityId": "system",
                "entityMetadata": {"trainingTimestamp": now_iso},
            },
            "lastUpdatedBy": {"entityType": "analytics", "entityId": "system"},
            "lastUpdated": now_iso,
            "created": now_iso,
            "statedata": {"locked": False, "state": "active"},
            "model": {"analytic": analytic, "trainingTimestamp": now_iso},
        }
    else:
        obj.setdefault("model", {})
        if groupid and "analytic" not in obj["model"]:
            obj["model"]["analytic"] = groupid
        obj["model"]["trainingTimestamp"] = now_iso if groupid == "analytics.temporal-patterns" else now_sec
        obj.setdefault("statedata", {})
        obj["statedata"].setdefault("locked", False)
        obj["statedata"].setdefault("state", "active")
        obj["lastUpdated"] = now_iso

    return json.dumps(obj, separators=(",", ":"))


def update_pattern_metrics(template_metrics: str, event_count: int, groupid: str) -> str:
    obj = json_loads_safe(template_metrics)
    if groupid == "analytics.temporal-patterns":
        obj["col1"] = {
            "numGroupOccurrences": random.randint(3, 10),
            "maxNumGroupOccurrences": random.randint(10, 20),
        }
        obj["rankingScore"] = round(random.uniform(0.5, 1.0), 4)
    elif groupid == "seasonality":
        occurrences = random.randint(3, 10)
        obj["col1"] = {"occurrences": occurrences, "maxOccurrences": max(occurrences, random.randint(6, 12))}
        obj["col2"] = {"age": round(random.uniform(0, 1), 6), "maxAge": round(random.uniform(1, 3), 6)}
        obj["col3"] = {"severity": random.choice([30, 40, 50, 60]), "maxSeverity": 60}
        obj["col4"] = {"timeWindowCount": 1, "maxTimeWindowCount": random.randint(1, 3)}
        obj["rankingScore"] = round(random.uniform(40, 99), 2)
    else:
        obj = json_loads_safe(update_metrics(template_metrics, event_count))
    return json.dumps(obj, separators=(",", ":"))


def get_policy_occurrence_count(policy_row: dict) -> int:
    """Return how many historical occurrences should exist for each event in this policy."""
    metrics = json_loads_safe(policy_row.get("metrics", ""))
    col1 = metrics.get("col1", {}) if isinstance(metrics, dict) else {}
    candidates = []
    if isinstance(col1, dict):
        candidates.extend([
            col1.get("occurrences"),
            col1.get("numGroupOccurrences"),
            col1.get("maxOccurrences"),
            col1.get("maxNumGroupOccurrences"),
        ])
    for value in candidates:
        try:
            parsed = int(float(value))
            if parsed > 0:
                return parsed
        except Exception:
            continue
    return 1


def register_event_instance_requirements(policy_row: dict, event_instance_requirements: Dict[str, int]) -> None:
    """Ensure event instance output can satisfy events * occurrences for each policy."""
    event_ids = parse_event_ids_from_policy_config(policy_row.get("configuration", ""))
    if not event_ids:
        return
    occurrences = get_policy_occurrence_count(policy_row)
    for event_id in event_ids:
        event_instance_requirements[event_id] += occurrences


def format_export_timestamp(epoch_ms: int) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(epoch_ms / 1000)) + ".000+0000"


def daykey_ms(epoch_ms: int) -> int:
    # UTC midnight for the event timestamp.
    seconds = epoch_ms // 1000
    day_start = seconds - (seconds % 86400)
    return day_start * 1000


def safe_json_payload(value: str) -> dict:
    loaded = json_loads_safe(value)
    return loaded if loaded else {}


def make_event_summary(event_id: str) -> str:
    # Event ids are often already descriptive. Keep finalised ids compact in the payload summary.
    if event_id.startswith("FINALISED:"):
        return "Synthetic correlated event " + hashlib.sha1(event_id.encode()).hexdigest()[:10]
    return event_id[:240]


def update_event_instance_payload(template_payload: str, event_id: str, instance_id: str, severity: int, timestamp_ms: int) -> str:
    payload = safe_json_payload(template_payload)
    summary = make_event_summary(event_id)
    host_seed = hashlib.sha1(event_id.encode()).hexdigest()[:6]
    host = f"node-hostname-synth-{host_seed}"

    payload["id"] = instance_id
    payload["eventid"] = event_id
    payload["severity"] = severity
    payload["timestamp"] = timestamp_ms
    payload["summary"] = summary
    payload["resolution"] = bool(payload.get("resolution", False))

    payload.setdefault("sender", {"service": "ITM", "name": "Probe", "type": "Netcool/OMNIbus"})
    payload.setdefault("type", {"eventType": "Synthetic-Monitor:Synthetic-Monitor"})

    resource = payload.setdefault("resource", {})
    if isinstance(resource, dict):
        resource["name"] = host
        resource["hostname"] = host
        resource["node"] = host
        resource.setdefault("type", "unknown")
        resource["NodeAlias"] = host.replace("-", " ").title()

    details = payload.setdefault("details", {})
    if isinstance(details, dict):
        details["FirstOccurrence"] = timestamp_ms
        details["LastOccurrence"] = timestamp_ms
        details["lastmodified"] = timestamp_ms
        details["deletedat"] = timestamp_ms
        details["AlertKey"] = summary[:255]
        details["Node"] = host
        details["Summary"] = summary
        details["Severity"] = severity
        details["originalseverity"] = severity
        details["ServerSerial"] = int(instance_id.split(":")[-1]) if ":" in instance_id and instance_id.split(":")[-1].isdigit() else random.randint(100000, 999999)
        details["Tally"] = max(1, int(details.get("Tally", 1) or 1))

    return json.dumps(payload, separators=(",", ":"))


def generate_event_instance_rows(
    event_instances_template: Path | None,
    event_instance_requirements: Dict[str, int],
    output_prefix: str,
    progress_every: int,
) -> Tuple[pd.DataFrame, Path]:
    # Load or create event instances template
    if event_instances_template and event_instances_template.exists():
        instances_df = read_export_csv(event_instances_template)
    else:
        if event_instances_template:
            log(f"Event instances template {event_instances_template} not found, using built-in defaults...")
        else:
            log("No event instances template specified, using built-in defaults...")
        instances_df = create_default_event_instances_template()
    required_cols = ["subscription", "daykey", "event_id", "ftimestamp", "id", "ltimestamp", "payload", "severity"]
    missing = [col for col in required_cols if col not in instances_df.columns]
    if missing:
        raise ValueError(f"Missing columns in event instances template: {missing}")

    instance_columns = list(instances_df.columns)
    template_rows = instances_df.to_dict("records")
    subscription = instances_df["subscription"].iloc[0] if not instances_df.empty else "default_subscription"

    total_rows = sum(event_instance_requirements.values())
    log(f"Building event-instance rows for {len(event_instance_requirements):,} events and {total_rows:,} required occurrences...")

    rows: List[dict] = []
    start = time.time()
    row_index = 0
    base_now_ms = int(time.time() * 1000)

    for event_id, required_count in sorted(event_instance_requirements.items()):
        for occurrence_index in range(1, required_count + 1):
            row_index += 1
            template = random.choice(template_rows).copy() if template_rows else {col: "" for col in instance_columns}
            # Spread timestamps backward so daykey/first/last look realistic.
            timestamp_ms = base_now_ms - random.randint(0, 365 * 24 * 60 * 60 * 1000)
            timestamp_ms += occurrence_index * random.randint(1000, 60000)
            severity_int = random.choice([3, 4, 5, 6])
            instance_id = f"AGG_P:{random.randint(100000, 9999999)}"

            row = {col: template.get(col, "") for col in instance_columns}
            row["subscription"] = subscription
            row["daykey"] = str(daykey_ms(timestamp_ms))
            row["event_id"] = event_id
            row["ftimestamp"] = format_export_timestamp(timestamp_ms)
            row["id"] = instance_id
            row["ltimestamp"] = format_export_timestamp(timestamp_ms)
            row["payload"] = update_event_instance_payload(template.get("payload", ""), event_id, instance_id, severity_int, timestamp_ms)
            row["severity"] = "{" + str(severity_int) + "}"
            rows.append(row)

            if total_rows >= 10000 and (row_index == 1 or row_index % max(1, progress_every * 100) == 0 or row_index == total_rows):
                elapsed = time.time() - start
                rate = row_index / elapsed if elapsed > 0 else 0
                log(
                    f"Event-instance rows built: {row_index:,}/{total_rows:,} "
                    f"({row_index / total_rows:.0%}) | {rate:,.1f} rows/sec"
                )

    out_path = Path(f"{output_prefix}_event_instances_export.csv")
    return pd.DataFrame(rows, columns=instance_columns), out_path


def choose_pattern_event_count(template: dict) -> int:
    """Use the template's group size when present; seasonality is normally one event."""
    original_events = parse_event_ids_from_policy_config(template.get("configuration", ""))
    if original_events:
        return max(1, len(original_events))
    groupid = template.get("groupid", "")
    if groupid == "seasonality":
        return 1
    if groupid == "analytics.temporal-patterns":
        return 0
    return 0


def generate_standard_policy(
    policies_columns: List[str],
    template_rows: List[dict],
    min_events: int,
    max_events: int,
    event_to_policies: Dict[str, List[str]],
) -> dict:
    template = pick_template_dict(template_rows, prefer_group=True)
    policy_id = str(uuid.uuid1())
    event_count = random.randint(min_events, max_events)
    style = random.choice(["noi", "finalised"])
    event_ids = [make_event_id(i, style, policy_id) for i in range(event_count)]

    template["policyid"] = policy_id
    template["type"] = template.get("type") or "correlation"
    template["configuration"] = update_configuration(template.get("configuration", ""), event_ids)
    template["metadata"] = update_metadata(template.get("metadata", ""))
    template["metrics"] = update_metrics(template.get("metrics", ""), event_count)
    template["groupid"] = template.get("groupid") or "related-events"
    template["isuser"] = template.get("isuser") or "True"

    for event_id in event_ids:
        event_to_policies[event_id].append(policy_id)

    return {col: template.get(col, "") for col in policies_columns}


def generate_pattern_policy(
    policies_columns: List[str],
    pattern_rows: List[dict],
    event_to_policies: Dict[str, List[str]],
    tenantid: str,
    policyset: str,
) -> dict:
    template = pick_template_dict(pattern_rows, prefer_group=False)
    policy_id = str(uuid.uuid1())
    groupid = template.get("groupid", "")
    event_count = choose_pattern_event_count(template)

    event_ids: List[str] = []
    if event_count > 0:
        event_ids = [make_event_id(i, "pattern_text", policy_id) for i in range(event_count)]

    template["tenantid"] = template.get("tenantid") or tenantid
    template["policyset"] = template.get("policyset") or policyset
    template["policyid"] = policy_id
    template["configuration"] = update_pattern_configuration(template.get("configuration", ""), event_ids, groupid)
    template["metadata"] = update_pattern_metadata(template.get("metadata", ""), groupid)
    template["metrics"] = update_pattern_metrics(template.get("metrics", ""), event_count, groupid)

    for event_id in event_ids:
        event_to_policies[event_id].append(policy_id)

    return {col: template.get(col, "") for col in policies_columns}


def create_default_policy_template(deployed: bool = True) -> pd.DataFrame:
    """Create a minimal default policy template when no template file is provided."""
    return pd.DataFrame([{
        "tenantid": "cfd95b7e-3bc7-4006-a4a8-a73a79c71255",
        "partitionid": "0",
        "policyset": "-",
        "policyid": "00000000-0000-0000-0000-000000000000",
        "type": "correlation",
        "configuration": json.dumps({
            "deployed": deployed,
            "group": [],
            "ghash": ""
        }, separators=(",", ":")),
        "dynamic": "False",
        "groupid": "related-events",
        "issystem": "False",
        "isuser": "True",
        "metadata": json.dumps({
            "model": {"analytic": "related-events", "version": "1.0"},
            "statedata": {"state": "hidden", "locked": False, "userId": "smadmin"}
        }, separators=(",", ":")),
        "metrics": json.dumps({
            "col1": {"occurrences": 5, "maxOccurrences": 10},
            "col2": {"age": 1.5, "maxAge": 10.0},
            "col3": {"severity": 50, "maxSeverity": 60},
            "col4": {"size": 10, "maxSize": 50},
            "rankingScore": 75.0
        }, separators=(",", ":")),
        "resolver": "",
    }])


def create_default_events_template() -> pd.DataFrame:
    """Create a minimal default events template when no template file is provided."""
    return pd.DataFrame(columns=["tenantid", "policyset", "eventid", "policies"])


def create_default_event_instances_template() -> pd.DataFrame:
    """Create a minimal default event instances template when no template file is provided."""
    return pd.DataFrame([{
        "subscription": "default_subscription",
        "daykey": "0",
        "event_id": "",
        "ftimestamp": "2024-01-01 00:00:00.000+0000",
        "id": "AGG_P:0",
        "ltimestamp": "2024-01-01 00:00:00.000+0000",
        "payload": json.dumps({
            "id": "",
            "eventid": "",
            "severity": 5,
            "timestamp": 0,
            "summary": "",
            "resolution": False,
            "sender": {"service": "ITM", "name": "Probe", "type": "Netcool/OMNIbus"},
            "type": {"eventType": "Synthetic-Monitor:Synthetic-Monitor"},
            "resource": {"name": "", "hostname": "", "node": "", "type": "unknown"},
            "details": {}
        }, separators=(",", ":")),
        "severity": "{5}",
    }])


def create_default_pattern_policy_templates(deployed: bool = True) -> List[dict]:
    """Create default pattern policy templates based on real examples from policies_export.csv."""
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    
    # Seasonality policy template (type: enrich, groupid: seasonality)
    seasonality_policy = {
        "tenantid": "cfd95b7e-3bc7-4006-a4a8-a73a79c71255",
        "partitionid": "0",
        "policyset": "-",
        "policyid": "00000000-0000-0000-0000-000000000001",
        "type": "enrich",
        "configuration": json.dumps({
            "deployed": deployed,
            "group": [],
            "ghash": ""
        }, separators=(",", ":")),
        "dynamic": "",
        "groupid": "seasonality",
        "issystem": "True",
        "isuser": "",
        "metadata": json.dumps({
            "createdBy": {
                "entityType": "analytics",
                "entityId": "system",
                "entityMetadata": {"trainingTimestamp": now_iso}
            },
            "lastUpdatedBy": {"entityType": "analytics", "entityId": "system"},
            "lastUpdated": now_iso,
            "created": now_iso,
            "statedata": {"locked": False, "state": "active"},
            "model": {"analytic": "seasonality", "trainingTimestamp": now_iso}
        }, separators=(",", ":")),
        "metrics": json.dumps({
            "col1": {"occurrences": 5, "maxOccurrences": 10},
            "col2": {"age": 0.5, "maxAge": 2.0},
            "col3": {"severity": 50, "maxSeverity": 60},
            "col4": {"timeWindowCount": 1, "maxTimeWindowCount": 2},
            "rankingScore": 75.5
        }, separators=(",", ":")),
        "resolver": json.dumps({
            "static": True,
            "stub": "com.ibm.itsm.inference.resolver.SeasonalityResolver",
            "version": "0.0.1"
        }, separators=(",", ":")),
    }
    
    # Temporal-patterns policy template (type: v2policy, groupid: analytics.temporal-patterns)
    temporal_policy = {
        "tenantid": "cfd95b7e-3bc7-4006-a4a8-a73a79c71255",
        "partitionid": "9",
        "policyset": now_iso,
        "policyid": "00000000-0000-0000-0000-000000000002",
        "type": "v2policy",
        "configuration": json.dumps({
            "api": "policy/2.0.0",
            "executionOrder": 1,
            "trigger": {
                "type": ["alert.create", "alert.update"],
                "conditions": {
                    "operator": "||",
                    "ignoreValues": ["null", "nan", "nil", "na", "undefined", "empty", "unknown", "0"],
                    "value": [{
                        "operator": "&&",
                        "value": [
                            {"field": "alert.type.eventType", "operator": "==", "value": "Synthetic-Monitor:Synthetic-Monitor"},
                            {"field": "alert.resource.node", "operator": "==", "allOf": ["{{alert.resource.hostname}}", "{{alert.resource.NodeAlias}}", "{{alert.resource.name}}"]}
                        ],
                        "actions": [{
                            "actionType": "alert.group",
                            "ref": "analytics.correlation-patterns",
                            "parameters": {
                                "resourceFields": ["alert.resource.node", "alert.resource.hostname", "alert.resource.NodeAlias", "alert.resource.name"],
                                "resourceValues": ["{{alert.resource.node}}"],
                                "patternId": "12345"
                            }
                        }]
                    }]
                }
            },
            "deployed": deployed,
            "group": [],
            "ghash": ""
        }, separators=(",", ":")),
        "dynamic": "",
        "groupid": "analytics.temporal-patterns",
        "issystem": "True",
        "isuser": "",
        "metadata": json.dumps({
            "createdBy": {
                "entityType": "analytics",
                "entityId": "system",
                "entityMetadata": {"trainingTimestamp": now_iso}
            },
            "lastUpdatedBy": {"entityType": "analytics", "entityId": "system"},
            "lastUpdated": now_iso,
            "created": now_iso,
            "statedata": {"locked": False, "state": "active"},
            "model": {"trainingTimestamp": now_iso, "analytic": "analytics.temporal-patterns"}
        }, separators=(",", ":")),
        "metrics": json.dumps({
            "col1": {"numGroupOccurrences": 5, "maxNumGroupOccurrences": 15},
            "rankingScore": 0.85
        }, separators=(",", ":")),
        "resolver": "",
    }
    
    return pd.DataFrame([seasonality_policy, temporal_policy])


def generate_exports(
    policies_template: Path | None,
    events_template: Path | None,
    num_policies: int,
    min_events: int,
    max_events: int,
    output_prefix: str,
    seed: int | None,
    pattern_policies_template: Path | None,
    pattern_policy_count: int,
    pattern_policy_ratio: float,
    progress_every: int,
    event_instances_template: Path | None,
    generate_event_instances: bool,
    deployed: bool = True,
) -> Tuple[Path, Path, Path | None]:
    if seed is not None:
        random.seed(seed)

    if min_events < 3:
        raise ValueError("min-events must be at least 3.")
    if max_events < min_events:
        raise ValueError("max-events must be greater than or equal to min-events.")
    if num_policies < 1:
        raise ValueError("num-policies must be at least 1.")
    if pattern_policy_count < 0:
        raise ValueError("pattern-policy-count cannot be negative.")
    if pattern_policy_ratio < 0:
        raise ValueError("pattern-policy-ratio cannot be negative.")

    log("Starting the process...")
    
    # Load or create policy template
    if policies_template and policies_template.exists():
        log(f"Loading policy template from {policies_template}...")
        policies_df = read_export_csv(policies_template)
    else:
        if policies_template:
            log(f"Policy template {policies_template} not found, using built-in defaults...")
        else:
            log("No policy template specified, using built-in defaults...")
        policies_df = create_default_policy_template(deployed=deployed)

    # Load or create events template
    if events_template and events_template.exists():
        log(f"Loading events template from {events_template}...")
        events_df = read_export_csv(events_template)
    else:
        if events_template:
            log(f"Events template {events_template} not found, using built-in defaults...")
        else:
            log("No events template specified, using built-in defaults...")
        events_df = create_default_events_template()

    required_policy_cols = [
        "tenantid", "partitionid", "policyset", "policyid", "type", "configuration",
        "dynamic", "groupid", "issystem", "isuser", "metadata", "metrics", "resolver",
    ]
    required_event_cols = ["tenantid", "policyset", "eventid", "policies"]
    missing_policy = [c for c in required_policy_cols if c not in policies_df.columns]
    missing_event = [c for c in required_event_cols if c not in events_df.columns]
    if missing_policy:
        raise ValueError(f"Missing columns in policy template: {missing_policy}")
    if missing_event:
        raise ValueError(f"Missing columns in event template: {missing_event}")

    policies_columns = list(policies_df.columns)
    events_columns = list(events_df.columns)
    template_rows = policies_df.to_dict("records")

    tenantid = policies_df["tenantid"].iloc[0] if not policies_df.empty else "cfd95b7e-3bc7-4006-a4a8-a73a79c71255"
    policyset = policies_df["policyset"].iloc[0] if not policies_df.empty else "-"

    pattern_rows: List[dict] = []
    ratio_count = int(num_policies * pattern_policy_ratio)
    total_pattern_policies = pattern_policy_count + ratio_count
    
    if total_pattern_policies > 0:
        # Load or create pattern policy template
        if pattern_policies_template and pattern_policies_template.exists():
            log(f"Loading pattern policy template from {pattern_policies_template}...")
            pattern_df = read_export_csv(pattern_policies_template)
            missing_pattern = [c for c in required_policy_cols if c not in pattern_df.columns]
            if missing_pattern:
                raise ValueError(f"Missing columns in pattern policy template: {missing_pattern}")
            pattern_rows = pattern_df.to_dict("records")
            log(f"Loaded {len(pattern_rows):,} pattern-policy template rows from {pattern_policies_template}")
        else:
            if pattern_policies_template:
                log(f"Pattern policy template {pattern_policies_template} not found, using built-in defaults...")
            else:
                log("No pattern policy template specified, using built-in defaults...")
            pattern_rows = create_default_pattern_policy_templates(deployed=deployed)
            log(f"Using {len(pattern_rows)} built-in pattern policy templates")
        
        log(f"Pattern policies requested: {total_pattern_policies:,}")

    event_to_policies: Dict[str, List[str]] = defaultdict(list)
    event_instance_requirements: Dict[str, int] = defaultdict(int)
    generated_policy_rows: List[dict] = []

    start_time = time.time()

    # Standard related-events/correlation-like policies.
    for policy_index in range(1, num_policies + 1):
        policy_row = generate_standard_policy(
            policies_columns=policies_columns,
            template_rows=template_rows,
            min_events=min_events,
            max_events=max_events,
            event_to_policies=event_to_policies,
        )
        generated_policy_rows.append(policy_row)
        register_event_instance_requirements(policy_row, event_instance_requirements)

        if policy_index == 1 or policy_index % progress_every == 0 or policy_index == num_policies:
            elapsed = time.time() - start_time
            rate = policy_index / elapsed if elapsed > 0 else 0
            log(
                f"Policies generated: {policy_index:,}/{num_policies:,} "
                f"({policy_index / num_policies:.0%}) | "
                f"unique events so far: {len(event_to_policies):,} | "
                f"{rate:,.1f} policies/sec"
            )

    # Optional pattern-style policies.
    if total_pattern_policies:
        pattern_start = time.time()
        for pattern_index in range(1, total_pattern_policies + 1):
            policy_row = generate_pattern_policy(
                policies_columns=policies_columns,
                pattern_rows=pattern_rows,
                event_to_policies=event_to_policies,
                tenantid=tenantid,
                policyset=policyset,
            )
            generated_policy_rows.append(policy_row)
            register_event_instance_requirements(policy_row, event_instance_requirements)
            if pattern_index == 1 or pattern_index % progress_every == 0 or pattern_index == total_pattern_policies:
                elapsed = time.time() - pattern_start
                rate = pattern_index / elapsed if elapsed > 0 else 0
                log(
                    f"Pattern policies generated: {pattern_index:,}/{total_pattern_policies:,} "
                    f"({pattern_index / total_pattern_policies:.0%}) | "
                    f"unique events so far: {len(event_to_policies):,} | "
                    f"{rate:,.1f} policies/sec"
                )

    generated_event_rows: List[dict] = []
    total_events = len(event_to_policies)
    log(f"Building policy-event rows for {total_events:,} unique events...")
    event_start_time = time.time()

    for event_index, (event_id, policy_ids) in enumerate(sorted(event_to_policies.items()), start=1):
        row = {col: "" for col in events_columns}
        row["tenantid"] = tenantid
        row["policyset"] = policyset
        row["eventid"] = event_id
        row["policies"] = format_policy_set(policy_ids)
        generated_event_rows.append(row)

        if total_events >= 10000 and (event_index == 1 or event_index % 50000 == 0 or event_index == total_events):
            elapsed = time.time() - event_start_time
            rate = event_index / elapsed if elapsed > 0 else 0
            log(
                f"Policy-event rows built: {event_index:,}/{total_events:,} "
                f"({event_index / total_events:.0%}) | "
                f"{rate:,.1f} rows/sec"
            )

    out_policy_path = Path(f"{output_prefix}_policies_export.csv")
    out_event_path = Path(f"{output_prefix}_policies_events_export.csv")

    log("Writing policy CSV...")
    write_export_csv(pd.DataFrame(generated_policy_rows, columns=policies_columns), out_policy_path)

    log("Writing policy-event CSV...")
    write_export_csv(pd.DataFrame(generated_event_rows, columns=events_columns), out_event_path)

    out_instances_path: Path | None = None
    if generate_event_instances:
        event_instances_df, out_instances_path = generate_event_instance_rows(
            event_instances_template=event_instances_template,
            event_instance_requirements=event_instance_requirements,
            output_prefix=output_prefix,
            progress_every=progress_every,
        )
        log("Writing event-instances CSV...")
        write_export_csv(event_instances_df, out_instances_path)

    elapsed_total = time.time() - start_time
    log(f"Done in {elapsed_total:,.2f} seconds.")

    return out_policy_path, out_event_path, out_instances_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate synthetic policy and policy-event export CSV files.",
        epilog="Templates are optional. If not provided or not found, built-in defaults will be used."
    )
    parser.add_argument("--policies-template", type=Path, default=None, help="Optional policy export template. If not provided, uses built-in defaults.")
    parser.add_argument("--events-template", type=Path, default=None, help="Optional events export template. If not provided, uses built-in defaults.")
    parser.add_argument("--num-policies", type=int, default=10, help="Number of policies to generate. Default: 10")
    parser.add_argument("--min-events", type=int, default=3, help="Minimum events per standard policy. Must be >= 3. Default: 3")
    parser.add_argument("--max-events", type=int, default=100, help="Maximum events per standard policy. Default: 100")
    parser.add_argument("--pattern-policies-template", type=Path, default=None, help="Optional policy export file containing pattern policy examples.")
    parser.add_argument("--pattern-policy-count", type=int, default=0, help="Number of additional pattern-style policies to generate.")
    parser.add_argument("--pattern-policy-ratio", type=float, default=0.1, help="Additional pattern policies as ratio of --num-policies. Default: 0.1 (10%%). Set to 0 to disable.")
    parser.add_argument("--progress-every", type=int, default=500, help="Print policy progress every N rows. Default: 500")
    parser.add_argument("--event-instances-template", type=Path, default=None, help="Optional template for generating event details/instances export. If not provided, uses built-in defaults.")
    parser.add_argument("--no-event-instances", action="store_true", help="Do not generate the event instances/details export.")
    parser.add_argument("--output-prefix", default="generated", help="Prefix for output files. Default: generated")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducible generation.")
    parser.add_argument("--deployed", action="store_true", default=True, help="Set deployed status to true for all generated policies. Default: true")
    parser.add_argument("--not-deployed", dest="deployed", action="store_false", help="Set deployed status to false for all generated policies.")
    args = parser.parse_args()

    policy_path, event_path, instances_path = generate_exports(
        policies_template=args.policies_template,
        events_template=args.events_template,
        num_policies=args.num_policies,
        min_events=args.min_events,
        max_events=args.max_events,
        output_prefix=args.output_prefix,
        seed=args.seed,
        pattern_policies_template=args.pattern_policies_template,
        pattern_policy_count=args.pattern_policy_count,
        pattern_policy_ratio=args.pattern_policy_ratio,
        progress_every=max(1, args.progress_every),
        event_instances_template=args.event_instances_template,
        generate_event_instances=not args.no_event_instances,
        deployed=args.deployed,
    )

    log(f"Generated: {policy_path}")
    log(f"Generated: {event_path}")
    if instances_path:
        log(f"Generated: {instances_path}")
    log(f"Standard policies: {args.num_policies}")
    log(f"Standard events per policy: {args.min_events} to {args.max_events}")
    
    # Show pattern policies count if any were generated
    pattern_total = args.pattern_policy_count + int(args.num_policies * args.pattern_policy_ratio)
    if pattern_total > 0:
        log(f"Pattern policies: {pattern_total}")


if __name__ == "__main__":
    main()
