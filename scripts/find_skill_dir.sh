#!/bin/sh
# Print the absolute directory of this skill (the folder containing SKILL.md).
#
# Usage:
#   sh <any-install>/scripts/find_skill_dir.sh          # resolve from this copy
#   sh scripts/find_skill_dir.sh --search               # scan known harness dirs
#
# Without --search the script resolves its own location, following symlinks,
# so a harness that only knows one install path can still print the canonical
# directory. With --search it walks the usual per-harness skill roots and prints
# the first one that contains git-commit-helper/SKILL.md.

set -eu

resolve_self() {
    script="$0"
    while [ -L "$script" ]; do
        target="$(readlink "$script")"
        case "$target" in
            /*) script="$target" ;;
            *) script="$(dirname "$script")/$target" ;;
        esac
    done
    dir="$(cd "$(dirname "$script")/.." && pwd -P)"
    if [ -f "$dir/SKILL.md" ]; then
        printf '%s\n' "$dir"
        return 0
    fi
    return 1
}

search_known_roots() {
    home="${HOME:-$USERPROFILE}"
    for root in \
        ".agents/skills" ".claude/skills" ".codex/skills" ".cursor/skills" \
        ".gemini/skills" ".hermes/skills" ".config/opencode/skills" ".copilot/skills" \
        ".pi/agent/skills" ".omp/agent/skills"; do
        candidate="$home/$root/git-commit-helper"
        if [ -f "$candidate/SKILL.md" ]; then
            (cd "$candidate" && pwd -P)
            return 0
        fi
    done
    for root in ".claude/skills" ".agents/skills"; do
        candidate="$PWD/$root/git-commit-helper"
        if [ -f "$candidate/SKILL.md" ]; then
            (cd "$candidate" && pwd -P)
            return 0
        fi
    done
    return 1
}

if [ "${1:-}" = "--search" ]; then
    search_known_roots || { echo "git-commit-helper: no install found in known skill roots" >&2; exit 1; }
else
    resolve_self || search_known_roots || { echo "git-commit-helper: cannot resolve skill directory" >&2; exit 1; }
fi
