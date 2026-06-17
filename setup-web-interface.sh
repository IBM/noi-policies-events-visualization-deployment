#!/bin/bash
#
# Copyright IBM Corp. 2024 - 2026
# SPDX-License-Identifier: Apache-2.0
#
# Two-phase deployment script for the web interface
# Phase 1: Deploy with empty files containing headers
# Phase 2: Copy actual data and trigger update
#
# Usage:
#   ./setup-web-interface.sh           # Interactive deployment
#   ./setup-web-interface.sh --cleanup # Cleanup/delete deployment

# Default values (will be auto-detected if possible)
DEFAULT_NAMESPACE=""
DEFAULT_DEPLOYMENT_NAME="evtmanager-ibm-ea-web-interface"
DEFAULT_SOURCE_DIR="src"

# Parse command line arguments
MODE="deploy"
AUTO_YES=false

# Parse all arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --cleanup|cleanup|--delete|delete)
      MODE="cleanup"
      shift
      ;;
    --yes|-y)
      AUTO_YES=true
      shift
      ;;
    --help|-h)
      echo "Usage: $0 [OPTIONS]"
      echo ""
      echo "Options:"
      echo "  (no options)    Interactive deployment mode (default)"
      echo "  --cleanup       Cleanup/delete the deployment, service, route, and configmap"
      echo "  --yes, -y       Skip confirmation prompts (for automation)"
      echo "  --help, -h      Show this help message"
      echo ""
      echo "Examples:"
      echo "  $0                      # Deploy web interface interactively"
      echo "  $0 --yes                # Deploy without prompts (use defaults)"
      echo "  $0 --cleanup            # Remove all resources (with confirmation)"
      echo "  $0 --cleanup --yes      # Remove all resources (no confirmation)"
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      echo "Use --help for usage information"
      exit 1
      ;;
  esac
done

# Function to check if kubectl/oc is available and user is logged in
check_cluster_connection() {
  echo -e "\n\033[1;36m🔍 === Checking Cluster Connection === 🔍\033[0m"
  
  # Determine which CLI to use (prefer oc for OpenShift, fallback to kubectl)
  local CLI_CMD=""
  if command -v oc &> /dev/null; then
    CLI_CMD="oc"
    echo "Using OpenShift CLI (oc)"
  elif command -v kubectl &> /dev/null; then
    CLI_CMD="kubectl"
    echo "Using Kubernetes CLI (kubectl)"
  else
    echo -e "\033[1;31m❌ ERROR: Neither 'oc' nor 'kubectl' command found!\033[0m"
    echo -e "\033[1;33m   Please install one of these tools:\033[0m"
    echo -e "\033[1;33m   - OpenShift CLI: https://docs.openshift.com/container-platform/latest/cli_reference/openshift_cli/getting-started-cli.html\033[0m"
    echo -e "\033[1;33m   - Kubernetes CLI: https://kubernetes.io/docs/tasks/tools/\033[0m"
    exit 1
  fi
  
  # Check if user is logged in to a cluster (fast check using config)
  echo "Checking cluster connection..."
  if ! $CLI_CMD config current-context &> /dev/null; then
    echo -e "\033[1;31m❌ ERROR: No active Kubernetes/OpenShift context found!\033[0m"
    echo -e "\033[1;33m   Please log in to your cluster first using one of these commands:\033[0m"
    echo -e "\033[1;33m   - kubectl: kubectl config use-context <context-name>\033[0m"
    echo -e "\033[1;33m   - OpenShift: oc login <cluster-url> -u <username> -p <password>\033[0m"
    exit 1
  fi
  
  # Quick API server connectivity check with timeout - try simple namespace list
  echo "Verifying API server connectivity..."
  if ! timeout 10 $CLI_CMD get namespaces --request-timeout=5s &> /dev/null; then
    echo -e "\033[1;33m⚠️  WARNING: Cannot verify API server connectivity.\033[0m"
    echo -e "\033[1;33m   This may be due to network issues or permissions.\033[0m"
    echo -e "\033[1;33m   Attempting to continue anyway...\033[0m"
  else
    echo -e "\033[1;32m✅ API server is reachable\033[0m"
  fi
  
  # Get current context information
  local current_context=$($CLI_CMD config current-context 2>/dev/null)
  local current_server=$($CLI_CMD config view --minify -o jsonpath='{.clusters[0].cluster.server}' 2>/dev/null)
  local current_user=$($CLI_CMD config view --minify -o jsonpath='{.contexts[0].context.user}' 2>/dev/null)
  
  echo -e "\033[1;32m✅ Connected to cluster!\033[0m"
  echo -e "\033[1;36m   Context: ${current_context}\033[0m"
  echo -e "\033[1;36m   Server: ${current_server}\033[0m"
  echo -e "\033[1;36m   User: ${current_user}\033[0m"
  
  # Try to detect current namespace from context
  echo ""
  echo "Detecting current namespace..."
  local detected_namespace=$($CLI_CMD config view --minify -o jsonpath='{.contexts[0].context.namespace}' 2>/dev/null)
  
  if [ -n "$detected_namespace" ]; then
    echo -e "\033[1;32m✅ Detected current namespace: '$detected_namespace'\033[0m"
    DEFAULT_NAMESPACE="$detected_namespace"
    
    # Verify access to detected namespace
    if timeout 5 $CLI_CMD get namespace "$detected_namespace" &> /dev/null; then
      echo -e "\033[1;32m✅ Access to namespace '$detected_namespace' confirmed\033[0m"
    else
      echo -e "\033[1;33m⚠️  WARNING: Cannot verify access to namespace '$detected_namespace'\033[0m"
    fi
  else
    echo -e "\033[1;33m⚠️  Could not auto-detect namespace from context\033[0m"
    echo -e "\033[1;33m   You will be prompted to enter the namespace manually\033[0m"
    DEFAULT_NAMESPACE="default"
  fi
  
  echo ""
}

