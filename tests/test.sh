#!/usr/bin/env bash
set -euo pipefail

REWARD=/logs/verifier/reward.txt
mkdir -p /logs/verifier
printf '0\n' > "$REWARD"

if [ -f /workspace/src/xrd_analyzer.py ]; then
  export XRD_APP_ROOT=/workspace
  TEST_FILE=/tests/test_xrd_analyzer.py
else
  ROOT="$(cd "$(dirname "$0")/.." && pwd)"
  export XRD_APP_ROOT="$ROOT/environment"
  TEST_FILE="$ROOT/tests/test_xrd_analyzer.py"
fi

# Keep Harbor scoring deterministic: pytest failures are a zero reward, while
# infrastructure failures still surface as a nonzero verifier error.
if python3 -m pytest -q -p no:cacheprovider "$TEST_FILE"; then
  printf '1\n' > "$REWARD"
  exit 0
fi

printf '0\n' > "$REWARD"
exit 0
