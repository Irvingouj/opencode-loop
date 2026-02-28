from __future__ import annotations


def build_supervisor_help_text() -> str:
    return """opencode-loop supervisor guide

What this tool is

`opencode-loop` is a loop controller that repeatedly calls `opencode run` in two roles:

1. evaluator
2. implementer

The evaluator decides whether the goal is already complete. If not complete, it must produce a concrete next task for the implementer.
The implementer executes that next task and reports a machine-readable result.
The script keeps alternating between these two roles until:

1. the evaluator returns `is_done=true`
2. the maximum iteration limit is reached
3. the process hits an unrecoverable error

If you are an upstream/supervisor LLM, treat this tool as an execution orchestrator, not as a general chatbot.
Your job is to launch it with enough structure that the evaluator and implementer can work without guessing.

Mental model

- `goal`: the high-level outcome you want achieved
- `done_criteria`: the exact completion standard
- `checks`: commands or validations that define acceptance
- evaluator: decides whether work is done and what should happen next
- implementer: performs one concrete unit of work
- `session_id`: the underlying OpenCode conversation/session identifier
- `--continue` / `-c`: resume the script-level loop from the last saved state

How the loop behaves

Per iteration, the script does this:

1. Build evaluator prompt
2. Run `opencode run --format json --thinking`
3. Parse evaluator JSON
4. If done, exit successfully
5. If not done, build implementer prompt using evaluator output
6. Run `opencode run --format json --thinking`
7. Parse implementer JSON
8. Save implementer result as `last_action_json`
9. Continue to the next iteration

JSON contract expectations

Evaluator must return a top-level JSON object with:

- required: `is_done` (bool), `reason` (str)
- optional: `next_task_prompt` (str), `recommended_checks` (list[str]), `fix_plan` (list[str]), `context_for_implementer` (str)

If evaluator returns `is_done=false`, it must also provide a non-empty `next_task_prompt`.
If evaluator returns invalid JSON, wrapped JSON, empty output, or semantically invalid output, the script will try to recover in the same OpenCode session by sending a repair prompt with `-c`.

Implementer must return a top-level JSON object with:

- required: `summary` (str), `files_touched` (list[str]), `checks` (list[object])
- optional: `risks` (list[str]), `open_issues` (list[str])

State persistence and resume

The script writes a state file in the current working directory:

- `.opencode-loop-state.json`

That file stores enough information to resume the loop:

- current session id
- current phase (`evaluator` or `implementer`)
- next iteration number
- run history
- last implementer result
- pending implementer payload when evaluator already completed but implementer has not yet run
- prompt templates and schema config required to resume consistently

To resume the last interrupted run, use:

```bash
opencode-loop --continue
```

or:

```bash
opencode-loop -c
```

When resumed, the script uses the saved loop state and also uses `opencode -c` for the first resumed phase so the underlying model session continues in context.

Streaming behavior

The tool uses `opencode run --format json --thinking` by default.
It prints a transcript-style stream that usually includes:

- current phase step boundaries
- tool calls
- tool input summaries
- tool output previews
- reasoning summaries
- text output lines
- step finish reasons and token counts

This output is designed for live observation by a supervisor LLM or human operator.

How to invoke it well

Good invocation strategy:

1. Be explicit about the goal
2. Be explicit about done criteria
3. Supply concrete checks whenever possible
4. Restrict allowed paths when you want to reduce blast radius
5. Keep forbidden changes concrete
6. Choose a model explicitly when reproducibility matters

Minimal example:

```bash
opencode-loop \\
  --goal "Add a health endpoint that returns 200 and JSON body { ok: true }" \\
  --done-criteria "Endpoint exists, tests pass, and no unrelated files are modified" \\
  --check "npm test -- --runInBand" \\
  --check "curl -f http://localhost:3000/health"
```

Example with explicit model and agent:

```bash
opencode-loop \\
  --model openai/gpt-5-mini \\
  --agent builder \\
  --goal "Refactor the parser to eliminate duplicate branch logic" \\
  --done-criteria "Behavior is unchanged and parser tests pass" \\
  --check "uv run pytest tests/test_parser.py -q"
```

When to use `--goal` vs `--goal-file`

- Use `--goal` for short goals
- Use `--goal-file` when the task description is long, multi-part, or generated elsewhere

When to use `--done-criteria` vs `--done-criteria-file`

- Use inline criteria for short completion conditions
- Use the file form when the completion contract is long or generated

Checks behavior

You can provide checks in two ways:

1. repeat `--check`
2. repeat `--check-file`

The evaluator may also recommend additional checks.
The script computes `effective_checks` as:

- evaluator recommended checks + base checks
- deduplicated, preserving order
- capped to `--max-effective-checks` (default: 5)

If evaluator output had to be recovered, evaluator-recommended checks are discarded for that iteration and the script falls back to base checks only.

Important control flags

- `--max-iters`: hard stop for loop length
- `--json-repair-attempts`: how many repair retries to allow for invalid JSON
- `--max-effective-checks`: upper bound on checks passed to implementer prompt
- `--allowed-paths`: edit allowlist communicated to the agent
- `--forbidden-changes`: explicit disallowed change classes
- `--system-prompt` / `--system-prompt-file`: extra prompt prefix injected into every turn
- `--session`: manually continue a specific OpenCode session for fresh runs
- `--no-pass-evaluator-json`: omit full evaluator JSON from implementer prompt if needed

What an upstream LLM should provide

If you are constructing a command for another agent or automation layer, provide at least:

1. one precise goal
2. one precise done criteria string
3. one or more checks if they are known

Prefer:

- concrete filenames
- concrete endpoints
- concrete commands
- concrete invariants

Avoid vague goals such as:

- "make it better"
- "fix the architecture"
- "clean this up"

Instead write:

- "Move JSON repair state handling into a dedicated module without changing CLI behavior; all tests must pass"

Failure and recovery behavior

The script can recover from:

- empty text output
- malformed JSON
- wrapped JSON under `required` / `optional`
- semantic evaluator errors such as `is_done=false` with empty `next_task_prompt`

Recovery is done by prompting the same session again with a repair instruction and `-c`.

What `--continue` does not mean

`--continue` is not a generic way to change the task while keeping history.
It resumes the last saved loop state only.
Do not combine it with a new goal, new checks, or a new model in the same invocation.

Exit behavior

- exit code `0`: evaluator determined the goal is complete
- exit code `2`: configuration, parsing, or unrecoverable runtime error
- exit code `3`: max iterations reached without completion
- exit code `127`: `opencode` executable not found

Practical recommendations for supervisor LLMs

1. Always set a specific goal and done criteria
2. Add at least one verification check whenever feasible
3. Set an explicit model for reproducibility-sensitive workflows
4. Use `--goal-file` when prompt size gets large
5. Prefer short, testable tasks over broad ambiguous objectives
6. Use `--continue` after interruptions instead of restarting from scratch

Short command templates

Fresh run:

```bash
opencode-loop --goal "..." --done-criteria "..." --check "..."
```

Resume:

```bash
opencode-loop --continue
```

Human-oriented flag summary

Use `-h` or `--help-human` if you want the concise argparse option list instead of this supervisor manual.
"""
