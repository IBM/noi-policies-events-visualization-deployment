#!/usr/bin/env python3
#
# Copyright IBM Corp.  2026
# SPDX-License-Identifier: Apache-2.0
#
"""
Test script for Policy and Event Data Visualization API endpoints.

This script validates all API endpoints documented in docs/API.md.
It can be run with or without authentication enabled.

Usage:
    python test_api_endpoints.py [--host HOST] [--port PORT] [--username USER] [--password PASS]

Examples:
    # Test without authentication
    python test_api_endpoints.py

    # Test with authentication
    python test_api_endpoints.py --username admin --password password

    # Test remote server
    python test_api_endpoints.py --host 192.168.1.100 --port 8080
"""

import argparse
import json
import sys
import urllib.request
import urllib.error
import urllib.parse
import base64
from typing import Dict, Optional, Tuple, Any


class Colors:
    """ANSI color codes for terminal output"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


class APITester:
    """Test all API endpoints"""
    
    def __init__(self, host: str, port: int, username: Optional[str] = None, 
                 password: Optional[str] = None):
        self.base_url = f"http://{host}:{port}"
        self.username = username
        self.password = password
        self.auth_header = None
        
        if username and password:
            credentials = f"{username}:{password}"
            encoded = base64.b64encode(credentials.encode()).decode()
            self.auth_header = f"Basic {encoded}"
        
        self.passed = 0
        self.failed = 0
        self.skipped = 0
    
    def _make_request(self, method: str, path: str, data: Optional[Dict] = None,
                     headers: Optional[Dict] = None) -> Tuple[int, Any, str]:
        """Make HTTP request and return status, response data, and error message"""
        url = f"{self.base_url}{path}"
        
        req_headers = headers or {}
        if self.auth_header:
            req_headers['Authorization'] = self.auth_header
        
        try:
            if data:
                req_headers['Content-Type'] = 'application/json'
                data_bytes = json.dumps(data).encode('utf-8')
                request = urllib.request.Request(url, data=data_bytes, headers=req_headers, method=method)
            else:
                request = urllib.request.Request(url, headers=req_headers, method=method)
            
            with urllib.request.urlopen(request, timeout=10) as response:
                status = response.status
                content_type = response.headers.get('Content-Type', '')
                
                if 'application/json' in content_type:
                    response_data = json.loads(response.read().decode('utf-8'))
                else:
                    response_data = response.read().decode('utf-8')
                
                return status, response_data, ""
                
        except urllib.error.HTTPError as e:
            try:
                error_data = json.loads(e.read().decode('utf-8'))
                return e.code, error_data, str(error_data.get('error', e.reason))
            except:
                return e.code, None, str(e.reason)
        except Exception as e:
            return 0, None, str(e)
    
    def _print_test(self, name: str, passed: bool, message: str = ""):
        """Print test result"""
        if passed:
            print(f"{Colors.GREEN}✓{Colors.RESET} {name}")
            if message:
                print(f"  {Colors.BLUE}→{Colors.RESET} {message}")
            self.passed += 1
        else:
            print(f"{Colors.RED}✗{Colors.RESET} {name}")
            if message:
                print(f"  {Colors.RED}→{Colors.RESET} {message}")
            self.failed += 1
    
    def _print_skip(self, name: str, reason: str):
        """Print skipped test"""
        print(f"{Colors.YELLOW}⊘{Colors.RESET} {name}")
        print(f"  {Colors.YELLOW}→{Colors.RESET} {reason}")
        self.skipped += 1
    
    def _print_section(self, title: str):
        """Print section header"""
        print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.BLUE}{title}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}\n")
    
    def test_static_assets(self):
        """Test static file serving"""
        self._print_section("Static Assets")
        
        # Test main page
        status, data, error = self._make_request("GET", "/")
        self._print_test(
            "GET / (main page)",
            status in (200, 302),  # 200 OK or 302 redirect to login
            f"Status: {status}"
        )
        
        # Test static files
        static_files = [
            "/static/app.js",
            "/static/styles.css",
            "/static/advanced-filter.js",
            "/static/config-handler.js"
        ]
        
        for file_path in static_files:
            status, data, error = self._make_request("GET", file_path)
            self._print_test(
                f"GET {file_path}",
                status == 200,
                error if status != 200 else f"Status: {status}"
            )
    
    def test_authentication_endpoints(self):
        """Test authentication endpoints"""
        self._print_section("Authentication Endpoints")
        
        # Test config endpoint (should work without auth)
        status, data, error = self._make_request("GET", "/api/config")
        self._print_test(
            "GET /api/config",
            status == 200 and 'APP_CONFIG' in str(data),
            error if status != 200 else "Config loaded successfully"
        )
        
        # Test register endpoint (if auth is enabled)
        test_user = f"test_user_{int(time.time())}"
        status, data, error = self._make_request(
            "POST", "/api/register",
            {"username": test_user, "password": "test123456"}
        )
        
        if status == 400 and "disabled" in error.lower():
            self._print_skip(
                "POST /api/register",
                "Authentication is disabled on server (set ENABLE_AUTH=true to test)"
            )
        else:
            self._print_test(
                "POST /api/register",
                status in (200, 400),  # 200 success or 400 if user exists
                error if status not in (200, 400) else f"Status: {status}"
            )
        
        # Test login endpoint
        if self.username and self.password:
            status, data, error = self._make_request(
                "POST", "/api/login",
                None,
                {'Content-Type': 'application/x-www-form-urlencoded'}
            )
            self._print_test(
                "POST /api/login",
                status in (200, 302),  # Success or redirect
                error if status not in (200, 302) else f"Status: {status}"
            )
        else:
            self._print_skip("POST /api/login", "No credentials provided")
    
    def test_data_endpoints(self):
        """Test data retrieval endpoints"""
        self._print_section("Data Endpoints (Server-Side)")
        
        # Test policies endpoint
        params = "?draw=1&start=0&length=10"
        status, data, error = self._make_request("GET", f"/api/policies_ss{params}")
        policies_count = len(data.get('data', [])) if isinstance(data, dict) else 0
        self._print_test(
            "GET /api/policies_ss",
            status == 200 and isinstance(data, dict) and 'data' in data,
            error if status != 200 else f"Returned {policies_count} policies"
        )
        
        # Test events endpoint
        status, data, error = self._make_request("GET", f"/api/events_ss{params}")
        events_count = len(data.get('data', [])) if isinstance(data, dict) else 0
        self._print_test(
            "GET /api/events_ss",
            status == 200 and isinstance(data, dict) and 'data' in data,
            error if status != 200 else f"Returned {events_count} events"
        )
        
        # Note: /api/event_instances_ss is deprecated (SQLite mode no longer used)
    
    def test_legacy_endpoints(self):
        """Test legacy data endpoints"""
        self._print_section("Legacy Data Endpoints")
        
        # Test legacy policies
        status, data, error = self._make_request("GET", "/api/policies")
        policies_count = len(data) if isinstance(data, list) else 0
        self._print_test(
            "GET /api/policies (legacy)",
            status == 200 and isinstance(data, list),
            error if status != 200 else f"Returned {policies_count} policies"
        )
        
        # Test legacy events
        status, data, error = self._make_request("GET", "/api/events")
        events_count = len(data) if isinstance(data, list) else 0
        self._print_test(
            "GET /api/events (legacy)",
            status == 200 and isinstance(data, list),
            error if status != 200 else f"Returned {events_count} events"
        )
        
        # Test legacy payloads
        status, data, error = self._make_request("GET", "/api/payloads")
        payloads_count = len(data) if isinstance(data, list) else 0
        self._print_test(
            "GET /api/payloads (legacy)",
            status == 200 and isinstance(data, list),
            error if status != 200 else f"Returned {payloads_count} payloads"
        )
    
    def test_utility_endpoints(self):
        """Test utility endpoints"""
        self._print_section("Utility Endpoints")
        
        # Test last update
        status, data, error = self._make_request("GET", "/api/last_update")
        last_update = data.get('last_update', 'N/A') if isinstance(data, dict) else 'N/A'
        self._print_test(
            "GET /api/last_update",
            status == 200 and isinstance(data, dict),
            error if status != 200 else f"Last update: {last_update}"
        )
        
        # Test deploy cache GET
        status, data, error = self._make_request("GET", "/api/deploy_cache")
        cache_size = len(data.get('ids', [])) if isinstance(data, dict) else 0
        self._print_test(
            "GET /api/deploy_cache",
            status == 200 and isinstance(data, dict) and 'ids' in data,
            error if status != 200 else f"Cache has {cache_size} items"
        )
    
    def test_advanced_filtering(self):
        """Test advanced filtering"""
        self._print_section("Advanced Filtering")
        
        # Test with advanced filter
        filter_json = json.dumps({
            "conditions": [
                {"column": "Severity", "operator": ">", "value": "3"}
            ],
            "logic": "AND"
        })
        
        params = f"?draw=1&start=0&length=10&advancedFilter={urllib.parse.quote(filter_json)}"
        status, data, error = self._make_request("GET", f"/api/events_ss{params}")
        filtered_count = len(data.get('data', [])) if isinstance(data, dict) else 0
        self._print_test(
            "GET /api/events_ss with advanced filter",
            status == 200 and isinstance(data, dict) and 'data' in data,
            error if status != 200 else f"Filtered to {filtered_count} events"
        )
    
    def test_pattern_endpoints(self):
        """Test pattern configuration endpoints"""
        self._print_section("Pattern Configuration")
        
        # First get a policy ID
        status, data, error = self._make_request("GET", "/api/policies_ss?draw=1&start=0&length=1")
        
        if status == 200 and isinstance(data, dict) and data.get('data'):
            # Try both field names (policy_id and policyId for compatibility)
            policy_id = data['data'][0].get('policy_id') or data['data'][0].get('policyId')
            if policy_id:
                # Test pattern config
                status, data, error = self._make_request("GET", f"/api/pattern_config/{policy_id}")
                self._print_test(
                    f"GET /api/pattern_config/{policy_id[:8]}...",
                    status in (200, 404),  # 200 if exists, 404 if no pattern config
                    error if status not in (200, 404) else f"Status: {status}"
                )
                
                # Test payload preview
                status, data, error = self._make_request("GET", f"/api/payload_preview/{policy_id}")
                self._print_test(
                    f"GET /api/payload_preview/{policy_id[:8]}...",
                    status in (200, 404),
                    error if status not in (200, 404) else f"Status: {status}"
                )
            else:
                self._print_skip("Pattern endpoints", "No policy ID available")
        else:
            self._print_skip("Pattern endpoints", "Could not fetch policies")
    
    def _verify_credentials(self) -> bool:
        """Verify that credentials are correct before running tests"""
        if not self.username:
            return True  # No auth, skip check
        
        # Try to access a protected endpoint
        status, data, error = self._make_request("GET", "/api/config")
        
        if status == 401 or (status == 200 and isinstance(data, str) and '<!DOCTYPE html>' in data):
            # 401 or HTML login page means auth failed
            print(f"\n{Colors.RED}{Colors.BOLD}✗ Authentication Failed{Colors.RESET}")
            print(f"{Colors.RED}Invalid username or password: {self.username}:***{Colors.RESET}")
            print(f"{Colors.YELLOW}Hint: Check your credentials and try again{Colors.RESET}\n")
            return False
        elif status == 200:
            # Successfully authenticated
            print(f"{Colors.GREEN}✓ Credentials verified{Colors.RESET}")
            return True
        else:
            # Other error (server down, etc.)
            print(f"{Colors.YELLOW}⚠ Could not verify credentials (server may be down){Colors.RESET}")
            return True  # Continue anyway
    
    def run_all_tests(self):
        """Run all API endpoint tests"""
        print(f"\n{Colors.BOLD}{'='*60}{Colors.RESET}")
        print(f"{Colors.BOLD}API Endpoint Test Suite{Colors.RESET}")
        print(f"{Colors.BOLD}Testing: {self.base_url}{Colors.RESET}")
        if self.username:
            print(f"{Colors.BOLD}Auth: Enabled (user: {self.username}){Colors.RESET}")
        else:
            print(f"{Colors.BOLD}Auth: Disabled{Colors.RESET}")
        print(f"{Colors.BOLD}{'='*60}{Colors.RESET}")
        
        # Verify credentials if authentication is enabled
        if self.username and not self._verify_credentials():
            return 1  # Exit with error code
        
        # Run test suites
        self.test_static_assets()
        self.test_authentication_endpoints()
        self.test_data_endpoints()
        self.test_legacy_endpoints()
        self.test_utility_endpoints()
        self.test_advanced_filtering()
        self.test_pattern_endpoints()
        
        # Print summary
        print(f"\n{Colors.BOLD}{'='*60}{Colors.RESET}")
        print(f"{Colors.BOLD}Test Summary{Colors.RESET}")
        print(f"{Colors.BOLD}{'='*60}{Colors.RESET}")
        print(f"{Colors.GREEN}Passed:{Colors.RESET}  {self.passed}")
        print(f"{Colors.RED}Failed:{Colors.RESET}  {self.failed}")
        print(f"{Colors.YELLOW}Skipped:{Colors.RESET} {self.skipped}")
        print(f"{Colors.BOLD}Total:{Colors.RESET}   {self.passed + self.failed + self.skipped}")
        print(f"{Colors.BOLD}{'='*60}{Colors.RESET}\n")
        
        # Return exit code
        return 0 if self.failed == 0 else 1


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Test Policy and Event Data Visualization API endpoints",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test without authentication
  python test_api_endpoints.py

  # Test with authentication
  python test_api_endpoints.py --username admin --password password

  # Test remote server
  python test_api_endpoints.py --host 192.168.1.100 --port 8080
        """
    )
    
    parser.add_argument('--host', default='localhost', help='Server host (default: localhost)')
    parser.add_argument('--port', type=int, default=5000, help='Server port (default: 5000)')
    parser.add_argument('--username', help='Username for authentication')
    parser.add_argument('--password', help='Password for authentication')
    
    args = parser.parse_args()
    
    # Create tester and run tests
    tester = APITester(args.host, args.port, args.username, args.password)
    exit_code = tester.run_all_tests()
    
    sys.exit(exit_code)


if __name__ == '__main__':
    import time
    main()

# Made with Bob
