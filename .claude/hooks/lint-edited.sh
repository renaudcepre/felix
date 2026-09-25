#!/usr/bin/env bash
# PostToolUse hook (Edit|Write): format + lint the single file Claude just touched.
# Exit 2 sends the remaining errors back to Claude; exit 0 stays silent.
set -uo pipefail

root="${CLAUDE_PROJECT_DIR:?}"
file=$(jq -r '.tool_input.file_path // empty')

[[ -n "$file" && -f "$file" ]] || exit 0
[[ "$file" == "$root"/* ]] || exit 0

case "$file" in
  *.py)
    cd "$root" || exit 0
    .venv/bin/ruff format --quiet "$file"
    out=$(.venv/bin/ruff check --fix --quiet "$file" 2>&1) && exit 0
    ;;
  "$root"/web/*.vue | "$root"/web/*.ts)
    cd "$root/web" || exit 0
    out=$(node_modules/.bin/eslint --fix "$file" 2>&1) && exit 0
    ;;
  *)
    exit 0
    ;;
esac

echo "Lint errors remain in $file:" >&2
echo "$out" >&2
exit 2