# Function to prompt for input with default value
prompt_with_default() {
  local prompt=$1
  local default=$2
  local input
  
  read -p "$prompt [$default]: " input
  echo "${input:-$default}"
}

# Function to cleanup/delete deployment
cleanup_deployment() {
  echo -e "\n\033[1;31m🗑️  === CLEANUP MODE === 🗑️\033[0m"
  echo -e "\033[1;31m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m"
  echo -e "\033[1;33mThis will delete all resources for the web interface deployment.\033[0m"
  echo ""
  
  # Get namespace and deployment name
  NAMESPACE=$(prompt_with_default "Kubernetes namespace" "$DEFAULT_NAMESPACE")
  DEPLOYMENT_NAME=$(prompt_with_default "Deployment name" "$DEFAULT_DEPLOYMENT_NAME")
  
  echo ""
  echo -e "\033[1;31m⚠️  WARNING! ⚠️\033[0m"
  echo -e "\033[1;31m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m"
  echo -e "\033[1;31m  This will DELETE the following resources in namespace '$NAMESPACE':\033[0m"
  echo -e "\033[1;31m  - Deployment: $DEPLOYMENT_NAME\033[0m"
  echo -e "\033[1;31m  - Service: $DEPLOYMENT_NAME\033[0m"
  echo -e "\033[1;31m  - Route: $DEPLOYMENT_NAME (if exists)\033[0m"
  echo -e "\033[1;31m  - ConfigMap: web-interface-config (if exists)\033[0m"
  echo -e "\033[1;31m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m"
  echo ""
  
  if [ "$AUTO_YES" = false ]; then
    read -p "Are you sure you want to proceed? (yes/no): " CONFIRM
    
    if [ "$CONFIRM" != "yes" ]; then
      echo -e "\033[1;33m❌ Cleanup cancelled.\033[0m"
      exit 0
    fi
  else
    echo -e "\033[1;33m⚡ Auto-confirm enabled (--yes flag), proceeding with cleanup...\033[0m"
  fi
  
  echo ""
  echo -e "\033[1;36m🗑️  Starting cleanup...\033[0m"
  echo ""
  
  # Delete route if it exists
  echo "Checking for route..."
  if kubectl get route $DEPLOYMENT_NAME -n $NAMESPACE &>/dev/null; then
    echo "Deleting route $DEPLOYMENT_NAME..."
    kubectl delete route $DEPLOYMENT_NAME -n $NAMESPACE
    echo -e "\033[1;32m✅ Route deleted\033[0m"
  else
    echo "No route found (this is normal if you're not using OpenShift)"
  fi
  
  # Delete service
  echo ""
  echo "Checking for service..."
  if kubectl get service $DEPLOYMENT_NAME -n $NAMESPACE &>/dev/null; then
    echo "Deleting service $DEPLOYMENT_NAME..."
    kubectl delete service $DEPLOYMENT_NAME -n $NAMESPACE
    echo -e "\033[1;32m✅ Service deleted\033[0m"
  else
    echo "No service found"
  fi
  
  # Delete deployment
  echo ""
  echo "Checking for deployment..."
  if kubectl get deployment $DEPLOYMENT_NAME -n $NAMESPACE &>/dev/null; then
    echo "Deleting deployment $DEPLOYMENT_NAME..."
    kubectl delete deployment $DEPLOYMENT_NAME -n $NAMESPACE
    echo -e "\033[1;32m✅ Deployment deleted\033[0m"
    
    # Wait for pods to terminate
    echo "Waiting for pods to terminate..."
    kubectl wait --for=delete pod -l app=$DEPLOYMENT_NAME -n $NAMESPACE --timeout=60s 2>/dev/null || true
    echo -e "\033[1;32m✅ Pods terminated\033[0m"
  else
    echo "No deployment found"
  fi
  
  # Delete configmap
  echo ""
  echo "Checking for configmap..."
  if kubectl get configmap web-interface-config -n $NAMESPACE &>/dev/null; then
    echo "Deleting configmap web-interface-config..."
    kubectl delete configmap web-interface-config -n $NAMESPACE
    echo -e "\033[1;32m✅ ConfigMap deleted\033[0m"
  else
    echo "No configmap found"
  fi
  
  echo ""
  echo -e "\033[1;32m✅ Cleanup complete!\033[0m"
  echo -e "\033[1;36m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m"
  echo ""
  echo "All resources have been removed from namespace '$NAMESPACE'."
  echo "You can redeploy by running this script without the --cleanup flag."
  exit 0
}

# Check if we're in cleanup mode
if [ "$MODE" = "cleanup" ]; then
  check_cluster_connection
  cleanup_deployment
fi

# Check cluster connection first (this will auto-detect namespace)
check_cluster_connection

# Interactive setup
echo -e "\n\033[1;36m🚀 === Interactive Web Interface Deployment Setup === 🚀\033[0m"
if [ -n "$DEFAULT_NAMESPACE" ] && [ "$DEFAULT_NAMESPACE" != "default" ]; then
  echo -e "\033[1;32m📋 Auto-detected configuration:\033[0m"
  echo -e "\033[1;36m   Namespace: $DEFAULT_NAMESPACE\033[0m"
  echo ""
  echo -e "\033[1;33m📋 Please confirm or modify the following (press Enter to use detected/default values):\033[0m"
else
  echo -e "\033[1;33m📋 Please provide the following information:\033[0m"
fi
NAMESPACE=$(prompt_with_default "Kubernetes namespace" "$DEFAULT_NAMESPACE")
DEPLOYMENT_NAME=$(prompt_with_default "Deployment name" "$DEFAULT_DEPLOYMENT_NAME")
SOURCE_DIR=$(prompt_with_default "Source directory" "$DEFAULT_SOURCE_DIR")

