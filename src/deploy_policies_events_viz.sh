#!/usr/bin/env bash
#
# Copyright IBM Corp. 2024 - 2026
# SPDX-License-Identifier: Apache-2.0
#
set -euo pipefail

# =======================
# Config (env-overridable)
# =======================
PROJECT="${PROJECT:-namespacenoi}"          # your OCP project/namespace
APP_NAME="${APP_NAME:-policy-events-viz}"   # BuildConfig, Deployment, Svc, Route, ImageStream
APP_PORT="${APP_PORT:-8080}"                # container port your app binds to
HEALTH_PATH="${HEALTH_PATH:-/health}"       # set to "" to use TCP probe
EXPOSE_ROUTE="${EXPOSE_ROUTE:-true}"        # set false if you don't want a Route
DOCKERFILE_PATH="${DOCKERFILE_PATH:-Dockerfile}" # path to Dockerfile relative to CWD
PVC_NAME="${PVC_NAME:-${APP_NAME}-pvc}"     # optional PVC name used by the app

# Container command (shell-form) so ${APP_PORT} expands at runtime
CONTAINER_CMD=( "sh" "-lc" "exec python web_interface.py --host 0.0.0.0 --port ${APP_PORT}" )

# =======================
# Flags
# =======================
CLEAN=false
CLEAN_PVC=false
NO_DEPLOY=false
YES=false

usage() {
  cat <<USAGE
Usage: $(basename "$0") [options]

Options:
  --clean           Delete existing app resources first (BC, IS, Deploy, RS/Pods, Svc, Route, Builds).
  --clean-pvc       Also delete PVC: ${PVC_NAME}  (only applies with --clean).
  --no-deploy       Do not (re)deploy after cleanup.
  --yes             Non-interactive (assume yes for cleanup).
  -h, --help        Show this help.

Environment overrides:
  PROJECT, APP_NAME, APP_PORT, HEALTH_PATH, EXPOSE_ROUTE, DOCKERFILE_PATH, PVC_NAME

Examples:
  # Fresh redeploy:
  PROJECT=namespacenoi APP_NAME=policy-events-viz bash $0 --clean

  # Clean only (keep PVC):
  bash $0 --clean --no-deploy

  # Clean incl. PVC, then redeploy:
  bash $0 --clean --clean-pvc
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --clean) CLEAN=true ;;
    --clean-pvc) CLEAN_PVC=true ;;
    --no-deploy) NO_DEPLOY=true ;;
    --yes) YES=true ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1"; usage; exit 1 ;;
  esac
  shift
done

# =======================
# Pre-flight checks
# =======================
if ! command -v oc >/dev/null 2>&1; then
  echo "❌ 'oc' CLI not found in PATH"; exit 1
fi
if ! oc whoami >/dev/null 2>&1; then
  echo "❌ Not logged in to OpenShift. Run: oc login ..."; exit 1
fi
if [ ! -f "${DOCKERFILE_PATH}" ] && [ "${NO_DEPLOY}" = "false" ]; then
  echo "❌ ${DOCKERFILE_PATH} not found in $(pwd)"; exit 1
fi

echo "➡️ Project: ${PROJECT}"
echo "➡️ App:     ${APP_NAME}"
echo "➡️ Port:    ${APP_PORT}"
echo "➡️ Health:  ${HEALTH_PATH:-<TCP 8080>}"
echo ""

# Switch/create project (do NOT delete it)
oc new-project "${PROJECT}" >/dev/null 2>&1 || oc project "${PROJECT}"

# =======================
# Cleanup (safe, idempotent)
# =======================
if [ "${CLEAN}" = "true" ]; then
  echo "🧹 Cleanup requested for app '${APP_NAME}' in project '${PROJECT}'"
  if [ "${YES}" = "false" ]; then
    read -r -p "Proceed to delete app resources (not the project) [y/N]? " ans
    case "${ans:-N}" in y|Y) ;; *) echo "Aborted."; exit 0 ;; esac
  fi

  # Scale down to unblock deletions
  oc scale deploy/${APP_NAME} --replicas=0 >/dev/null 2>&1 || true

  # Delete route, service, deployment, replica sets, pods
  oc delete route/${APP_NAME} >/dev/null 2>&1 || true
  oc delete svc/${APP_NAME} >/dev/null 2>&1 || true
  oc delete deploy/${APP_NAME} >/dev/null 2>&1 || true
  oc delete rs -l app=${APP_NAME} >/dev/null 2>&1 || true
  oc delete pods -l app=${APP_NAME} --force --grace-period=0 >/dev/null 2>&1 || true

  # Delete BuildConfig, Builds, ImageStream
  oc delete bc/${APP_NAME} >/dev/null 2>&1 || true
  oc delete builds -l build=${APP_NAME} >/dev/null 2>&1 || true
  oc delete is/${APP_NAME} >/dev/null 2>&1 || true

  # Optionally delete PVC
  if [ "${CLEAN_PVC}" = "true" ]; then
    echo "🧹 Deleting PVC ${PVC_NAME}"
    oc delete pvc/${PVC_NAME} >/dev/null 2>&1 || true
  fi

  echo "✅ Cleanup done."
  if [ "${NO_DEPLOY}" = "true" ]; then
    echo "ℹ️ --no-deploy set; exiting after cleanup."
    exit 0
  fi
