#!/usr/bin/env bash
# macOS / Ubuntu: 더블클릭 또는 ./run.sh
cd "$(dirname "$0")"
python3 -m tripdesk "$@"
