# Benchmark: skill vs no-skill

Measures whether the diagram-authoring skill changes a crawl agent's diagrams and token cost. The only
variable is the skill; everything else is held constant.

## Method
- Same model on both arms, pinned with `--model`.
- Same repo under test, same task prompt (`ab-baseline-prompt.md` and `ab-withskill-prompt.md`), same
  turn cap.
- Arm A (baseline): the skill is physically MOVED OUT of the skill dirs so the agent cannot discover
  it. Excluding the `Skill` tool from `--allowedTools` is NOT enough — a headless agent gets the skill
  list injected into its context and will invoke it anyway.
- Arm B (with-skill): the skill is present.

## Run
```
./run_ab.sh <model-id>        # claude-opus-4-8 | claude-sonnet-5 | claude-fable-5-1
```
Each arm writes a `run.json` in its output folder. Parse `usage` (input, output, cache) and `num_turns`.

## Note on portability
`run_ab.sh` is the exact harness we used; its paths (the repo under test, the skill dirs, the Claude
binary) are absolute and environment-specific. Adapt those paths for your setup. Treat it as the
reference implementation of the isolation method, not a drop-in.

## Cost
Real money. The pilot measured ~2.2 M tokens (including cache reads) per arm. Budget accordingly, and
prefer one deliberate run per model over repeated runs.
