#!/bin/bash
#
# Copyright IBM Corp. 2024 - 2026
# SPDX-License-Identifier: Apache-2.0
#
# copy_policies_details_from_cassandra.sh
# Export CSVs from Cassandra. Dedup logic removed.

set -euo pipefail

DEFAULT_POLICIES_FILE="policies_export.csv"
DEFAULT_EVENTS_FILE="policies_events_export.csv"
DEFAULT_EVENT_INSTANCES_FILE="event_instances_export.csv"

POD_TMP_DIR="/tmp"
LOCAL_MODE=false
NAMESPACE=""
RELEASE_NAME=""

print_help() {
  cat <<'EOF'
Usage:
  ./copy_policies_details_from_cassandra.sh [--reuse] [--local] [--namespace NAMESPACE] [--release RELEASE_NAME]

Options:
  --reuse             Reuse existing local CSVs; only export tables whose output file is missing.
  --local             Run in local mode when already inside a Cassandra pod; uses cqlsh directly.
  --namespace NS      Use specified OpenShift namespace/project.
  --release NAME      Use specified NOI release name.
  -h, --help          Show this help.

Tables exported:
  ea_policies.policies           -> policies_export.csv
  ea_policies.eventid_to_policy  -> policies_events_export.csv
  ea_events.event_instances      -> event_instances_export.csv
EOF
}

REUSE=false
LOCAL_MODE=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --reuse) REUSE=true; shift ;;
    --local) LOCAL_MODE=true; shift ;;
    --namespace)
      NAMESPACE="$2"
      shift 2
      ;;
    --release)
      RELEASE_NAME="$2"
      shift 2
      ;;
    -h|--help) print_help; exit 0 ;;
    *) echo "Unknown option: $1"; print_help; exit 1 ;;
  esac
done

find_cassandra_pod() {
  local pod
  local ns_arg=""
  
  # Use namespace if provided
  if [[ -n "$NAMESPACE" ]]; then
    ns_arg="-n $NAMESPACE"
    echo "[INFO] Looking for Cassandra pod in namespace: $NAMESPACE" >&2
  fi
  
  # Try to find Cassandra pod using the release name if provided
  if [[ -n "$RELEASE_NAME" ]]; then
    echo "[INFO] Looking for Cassandra pod with release name: $RELEASE_NAME" >&2
    pod="$(oc get pods $ns_arg | grep "$RELEASE_NAME.*cassandra" | awk '{print $1}' | head -n1 || true)"
    
    # If not found with release name, try just cassandra
    if [[ -z "$pod" ]]; then
      pod="$(oc get pods $ns_arg | grep cassandra | awk '{print $1}' | head -n1 || true)"
    fi
  else
    # No release name, just look for cassandra
    pod="$(oc get pods $ns_arg | grep cassandra | awk '{print $1}' | head -n1 || true)"
  fi
  
  if [[ -z "$pod" ]]; then
    echo "ERROR: No Cassandra pod found." >&2
    exit 1
  fi
  
  # Make sure the pod name doesn't contain any log messages or whitespace
  pod=$(echo "$pod" | tr -d '[:space:]' | grep -v '\[.*\]')
  
  echo "[INFO] Found Cassandra pod: $pod" >&2
  echo "$pod"
}

cql_exec() {
  local pod="$1"
  local cql="$2"
  local ns_arg=""
  
  # Use namespace if provided
  if [[ -n "$NAMESPACE" ]]; then
    ns_arg="-n $NAMESPACE"
  fi
  
  if $LOCAL_MODE; then
    # When running inside the pod, execute cqlsh directly with the same auth credentials
    cqlsh \
      -u "$(cat "${CASSANDRA_AUTH_USERNAME_FILE}")" \
      -p "$(cat "${CASSANDRA_AUTH_PASSWORD_FILE}")" \
      -e "$cql"
  else
    # Original behavior using oc exec with namespace if provided
    oc exec $ns_arg -i "$pod" -- bash -lc \
      "cqlsh \
        -u \$(cat \"\${CASSANDRA_AUTH_USERNAME_FILE}\") \
        -p \$(cat \"\${CASSANDRA_AUTH_PASSWORD_FILE}\") \
        -e \"$cql\""
  fi
}

copy_from_pod() {
  local pod="$1" pod_path="$2" dest_local="$3"
  local ns_arg=""
  
  # Use namespace if provided
  if [[ -n "$NAMESPACE" ]]; then
    ns_arg="-n $NAMESPACE"
  fi
  
  if $LOCAL_MODE; then
    # In local mode, the file is already in the current directory
    # Just move or copy it to the destination if needed
    if [[ "$pod_path" != "$dest_local" ]]; then
      echo "[INFO] Moving $pod_path to $dest_local ..."
      mv "$pod_path" "$dest_local"
    else
      echo "[INFO] File already at destination: $dest_local"
    fi
  else
    # Original behavior using oc cp with namespace if provided
    echo "[INFO] Copying $pod_path to $dest_local ..."
    oc cp $ns_arg "$pod:$pod_path" "$dest_local"
  fi
}

export_table_if_needed() {
  # $1: full keyspace.table  $2: local filename  $3: pod
  local table="$1" file="$2" pod="$3"
  if $REUSE && [[ -f "$file" ]]; then
    echo "[SKIP] $table -> $file (reuse enabled and file exists)"
    return 0
  fi
  
  local pod_path
  if $LOCAL_MODE; then
    # In local mode, export directly to the destination file
    pod_path="$file"
  else
    # Original behavior using temp directory in pod
    pod_path="$POD_TMP_DIR/$file"
  fi
  
  local cql="COPY $table TO '$pod_path' WITH HEADER = true AND DELIMITER=';';"
  echo "[INFO] Exporting $table -> $file"
  cql_exec "$pod" "$cql"
  
  if ! $LOCAL_MODE; then
    # Only need to copy and clean up in non-local mode
    copy_from_pod "$pod" "$pod_path" "$file"
    oc exec "$pod" -- rm -f "$pod_path" >/dev/null 2>&1 || true
  fi
}

main() {
  local pod=""
  
  if ! $LOCAL_MODE; then
    pod="$(find_cassandra_pod)"
  else
    # In local mode, we don't need a pod reference
    echo "[INFO] Running in local mode (inside Cassandra pod)"
  fi

  if [[ -e "deployed_cache.json" ]]; then
    echo "[INFO] deleting cache file: deployed_cache.json"
    rm -f deployed_cache.json
  fi

  # Display mode information
  local mode_str="$([[ "$REUSE" == true ]] && echo "reuse (export missing only)" || echo "full export")"
  if $LOCAL_MODE; then
    mode_str="$mode_str, local execution"
  fi
  echo "[MODE] $mode_str"

  export_table_if_needed "ea_policies.policies"          "$DEFAULT_POLICIES_FILE"          "$pod"
  export_table_if_needed "ea_policies.eventid_to_policy" "$DEFAULT_EVENTS_FILE"            "$pod"
  export_table_if_needed "ea_events.event_instances"     "$DEFAULT_EVENT_INSTANCES_FILE"   "$pod"

  echo "[INFO] Export complete."
}

main "$@"