# Ask if user wants to create a route
if [ "$AUTO_YES" = false ]; then
  echo -e "\033[1;34m🌐 Route Creation\033[0m"
  read -p "Do you want to create a route to access the web interface from outside the cluster? (y/n): " CREATE_ROUTE
else
  CREATE_ROUTE="y"
  echo -e "\033[1;36m🌐 Route creation: enabled (auto-confirm)\033[0m"
fi

# Warning about deletion
echo ""
if [ "$AUTO_YES" = false ]; then
  echo -e "\033[1;31m⚠️  WARNING! ⚠️\033[0m"
  echo -e "\033[1;31m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m"
  echo -e "\033[1;31m  This script will DELETE any existing deployment with name '$DEPLOYMENT_NAME'\033[0m"
  echo -e "\033[1;31m  in namespace '$NAMESPACE'\033[0m"
  echo -e "\033[1;31m  This includes pods, services, configmaps, and routes with this name.\033[0m"
  echo -e "\033[1;31m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m"
  echo ""
  read -p "Do you want to continue? (y/n): " confirm
  if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
    echo "Deployment cancelled."
    exit 0
  fi
else
  echo -e "\033[1;33m⚡ Auto-confirm enabled (--yes flag), proceeding with deployment...\033[0m"
  echo -e "\033[1;36m   Namespace: $NAMESPACE\033[0m"
  echo -e "\033[1;36m   Deployment: $DEPLOYMENT_NAME\033[0m"
  echo ""
fi

# Function to display a progress bar
show_progress() {
  local duration=$1
  local message=$2
  local i=0
  local bar_length=30
  local fill_char="▓"
  local empty_char="░"
  
  echo -e "\033[1;36m$message\033[0m"
  
  while [ $i -lt $duration ]; do
    # Calculate how many characters to fill
    local filled=$(( i * bar_length / duration ))
    local empty=$(( bar_length - filled ))
    
    # Create the progress bar
    local bar=""
    local j=0
    while [ $j -lt $filled ]; do
      bar="${bar}${fill_char}"
      j=$((j+1))
    done
    
    j=0
    while [ $j -lt $empty ]; do
      bar="${bar}${empty_char}"
      j=$((j+1))
    done
    
    # Calculate percentage
    local percent=$(( i * 100 / duration ))
    
    # Print the progress bar
    echo -ne "\r\033[1;36m[${bar}] ${percent}%\033[0m"
    
    sleep 1
    i=$((i+1))
  done
  
  # Print 100% when done
  local bar=""
  local j=0
  while [ $j -lt $bar_length ]; do
    bar="${bar}${fill_char}"
    j=$((j+1))
  done
  
  echo -e "\r\033[1;32m[${bar}] 100% ✓\033[0m"
}

# Function to wait for container to be available and ready for file operations
wait_for_container() {
  local namespace=$1
  local pod=$2
  local container=$3
  local max_attempts=45  # Increased from 30 to 45
  local attempt=1
  
  echo "Waiting for container to be available..."
  
  while [ $attempt -le $max_attempts ]; do
    # Check if pod exists
    if ! kubectl get pod $pod -n $namespace &>/dev/null; then
      echo "Pod $pod does not exist yet. Waiting..."
      sleep 5
      attempt=$((attempt+1))
      continue
    fi
    
    # Check if pod is running
    local pod_status=$(kubectl get pod $pod -n $namespace -o jsonpath='{.status.phase}' 2>/dev/null)
    if [ "$pod_status" != "Running" ]; then
      echo "Pod status is $pod_status, waiting for it to be Running..."
      sleep 5
      attempt=$((attempt+1))
      continue
    fi
    
    # Check if container exists in pod
    local container_exists=$(kubectl get pod $pod -n $namespace -o jsonpath="{.spec.containers[*].name}" 2>/dev/null | grep -w "$container" || echo "")
    if [ -z "$container_exists" ]; then
      echo "Container $container does not exist in pod yet. Waiting..."
      sleep 5
      attempt=$((attempt+1))
      continue
    fi
    
    # Check if container is ready according to Kubernetes
    local container_ready=$(kubectl get pod $pod -n $namespace -o jsonpath="{.status.containerStatuses[?(@.name==\"$container\")].ready}" 2>/dev/null)
    if [ "$container_ready" != "true" ]; then
      echo "Container not ready according to Kubernetes, waiting..."
      sleep 5
      attempt=$((attempt+1))
      continue
    fi
    
    # Try to execute a command in the container
    if kubectl exec -n $namespace $pod -c $container -- echo "Container is available" &>/dev/null; then
      echo "✓ Container is available and ready for file operations!"
      
      # Additional check: try to create a test file
      echo "Performing additional file operation test..."
      local test_file="/tmp/test_file_$(date +%s)"
      echo "test" > $test_file
      if kubectl cp $test_file $namespace/$pod:/tmp/test_file -c $container &>/dev/null; then
        echo "✓ File operations are working!"
        rm -f $test_file
        
        # Final check: try to create a test directory
        echo "Testing directory creation..."
        local test_dir="/tmp/test_dir_$(date +%s)"
        if kubectl exec -n $namespace $pod -c $container -- mkdir -p "$test_dir" &>/dev/null; then
          echo "✓ Directory operations are working!"
          kubectl exec -n $namespace $pod -c $container -- rmdir "$test_dir" &>/dev/null || true
          return 0
        else
          echo "Container is available but directory operations are not working yet. Waiting..."
          sleep 5
          attempt=$((attempt+1))
        fi
      else
        echo "Container is available but file operations are not working yet. Waiting..."
        rm -f $test_file
        sleep 5
        attempt=$((attempt+1))
      fi
    else
      echo "Attempt $attempt/$max_attempts: Container not available yet. Waiting 5 seconds..."
      sleep 5
      attempt=$((attempt+1))
    fi
  done
  
  echo "Container did not become fully available after $max_attempts attempts."
  echo "Checking pod status and events..."
  kubectl describe pod $pod -n $namespace
  return 1
}

