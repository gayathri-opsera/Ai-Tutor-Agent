#!/usr/bin/env bash
# Update all OpenAPI baseline schemas from the current service code.
# Run this after intentional API changes to record the new baseline.
#
# Usage:
#   ./scripts/update-openapi-baselines.sh
#   ./scripts/update-openapi-baselines.sh --service chat-orchestrator

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$REPO_ROOT"

if [[ "${1:-}" == "--service" && -n "${2:-}" ]]; then
    echo "Updating baseline for service: $2"
    python scripts/validate-openapi.py --service "$2" --update
else
    echo "Updating all OpenAPI baselines..."
    python scripts/validate-openapi.py --all --update
fi

echo ""
echo "Done. Commit the updated files in libs/contracts/openapi/ with your API change."
