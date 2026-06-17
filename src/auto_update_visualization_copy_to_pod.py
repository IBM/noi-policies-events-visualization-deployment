#!/usr/bin/env python3
#
# Copyright IBM Corp. 2024 - 2026
# SPDX-License-Identifier: Apache-2.0
#
"""
auto_update_visualization_copy_to_pod.py
---------------------------------
Automated data pipeline script that:
1. Extracts data from Cassandra
2. Processes the data using the existing processing script
3. Updates the web server with new files
4. Copies the resulting files to visualization pod(s)
5. Runs on a configurable schedule

This script can be run manually or as a scheduled job to keep
the visualization up to date with the latest data in Cassandra.

Features:
- Auto-detects if running in a Kubernetes pod without 'oc' command
- Can use either shell script or Python script for data extraction
- Configurable via config file or command line arguments
- Supports retry logic for resilience
- Provides notifications and logging for monitoring
- Automatically finds and updates visualization pods

Configuration options for script selection:
- force_python_script = 'auto' (default): Auto-detect environment
- force_python_script = 'true': Always use Python script
- force_python_script = 'false': Always use shell script
"""

import os
import sys
import time
import json
import argparse
import logging
import subprocess
import shutil
import datetime
import configparser
from pathlib import Path
from typing import Dict, List, Optional, Any, Union, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('auto_update_visualization_copy_to_pod.log')
    ]
)
logger = logging.getLogger('auto_update_visualization_copy_to_pod')