# Function to copy a file with basic retry and error handling for missing files
copy_file() {
  local src=$1
  local dest=$2
  local max_attempts=10
  local attempt=1
  local success=false
  
  # Check if source file exists
  if [ ! -f "$src" ] && [ ! -d "$src" ]; then
    echo -e "\033[1;33m⚠️  WARNING: Source file/directory '$src' does not exist. Skipping copy operation.\033[0m"
    return 0
  fi
  
  echo -e "\033[1;36m📂 Copying $(basename $src)...\033[0m"
  
  while [ $attempt -le $max_attempts ] && [ "$success" = false ]; do
    if kubectl cp $src $dest -c web-interface 2>/dev/null; then
      echo -e "\033[1;32m✅ Copied $(basename $src) successfully\033[0m"
      success=true
    else
      echo -e "\033[1;33m🔄 Attempt $attempt/$max_attempts: Retrying in 5 seconds...\033[0m"
      sleep 5
      attempt=$((attempt+1))
    fi
  done
  
  if [ "$success" = false ]; then
    echo -e "\033[1;33m⚠️  WARNING: Failed to copy $(basename $src) after $max_attempts attempts. Continuing with deployment.\033[0m"
  fi
  
  return 0
}

# Function to ensure directory exists in pod
ensure_directory_exists() {
  local namespace=$1
  local pod=$2
  local container=$3
  local directory=$4
  local max_attempts=10
  local attempt=1
  
  echo "Ensuring directory exists: $directory"
  
  # First verify container is truly ready
  echo "Verifying container readiness before directory creation..."
  if ! kubectl exec -n $namespace $pod -c $container -- echo "Container ready check" &>/dev/null; then
    echo "Container not ready for directory operations. Waiting..."
    # Wait for container to be fully ready
    if ! wait_for_container $namespace $pod $container; then
      echo "ERROR: Container failed to become ready for directory operations"
      return 1
    fi
  fi
  
  # Now try to create the directory with retries
  while [ $attempt -le $max_attempts ]; do
    if kubectl exec -n $namespace $pod -c $container -- mkdir -p "$directory" &>/dev/null; then
      echo "✓ Successfully created directory: $directory"
      return 0
    else
      echo "Attempt $attempt/$max_attempts: Failed to create directory $directory"
      echo "Waiting 5 seconds before retry..."
      sleep 5
      
      # Check if container is still running
      local pod_status=$(kubectl get pod $pod -n $namespace -o jsonpath='{.status.phase}' 2>/dev/null)
      if [ "$pod_status" != "Running" ]; then
        echo "ERROR: Pod is no longer running (status: $pod_status)"
        kubectl describe pod $pod -n $namespace
        return 1
      fi
      
      attempt=$((attempt+1))
    fi
  done
  
  echo "ERROR: Failed to create directory $directory after $max_attempts attempts"
  echo "Checking container status..."
  kubectl describe pod $pod -n $namespace | grep -A 10 "Containers:"
  return 1
}

# Function to create a file with header in pod
create_file_with_header() {
  local namespace=$1
  local pod=$2
  local container=$3
  local filepath=$4
  local header=$5
  local temp_file="/tmp/header_file_$(date +%s).tmp"
  local directory=$(dirname "$filepath")
  local max_attempts=10
  local attempt=1
  
  echo "Creating file with header: $filepath"
  
  # Ensure parent directory exists
  if ! ensure_directory_exists "$namespace" "$pod" "$container" "$directory"; then
    echo "ERROR: Could not ensure directory exists: $directory"
    echo "Will try to create directory again..."
    sleep 5
    if ! ensure_directory_exists "$namespace" "$pod" "$container" "$directory"; then
      echo "ERROR: Failed to create directory after retry: $directory"
      return 1
    fi
  fi
  
  # Create a temporary file locally
  echo "$header" > "$temp_file"
  
  # Copy the temporary file to the pod with retries
  echo "Copying header file to pod: $filepath"
  while [ $attempt -le $max_attempts ]; do
    if kubectl cp "$temp_file" "$namespace/$pod:$filepath" -c "$container" &>/dev/null; then
      echo "✓ Created file with header: $filepath"
      
      # Verify the file was actually created
      if kubectl exec -n $namespace $pod -c $container -- test -f "$filepath" &>/dev/null; then
        echo "✓ Verified file exists: $filepath"
        rm -f "$temp_file"
        return 0
      else
        echo "WARNING: File copy appeared to succeed but file doesn't exist in pod"
        if [ $attempt -eq $max_attempts ]; then
          echo "ERROR: Failed to create file after $max_attempts attempts"
          rm -f "$temp_file"
          return 1
        fi
      fi
    else
      echo "Attempt $attempt/$max_attempts: Failed to create $filepath"
      
      # Check if container is still running
      local pod_status=$(kubectl get pod $pod -n $namespace -o jsonpath='{.status.phase}' 2>/dev/null)
      if [ "$pod_status" != "Running" ]; then
        echo "ERROR: Pod is no longer running (status: $pod_status)"
        kubectl describe pod $pod -n $namespace
        rm -f "$temp_file"
        return 1
      fi
    fi
    
    echo "Waiting 5 seconds before retry..."
    sleep 5
    attempt=$((attempt+1))
  done
  
  echo "ERROR: Failed to create $filepath after $max_attempts attempts"
  echo "Checking if file exists in pod..."
  kubectl exec -n $namespace $pod -c $container -- ls -la "$filepath" 2>&1 || echo "File does not exist"
  echo "Checking if container is still running..."
  kubectl get pod $pod -n $namespace
  rm -f "$temp_file"
  return 1
}

