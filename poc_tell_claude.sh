#!/usr/bin/env bash
# POC: drive an interactive `claude` session in a tmux pane to extract a crawled
# job file. The HOST does the heavy, deterministic parts (slice + merge); claude
# only runs the per-shard LLM extraction via parallel subagents.
#
#   host  : slice input -> N small shard files          (free, deterministic)
#   claude: extract shards in WAVES of MAX_AGENTS subagents (the only LLM work)
#   host  : merge shard outputs by index -> $OUT         (free, deterministic)
#
# Why this shape: pre-slicing means each subagent reads only its ~12 jobs (not
# the 13MB input); host-side merge removes a fragile agent step. PER_SHARD fixes
# the shard SIZE; MAX_AGENTS bounds how many run per wave — so a 1884-job file
# becomes 157 small shards run as ~10 reliable waves, not one 157-Task message.
#
# ⚠️ Personal one-off convenience only. Production extraction = the LLM-API path
#    (manage.py extract_jobs + LLMService). Run from a NORMAL terminal (NOT
#    inside a Claude Code session):  bash poc_tell_claude.sh [provider] [date]
#
# Tunables (env):
#   MODEL=claude-sonnet-4-6   model for the claude session + subagents
#   PER_SHARD=12              jobs per shard (shard SIZE, honored strictly)
#   MAX_AGENTS=12             subagents per WAVE (concurrency, not a total cap)
#   DESC=6000                 description chars sent per job (token control)
#   FRESH=1                   re-slice from scratch (default: resume existing shards)
set -euo pipefail

PROJECT="$(cd "$(dirname "$0")" && pwd)"
SESSION="jbextract"
PROVIDER="${1:-remotive}"
DATE="${2:-$(date +%F)}"
MODEL="${MODEL:-claude-sonnet-4-6}"
PER_SHARD="${PER_SHARD:-12}"
MAX_AGENTS="${MAX_AGENTS:-12}"
DESC="${DESC:-6000}"
FRESH="${FRESH:-0}"

cd "$PROJECT/backend"
PY=.venv/bin/python
IN="data/crawl/${PROVIDER}/${DATE}.json"
OUT="data/extracted/${PROVIDER}/${DATE}.json"
SHARDS="data/extracted/${PROVIDER}/.shards-${DATE}"
PROMPT_FILE="apps/jobs/prompts/jd_extraction.md"

[ -f "$IN" ] || { echo "✗ input not found: $IN"; exit 1; }

# Ctrl-C (or kill) tears down the detached claude session — otherwise it keeps
# running in the background (it's a tmux-server child, not ours). The in-flight
# wave's shards become invalid/partial and are simply redone on resume. Only on
# INT/TERM, not EXIT — a clean finish leaves the session alive for inspection.
trap 'echo; echo "⏹  stopping — killing claude session $SESSION"; tmux kill-session -t "$SESSION" 2>/dev/null; exit 130' INT TERM

# ── helpers ────────────────────────────────────────────────────────────────────
# Busy = the spinner status line is on screen. Its text changes across CLI
# versions, so match several shapes. Used only as an idle-detector; the shard
# output files are the authoritative completion signal.
claude_busy() {
    tmux capture-pane -t "${1:-$SESSION}" -p \
        | grep -qE 'esc to interrupt|· ↓ [0-9.]+k? tokens|…[[:space:]]*\([0-9]+m? ?[0-9]*s'
}

# send a message to the claude pane, wait until the response settles
tell_claude() {
    local message="$1" target="${2:-$SESSION}" waited=0
    tmux send-keys -t "$target" "$message"; sleep 0.3; tmux send-keys -t "$target" Enter
    while [ "$waited" -lt 60 ]; do sleep 0.5; waited=$((waited+1)); claude_busy "$target" && break; done
}

# ── 1. HOST slices input into shard files (deterministic, free) ───────────────
# Re-slice when: forced (FRESH=1), no shard dir yet, OR shards exist but NOTHING
# has been extracted yet (no *.out.json). The last case lets you change
# PER_SHARD/MAX_AGENTS by simply re-running — without it, stale shards from a
# prior run silently win (the jobspy "4×471" trap). Mid-run (some .out.json
# present) we keep the existing shards and resume.
NEED_SLICE=0
if [ "$FRESH" = "1" ] || [ ! -d "$SHARDS" ]; then
    NEED_SLICE=1
elif ! ls "$SHARDS"/shard*.out.json >/dev/null 2>&1; then
    NEED_SLICE=1
