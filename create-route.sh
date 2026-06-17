#!/bin/bash
#
# Copyright IBM Corp. 2024 - 2026
# SPDX-License-Identifier: Apache-2.0
#
# create-route.sh
# Simple script to create an OpenShift route for the web interface if it doesn't exist

set -e

# Default values
DEFAULT_NAMESPACE=""
DEFAULT_SERVICE_NAME="evtmanager-ibm-ea-web-interface"
DEFAULT_ROUTE_NAME="evtmanager-ibm-ea-web-interface"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored messages
print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Check if oc command is available
if ! command -v oc &> /dev/null; then
    print_error "OpenShift CLI (oc) is not installed or not in PATH"
    echo "Please install it from: https://docs.openshift.com/container-platform/latest/cli_reference/openshift_cli/getting-started-cli.html"
    exit 1
fi

# Check if logged in
if ! oc whoami &> /dev/null; then
    print_error "Not logged in to OpenShift cluster"
    echo "Please login first: oc login <cluster-url>"
    exit 1
fi

# Get namespace
if [ -z "$1" ]; then
    # Try to detect namespace
    NAMESPACE=$(oc get deployment $DEFAULT_SERVICE_NAME -A -o jsonpath='{.items[0].metadata.namespace}' 2>/dev/null || echo "")
    
    if [ -z "$NAMESPACE" ]; then
        print_error "Could not auto-detect namespace"
        echo ""
        echo "Usage: $0 [NAMESPACE] [SERVICE_NAME] [ROUTE_NAME]"
        echo ""
        echo "Examples:"
        echo "  $0 noi-namespace"
        echo "  $0 noi-namespace evtmanager-ibm-ea-web-interface"
        echo "  $0 noi-namespace evtmanager-ibm-ea-web-interface my-custom-route"
        exit 1
    fi
    print_info "Auto-detected namespace: $NAMESPACE"
else
    NAMESPACE="$1"
fi

SERVICE_NAME="${2:-$DEFAULT_SERVICE_NAME}"
ROUTE_NAME="${3:-$DEFAULT_ROUTE_NAME}"

print_info "Configuration:"
echo "  Namespace:    $NAMESPACE"
echo "  Service:      $SERVICE_NAME"
echo "  Route:        $ROUTE_NAME"
echo ""

# Check if service exists
print_info "Checking if service exists..."
if ! oc get service "$SERVICE_NAME" -n "$NAMESPACE" &> /dev/null; then
    print_error "Service '$SERVICE_NAME' not found in namespace '$NAMESPACE'"
    echo ""
    echo "Available services in namespace:"
    oc get services -n "$NAMESPACE" 2>/dev/null || echo "  (none or no access)"
    exit 1
fi
print_success "Service '$SERVICE_NAME' found"

# Check if route already exists
print_info "Checking if route already exists..."
if oc get route "$ROUTE_NAME" -n "$NAMESPACE" &> /dev/null; then
    print_warning "Route '$ROUTE_NAME' already exists"
    
    # Get the route URL
    ROUTE_HOST=$(oc get route "$ROUTE_NAME" -n "$NAMESPACE" -o jsonpath='{.spec.host}' 2>/dev/null)
    
    if [ -n "$ROUTE_HOST" ]; then
        print_success "Route is accessible at: http://$ROUTE_HOST"
    fi
    
    echo ""
    echo "To delete and recreate the route:"
    echo "  oc delete route $ROUTE_NAME -n $NAMESPACE"
    echo "  $0 $NAMESPACE $SERVICE_NAME $ROUTE_NAME"
    exit 0
fi

# Create the route
print_info "Creating route..."
if oc expose service "$SERVICE_NAME" --name="$ROUTE_NAME" -n "$NAMESPACE" 2>/dev/null; then
    print_success "Route created successfully!"
    
    # Wait a moment for route to be ready
    sleep 2
    
    # Get the route URL
    ROUTE_HOST=$(oc get route "$ROUTE_NAME" -n "$NAMESPACE" -o jsonpath='{.spec.host}' 2>/dev/null)
    
    if [ -n "$ROUTE_HOST" ]; then
        echo ""
        print_success "🌐 Web interface is now accessible at:"
        echo ""
        echo "  http://$ROUTE_HOST"
        echo ""
        print_info "Default credentials:"
        echo "  Username: admin"
        echo "  Password: changeme"
        echo ""
        print_warning "Remember to change the default password after first login!"
    else
        print_warning "Route created but URL could not be retrieved"
        echo "Run: oc get route $ROUTE_NAME -n $NAMESPACE"
    fi
else
    print_error "Failed to create route"
    echo ""
    echo "You can try creating it manually:"
    echo "  oc expose service $SERVICE_NAME --name=$ROUTE_NAME -n $NAMESPACE"
    exit 1
fi

