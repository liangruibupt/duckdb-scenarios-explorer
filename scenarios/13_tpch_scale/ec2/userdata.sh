#!/bin/bash
# EC2 user-data for scenario 13: run the TPC-H benchmark unattended on a
# Graviton instance with local NVMe, print the results to the EC2 console log,
# then shut down. Launch with --instance-initiated-shutdown-behavior terminate
# so the shutdown also terminates (and stops billing for) the instance.
#
# launch.sh fills in the instance type, the git branch and the run list (one
# bench.py argument list per line) before passing this file as user-data.
set -uo pipefail
exec > >(tee -a /var/log/tpch-bench.log) 2>&1

shutdown -h +300 "tpch bench hard cap"           # never run longer than 5 h

REPO=https://github.com/liangruibupt/duckdb-scenarios-explorer.git
BRANCH=__BRANCH__
TYPE=__TYPE__
export BENCH_INSTANCE_TYPE=$TYPE
echo "TPCH-BENCH start $(date -u +%FT%TZ) on $TYPE"

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq && apt-get install -y -qq git python3-venv xfsprogs >/dev/null

# Local NVMe instance store for data + spill. Select it by model name so the
# EBS root volume can never be picked.
NVME=$(lsblk -dno NAME,MODEL | awk '/Instance Storage/{print $1; exit}')
WORK=/mnt/bench
mkdir -p $WORK
if [ -n "$NVME" ] && ! lsblk -no MOUNTPOINT "/dev/$NVME" | grep -q .; then
  mkfs.xfs -f "/dev/$NVME" && mount "/dev/$NVME" $WORK
fi
df -h $WORK

git clone --depth 1 --branch "$BRANCH" "$REPO" $WORK/repo
python3 -m venv $WORK/venv
$WORK/venv/bin/pip install -q duckdb==2.0.0 psutil
cd $WORK/repo/scenarios/13_tpch_scale

while IFS= read -r args; do
  [ -z "$args" ] && continue
  echo "TPCH-BENCH run: $args"
  # shellcheck disable=SC2086
  $WORK/venv/bin/python bench.py $args --data-dir $WORK/data --results-dir $WORK/results < /dev/null
done <<'RUNS'
__RUNS__
RUNS

# Results to the console log: compact gzip+base64 JSON bundle, between markers.
cd $WORK/results
echo "TPCH-RESULTS-BEGIN"
tar czf - *.json | base64 -w 76
echo "TPCH-RESULTS-END"
echo "TPCH-BENCH done $(date -u +%FT%TZ)"

# Leave time to read the console log, then terminate.
shutdown -c 2>/dev/null
shutdown -h +30 "tpch bench finished"