fi
if [ "$NEED_SLICE" = "1" ]; then
    rm -rf "$SHARDS" "$OUT"
    "$PY" - "$IN" "$SHARDS" "$PER_SHARD" "$MAX_AGENTS" "$DESC" <<'PY'
import json, sys, os, math
inp, shards, size, per_wave, desc = sys.argv[1], sys.argv[2], max(1, int(sys.argv[3])), max(1, int(sys.argv[4])), int(sys.argv[5])
jobs = json.load(open(inp))
n = len(jobs)
os.makedirs(shards, exist_ok=True)
k = 0
for start in range(0, n, size):                 # PER_SHARD = shard SIZE, honored strictly
    chunk = [{"index": i, "title": jobs[i].get("title", ""), "company": jobs[i].get("company", ""),
              "location": jobs[i].get("location", ""), "source_url": jobs[i].get("source_url", ""),
              "description": (jobs[i].get("description") or "")[:desc]}
             for i in range(start, min(start + size, n))]
    json.dump(chunk, open(os.path.join(shards, f"shard{k}.json"), "w"), ensure_ascii=False)
    k += 1
waves = math.ceil(k / per_wave)
print(f"{n} jobs -> {k} shards × ~{size} jobs · {per_wave} agents/wave -> {waves} wave(s)")
if size > 40:
    print(f"  ⚠ {size} jobs/shard is large: each subagent processes them SEQUENTIALLY "
          f"(slow). Lower --per-shard for smaller, faster shards.", file=sys.stderr)
PY
fi

# ── 2. figure out which shards still need extracting (resume) ─────────────────
PENDING=()
for f in "$SHARDS"/shard*.json; do
    case "$f" in *.out.json) continue;; esac          # skip output files
    out="${f%.json}.out.json"
    if [ -f "$out" ] && "$PY" -c "import json;json.load(open('$out'))" 2>/dev/null; then continue; fi
    PENDING+=("$f")
done
NSH=$(ls "$SHARDS"/shard*.json 2>/dev/null | grep -vc '\.out\.json$' || true)
echo "Shards: $NSH total, ${#PENDING[@]} pending (model=$MODEL)"

# ── 3. spawn claude ONCE, extract in WAVES of MAX_AGENTS shards ───────────────
# PER_SHARD fixes shard SIZE; MAX_AGENTS = subagents per wave (concurrency, not
# a total cap). Each wave spawns the next batch of pending shards, waits for
# their .out.json, then the next wave — so big files (157 small shards) run as
# ~10 reliable waves instead of one 157-Task message. Resume-safe across waves.
is_done() { [ -f "$1" ] && "$PY" -c "import json;json.load(open('$1'))" 2>/dev/null; }

if [ "${#PENDING[@]}" -gt 0 ]; then
    tmux kill-session -t "$SESSION" 2>/dev/null || true
    tmux new-session -d -s "$SESSION" -c "$PROJECT/backend" -x 220 -y 50
    tmux send-keys -t "$SESSION" "env -u CLAUDECODE claude --model $MODEL --dangerously-skip-permissions" Enter
    echo "Booting claude…"; sleep 6

    wave=0 stall=0
    while :; do
        # recompute pending shards each wave (drives progress + resume)
        PEND=()
        for f in "$SHARDS"/shard*.json; do
            case "$f" in *.out.json) continue;; esac
            is_done "${f%.json}.out.json" || PEND+=("$f")
        done
        [ "${#PEND[@]}" -eq 0 ] && break

        WAVE=("${PEND[@]:0:$MAX_AGENTS}")
        wave=$((wave + 1))
        echo "── Wave $wave: ${#WAVE[@]} shards (${#PEND[@]} pending) ──"
        MAP=$(for f in "${WAVE[@]}"; do echo "  - $f  ->  ${f%.json}.out.json"; done)
        read -r -d '' PROMPT <<EOF || true
