#!/usr/bin/env bash
set -u
REWARD=/logs/verifier/reward.txt
mkdir -p /logs/verifier
printf '0
' > "$REWARD"
fail_safe() { printf '0
' > "$REWARD"; exit 1; }
trap fail_safe INT TERM HUP
if [ -f /workspace/src/xrd_analyzer.py ]; then
  APP_ROOT=/workspace
  RUNNER=/tests/runner.py
else
  ROOT="$(cd "$(dirname "$0")/.." && pwd)"
  APP_ROOT="$ROOT/environment"
  RUNNER="$ROOT/tests/runner.py"
fi
set +e
python3 "$RUNNER" "$APP_ROOT" > /tmp/xrd-test.log 2>&1
status=$?
cat /tmp/xrd-test.log
score=$(awk -F= '/^GROUP[0-9]+=/{sum += $2; count += 1} END { if (count == 4) printf "%.3f", sum / 4; else printf "0.000" }' /tmp/xrd-test.log)
printf '%s
' "$score" > "$REWARD"
exit 0
