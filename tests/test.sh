#!/usr/bin/env bash
set -uo pipefail

LOG_DIR=/logs/verifier
REWARD=${REWARD_FILE:-$LOG_DIR/reward.txt}
STATUS=$LOG_DIR/verification-status.txt
JUNIT=$LOG_DIR/results.xml
REPORT=$LOG_DIR/scoring-report.json
TRUSTED_PYTHON=/usr/local/bin/python3
TRUSTED_TIMEOUT=/usr/bin/timeout
SITE_PACKAGES="/opt/verifier-wheels/iniconfig-2.3.1-py3-none-any.whl:/opt/verifier-wheels/packaging-26.3-py3-none-any.whl:/opt/verifier-wheels/pluggy-1.7.0-py3-none-any.whl:/opt/verifier-wheels/pygments-2.21.0-py3-none-any.whl:/opt/verifier-wheels/pytest-9.1.1-py3-none-any.whl"
COMPLETED=0

reset_reward_file() {
  rm -f "$REWARD" "$STATUS" 2>/dev/null || true
  mkdir -p "$(dirname "$REWARD")"
  printf '0\n' > "$REWARD"
}

fail_closed() {
  reset_reward_file
  printf 'INCOMPLETE: verifier did not complete: %s\n' "$1" > "$STATUS" 2>/dev/null || true
  chmod 0444 "$REWARD" 2>/dev/null || true
}

trap 'if [ "$COMPLETED" -ne 1 ]; then fail_closed "interrupted or exited"; fi' EXIT INT TERM HUP

mkdir -p "$LOG_DIR"
reset_reward_file
printf 'INCOMPLETE: verifier has not completed\n' > "$STATUS"
rm -f "$JUNIT" "$REPORT"

TEST_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f /workspace/src/xrd_analyzer.py ]; then
  XRD_APP_ROOT=/workspace
else
  XRD_APP_ROOT="$(cd "$TEST_DIR/.." && pwd)/environment"
fi

# The verifier wheels are immutable artifacts in the image. Keep this
# independent check in a trusted interpreter, not the candidate's PATH.
env -i \
  PATH=/usr/local/bin:/usr/bin:/bin \
  HOME=/tmp \
  PYTHONNOUSERSITE=1 \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$SITE_PACKAGES:/tests" \
  "$TRUSTED_PYTHON" -S -s -P -B -c 'import importlib.metadata as m, sys; required={"iniconfig":"2.3.1","packaging":"26.3","pluggy":"1.7.0","Pygments":"2.21.0","pytest":"9.1.1"}; bad=[f"{k}: expected {v}, found {m.version(k)}" for k,v in required.items() if m.version(k)!=v]; sys.exit("; ".join(bad)) if bad else None' || {
  fail_closed "verifier dependency check failed"
  exit 0
}

cd "$TEST_DIR"
env -i \
  PATH=/usr/local/bin:/usr/bin:/bin \
  HOME=/tmp \
  PYTHONNOUSERSITE=1 \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  PYTHONPATH="$SITE_PACKAGES:/tests" \
  XRD_APP_ROOT="$XRD_APP_ROOT" \
  "$TRUSTED_TIMEOUT" --signal=TERM --kill-after=5s 240s \
  "$TRUSTED_PYTHON" -S -s -P -B -m pytest \
  -q -p no:cacheprovider \
  --junitxml="$JUNIT" \
  --rootdir="$TEST_DIR" \
  "$TEST_DIR/test_xrd_analyzer.py" || true

if test -s "$JUNIT"; then
  if env -i \
    PATH=/usr/local/bin:/usr/bin:/bin \
    HOME=/tmp \
    PYTHONNOUSERSITE=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="$SITE_PACKAGES:/tests" \
    "$TRUSTED_PYTHON" -S -s -P -B /tests/score.py \
    --config /tests/scoring.json \
    --junit "$JUNIT" \
    --report-out "$REPORT" \
    --reward-out "$REWARD" \
    --status-out "$STATUS"; then
    if grep -q '^COMPLETED$' "$STATUS" 2>/dev/null; then
      COMPLETED=1
    else
      fail_closed "scorer did not mark completion"
    fi
  else
    fail_closed "scorer failed"
  fi
else
  fail_closed "pytest completion report missing"
fi

chmod 0444 "$REWARD" 2>/dev/null || true
exit 0
