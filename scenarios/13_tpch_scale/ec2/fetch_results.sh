#!/usr/bin/env bash
# Pull the results bundle from an instance's console log into ../results/.
#   ./fetch_results.sh <instance-id> [region]
set -euo pipefail
ID=$1; REGION=${2:-us-east-1}
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=$(aws ec2 get-console-output --region "$REGION" --instance-id "$ID" --latest \
  --query Output --output text)
B64=$(printf '%s\n' "$OUT" | sed -n '/TPCH-RESULTS-BEGIN/,/TPCH-RESULTS-END/p' \
  | grep -v 'TPCH-RESULTS' | tr -d '\r\n ')
if [ -z "$B64" ]; then
  echo "no results yet; last lines:"; printf '%s\n' "$OUT" | grep 'TPCH-BENCH\|Q[0-9][0-9] ' | tail -5
  exit 1
fi
mkdir -p "$HERE/../results"
printf '%s' "$B64" | base64 -d | tar xzf - -C "$HERE/../results"
ls -1 "$HERE/../results"
