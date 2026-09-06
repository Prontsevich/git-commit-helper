#!/bin/sh
# Install git-commit-helper into one or more agent harnesses.
#
# Usage:
#   ./install.sh                     # link into every harness whose home dir exists
#   ./install.sh claude cursor       # link into the named harnesses only
#   ./install.sh --copy codex        # copy instead of symlink (for hosts that reject links)
#   ./install.sh --check             # report drift, change nothing
#   ./install.sh --force claude      # replace an existing plain directory (backed up first)
#
# Backups of replaced directories go to ~/.git-commit-helper-backups/<target>-<stamp>
# (override with GIT_COMMIT_HELPER_BACKUP_DIR); never next to the skill, where a
# harness would load them as a duplicate skill.
# Targets: claude cursor codex agents gemini hermes opencode copilot all
#
# The repo stays the single source of truth. A symlink means every harness sees
# edits immediately; a copy must be refreshed by re-running this script.

set -eu

REPO_DIR="$(cd "$(dirname "$0")" && pwd -P)"
MODE="link"
FORCE=0
CHECK=0
TARGETS=""

usage() {
    sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'
    exit "${1:-0}"
}

harness_root() {
    case "$1" in
        claude)   printf '%s' "$HOME/.claude/skills" ;;
        cursor)   printf '%s' "$HOME/.cursor/skills" ;;
        codex)    printf '%s' "$HOME/.codex/skills" ;;
        agents)   printf '%s' "$HOME/.agents/skills" ;;
        gemini)   printf '%s' "$HOME/.gemini/skills" ;;
        hermes)   printf '%s' "$HOME/.hermes/skills" ;;
        opencode) printf '%s' "$HOME/.config/opencode/skills" ;;
        copilot)  printf '%s' "$HOME/.copilot/skills" ;;
        *) echo "unknown target: $1" >&2; exit 2 ;;
    esac
}

ALL_TARGETS="claude cursor codex agents gemini hermes opencode copilot"

for arg in "$@"; do
    case "$arg" in
        --link) MODE="link" ;;
        --copy) MODE="copy" ;;
        --force) FORCE=1 ;;
        --check) CHECK=1 ;;
        -h|--help) usage 0 ;;
        all) TARGETS="$ALL_TARGETS" ;;
        --*) echo "unknown flag: $arg" >&2; usage 2 ;;
        *) TARGETS="$TARGETS $arg" ;;
    esac
done

if [ -z "$TARGETS" ]; then
    for t in $ALL_TARGETS; do
        parent="$(dirname "$(harness_root "$t")")"
        [ -d "$parent" ] && TARGETS="$TARGETS $t"
    done
fi

# Files that make up the installed skill. Repo-only files (tests, AGENTS.md,
# install.sh itself, .git) are deliberately left out of copies.
PAYLOAD="SKILL.md references scripts"

describe() {
    dest="$1"
    if [ -L "$dest" ]; then
        real="$(cd "$dest" 2>/dev/null && pwd -P || echo '?')"
        if [ "$real" = "$REPO_DIR" ]; then
            echo "symlink -> repo (ok)"
        else
            echo "symlink -> $real (foreign)"
        fi
    elif [ -d "$dest" ]; then
        drift=0
        for item in $PAYLOAD; do
            if ! diff -rq --exclude=.DS_Store --exclude=__pycache__ "$REPO_DIR/$item" "$dest/$item" >/dev/null 2>&1; then
                drift=$((drift + 1))
            fi
        done
        if [ "$drift" -eq 0 ]; then
            echo "plain copy, in sync"
        else
            echo "plain copy, DRIFTED ($drift of 3 payload entries differ)"
        fi
    elif [ -e "$dest" ]; then
        echo "exists but is not a directory"
    else
        echo "missing"
    fi
}

# Backups go outside the skills directories: a harness treats every folder
# there as a skill, so a sibling *.bak would be loaded as a duplicate.
BACKUP_ROOT="${GIT_COMMIT_HELPER_BACKUP_DIR:-$HOME/.git-commit-helper-backups}"

backup() {
    dest="$1"
    target_name="$2"
    stamp="$(date +%Y%m%d-%H%M%S)"
    mkdir -p "$BACKUP_ROOT"
    mv "$dest" "$BACKUP_ROOT/$target_name-$stamp"
    echo "  backed up previous install to $BACKUP_ROOT/$target_name-$stamp"
}

install_link() {
    dest="$1"
    target_name="$2"
    if [ -L "$dest" ]; then
        rm "$dest"
    elif [ -e "$dest" ]; then
        if [ "$FORCE" -ne 1 ]; then
            echo "  refusing to replace existing directory without --force"
            return 1
        fi
        backup "$dest" "$target_name"
    fi
    mkdir -p "$(dirname "$dest")"
    ln -s "$REPO_DIR" "$dest"
    echo "  linked -> $REPO_DIR"
}

install_copy() {
    dest="$1"
    target_name="$2"
    if [ -L "$dest" ]; then
        rm "$dest"
    elif [ -e "$dest" ]; then
        if [ "$FORCE" -ne 1 ]; then
            echo "  refusing to overwrite existing directory without --force"
            return 1
        fi
        backup "$dest" "$target_name"
    fi
    mkdir -p "$dest"
    for item in $PAYLOAD; do
        cp -R "$REPO_DIR/$item" "$dest/"
    done
    find "$dest" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
    find "$dest" -name .DS_Store -delete 2>/dev/null || true
    echo "  copied payload ($PAYLOAD)"
}

status=0
for t in $TARGETS; do
    dest="$(harness_root "$t")/git-commit-helper"
    printf '%-9s %s\n' "$t" "$dest"
    echo "  before: $(describe "$dest")"
    if [ "$CHECK" -eq 1 ]; then
        continue
    fi
    if [ "$MODE" = "link" ]; then
        install_link "$dest" "$t" || status=1
    else
        install_copy "$dest" "$t" || status=1
    fi
    echo "  after:  $(describe "$dest")"
done
exit "$status"
