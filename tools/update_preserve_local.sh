#!/usr/bin/env bash
set -Eeuo pipefail

REPO=${1:-/data/openpilot}
REMOTE=${2:-origin}
BRANCH=${3:-$(git -C "$REPO" branch --show-current)}
STAMP=$(date +%Y%m%d_%H%M%S)
IDENTITY_NAME=${GIT_UPDATE_NAME:-nvidia-local}
IDENTITY_EMAIL=${GIT_UPDATE_EMAIL:-nvidia@localhost}

cd "$REPO"
[[ -d .git ]] || { echo "not a git repository: $REPO" >&2; exit 2; }

echo "[1/7] repository: $REPO"
echo "      branch:   $BRANCH"
echo "      remote:   $REMOTE/$BRANCH"

# Keep a named pointer before changing anything. This is cheap and reversible.
BACKUP_BRANCH="local-backup-before-update-$STAMP"
git branch "$BACKUP_BRANCH"

# Commit tracked local changes only. Untracked build products and local tools are
# deliberately left in place; they are not overwritten by a normal merge.
git add -u
if ! git diff --cached --quiet; then
  git -c user.name="$IDENTITY_NAME" -c user.email="$IDENTITY_EMAIL" \
    commit -m "checkpoint local changes before remote update $STAMP"
fi

# Fetch only; never use pull/reset/clean.
echo "[2/7] fetching remote"
git fetch "$REMOTE" --prune
TARGET="$REMOTE/$BRANCH"
git show-ref --verify --quiet "refs/remotes/$TARGET" || {
  echo "remote branch not found: $TARGET" >&2; exit 3;
}

# A remote update must not silently take over an untracked local file.
COLLISION_FILE="/tmp/openpilot-untracked-collisions.$$.txt"
trap 'rm -f "$COLLISION_FILE"' EXIT
comm -12 \
  <(git ls-files --others --exclude-standard | sort) \
  <(git ls-tree -r --name-only "$TARGET" | sort) > "$COLLISION_FILE"
if [[ -s "$COLLISION_FILE" ]]; then
  echo "untracked files would collide with remote tracked files; no merge made:" >&2
  sed -n '1,80p' "$COLLISION_FILE" >&2
  echo "checkpoint branch: $BACKUP_BRANCH" >&2
  exit 4
fi

# Merge remote changes while preferring the already checkpointed local content
# whenever both sides changed the same path. This is intentionally not theirs.
echo "[3/7] merging with local changes preferred"
set +e
git -c user.name="$IDENTITY_NAME" -c user.email="$IDENTITY_EMAIL" \
  merge --allow-unrelated-histories --no-edit -X ours "$TARGET"
MERGE_RC=$?
set -e
if (( MERGE_RC != 0 )); then
  CONFLICTS=$(git diff --name-only --diff-filter=U || true)
  if [[ -z "$CONFLICTS" ]]; then
    echo "merge failed without resolvable file conflicts; aborting" >&2
    git merge --abort || true
    exit "$MERGE_RC"
  fi
  echo "[4/7] resolving remaining conflicts with local (ours) versions"
  # shellcheck disable=SC2086
  git checkout --ours -- $CONFLICTS
  # shellcheck disable=SC2086
  git add $CONFLICTS
  git -c user.name="$IDENTITY_NAME" -c user.email="$IDENTITY_EMAIL" \
    commit --no-edit -m "merge $TARGET preserving local changes"
else
  echo "[4/7] merge completed without conflicts"
fi

# Do not stage untracked files. Show a concise audit for the operator.
echo "[5/7] verifying"
test -z "$(git diff --name-only --diff-filter=U)"
echo "      HEAD: $(git rev-parse --short HEAD)"
echo "      backup branch: $BACKUP_BRANCH"
echo "      remote: $(git rev-parse --short "$TARGET")"
echo "[6/7] local tracked diff after merge:"
git diff --stat || true
echo "[7/7] untracked files remain untouched: $(git ls-files --others --exclude-standard | wc -l)"