# Function to update last_update.json
update_last_update_json() {
  local namespace=$1
  local pod=$2
  local container=$3
  local current_time=$(date -u +"%Y-%m-%dT%H:%M:%S.%6N")
  local temp_file="/tmp/last_update_$(date +%s).json"
  local output_dir="/opt/app/output"
  local max_attempts=10
  local attempt=1
  
  echo "Updating last_update.json..."
  
  # Ensure output directory exists with retry
  if ! ensure_directory_exists "$namespace" "$pod" "$container" "$output_dir"; then
    echo "WARNING: Failed to ensure output directory exists. Retrying..."
    sleep 5
    if ! ensure_directory_exists "$namespace" "$pod" "$container" "$output_dir"; then
      echo "ERROR: Failed to create output directory after retry. Will try to continue anyway."
    fi
  fi
  
  # Get current update_count
  local update_count=1
  echo "Retrieving current update_count..."
  if kubectl cp "$namespace/$pod:$output_dir/last_update.json" "$temp_file" -c "$container" 2>/dev/null; then
    update_count=$(cat "$temp_file" 2>/dev/null | grep -o '"update_count": [0-9]*' | grep -o '[0-9]*' || echo "1")
    echo "Current update_count: $update_count"
  else
    echo "Could not retrieve current update_count, using default: 1"
  fi
  
  # Increment update_count
  local new_update_count=$((update_count + 1))
  
  # Create new last_update.json content
  cat > "$temp_file" << EOF
{
  "last_update": "$current_time",
  "update_count": $new_update_count,
  "last_status": "success"
}
EOF
  
  # Update the file with retries
  echo "Updating last_update.json with update_count: $new_update_count"
  while [ $attempt -le $max_attempts ]; do
    if kubectl cp "$temp_file" "$namespace/$pod:$output_dir/last_update.json" -c "$container" 2>/dev/null; then
      echo "✓ Successfully updated last_update.json with update_count: $new_update_count"
      
      # Verify the file was actually updated
      if kubectl exec -n $namespace $pod -c $container -- test -f "$output_dir/last_update.json" &>/dev/null; then
        echo "✓ Verified last_update.json exists in pod"
        rm -f "$temp_file"
        return 0
      else
        echo "WARNING: File copy appeared to succeed but last_update.json doesn't exist in pod"
      fi
    else
      echo "Attempt $attempt/$max_attempts: Failed to update last_update.json"
    fi
    
    # Check if container is still running
    local pod_status=$(kubectl get pod $pod -n $namespace -o jsonpath='{.status.phase}' 2>/dev/null)
    if [ "$pod_status" != "Running" ]; then
      echo "ERROR: Pod is no longer running (status: $pod_status)"
      kubectl describe pod $pod -n $namespace
      rm -f "$temp_file"
      return 1
    fi
    
    echo "Waiting 5 seconds before retry..."
    sleep 5
    attempt=$((attempt+1))
  done
  
  echo "WARNING: Failed to update last_update.json after $max_attempts attempts"
  echo "This may prevent the web interface from detecting new data"
  
  # Clean up
  rm -f "$temp_file"
  return 1
}

# Function to check container logs for errors
check_container_logs() {
  local namespace=$1
  local pod=$2
  local container=$3
  local lines=${4:-50}
  
  echo "Checking container logs for errors..."
  kubectl logs -n $namespace $pod -c $container --tail=$lines || {
    echo "WARNING: Could not retrieve container logs"
    return 1
  }
  
  # Check for specific error patterns
  echo "Analyzing logs for common error patterns..."
  local logs=$(kubectl logs -n $namespace $pod -c $container --tail=100 2>/dev/null)
  
  if echo "$logs" | grep -q "ImportError"; then
    echo "ERROR: Python import error detected. Missing dependencies?"
  fi
  
  if echo "$logs" | grep -q "FileNotFoundError"; then
    echo "ERROR: File not found error detected. Missing required files?"
  fi
  
  if echo "$logs" | grep -q "Permission"; then
    echo "ERROR: Permission error detected. Check file permissions."
  fi
  
  if echo "$logs" | grep -q "ConfigParser"; then
    echo "ERROR: Configuration parsing error detected. Check config file format."
  fi
  
  return 0
}

# Function to verify file exists in pod
verify_file_exists() {
  local namespace=$1
  local pod=$2
  local container=$3
  local filepath=$4
  
  echo "Verifying file exists: $filepath"
  if kubectl exec -n $namespace $pod -c $container -- test -f "$filepath" &>/dev/null; then
    echo "✓ File exists: $filepath"
    return 0
  else
    echo "✗ File does not exist: $filepath"
    return 1
  fi
}