Batch JD extraction. There are ${#WAVE[@]} shard files; spawn ${#WAVE[@]} PARALLEL subagents with the Task tool — ONE per shard, all launched in a single message. Each subagent must:
1. read $PROMPT_FILE — the canonical JD-extraction prompt. It is the SOURCE OF TRUTH for field semantics: follow its Field rules EXACTLY (seniority scale + title-override rule, role_category buckets, canonical skill identifiers, importance distribution).
2. read its assigned shard file (a JSON array of {index,title,company,location,description});
3. for EVERY job in the shard, write the shard's .out.json as a JSON array of {"index": <same index as input>, "extracted": {...}}.

STRICT OUTPUT CONTRACT (nothing validates this automatically — obey it exactly):
- "extracted" has ONLY these keys: is_remote(bool), seniority(int 0-5 or null), role_category(string), job_type(string), salary_min(int), salary_max(int), salary_currency(string), salary_type(string), experience_min(number), experience_max(number or null), degree_requirement(int), skills(array of {"name","importance"}). No extra keys; no title/company/location (the crawl already has those).
- role_category MUST be EXACTLY one of: ba, backend, data_eng, data_ml, design, devops, frontend, fullstack, mobile, other, qa. Never invent another value; if unsure use "other".
- skills[].name MUST be a CANONICAL snake_case identifier from the catalog in the prompt file (e.g. python, rest_api, postgresql, react). If a skill is NOT in that catalog, DROP it — never emit free-form phrases (no "team leadership", "fast learner", etc.). importance is an int 1-5.
- Unknown numbers = 0 (or null where null is allowed). Do NOT guess salaries.
- Each .out.json is a VALID JSON array ONLY — no markdown fences, no prose, no trailing commentary.

Assign exactly one subagent per shard (input -> output):
$MAP
Do NOT read any file other than the prompt + your shard. Do NOT merge or touch $IN/$OUT — a host script merges. Every input index must appear EXACTLY once in your shard's output. When ALL ${#WAVE[@]} .out.json files are written, reply exactly: DONE.
EOF
        tell_claude "$PROMPT"

        # wait for THIS wave's outputs (file = truth; idle pane = give up on wave)
        waited=0 idle=0
        while [ "$waited" -lt 1800 ]; do
            ready=1
            for f in "${WAVE[@]}"; do is_done "${f%.json}.out.json" || { ready=0; break; }; done
            [ "$ready" = 1 ] && break
            if claude_busy "$SESSION"; then idle=0; else idle=$((idle + 5)); fi
            [ "$idle" -ge 90 ] && break
            sleep 5; waited=$((waited + 5))
        done

        # progress guard: 2 consecutive waves with zero new outputs → abort (resume by re-running)
        new=0
        for f in "${WAVE[@]}"; do is_done "${f%.json}.out.json" && new=$((new + 1)); done
        echo "   wave $wave: $new/${#WAVE[@]} shards extracted"
        if [ "$new" -eq 0 ]; then
            stall=$((stall + 1))
            [ "$stall" -ge 2 ] && { echo "⚠ two waves with no progress — aborting; re-run to resume"; break; }
        else
            stall=0
        fi
    done
fi

# ── 4. HOST merges shard outputs by index (deterministic, free) ───────────────
"$PY" - "$IN" "$OUT" "$SHARDS" <<'PY'
import json, sys, glob, os
inp, out, shards = sys.argv[1], sys.argv[2], sys.argv[3]
jobs = json.load(open(inp))
got = {}
for f in glob.glob(os.path.join(shards, "shard*.out.json")):
    try:
        for r in json.load(open(f)):
            if isinstance(r, dict) and "index" in r and "extracted" in r:
                got[r["index"]] = r["extracted"]
    except Exception as e:
        print(f"  ! skip {os.path.basename(f)}: {e}")
for i, j in enumerate(jobs):
    if i in got:
        j["extracted"] = got[i]
missing = [i for i in range(len(jobs)) if i not in got]
os.makedirs(os.path.dirname(out), exist_ok=True)
json.dump(jobs, open(out, "w"), ensure_ascii=False, indent=2)
print(f"merged {len(got)}/{len(jobs)} jobs"
      + (f" — MISSING {len(missing)}: {missing[:15]}{'…' if len(missing) > 15 else ''}" if missing else " — complete ✓"))
sys.exit(0 if not missing else 2)
PY
MERGE_RC=$?

# ── 5. result + cleanup (keep shards if anything is missing, for resume) ──────
echo
if [ "$MERGE_RC" = 0 ]; then
    echo "✓ $OUT written ($("$PY" -c "import json;print(len(json.load(open('$OUT'))))") jobs)"
    rm -rf "$SHARDS"
    echo "Next: $PY manage.py import_extracted --provider $PROVIDER --date $DATE --dry-run"
else
    echo "⚠ some shards missing — kept $SHARDS for resume. Re-run the SAME command to fill gaps,"
    echo "  or inspect:  tmux attach -t $SESSION"
fi
# tmux kill-session -t "$SESSION" 2>/dev/null || true   # uncomment to auto-close
