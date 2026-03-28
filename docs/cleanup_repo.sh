#!/bin/bash
# cleanup_repo.sh — Organise ccn-linux-qdisc-study into clean structure
# Amritha S — VIT Chennai 2026
# Run from: ~/ccn-linux-qdisc-study/
# Usage: bash cleanup_repo.sh

set -e
REPO="$HOME/ccn-linux-qdisc-study"
cd "$REPO"

echo "=== ACAPE Repo Cleanup ==="
echo "Working in: $REPO"
echo ""

# ── Create clean directory structure ──────────────────────────
mkdir -p scripts ebpf logs plots data docs

# ── Move all Python scripts to scripts/ ───────────────────────
echo "Moving scripts..."
for f in *.py setup_ns.sh; do
    [ -f "$f" ] && mv "$f" scripts/ && echo "  moved: $f → scripts/"
done

# ── Move all .c and Makefile to ebpf/ ─────────────────────────
echo "Moving eBPF files..."
for f in *.c Makefile tc_monitor.o; do
    [ -f "$f" ] && mv "$f" ebpf/ && echo "  moved: $f → ebpf/"
done

# ── Move logs ─────────────────────────────────────────────────
echo "Moving logs..."
for f in *.csv *.log *.json; do
    [ -f "$f" ] && mv "$f" logs/ && echo "  moved: $f → logs/"
done
[ -d "results_controllertry1" ] && mv results_controllertry1/* logs/ 2>/dev/null && \
    rmdir results_controllertry1 && echo "  merged: results_controllertry1/ → logs/"

# ── Move plots ────────────────────────────────────────────────
echo "Moving plots..."
for f in *.png *.pdf; do
    [ -f "$f" ] && mv "$f" plots/ && echo "  moved: $f → plots/"
done

# ── Move HTML/docs ────────────────────────────────────────────
echo "Moving docs..."
for f in *.html *.md *.sh; do
    [ -f "$f" ] && [ "$f" != "README.md" ] && mv "$f" docs/ && echo "  moved: $f → docs/"
done

# ── Keep ONLY these scripts (remove old duplicates) ───────────
echo ""
echo "Keeping only canonical scripts..."
cd scripts/
# The canonical files we want to keep
KEEP=(
    "setup_ns.sh"
    "acape_v5.py"
    "plot_acape.py"
    "controller.py"
    "plot_part3.py"
    "ebpf_dashboard.py"
)

for f in *.py *.sh; do
    keep=false
    for k in "${KEEP[@]}"; do
        [ "$f" = "$k" ] && keep=true && break
    done
    if [ "$keep" = false ]; then
        echo "  archiving old: $f"
        mkdir -p ../docs/archive
        mv "$f" ../docs/archive/ 2>/dev/null || true
    fi
done
cd "$REPO"

# ── Final structure printout ──────────────────────────────────
echo ""
echo "=== Final Structure ==="
find . -not -path './.git/*' -not -name '.git' | sort | \
    sed 's|[^/]*/|  |g' | head -60

echo ""
echo "✅ Cleanup complete."
echo ""
echo "Next steps:"
echo "  git add -A"
echo "  git commit -m 'repo: clean structure'"
echo "  git push"
