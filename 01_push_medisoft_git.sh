#!/usr/bin/env bash
set -Eeuo pipefail
PROJECT_DIR="${1:-/opt/medisoft-guardian-v3}"
cd "$PROJECT_DIR"

echo "== Medisoft Git save and push =="
git status --short

touch .gitignore
for pattern in '*.bak' '*.bak_*' '*.bak-*' '*_backup_*' '__pycache__/' '*.pyc' '.env' '.env.*' 'backend/venv/' 'node_modules/' 'dist/'; do
  grep -qxF "$pattern" .gitignore || echo "$pattern" >> .gitignore
done

git add -A

echo
echo "Staged changes:"
git diff --cached --stat

echo
echo "Review staged file names:"
git diff --cached --name-status

echo
echo "Checking staged files for obvious secrets..."
if git diff --cached --name-only -z | xargs -0 -r grep -nEI '(password|passwd|secret|token|api[_-]?key)[[:space:]]*[:=]' 2>/dev/null; then
  echo
  echo "WARNING: Possible secrets were found above. Review before continuing."
  exit 1
fi

COMMIT_MESSAGE="${COMMIT_MESSAGE:-Fix monitoring, alerts, SMS and dashboard health reporting}"
git commit -m "$COMMIT_MESSAGE" || echo "Nothing new to commit."
BRANCH="$(git branch --show-current)"
git push origin "$BRANCH"

echo
git status
