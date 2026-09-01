#!/usr/bin/env bash
# Create the dedicated AgentCore Runtime execution role for the chat-BI agent,
# with the right S3-read + Bedrock + logs policy baked in.
#
# Run ONCE with an IAM-privileged profile (the EC2 instance role cannot do IAM):
#   ./create_runtime_role.sh <aws-profile>
#
# Idempotent: re-running updates the inline policy and re-puts the trust policy.
set -euo pipefail
PROFILE="${1:?usage: ./create_runtime_role.sh <aws-profile>}"
ROLE="duckdb-chatbi-runtime-exec"
DIR="$(cd "$(dirname "$0")" && pwd)"

# create the role (ignore if it already exists), then (re)set trust + policy
aws iam create-role --role-name "$ROLE" \
  --assume-role-policy-document "file://$DIR/runtime-trust-policy.json" \
  --description "Exec role for duckdb_chatbi AgentCore Runtime (scenarios 04+07)" \
  --profile "$PROFILE" 2>/dev/null || \
aws iam update-assume-role-policy --role-name "$ROLE" \
  --policy-document "file://$DIR/runtime-trust-policy.json" --profile "$PROFILE"

aws iam put-role-policy --role-name "$ROLE" \
  --policy-name duckdb-chatbi-exec \
  --policy-document "file://$DIR/runtime-exec-policy.json" --profile "$PROFILE"

ARN=$(aws iam get-role --role-name "$ROLE" --query 'Role.Arn' --output text --profile "$PROFILE")
echo "Role ready: $ARN"
echo "Next: tell the agent to re-point the Runtime at this role and redeploy."