# Function to restart deployment if needed
restart_deployment_if_needed() {
  local namespace=$1
  local deployment=$2
  local pod=$3
  
  echo "Checking if deployment restart is needed..."
  
  # Check if pod is in CrashLoopBackOff state
  local container_status=$(kubectl get pod $pod -n $namespace -o jsonpath="{.status.containerStatuses[?(@.name==\"web-interface\")].state}" 2>/dev/null)
  if echo "$container_status" | grep -q "waiting"; then
    local waiting_reason=$(kubectl get pod $pod -n $namespace -o jsonpath="{.status.containerStatuses[?(@.name==\"web-interface\")].state.waiting.reason}" 2>/dev/null)
    if [ "$waiting_reason" = "CrashLoopBackOff" ]; then
      echo "Container is in CrashLoopBackOff state. Attempting to restart the deployment..."
      
      # Get logs before restarting
      echo "Getting logs before restart..."
      kubectl logs -n $namespace $pod -c web-interface --tail=50 || true
      
      # Restart the deployment
      echo "Restarting deployment $deployment..."
      kubectl rollout restart deployment/$deployment -n $namespace
      
      # Wait for rollout to complete
      echo "Waiting for rollout to complete..."
      kubectl rollout status deployment/$deployment -n $namespace --timeout=180s
      
      # Get new pod name
      local new_pod=$(kubectl get pods -n $namespace -l app.kubernetes.io/name=ibm-ea-web-interface -o jsonpath="{.items[0].metadata.name}")
      echo "New pod name: $new_pod"
      
      # Return the new pod name
      echo "$new_pod"
      return 0
    fi
  fi
  
  # No restart needed, return the original pod name
  echo "$pod"
  return 0
}

echo -e "\n\033[1;32m📦 === PHASE 1: DEPLOYMENT WITH EMPTY FILES === 📦\033[0m"
echo -e "\033[1;32m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m"

# Cleanup any existing deployment
echo "Cleaning up any existing deployment..."
kubectl delete deployment $DEPLOYMENT_NAME -n $NAMESPACE --ignore-not-found=true
kubectl delete service $DEPLOYMENT_NAME -n $NAMESPACE --ignore-not-found=true
kubectl delete configmap web-interface-config -n $NAMESPACE --ignore-not-found=true
kubectl delete route $DEPLOYMENT_NAME -n $NAMESPACE --ignore-not-found=true 2>/dev/null || true

# Apply the modified deployment YAML with namespace replacement
echo "Applying deployment YAML to namespace '$NAMESPACE'..."
if [ -f "web-interface-deployment-modified.yaml" ]; then
  # Create a temporary YAML file with the correct namespace
  TEMP_YAML="/tmp/web-interface-deployment-${NAMESPACE}-$$.yaml"
  
  # Replace all occurrences of 'namespacenoi' with the actual namespace
  sed "s/namespace: namespacenoi/namespace: $NAMESPACE/g" web-interface-deployment-modified.yaml > "$TEMP_YAML"
  
  # Also replace any standalone 'namespacenoi' references
  sed -i.bak "s/namespacenoi/$NAMESPACE/g" "$TEMP_YAML"
  
  # Apply the modified YAML
  if kubectl apply -f "$TEMP_YAML"; then
    echo -e "\033[1;32m✅ Deployment YAML applied successfully\033[0m"
  else
    echo -e "\033[1;31m❌ ERROR: Failed to apply deployment YAML\033[0m"
    echo "Checking temporary YAML file for issues..."
    cat "$TEMP_YAML"
    rm -f "$TEMP_YAML" "${TEMP_YAML}.bak"
    exit 1
  fi
  
  # Clean up temporary file
  rm -f "$TEMP_YAML" "${TEMP_YAML}.bak"
else
  echo -e "\033[1;31m❌ ERROR: web-interface-deployment-modified.yaml not found!\033[0m"
  echo -e "\033[1;33m   Please ensure the YAML file exists in the current directory.\033[0m"
  exit 1
fi

# Wait for the pod to be created
echo "Waiting for pod to be created..."
show_progress 30 "Waiting for pod creation"

# Get the pod name
POD_NAME=$(kubectl get pods -n $NAMESPACE -l app.kubernetes.io/name=ibm-ea-web-interface -o jsonpath="{.items[0].metadata.name}")
echo "Pod name: $POD_NAME"

# Wait for the pod to be ready
echo "Waiting for pod to be ready..."
kubectl wait --for=condition=Ready pod/$POD_NAME -n $NAMESPACE --timeout=180s || {
  echo "Pod did not become ready in time according to Kubernetes. Will perform our own checks..."
}

# Wait for container to be available with enhanced checks
echo "Performing enhanced container readiness checks..."
if ! wait_for_container $NAMESPACE $POD_NAME "web-interface"; then
  echo "WARNING: Container may not be fully ready. Will proceed with caution and retry operations as needed."
else
  echo "Container is fully ready and operational!"
fi

# Create necessary directories in the pod
echo "Creating necessary directories in the pod..."
if ! ensure_directory_exists $NAMESPACE $POD_NAME "web-interface" "/opt/app"; then
  echo "WARNING: Failed to create /opt/app directory. Will try again later..."
fi

if ! ensure_directory_exists $NAMESPACE $POD_NAME "web-interface" "/opt/app/output"; then
  echo "WARNING: Failed to create /opt/app/output directory. Will try again later..."
fi

# Copy the original web_interface.py file
echo "Copying web_interface.py to the pod..."
copy_file $SOURCE_DIR/web_interface.py $NAMESPACE/$POD_NAME:/opt/app/web_interface.py

# Copy the static directory to the pod
echo "Copying static directory to the pod..."
copy_file $SOURCE_DIR/static/. $NAMESPACE/$POD_NAME:/opt/app/static/

# Copy the templates directory to the pod
echo "Copying templates directory to the pod..."
if ! ensure_directory_exists $NAMESPACE $POD_NAME "web-interface" "/opt/app/templates"; then
  echo "WARNING: Failed to create /opt/app/templates directory. Will try again..."
  sleep 5
  ensure_directory_exists $NAMESPACE $POD_NAME "web-interface" "/opt/app/templates"
fi
copy_file $SOURCE_DIR/templates/. $NAMESPACE/$POD_NAME:/opt/app/templates/

# Create config directory and ensure the configuration file is available (PRIORITY)
echo "Ensuring configuration file is available (PRIORITY)..."
if ! ensure_directory_exists $NAMESPACE $POD_NAME "web-interface" "/opt/app/config"; then
  echo "WARNING: Failed to create /opt/app/config directory. Will try again..."
  sleep 5
  ensure_directory_exists $NAMESPACE $POD_NAME "web-interface" "/opt/app/config"
