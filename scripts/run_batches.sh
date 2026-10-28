#!/bin/zsh
# Download in batches of 25 codices; after each batch run steps 3-6 so the visualizer grows as we go.
# Then one more pass over everything to fetch pages that failed (e.g. while the laptop slept).
# Usage: scripts/run_batches.sh [total codices, default 200] [first batch start, default 0]
cd "$(dirname "$0")/.."
PY=.venv/bin/python
BATCH=25
TOTAL=${1:-200}   # a bit more than the 196 codices; batches past the end do nothing
FIRST=${2:-0}     # resume from this codex number

update_visualizer() {
  $PY code/03_organize_metadata.py | tail -3
  $PY -u code/04_extract_illustrations.py | grep -v "already extracted"
  $PY code/05_cluster_illustrations.py
  $PY code/06_build_visualizer.py
}

download() {   # retry a batch when Ktiv is down (the step stops itself), up to 12 times, 10 min apart
  for try in {1..12}; do
    $PY -u code/02_download_manuscripts.py "$@" && return 0
    echo "$(date '+%F %T') step 2 stopped (Ktiv down?); waiting 10 min"
    sleep 600
  done
  return 1
}

for (( start = FIRST; start < TOTAL; start += BATCH )); do
  echo "\n######## BATCH codices $start-$((start + BATCH - 1))  $(date '+%F %T')"
  download --start $start --limit $BATCH || { echo "giving up on this batch"; exit 2; }
  update_visualizer
  echo "######## BATCH DONE $start  $(date '+%F %T')"
done

echo "\n######## RETRY PASS (missing pages only)  $(date '+%F %T')"
download || exit 3
update_visualizer
echo "ALL BATCHES DONE $(date '+%F %T')"
