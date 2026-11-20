#!/bin/sh
# Install the local-html-report skill for Claude Code, Codex, and/or Antigravity.
#
#   ./install.sh [--claude] [--codex] [--antigravity] [--project DIR] [--link]
#
# With no tool flags, all three are installed. --project DIR installs into DIR's project-level
# skill folders instead of the user-level ones. --link symlinks to this checkout, not copying.
set -eu

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
src=$here/skills/local-html-report
claude=0 codex=0 anti=0 link=0 project=

while [ $# -gt 0 ]; do
    case $1 in
        --claude) claude=1 ;;
        --codex) codex=1 ;;
        --antigravity) anti=1 ;;
        --link) link=1 ;;
        --project) shift; project=${1:?--project needs a directory} ;;
        -h|--help) sed -n '2,7p' "$0"; exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
    shift
done
[ $((claude + codex + anti)) -eq 0 ] && claude=1 codex=1 anti=1

install_to() {
    dest=$1/local-html-report
    mkdir -p "$1"
    rm -rf "$dest"
    if [ "$link" -eq 1 ]; then
        ln -s "$src" "$dest"
    else
        mkdir -p "$dest"
        (cd "$src" && tar --exclude=.venv --exclude=__pycache__ -cf - .) | (cd "$dest" && tar -xf -)
    fi
    echo "Installed: $dest"
}

if [ -n "$project" ]; then
    [ "$claude" -eq 1 ] && install_to "$project/.claude/skills"
    # Codex and Antigravity both read .agents/skills in a workspace.
    if [ "$codex" -eq 1 ] || [ "$anti" -eq 1 ]; then install_to "$project/.agents/skills"; fi
else
    [ "$claude" -eq 1 ] && install_to "$HOME/.claude/skills"
    [ "$codex" -eq 1 ] && install_to "$HOME/.agents/skills"
    [ "$anti" -eq 1 ] && install_to "$HOME/.gemini/config/skills"
fi
command -v uv >/dev/null 2>&1 || echo "Note: uv is required at run time (https://docs.astral.sh/uv/)." >&2
