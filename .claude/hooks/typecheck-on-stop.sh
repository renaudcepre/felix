#!/usr/bin/env bash
# Stop hook: mypy --strict on src/ before Claude ends its turn.
# Exit 2 keeps Claude working with the errors; exit 0 lets the turn end.
set -uo pipefail

root="${CLAUDE_PROJECT_DIR:?}"

# Already continuing because of this hook: let the turn end, no loop.
[[ $(jq -r '.stop_hook_active') == "true" ]] && exit 0

cd "$root" || exit 0

# Pure conversation turns: nothing to check.
git status --porcelain -- 'src/*.py' | grep -q . || exit 0

out=$(.venv/bin/mypy src 2>&1) && exit 0

echo "mypy --strict fails on src/:" >&2
echo "$out" >&2
exit 2
