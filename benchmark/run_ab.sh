#!/usr/bin/env bash
# Clean A/B: does the diagram-authoring skill change a crawl agent's diagrams and token cost?
# The ONLY difference between arms is the skill. Same model, same repo, same rtk rules, same turn cap.
# Usage: run_ab.sh <model-id>      e.g.  run_ab.sh claude-opus-4-8
set -euo pipefail
MODEL="${1:?usage: run_ab.sh <model-id>  (claude-opus-4-8 | claude-sonnet-5 | claude-fable-5-1)}"
BIN=/root/.vscode-server/extensions/anthropic.claude-code-2.1.258/resources/native-binary/claude
BASE=/root/groundstation/docs/active/assets/skill-ab-test
GS=/root/groundstation/.claude/skills/diagram-authoring   # repo skill copy
GG=/root/.claude/skills/diagram-authoring                 # global skill copy
HOLD=/tmp/ab-skill-hold
TOOLS="Bash,Read,Write,Edit,Glob,Grep"

restore(){ [ -d "$HOLD/repo" ] && mv "$HOLD/repo" "$GS" || true; [ -d "$HOLD/glob" ] && mv "$HOLD/glob" "$GG" || true; }
trap restore EXIT
mkdir -p "$HOLD" "$BASE/baseline" "$BASE/with-skill"

# ---- Arm A: baseline. Skill HIDDEN from BOTH skill dirs so it cannot be discovered. ----
[ -d "$GS" ] && mv "$GS" "$HOLD/repo" || true
[ -d "$GG" ] && mv "$GG" "$HOLD/glob" || true
if [ -d "$GS" ] || [ -d "$GG" ]; then echo "ISOLATION FAILED — aborting"; exit 1; fi
echo "[A] baseline (no skill) on $MODEL ..."
rm -f "$BASE/baseline/DONE" "$BASE/baseline/run.json"
"$BIN" -p "$(cat /root/groundstation/docs/active/2026-09-12-ab-baseline-prompt.md)" \
  --model "$MODEL" --permission-mode acceptEdits --allowedTools "$TOOLS" \
  --output-format json --max-turns 200 > "$BASE/baseline/run.json" 2>&1
restore   # skill back for arm B

# ---- Arm B: with the skill present. ----
echo "[B] with-skill on $MODEL ..."
rm -f "$BASE/with-skill/DONE" "$BASE/with-skill/run.json"
"$BIN" -p "$(cat /root/groundstation/docs/active/2026-09-12-ab-withskill-prompt.md)" \
  --model "$MODEL" --permission-mode acceptEdits --allowedTools "$TOOLS,Skill" \
  --output-format json --max-turns 200 > "$BASE/with-skill/run.json" 2>&1
echo "A/B done for $MODEL. Parse run.json in each folder for usage."