fi

# Check if ConfigMap is properly mounted
if ! kubectl exec -n $NAMESPACE $POD_NAME -c web-interface -- test -f "/opt/app/config/web_interface_config.ini" &>/dev/null; then
  echo "WARNING: Configuration file not found in the pod. Copying it manually..."
  for attempt in {1..10}; do
    echo "Attempt $attempt to copy web_interface_config.ini..."
    if kubectl cp $SOURCE_DIR/web_interface_config.ini $NAMESPACE/$POD_NAME:/opt/app/config/web_interface_config.ini -c web-interface; then
      echo "✓ Successfully copied web_interface_config.ini"
      # Verify the file exists
      if kubectl exec -n $NAMESPACE $POD_NAME -c web-interface -- test -f "/opt/app/config/web_interface_config.ini" &>/dev/null; then
        echo "✓ Verified web_interface_config.ini exists in pod"
        break
      else
        echo "WARNING: web_interface_config.ini copy appeared to succeed but file doesn't exist in pod"
      fi
    else
      echo "Failed to copy web_interface_config.ini, retrying in 5 seconds..."
    fi
    
    if [ $attempt -eq 10 ]; then
      echo "ERROR: Failed to copy web_interface_config.ini after 10 attempts. Container may not start properly."
    fi
    
    sleep 5
  done
else
  echo "✓ Configuration file is properly mounted from ConfigMap"
fi

# Verify the configuration file content
echo "Verifying configuration file content..."
kubectl exec -n $NAMESPACE $POD_NAME -c web-interface -- cat "/opt/app/config/web_interface_config.ini" | head -5 || {
  echo "WARNING: Could not read configuration file. This may cause the application to fail."
}

# Create CSV files with headers
echo "Creating CSV files with headers..."
create_file_with_header $NAMESPACE $POD_NAME "web-interface" "/opt/app/event_instances_export.csv" "subscription;daykey;event_id;ftimestamp;id;ltimestamp;payload;severity"
create_file_with_header $NAMESPACE $POD_NAME "web-interface" "/opt/app/policies_events_export.csv" "tenantid;policyset;eventid;policies"
create_file_with_header $NAMESPACE $POD_NAME "web-interface" "/opt/app/policies_export.csv" "tenantid;partitionid;policyset;policyid;type;configuration;dynamic;groupid;issystem;isuser;metadata;metrics;resolver"
create_file_with_header $NAMESPACE $POD_NAME "web-interface" "/opt/app/users.csv" "username,password_hash"

# Create output directory files with headers
echo "Creating output directory files with headers..."
create_file_with_header $NAMESPACE $POD_NAME "web-interface" "/opt/app/output/policy_summary.csv" "policy_id,ranking_score,event_count,event_occurrences,policy_type,policy_set,group_id,event_ids_in_config"
create_file_with_header $NAMESPACE $POD_NAME "web-interface" "/opt/app/output/events_detail.csv" "event_id,policy_id,ranking_score"
create_file_with_header $NAMESPACE $POD_NAME "web-interface" "/opt/app/output/policy_events_payload.csv" "policy_id,ranking_score,event_id,timestamp,payload_details,payload_resource,payload_type,severity,summary,full_payload,note"

# Copy small JSON files
echo "Copying small JSON files..."
copy_file $SOURCE_DIR/output/condition_sets_by_policy.json $NAMESPACE/$POD_NAME:/opt/app/output/condition_sets_by_policy.json
copy_file $SOURCE_DIR/output/data_updated.signal $NAMESPACE/$POD_NAME:/opt/app/output/data_updated.signal
copy_file $SOURCE_DIR/output/last_update.json $NAMESPACE/$POD_NAME:/opt/app/output/last_update.json
copy_file $SOURCE_DIR/output/notification.json $NAMESPACE/$POD_NAME:/opt/app/output/notification.json

echo "Phase 1 complete. Web interface should now be starting with empty files."
echo "Waiting for web interface to be fully operational..."
show_progress 30 "Waiting for web interface startup"

echo -e "\n\033[1;35m📊 === PHASE 2: COPYING ACTUAL DATA === 📊\033[0m"
echo -e "\033[1;35m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m"

# Copy actual CSV files
echo "Copying actual CSV files..."
copy_file $SOURCE_DIR/users.csv $NAMESPACE/$POD_NAME:/opt/app/users.csv

# Copy actual output files (smaller ones first)
echo "Copying actual output files..."
copy_file $SOURCE_DIR/output/policy_summary.csv $NAMESPACE/$POD_NAME:/opt/app/output/policy_summary.csv
copy_file $SOURCE_DIR/output/events_detail.csv $NAMESPACE/$POD_NAME:/opt/app/output/events_detail.csv

# Try to copy larger files with extended timeout
echo "Attempting to copy larger files (this may take some time)..."
copy_file $SOURCE_DIR/policies_events_export.csv $NAMESPACE/$POD_NAME:/opt/app/policies_events_export.csv
copy_file $SOURCE_DIR/policies_export.csv $NAMESPACE/$POD_NAME:/opt/app/policies_export.csv

# Check for event_instances_export.csv and copy if it exists
echo "Checking for event_instances_export.csv file..."
if [ -f "$SOURCE_DIR/event_instances_export.csv" ]; then
  echo "Found event_instances_export.csv, copying to pod..."
  copy_file $SOURCE_DIR/event_instances_export.csv $NAMESPACE/$POD_NAME:/opt/app/event_instances_export.csv
else
  echo "event_instances_export.csv not found in source directory, using empty file with header"
fi

# Update last_update.json to trigger refresh
update_last_update_json $NAMESPACE $POD_NAME "web-interface"

