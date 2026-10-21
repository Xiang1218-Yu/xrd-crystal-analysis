#!/usr/bin/env bash
set -euo pipefail

if [ -f /solution/reference_impl.py ] && [ -d /workspace/src ]; then
  src=/solution/reference_impl.py
  dst=/workspace/src/xrd_analyzer.py
else
  root="$(cd "$(dirname "$0")/.." && pwd)"
  src="$root/solution/reference_impl.py"
  dst="$root/environment/src/xrd_analyzer.py"
fi

cp "$src" "$dst"
chmod +x "$dst"