fi

# =======================
# BuildConfig (Docker)
# =======================
if ! oc get bc "${APP_NAME}" >/dev/null 2>&1; then
  echo "ℹ️ Creating BuildConfig ${APP_NAME} (binary, Docker strategy)"
  oc new-build --name="${APP_NAME}" --binary --strategy=docker
fi

# Ensure BC uses the intended Dockerfile path
oc patch bc/${APP_NAME} --type=merge -p \
  "{\"spec\":{\"strategy\":{\"dockerStrategy\":{\"dockerfilePath\":\"${DOCKERFILE_PATH}\"}}}}" >/dev/null

# =======================
# Build from local dir
# =======================
echo "🚀 Starting binary build from: $(pwd)"
oc start-build "${APP_NAME}" --from-dir=. --follow

# =======================
# Deploy (create or update)
# =======================
if ! oc get deploy "${APP_NAME}" >/dev/null 2>&1; then
  echo "ℹ️ Creating Deployment ${APP_NAME}"
  oc new-app "${APP_NAME}:latest" --name="${APP_NAME}"
else
  echo "ℹ️ Updating Deployment image to latest"
  oc set image deploy/${APP_NAME} \
    ${APP_NAME}=image-registry.openshift-image-registry.svc:5000/${PROJECT}/${APP_NAME}:latest --record || true
fi

# Ensure APP_PORT env is set
oc set env deploy/${APP_NAME} APP_PORT="${APP_PORT}" >/dev/null || true

# =======================
# Patch only the container command (JSON patch; keep image intact)
# =======================
echo "ℹ️ Patching container command to expand \$APP_PORT at runtime"
IDX=$(oc get deploy/${APP_NAME} -o jsonpath='{range .spec.template.spec.containers[*]}{.name}{"\n"}{end}' | nl -ba | awk -v n="${APP_NAME}" '$2==n{print $1-1; found=1} END{if(!found) print 0}')
PATCH=$(
  cat <<JSON
[
  {"op":"add","path":"/spec/template/spec/containers/${IDX}/command","value":$(printf '%s\n' "${CONTAINER_CMD[@]}" | jq -R . | jq -s .)}
]
JSON
)
echo "$PATCH" | oc patch deploy/${APP_NAME} --type='json' -p "$(cat)"

# =======================
# Probes (HTTP or TCP)
# =======================
if [ -n "${HEALTH_PATH}" ]; then
  echo "ℹ️ Setting HTTP probes on ${HEALTH_PATH}"
  oc set probe deploy/${APP_NAME} --readiness --get-url="http://:${APP_PORT}${HEALTH_PATH}" \
    --initial-delay-seconds=5 --timeout-seconds=2 >/dev/null || true
  oc set probe deploy/${APP_NAME} --liveness  --get-url="http://:${APP_PORT}${HEALTH_PATH}" \
    --initial-delay-seconds=10 --timeout-seconds=2 >/dev/null || true
else
  echo "ℹ️ Setting TCP probes on ${APP_PORT}"
  oc set probe deploy/${APP_NAME} --readiness --tcp=${APP_PORT} \
    --initial-delay-seconds=5 --timeout-seconds=2 >/dev/null || true
  oc set probe deploy/${APP_NAME} --liveness  --tcp=${APP_PORT} \
    --initial-delay-seconds=10 --timeout-seconds=2 >/dev/null || true
fi

# =======================
# Service & Route
# =======================
if ! oc get svc "${APP_NAME}" >/dev/null 2>&1; then
  echo "ℹ️ Creating Service ${APP_NAME}"
  oc expose deploy/${APP_NAME} --port=${APP_PORT} >/dev/null || true
fi

if [ "${EXPOSE_ROUTE}" = "true" ]; then
  oc expose svc/${APP_NAME} >/dev/null 2>&1 || true
fi

# =======================
# Rollout & Output
# =======================
echo "🔁 Restarting rollout to apply changes"
oc rollout restart deploy/${APP_NAME}
echo "⏳ Waiting for rollout to complete…"
oc rollout status deploy/${APP_NAME}

IMG=$(oc get deploy ${APP_NAME} -o jsonpath='{.spec.template.spec.containers[0].image}')
ROUTE=$(oc get route ${APP_NAME} -o jsonpath='{.spec.host}' 2>/dev/null || true)

echo "✅ Done."
echo "   Image: ${IMG}"
echo "   Command: ${CONTAINER_CMD[*]}"
echo "   Probes: ${HEALTH_PATH:-TCP:${APP_PORT}}"
if [ -n "${ROUTE}" ]; then
  echo "   Route:  https://${ROUTE}"
  [ -n "${HEALTH_PATH}" ] && echo "   Health: curl -k https://${ROUTE}${HEALTH_PATH}"
fi
