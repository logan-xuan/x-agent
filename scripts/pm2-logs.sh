#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/pm2-common.sh"

pm2_cmd logs x-agent-backend x-agent-frontend --lines 100
