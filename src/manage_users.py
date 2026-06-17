#!/usr/bin/env python3
#
# Copyright IBM Corp. 2024 - 2026
# SPDX-License-Identifier: Apache-2.0
#
"""
manage_users.py - Utility for managing user credentials for the visualization web interface

This script allows you to:
1. Add new users with encrypted passwords
2. Update existing user passwords
3. Delete users
4. List all users

The passwords are stored as secure hashes using PBKDF2 with SHA-256.
"""

import os
import sys
import csv
import getpass
import hashlib
import secrets
import argparse
from typing import Dict, List, Tuple

# Configuration
USERS_FILE = "users.csv"
DEFAULT_ITERATIONS = 150000

def generate_salt() -> str:
    """Generate a random salt for password hashing"""
    return secrets.token_hex(8)

def hash_password(password: str, salt: str = "", iterations: int = DEFAULT_ITERATIONS) -> str:
    """
    Hash a password using PBKDF2 with SHA-256
    
    Args:
        password: The plaintext password to hash
        salt: Optional salt (will be generated if not provided)
        iterations: Number of iterations for PBKDF2
        
    Returns:
        String in format: pbkdf2:sha256:iterations$salt$hash
    """
    if not salt:
        salt = generate_salt()
        
    # Convert password to bytes
    password_bytes = password.encode('utf-8')
        
    # Hash the password
    hash_bytes = hashlib.pbkdf2_hmac(
        'sha256',
        password_bytes,
        salt.encode('utf-8'),
        iterations
    )
    
    # Convert to hex string
    hash_hex = hash_bytes.hex()
    
    # Return in the format: pbkdf2:sha256:iterations$salt$hash
    return f"pbkdf2:sha256:{iterations}${salt}${hash_hex}"

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
        # For backward compatibility with plain text passwords
        if not stored_hash.startswith("pbkdf2:"):
            return stored_hash == password
            
        # Parse the stored hash
        algorithm, iterations, salt, stored_hash_value = parse_hash(stored_hash)
        
        # Hash the provided password with the same parameters
        password_bytes = password.encode('utf-8')
        hash_bytes = hashlib.pbkdf2_hmac(
            'sha256',
            password_bytes,
            salt.encode('utf-8'),
            iterations
        )
        computed_hash = hash_bytes.hex()
        
        # Compare the hashes
        return computed_hash == stored_hash_value
    except Exception as e:
        print(f"Error verifying password: {e}")
        return False

def parse_hash(stored_hash: str) -> Tuple[str, int, str, str]:
    """Parse a stored hash into its components"""
    try:
        # Format: pbkdf2:sha256:iterations$salt$hash
        parts = stored_hash.split('$')
        if len(parts) != 3:
            raise ValueError("Hash should have 3 parts separated by $")
            
        algorithm_parts = parts[0].split(':')
        if len(algorithm_parts) != 3:
            raise ValueError("Algorithm part should have 3 components separated by :")
            
        algorithm = algorithm_parts[0] + ":" + algorithm_parts[1]  # pbkdf2:sha256
        iterations = int(algorithm_parts[2])  # iterations as integer
        salt = parts[1]  # salt
        hash_hex = parts[2]  # hash
        
        return algorithm, iterations, salt, hash_hex
    except Exception as e:
        raise ValueError(f"Invalid hash format: {e}")

def load_users() -> Dict[str, str]:
    """Load users from the CSV file"""
    users = {}
    
    if not os.path.exists(USERS_FILE):
        return users
        
    try:
        with open(USERS_FILE, 'r', newline='') as f:
            reader = csv.reader(f)
            # Skip header
            next(reader, None)
            for row in reader:
                if len(row) >= 2:
                    username, password_hash = row[0], row[1]
                    users[username] = password_hash
    except Exception as e:
        print(f"Error loading users: {e}")
        
    return users

def save_users(users: Dict[str, str]) -> bool:
    """Save users to the CSV file"""
    try:
        with open(USERS_FILE, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['username', 'password_hash'])
            for username, password_hash in users.items():
                writer.writerow([username, password_hash])
        return True
    except Exception as e:
        print(f"Error saving users: {e}")
        return False

def add_user(username: str, password: str = "") -> bool:
    """Add a new user or update an existing user"""
    users = load_users()
    
    if username in users:
        print(f"User '{username}' already exists. Updating password.")
    
    if not password:
        # Prompt for password if not provided
        password = getpass.getpass("Enter password: ")
        confirm = getpass.getpass("Confirm password: ")
        
        if password != confirm:
            print("Passwords do not match.")
            return False
    
    # Hash the password
    password_hash = hash_password(password)
    
    # Add or update the user
    users[username] = password_hash
    
    # Save the users
    if save_users(users):
        print(f"User '{username}' {'updated' if username in users else 'added'} successfully.")
        return True
    else:
        print(f"Failed to {'update' if username in users else 'add'} user '{username}'.")
        return False

def delete_user(username: str) -> bool:
    """Delete a user"""
    users = load_users()
    
    if username not in users:
        print(f"User '{username}' does not exist.")
        return False
    
    # Delete the user
    del users[username]
    
    # Save the users
    if save_users(users):
        print(f"User '{username}' deleted successfully.")
        return True
    else:
        print(f"Failed to delete user '{username}'.")
        return False

def list_users() -> None:
    """List all users"""
    users = load_users()
    
    if not users:
        print("No users found.")
        return
    
    print(f"Found {len(users)} users:")
    for username in users:
        print(f"- {username}")

def main() -> None:
    parser = argparse.ArgumentParser(description="Manage users for the visualization web interface")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # Add user command
    add_parser = subparsers.add_parser("add", help="Add a new user or update an existing user")
    add_parser.add_argument("username", help="Username")
    add_parser.add_argument("--password", help="Password (will prompt if not provided)")
    
    # Delete user command
    delete_parser = subparsers.add_parser("delete", help="Delete a user")
    delete_parser.add_argument("username", help="Username to delete")
    
    # List users command
    list_parser = subparsers.add_parser("list", help="List all users")
    
    # Verify password command
    verify_parser = subparsers.add_parser("verify", help="Verify a password")
    verify_parser.add_argument("username", help="Username")
    verify_parser.add_argument("--password", help="Password (will prompt if not provided)")
    
    args = parser.parse_args()
    
    # Create users file if it doesn't exist
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['username', 'password_hash'])
        print(f"Created new users file: {USERS_FILE}")
    
    if args.command == "add":
        add_user(args.username, args.password)
    elif args.command == "delete":
        delete_user(args.username)
    elif args.command == "list":
        list_users()
    elif args.command == "verify":
        users = load_users()
        if args.username not in users:
            print(f"User '{args.username}' does not exist.")
            return
            
        password = args.password
        if password is None:
            password = getpass.getpass("Enter password: ")
            
        if verify_password(users[args.username], password):
            print("Password is correct.")
        else:
            print("Password is incorrect.")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()

