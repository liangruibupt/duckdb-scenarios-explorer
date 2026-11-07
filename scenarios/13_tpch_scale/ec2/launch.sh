#!/usr/bin/env bash
# Launch one self-terminating benchmark instance.
#   ./launch.sh <instance-type> <branch> <runs-file> [region] [subnet-id] [hard-cap-minutes]
# <runs-file> has one script + arguments per line, e.g.
#   bench.py --sf 10
#   clickbench.py
# Uses the latest Ubuntu 24.04 arm64 AMI, no key pair, no inbound access, the
# subnet's default security group, and shutdown behavior = terminate.
set -euo pipefail
TYPE=$1; BRANCH=$2; RUNS_FILE=$3
REGION=${4:-us-east-1}; SUBNET=${5:-}; CAP=${6:-300}
HERE=$(cd "$(dirname "$0")" && pwd)

AMI=$(aws ssm get-parameter --region "$REGION" \
  --name /aws/service/canonical/ubuntu/server/24.04/stable/current/arm64/hvm/ebs-gp3/ami-id \
  --query Parameter.Value --output text)

UD=$(mktemp)
python3 - "$HERE/userdata.sh" "$BRANCH" "$RUNS_FILE" "$TYPE" "$CAP" > "$UD" <<'EOF'
import sys
tpl, branch, runs, typ, cap = (sys.argv[1], sys.argv[2], open(sys.argv[3]).read().strip(),
                               sys.argv[4], sys.argv[5])
out = open(tpl).read()
for k, v in {"__BRANCH__": branch, "__RUNS__": runs, "__TYPE__": typ, "__HARDCAP_MIN__": cap}.items():
    out = out.replace(k, v)
print(out, end="")
EOF

aws ec2 run-instances --region "$REGION" --image-id "$AMI" --instance-type "$TYPE" \
  ${SUBNET:+--subnet-id "$SUBNET"} \
  --instance-initiated-shutdown-behavior terminate \
  --block-device-mappings 'DeviceName=/dev/sda1,Ebs={VolumeSize=30,VolumeType=gp3,DeleteOnTermination=true}' \
  --metadata-options HttpTokens=required \
  --user-data "file://$UD" \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=duckdb-tpch-$TYPE},{Key=purpose,Value=duckdb-scenarios-explorer-13}]" \
  --query 'Instances[0].InstanceId' --output text
rm -f "$UD"
