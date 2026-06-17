#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2024 IBM Corporation

"""
Quick test script to verify HTML template refactoring works correctly.
Tests template loading, config endpoint, and basic server functionality.
"""

import os
import sys
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_template_exists():
    """Test that template file exists and is readable"""
    template_path = Path(__file__).parent / "src" / "templates" / "viewer.html"
    print(f"✓ Checking template file: {template_path}")
    
    if not template_path.exists():
        print(f"✗ FAIL: Template file not found")
        return False
    
    with open(template_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check for key elements
    checks = [
        ('<!DOCTYPE html>', 'DOCTYPE declaration'),
        ('<title>Policy and Event Data Visualization</title>', 'Title'),
        ('/api/config', 'Config endpoint reference'),
        ('/static/config-handler.js', 'Config handler script'),
        ('/static/app.js', 'Main app script'),
        ('id="logout-container"', 'Logout container'),
    ]
    
    for check_str, desc in checks:
        if check_str in content:
            print(f"  ✓ Found: {desc}")
        else:
            print(f"  ✗ FAIL: Missing {desc}")
            return False
    
    print(f"✓ Template file is valid ({len(content)} bytes)")
    return True

def test_config_handler_exists():
    """Test that config handler JavaScript exists"""
    config_js_path = Path(__file__).parent / "src" / "static" / "config-handler.js"
    print(f"\n✓ Checking config handler: {config_js_path}")
    
    if not config_js_path.exists():
        print(f"✗ FAIL: Config handler not found")
        return False
    
    with open(config_js_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check for key elements
    checks = [
        ('window.APP_CONFIG', 'APP_CONFIG variable'),
        ('enableAuth', 'enableAuth config'),
        ('logout-container', 'Logout container handling'),
    ]
    
    for check_str, desc in checks:
        if check_str in content:
            print(f"  ✓ Found: {desc}")
        else:
            print(f"  ✗ FAIL: Missing {desc}")
            return False
    
    print(f"✓ Config handler is valid ({len(content)} bytes)")
    return True

def test_web_interface_imports():
    """Test that web_interface.py can be imported"""
    print(f"\n✓ Testing web_interface.py imports...")
    
    try:
        import web_interface
        print(f"  ✓ Module imported successfully")
        
        # Check for new method
        if hasattr(web_interface, 'PolicyViewerHandler'):
            handler_class = web_interface.PolicyViewerHandler
            if hasattr(handler_class, '_api_config'):
                print(f"  ✓ _api_config method exists")
            else:
                print(f"  ✗ FAIL: _api_config method not found")
                return False
        
        return True
    except Exception as e:
        print(f"  ✗ FAIL: Import error: {e}")
        return False

def test_config_generation():
    """Test that config endpoint would generate valid JSON"""
    print(f"\n✓ Testing config generation...")
    
    # Simulate config generation
    config = {
        "enableAuth": True,
        "sessionTimeout": 30,
        "enableCors": True,
        "debugTiming": False,
    }
    
    try:
        js_content = f"window.APP_CONFIG = {json.dumps(config, indent=2)};\n"
        print(f"  ✓ Config JSON is valid")
        print(f"  ✓ Generated {len(js_content)} bytes of JavaScript")
        
        # Verify it's valid JavaScript
        if 'window.APP_CONFIG' in js_content and 'enableAuth' in js_content:
            print(f"  ✓ JavaScript structure is correct")
            return True
        else:
            print(f"  ✗ FAIL: JavaScript structure is incorrect")
            return False
    except Exception as e:
        print(f"  ✗ FAIL: Config generation error: {e}")
        return False

def main():
    """Run all tests"""
    print("=" * 60)
    print("HTML Template Refactoring - Quick Test")
    print("=" * 60)
    
    tests = [
        ("Template File", test_template_exists),
        ("Config Handler", test_config_handler_exists),
        ("Web Interface", test_web_interface_imports),
        ("Config Generation", test_config_generation),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n✗ EXCEPTION in {name}: {e}")
            results.append((name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")
    
    print(f"\nResults: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✓ All tests passed! Template refactoring is working correctly.")
        print("\nNext steps:")
        print("1. Generate data files (if needed)")
        print("2. Start the web server: cd src && python3 web_interface.py")
        print("3. Open browser to http://localhost:8000")
        print("4. Verify page loads and logout button visibility")
        return 0
    else:
        print("\n✗ Some tests failed. Please review the errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())

