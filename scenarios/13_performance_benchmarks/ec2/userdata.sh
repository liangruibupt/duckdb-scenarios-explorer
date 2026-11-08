#!/bin/bash
# EC2 user-data for scenario 13: run the TPC-H benchmark unattended on a
# Graviton instance with local NVMe, print the results to the EC2 console log,
# then shut down. Launch with --instance-initiated-shutdown-behavior terminate
# so the shutdown also terminates (and stops billing for) the instance.
#
# launch.sh fills in the instance type, the git branch, the hard time cap and
# the run list (one script + arguments per line, run from scenarios/13_performance_benchmarks)
# before passing this file as user-data.
set -uo pipefail
exec > >(tee -a /var/log/tpch-bench.log) 2>&1

shutdown -h +__HARDCAP_MIN__ "tpch bench hard cap"   # never run longer than this
# A reboot cancels the timer above and user-data does not run again, so the
# instance would idle forever. Make any reboot shut it down (= terminate).
# Before shutting down, print the previous boot's last kernel and system log
# lines to the console so the cause of the reboot can be read afterwards.
cat > /usr/local/sbin/tpch-reboot-report <<'GUARD'
#!/bin/bash
{
  echo "TPCH-REBOOT-REPORT begin (previous boot)"
  journalctl -k -b -1 -n 60 --no-pager
  journalctl -b -1 -n 40 --no-pager -p warning
  echo "TPCH-REBOOT-REPORT end"
} > /dev/console 2>&1
/sbin/shutdown -h +10 "tpch bench: rebooted, shutting down"
GUARD
chmod +x /usr/local/sbin/tpch-reboot-report
echo '@reboot root /usr/local/sbin/tpch-reboot-report' > /etc/cron.d/tpch-bench-reboot-guard
mkdir -p /var/log/journal && systemctl restart systemd-journald   # keep logs across reboot

# cloud-init runs without HOME; DuckDB needs it to install extensions.
export HOME=/root

REPO=https://github.com/liangruibupt/duckdb-scenarios-explorer.git
BRANCH=__BRANCH__
TYPE=__TYPE__
export BENCH_INSTANCE_TYPE=$TYPE
echo "TPCH-BENCH start $(date -u +%FT%TZ) on $TYPE"

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq && apt-get install -y -qq git python3-venv xfsprogs mdadm curl >/dev/null

# Local NVMe instance store for data + spill. Select disks by model name so the
# EBS root volume can never be picked; stripe them (RAID 0) when there are
# several.
mapfile -t DISKS < <(lsblk -dno NAME,MODEL | awk '/Instance Storage/{print "/dev/"$1}')
WORK=/mnt/bench
mkdir -p $WORK
if [ ${#DISKS[@]} -gt 1 ]; then
  mdadm --create /dev/md0 --level=0 --raid-devices=${#DISKS[@]} --run "${DISKS[@]}" \
    && mkfs.xfs -f /dev/md0 && mount /dev/md0 $WORK
elif [ ${#DISKS[@]} -eq 1 ]; then
  mkfs.xfs -f "${DISKS[0]}" && mount "${DISKS[0]}" $WORK
fi
df -h $WORK

git clone --depth 1 --branch "$BRANCH" "$REPO" $WORK/repo
python3 -m venv $WORK/venv
$WORK/venv/bin/pip install -q duckdb==2.0.0 psutil
cd $WORK/repo/scenarios/13_performance_benchmarks

while IFS= read -r args; do
  [ -z "$args" ] && continue
  echo "TPCH-BENCH run: $args"
  # shellcheck disable=SC2086
  $WORK/venv/bin/python $args --data-dir $WORK/data --results-dir $WORK/results < /dev/null \
    || echo "TPCH-BENCH run failed: $args"
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