def send_notification(config: configparser.ConfigParser, level: str, message: str) -> None:
    """Send a notification about the update process
    
    This is a placeholder function that can be expanded to send notifications
    via email, Slack, or other channels as needed.
    """
    logger.info(f"Notification [{level}]: {message}")
    
    # Write to notification file for web interface
    try:
        output_dir = config.get('general', 'output_dir')
        os.makedirs(output_dir, exist_ok=True)
        notification_file = os.path.join(output_dir, "notification.json")
        with open(notification_file, 'w') as f:
            json.dump({
                "level": level,
                "message": message,
                "timestamp": datetime.datetime.now().isoformat()
            }, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to write notification: {e}")

# Default configuration
DEFAULT_CONFIG = {
    'general': {
        'update_interval_minutes': '60',
        'output_dir': 'output',
        'timestamp_file': 'last_update.json',
        'max_retries': '3',
        'retry_delay_seconds': '30'
    },
    'cassandra': {
        'local_mode': 'false',
        'reuse_csv': 'false',
        'force_python_script': 'auto'  # 'auto', 'true', or 'false'
    },
    'ocp': {
        'namespace': '',  # Will be auto-detected if empty
        'release_name': '',  # Will be auto-detected if empty
        'deployment_name': 'evtmanager-ea-web-interface',  # Default deployment name
        'container_name': 'web-interface'  # Default container name
    }
}

def load_config(config_path: str) -> configparser.ConfigParser:
    """Load configuration from file or create default if not exists"""
    config = configparser.ConfigParser()
    
    # Set default configuration
    for section, options in DEFAULT_CONFIG.items():
        if not config.has_section(section):
            config.add_section(section)
        for option, value in options.items():
            config.set(section, option, value)
    
    # Try to load from file
    if os.path.exists(config_path):
        logger.info(f"Loading configuration from {config_path}")
        config.read(config_path)
    else:
        logger.info(f"No configuration file found at {config_path}, creating default")
        with open(config_path, 'w') as f:
            config.write(f)
    
    return config

def save_timestamp(timestamp_file: str, data: Dict[str, Any]) -> None:
    """Save timestamp information to a JSON file"""
    with open(timestamp_file, 'w') as f:
        json.dump(data, f, indent=2)
    
    # Also write to a change notification file for the web interface
    try:
        output_dir = os.path.dirname(timestamp_file)
        os.makedirs(output_dir, exist_ok=True)
        # Ensure the output directory exists
        logger.info(f"Writing change notification to directory: {output_dir}")
        change_file = os.path.join(output_dir, "data_updated.signal")
        with open(change_file, 'w') as f:
            f.write(json.dumps({
                "timestamp": datetime.datetime.now().isoformat(),
                "update_count": data.get("update_count", 0),
                "status": data.get("last_status", "unknown")
            }))
        logger.info(f"Wrote change notification to {change_file}")
    except Exception as e:
        logger.error(f"Failed to write change notification: {e}")

def load_timestamp(timestamp_file: str) -> Dict[str, Any]:
    """Load timestamp information from a JSON file"""
    if os.path.exists(timestamp_file):
        with open(timestamp_file, 'r') as f:
            return json.load(f)
    return {
        'last_update': None,
        'update_count': 0,
        'last_status': 'none'
    }

def is_oc_available() -> bool:
    """Check if the 'oc' command is available"""
    try:
        result = subprocess.run(['which', 'oc'], check=False, capture_output=True, text=True)
        return result.returncode == 0
    except Exception:
        return False

def is_kubectl_available() -> bool:
    """Check if the 'kubectl' command is available"""
    try:
        result = subprocess.run(['which', 'kubectl'], check=False, capture_output=True, text=True)
        return result.returncode == 0
    except Exception:
        return False

def is_running_in_pod() -> bool:
    """Check if we're running inside a Kubernetes pod"""
    return os.path.exists('/var/run/secrets/kubernetes.io/serviceaccount')

def extract_data_from_cassandra(config: configparser.ConfigParser) -> bool:
    """Extract data from Cassandra using the appropriate script"""
    logger.info("Starting data extraction from Cassandra")
    
    # Determine which script to use
    force_python = config.get('cassandra', 'force_python_script').lower()
    
    use_python_script = False
    if force_python == 'true':
        use_python_script = True
        logger.info("Using Python script as configured")
    elif force_python == 'auto':
        # Auto-detect: use Python script if in pod without oc
        in_pod = is_running_in_pod()
        has_oc = is_oc_available()
        
        if in_pod and not has_oc:
            use_python_script = True
            logger.info("Auto-detected running in pod without 'oc' command, using Python script")
        else:
            logger.info(f"Auto-detected environment: in_pod={in_pod}, has_oc={has_oc}, using shell script")
    else:
        logger.info("Using shell script as configured")
    
    # Get OCP namespace and release name from config
    namespace = config.get('ocp', 'namespace', fallback='')
    release_name = config.get('ocp', 'release_name', fallback='')
    
    # Prepare command based on script selection and environment
    env = os.environ.copy()  # Always create env copy to avoid unbound variable
    
    if use_python_script:
        cmd = ['python3', './copy_policies_details_from_cassandra.py']
        
        # Add namespace and release name as environment variables for Python script
        if namespace:
            env['OCP_NAMESPACE'] = namespace
            logger.info(f"Using namespace from config: {namespace}")
        if release_name:
            env['OCP_RELEASE_NAME'] = release_name
            logger.info(f"Using release name from config: {release_name}")
    else:
        cmd = ['./copy_policies_details_from_cassandra.sh']
        
        # Add namespace and release name as parameters for shell script
        if namespace:
            cmd.extend(['--namespace', namespace])
            logger.info(f"Using namespace from config: {namespace}")
        if release_name:
            cmd.extend(['--release', release_name])
            logger.info(f"Using release name from config: {release_name}")
    
    # Add options based on configuration
    if config.getboolean('cassandra', 'local_mode'):
        cmd.append('--local')
    
    if config.getboolean('cassandra', 'reuse_csv'):
        cmd.append('--reuse')
    
    try:
        logger.info(f"Executing command: {' '.join(cmd)}")
        # Always use the environment variables we prepared
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, env=env)
        logger.info("Data extraction completed successfully")
        logger.debug(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Data extraction failed: {e}")
        logger.error(f"STDOUT: {e.stdout}")
        logger.error(f"STDERR: {e.stderr}")
        return False

def process_data(config: configparser.ConfigParser) -> bool:
    """Process the extracted data using the processing script"""
    logger.info("Starting data processing")
    
    cmd = ['python3', 'process_policies_and_events.py']
    
    try:
        logger.info(f"Executing command: {' '.join(cmd)}")
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        logger.info("Data processing completed successfully")
        logger.debug(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Data processing failed: {e}")
        logger.error(f"STDOUT: {e.stdout}")
        logger.error(f"STDERR: {e.stderr}")
        return False

def get_pod_names(namespace: str, deployment_name: str) -> List[str]:
    """Get the names of all pods for a given deployment"""
    logger.info(f"Getting pod names for deployment {deployment_name} in namespace {namespace}")
    
    # Check if kubectl or oc is available
    cmd_base = 'kubectl' if is_kubectl_available() else 'oc' if is_oc_available() else None
    
    if not cmd_base:
        logger.error("Neither kubectl nor oc command is available")
        return []
    
    try:
        # Get pod names using kubectl/oc
        cmd = [cmd_base, 'get', 'pods', '-n', namespace, '-l', f'app.kubernetes.io/name={deployment_name}', '-o', 'jsonpath={.items[*].metadata.name}']
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        
        # Split the output by spaces to get individual pod names
        pod_names = result.stdout.strip().split()
        
        if not pod_names:
            logger.warning(f"No pods found for deployment {deployment_name} in namespace {namespace}")
            return []
        
        logger.info(f"Found {len(pod_names)} pod(s): {', '.join(pod_names)}")
        return pod_names
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to get pod names: {e}")
        logger.error(f"STDERR: {e.stderr}")
        return []

def copy_file_to_pod(namespace: str, pod_name: str, container_name: str, src_path: str, dest_path: str, max_retries: int = 3, retry_delay: int = 5) -> bool:
    """Copy a file to a pod with retry logic"""
    logger.info(f"Copying {src_path} to {pod_name}:{dest_path}")
    
    # Check if kubectl or oc is available
    cmd_base = 'kubectl' if is_kubectl_available() else 'oc' if is_oc_available() else None
    
    if not cmd_base:
        logger.error("Neither kubectl nor oc command is available")
        return False
    
    # Ensure source file exists
    if not os.path.exists(src_path):
        logger.error(f"Source file {src_path} does not exist")
        return False
    
    for attempt in range(1, max_retries + 1):
        try:
            # Create destination directory if needed
            dest_dir = os.path.dirname(dest_path)
            mkdir_cmd = [cmd_base, 'exec', '-n', namespace, pod_name, '-c', container_name, '--', 'mkdir', '-p', dest_dir]
            subprocess.run(mkdir_cmd, check=True, capture_output=True, text=True)
            
            # Copy the file
            cp_cmd = [cmd_base, 'cp', src_path, f"{namespace}/{pod_name}:{dest_path}", '-c', container_name]
            subprocess.run(cp_cmd, check=True, capture_output=True, text=True)
            
            logger.info(f"Successfully copied {src_path} to {pod_name}:{dest_path}")
            return True
        except subprocess.CalledProcessError as e:
            logger.warning(f"Attempt {attempt}/{max_retries} failed: {e}")
            if attempt < max_retries:
                logger.info(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                logger.error(f"Failed to copy file after {max_retries} attempts")
                logger.error(f"STDERR: {e.stderr}")
                return False
    
    return False

def copy_files_to_pods(config: configparser.ConfigParser) -> bool:
    """Copy all necessary files to visualization pods"""
    logger.info("Starting to copy files to visualization pods")
    
    # Get configuration values
    namespace = config.get('ocp', 'namespace')
    deployment_name = config.get('ocp', 'deployment_name')
    container_name = config.get('ocp', 'container_name')
    output_dir = config.get('general', 'output_dir')
    max_retries = config.getint('general', 'max_retries')
    retry_delay = config.getint('general', 'retry_delay_seconds')
    
    # Get pod names
    pod_names = get_pod_names(namespace, deployment_name)
    if not pod_names:
        logger.error("No pods found to copy files to")
        return False
    
    # Files to copy
    files_to_copy = [
        # Main CSV files
        ('policies_export.csv', '/opt/app/policies_export.csv'),
        ('policies_events_export.csv', '/opt/app/policies_events_export.csv'),
        ('event_instances_export.csv', '/opt/app/event_instances_export.csv'),
        
        # Output directory files
        (os.path.join(output_dir, 'policy_summary.csv'), '/opt/app/output/policy_summary.csv'),
        (os.path.join(output_dir, 'events_detail.csv'), '/opt/app/output/events_detail.csv'),
        (os.path.join(output_dir, 'policy_events_payload.csv'), '/opt/app/output/policy_events_payload.csv'),
        (os.path.join(output_dir, 'condition_sets_by_policy.json'), '/opt/app/output/condition_sets_by_policy.json'),
        (os.path.join(output_dir, 'last_update.json'), '/opt/app/output/last_update.json'),
        (os.path.join(output_dir, 'data_updated.signal'), '/opt/app/output/data_updated.signal'),
        (os.path.join(output_dir, 'notification.json'), '/opt/app/output/notification.json')
    ]
    
    # Copy files to each pod
    success = True
    for pod_name in pod_names:
        logger.info(f"Copying files to pod {pod_name}")
        
        for src_path, dest_path in files_to_copy:
            # Skip if source file doesn't exist
            if not os.path.exists(src_path):
                logger.warning(f"Source file {src_path} does not exist, skipping")
                continue
                
            if not copy_file_to_pod(namespace, pod_name, container_name, src_path, dest_path, max_retries, retry_delay):
                logger.error(f"Failed to copy {src_path} to {pod_name}:{dest_path}")
                success = False
    
    if success:
        logger.info("Successfully copied all files to all pods")
    else:
        logger.warning("Some files could not be copied to pods")
    
    return success

def run_update_process(config: configparser.ConfigParser) -> bool:
    """Run the complete update process"""
    # Ensure output directory exists
    output_dir = config.get('general', 'output_dir')
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp_file = os.path.join(output_dir, config.get('general', 'timestamp_file'))
    timestamp_data = load_timestamp(timestamp_file)
    
    # Update timestamp data
    timestamp_data['last_update'] = datetime.datetime.now().isoformat()
    timestamp_data['update_count'] += 1
    
    success = True
    max_retries = config.getint('general', 'max_retries')
    retry_delay = config.getint('general', 'retry_delay_seconds')
    
    # Extract data from Cassandra
    for attempt in range(1, max_retries + 1):
        if extract_data_from_cassandra(config):
            break
        elif attempt < max_retries:
            logger.info(f"Retrying data extraction (attempt {attempt+1}/{max_retries})...")
            time.sleep(retry_delay)
        else:
            success = False
            timestamp_data['last_status'] = 'extraction_failed'
            save_timestamp(timestamp_file, timestamp_data)
            send_notification(config, 'error', 'Data extraction from Cassandra failed')
            return False
    
    # Process the data
    for attempt in range(1, max_retries + 1):
        if process_data(config):
            break
        elif attempt < max_retries:
            logger.info(f"Retrying data processing (attempt {attempt+1}/{max_retries})...")
            time.sleep(retry_delay)
        else:
            success = False
            timestamp_data['last_status'] = 'processing_failed'
            save_timestamp(timestamp_file, timestamp_data)
            send_notification(config, 'error', 'Data processing failed')
            return False
    
    # Copy files to pods
    for attempt in range(1, max_retries + 1):
        if copy_files_to_pods(config):
            break
        elif attempt < max_retries:
            logger.info(f"Retrying file copying to pods (attempt {attempt+1}/{max_retries})...")
            time.sleep(retry_delay)
        else:
            success = False
            timestamp_data['last_status'] = 'pod_copy_failed'
            save_timestamp(timestamp_file, timestamp_data)
            send_notification(config, 'error', 'Copying files to pods failed')
            return False
    
    # All steps completed successfully
    if success:
        timestamp_data['last_status'] = 'success'
        save_timestamp(timestamp_file, timestamp_data)
        send_notification(config, 'success', 'Visualization updated successfully and copied to pods')
        return True
    
    return False

def run_scheduled_updates(config: configparser.ConfigParser) -> None:
    """Run updates on a schedule based on the configuration"""
    update_interval = config.getint('general', 'update_interval_minutes')
    logger.info(f"Starting scheduled updates every {update_interval} minutes")
    
    try:
        while True:
            logger.info("Running scheduled update")
            run_update_process(config)
            
            next_update = datetime.datetime.now() + datetime.timedelta(minutes=update_interval)
            logger.info(f"Next update scheduled for {next_update.strftime('%Y-%m-%d %H:%M:%S')}")
            
            # Sleep until next update
            time.sleep(update_interval * 60)
    except KeyboardInterrupt:
        logger.info("Scheduled updates stopped by user")

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Automated data pipeline for policy and event visualization with pod updates",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run once with auto-detection of script type
  python auto_update_visualization_copy_to_pod.py --run-once
  
  # Run scheduled updates using Python script for extraction
  python auto_update_visualization_copy_to_pod.py --schedule --use-python-script true
  
  # Run with custom config file and specific deployment
  python auto_update_visualization_copy_to_pod.py --config my_config.ini --run-once --deployment-name my-web-interface
"""
    )
    parser.add_argument("--config", default="auto_update_config.ini",
                      help="Path to configuration file (default: auto_update_config.ini)")
    parser.add_argument("--run-once", action="store_true",
                      help="Run the update process once and exit")
    parser.add_argument("--schedule", action="store_true",
                      help="Run updates on a schedule based on configuration")
    parser.add_argument("--use-python-script", choices=["auto", "true", "false"],
                      default=None,
                      help="""Whether to use Python script instead of shell script for data extraction:
                            'auto': Auto-detect based on environment (default)
                            'true': Always use Python script
                            'false': Always use shell script""")
    parser.add_argument("--namespace", default=None,
                      help="Kubernetes namespace where visualization pods are running")
    parser.add_argument("--deployment-name", default=None,
                      help="Name of the deployment for visualization pods")
    parser.add_argument("--container-name", default=None,
                      help="Name of the container in the visualization pods")
    args = parser.parse_args()
    
    # Load configuration
    config = load_config(args.config)
    
    # Override configuration with command line arguments if provided
    if args.use_python_script is not None:
        config.set('cassandra', 'force_python_script', args.use_python_script)
        logger.info(f"Script selection overridden by command line: {args.use_python_script}")
    
    if args.namespace is not None:
        config.set('ocp', 'namespace', args.namespace)
        logger.info(f"Namespace overridden by command line: {args.namespace}")
    
    if args.deployment_name is not None:
        config.set('ocp', 'deployment_name', args.deployment_name)
        logger.info(f"Deployment name overridden by command line: {args.deployment_name}")
    
    if args.container_name is not None:
        config.set('ocp', 'container_name', args.container_name)
        logger.info(f"Container name overridden by command line: {args.container_name}")
    
    # Check if namespace is provided
    if not config.get('ocp', 'namespace'):
        logger.error("Namespace must be provided either in config file or via --namespace argument")
        sys.exit(1)
    
    if args.run_once:
        logger.info("Running update process once")
        run_update_process(config)
    else:
        run_scheduled_updates(config)

if __name__ == "__main__":
    main()