# Copy policy_events_payload.csv if it exists
echo "Checking for policy_events_payload.csv file..."
if [ -f "$SOURCE_DIR/output/policy_events_payload.csv" ]; then
  echo "Found policy_events_payload.csv, copying to pod..."
  copy_file $SOURCE_DIR/output/policy_events_payload.csv $NAMESPACE/$POD_NAME:/opt/app/output/policy_events_payload.csv
else
  echo "policy_events_payload.csv not found in source directory, skipping"
fi

# Final verification step
echo -e "\n\033[1;33m🔍 === FINAL VERIFICATION === 🔍\033[0m"
echo -e "\033[1;33m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m"
echo "Checking pod status..."
kubectl get pod $POD_NAME -n $NAMESPACE

# Check if the container is in a BackOff state
CONTAINER_STATUS=$(kubectl get pod $POD_NAME -n $NAMESPACE -o jsonpath="{.status.containerStatuses[?(@.name==\"web-interface\")].state}" 2>/dev/null)
if echo "$CONTAINER_STATUS" | grep -q "waiting"; then
  WAITING_REASON=$(kubectl get pod $POD_NAME -n $NAMESPACE -o jsonpath="{.status.containerStatuses[?(@.name==\"web-interface\")].state.waiting.reason}" 2>/dev/null)
  if [ "$WAITING_REASON" = "CrashLoopBackOff" ]; then
    echo "ERROR: Container is in CrashLoopBackOff state. Checking logs for errors..."
    check_container_logs $NAMESPACE $POD_NAME "web-interface" 100
    
    echo "Possible solutions:"
    echo "1. Check if the configuration file is properly mounted"
    echo "2. Verify that all required files are present in the pod"
    echo "3. Check for Python dependencies issues"
    echo "4. Verify file permissions"
    echo ""
    echo "You can manually check the logs with:"
    echo "kubectl logs -n $NAMESPACE $POD_NAME -c web-interface"
  fi
else
  echo "✓ Container appears to be running normally"
  
  # Try to verify the web interface is responding
  echo "Checking if web interface is responding..."
  if kubectl exec -n $NAMESPACE $POD_NAME -c web-interface -- curl -s http://localhost:5000/ &>/dev/null; then
    echo "✓ Web interface is responding to requests!"
  else
    echo "WARNING: Web interface is not responding to local requests. It may still be starting up."
  fi
  
  # Verify critical files exist
  echo "Verifying critical files..."
  CRITICAL_FILES=(
    "/opt/app/web_interface.py"
    "/opt/app/config/web_interface_config.ini"
    "/opt/app/output/policy_summary.csv"
    "/opt/app/output/events_detail.csv"
    "/opt/app/output/last_update.json"
    "/opt/app/policies_export.csv"
    "/opt/app/policies_events_export.csv"
  )
  
  MISSING_FILES=0
  for file in "${CRITICAL_FILES[@]}"; do
    if ! verify_file_exists $NAMESPACE $POD_NAME "web-interface" "$file"; then
      MISSING_FILES=$((MISSING_FILES + 1))
    fi
  done
  
  if [ $MISSING_FILES -eq 0 ]; then
    echo "✓ All critical files are present in the pod"
  else
    echo "WARNING: $MISSING_FILES critical files are missing. The application may not function correctly."
  fi
fi

echo -e "\n\033[1;32m✅ Setup complete! ✅\033[0m"
echo -e "\033[1;32m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m"
echo -e "\033[1;36m🌐 The web interface should be available at:\033[0m"
echo -e "\033[1;36m   http://evtmanager-ibm-ea-web-interface.$NAMESPACE.svc:5000\033[0m"
echo ""

# Create route if user requested it
if [[ "$CREATE_ROUTE" == "y" || "$CREATE_ROUTE" == "Y" ]]; then
  echo -e "\033[1;34m🔄 Creating route for web interface...\033[0m"
  
  # Use oc expose command to create route (simpler and more reliable)
  if command -v oc &> /dev/null; then
    if oc expose service $DEPLOYMENT_NAME -n $NAMESPACE 2>/dev/null; then
      echo -e "\033[1;32m✅ Route created successfully!\033[0m"
    else
      # Route might already exist, try to get it
      echo "Route may already exist, checking..."
    fi
    
    # Get the route URL
    ROUTE_HOST=$(oc get route $DEPLOYMENT_NAME -n $NAMESPACE -o jsonpath='{.spec.host}' 2>/dev/null)
    if [ -n "$ROUTE_HOST" ]; then
      echo -e "\033[1;32m✅ Route is available!\033[0m"
      echo -e "\033[1;32m🌐 The web interface is accessible at: http://$ROUTE_HOST\033[0m"
    else
      echo -e "\033[1;33m⚠️  Could not retrieve route hostname. Please check with:\033[0m"
      echo -e "\033[1;33m   oc get route $DEPLOYMENT_NAME -n $NAMESPACE\033[0m"
    fi
  else
    echo -e "\033[1;33m⚠️  'oc' command not available. Cannot create OpenShift route.\033[0m"
    echo -e "\033[1;33m   You can create it manually with:\033[0m"
    echo -e "\033[1;33m   oc expose service $DEPLOYMENT_NAME -n $NAMESPACE\033[0m"
  fi
else
  echo -e "\033[1;36mℹ️ No route created. You can access the web interface using port-forwarding:\033[0m"
  echo -e "\033[1;36m   kubectl port-forward -n $NAMESPACE svc/$DEPLOYMENT_NAME 5000:5000\033[0m"
  echo -e "\033[1;36m   Or create a route with:\033[0m"
  echo -e "\033[1;36m   oc expose service $DEPLOYMENT_NAME -n $NAMESPACE\033[0m"
fi

