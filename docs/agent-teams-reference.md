# Agent Teams — Master Reference Guide

> A working reference for spawning, coordinating, and getting real value out of Claude Code agent teams.
> Source: https://code.claude.com/docs/en/agent-teams (and /en/hooks). Reflects behavior as of **v2.1.178+**.
> Status: **experimental**, disabled by default.

---

## 1. What agent teams are

Multiple Claude Code instances working together:

- **One lead** (the main session) coordinates work, assigns tasks, and synthesizes results.
- **Teammates** are *full, independent* Claude Code sessions — each with its own context window — that work on assigned tasks and **message each other directly**.

The key difference from subagents: teammates talk to each other and self-coordinate through a shared task list. You can also message any individual teammate directly without going through the lead.

### Subagents vs. agent teams

|                   | Subagents                                | Agent teams                              |
| :---------------- | :--------------------------------------- | :--------------------------------------- |
| **Context**       | Own context; result returns to caller    | Own context; fully independent           |
| **Communication** | Report back to main agent only           | Teammates message each other directly    |
| **Coordination**  | Main agent manages all work              | Shared task list with self-coordination  |
| **Best for**      | Focused tasks where only result matters  | Complex work needing discussion          |
| **Token cost**    | Lower (results summarized back)          | Higher (each teammate is a full instance)|

**Decision rule:** Use subagents for quick, focused workers that report back. Use agent teams when workers must share findings, challenge each other, and coordinate on their own.

---

## 2. Enabling (already done in this project)

Set the env var to `1`, via shell or `settings.json`:

```json
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  }
}
```

> ✅ This project already has it in `.claude/settings.local.json`. Requires a session restart to take effect.

Without this variable: no team is set up at startup, no team directories are written, and Claude will not spawn or propose teammates.

---

## 3. When to use a team (and when NOT to)

**Strong use cases** — parallel exploration adds real value:

- **Research & review** — investigate different aspects simultaneously, then share/challenge findings.
- **New modules or features** — each teammate owns a separate piece, no collisions.
- **Debugging with competing hypotheses** — teammates test rival theories in parallel and converge faster.
- **Cross-layer coordination** — frontend / backend / tests, each owned by a different teammate.

**Avoid teams for:**

- Sequential tasks, same-file edits, or work with many dependencies → use a single session or subagents.
- Routine work → a single session is more cost-effective.

Teams add coordination overhead and use **significantly more tokens**. They only pay off when teammates can operate independently.

> **Newcomer tip:** start with research/review tasks that don't write code (review a PR, research a library, investigate a bug). They show the value of parallel exploration without parallel-implementation conflicts.

---

## 4. How to spawn — prompt patterns

Describe the task and the teammates in natural language. The lead spawns them and coordinates.

**Basic, role-based (independent perspectives):**
```text
I'm designing a CLI tool that helps developers track TODO comments across
their codebase. Spawn three teammates to explore this from different angles:
one on UX, one on technical architecture, one playing devil's advocate.
```

**Specify count + model:**
```text
Spawn 4 teammates to refactor these modules in parallel. Use Sonnet for
each teammate.
```

**Parallel code review (distinct lenses so they don't overlap):**
```text
Spawn three teammates to review PR #142:
- One focused on security implications
- One checking performance impact
- One validating test coverage
Have them each review and report findings.
```

**Competing hypotheses / adversarial debate:**
```text
Users report the app exits after one message instead of staying connected.
Spawn 5 agent teammates to investigate different hypotheses. Have them talk to
each other to try to disprove each other's theories, like a scientific
debate. Update the findings doc with whatever consensus emerges.
```

**Rich, context-loaded spawn prompt (best practice):**
```text
Spawn a security reviewer teammate with the prompt: "Review the authentication
module at src/auth/ for security vulnerabilities. Focus on token handling,
session management, and input validation. The app uses JWT tokens stored in
httpOnly cookies. Report any issues with severity ratings."
```

Two ways teams form: **you request** teammates, or **Claude proposes** them (you confirm first). Claude never spawns without approval.

---

## 5. Models, effort, and plan approval

- **Models:** Teammates do **not** inherit the lead's `/model` by default. Set **Default teammate model** in `/config`; choose **Default (leader's model)** to follow the lead. Or specify per-spawn ("Use Sonnet for each teammate").
- **Effort level:** Teammates inherit the lead's effort level (split-pane parity since v2.1.186).
- **Plan approval (for risky tasks):** Require teammates to plan in read-only mode before implementing:
  ```text
  Spawn an architect teammate to refactor the authentication module.
  Require plan approval before they make any changes.
  ```
  The teammate submits a plan → lead approves or rejects with feedback → on rejection it revises and resubmits → on approval it exits plan mode and implements. The lead decides autonomously; steer it with criteria like *"only approve plans that include test coverage"* or *"reject plans that modify the database schema."*

---

## 6. Coordinating the running team

Talk to the lead in natural language; it handles assignment and delegation.

**Shared task list** (states: pending → in progress → completed):
- Tasks can **depend** on other tasks; a blocked task can't be claimed until its deps complete.
- **Lead assigns** explicitly, or teammates **self-claim** the next unassigned, unblocked task.
- Claiming uses **file locking** to avoid races. Dependencies auto-unblock when their prerequisite completes.

**Talk to teammates directly** — each is a full session:
- *In-process:* ↑/↓ in the agent panel to select, **Enter** to view + message, **x** to stop, **Ctrl+T** to toggle the task list.
- *Split-pane:* click into a teammate's pane.

**Shut down a teammate** (refer to it by name):
```text
Ask the researcher teammate to shut down
```
The teammate can approve (exits gracefully) or reject with an explanation. Shared directories are cleaned up automatically when the session ends.

**Naming:** the lead names each teammate at spawn. To get predictable names you can reference later, tell the lead what to call each one in the spawn instruction.

---

## 7. Display modes

| Mode          | What it does                                        | Requirements                         |
| :------------ | :------------------------------------------------- | :----------------------------------- |
| `in-process`  | All teammates in your main terminal (agent panel)  | **None** — works in any terminal     |
| split panes   | Each teammate gets its own pane                    | tmux **or** iTerm2 (`it2` CLI)       |

- **Default is `in-process`** (was `auto` before v2.1.179).
- `"auto"` → split panes when already inside tmux or on iTerm2, else in-process.
- `"tmux"` → split-pane mode, auto-detecting tmux vs. iTerm2.
- `"iterm2"` (v2.1.186+) → iTerm2 native panes explicitly; needs the [`it2` CLI](https://github.com/mkusaka/it2).

Set persistently:
```json
{ "teammateMode": "auto" }
```
Or per session: `claude --teammate-mode auto`

Setup notes:
- **tmux** works best on macOS; `tmux -CC` in iTerm2 is the suggested entrypoint.
- **iTerm2**: install `it2`, then enable **iTerm2 → Settings → General → Magic → Enable Python API**.
- Split panes are **not** supported in VS Code's integrated terminal, Windows Terminal, or Ghostty.

**Agent panel keys (in-process):** ↑/↓ select · **Enter** open transcript + message · **Esc** interrupt selected teammate's turn. Idle rows hide after 30s (v2.1.181+) and reappear on next turn — the teammate stays running and addressable.

---

## 8. Reusing roles via subagent definitions

Reference a [subagent](https://code.claude.com/docs/en/sub-agents) type (project / user / plugin / CLI scope) when spawning, to reuse a role:

```text
Spawn a teammate using the security-reviewer agent type to audit the auth module.
```

- The teammate honors that definition's `tools` allowlist and `model`.
- The definition's body is **appended** to the teammate's system prompt (does not replace it).
- `SendMessage` and task-management tools are **always available**, even if `tools` restricts everything else.
- ⚠️ The `skills` and `mcpServers` frontmatter fields are **NOT** applied to teammates — they load skills/MCP from project + user settings like a normal session.

---

## 9. Architecture & internals

| Component   | Role                                                              |
| :---------- | :--------------------------------------------------------------- |
| Team lead   | Main session; spawns teammates and coordinates                   |
| Teammates   | Separate Claude Code instances working assigned tasks            |
| Task list   | Shared work items teammates claim and complete                   |
| Mailbox     | Messaging system between agents                                  |

**Storage** (session-derived name = `session-` + first 8 chars of session ID):
- Team config: `~/.claude/teams/{team-name}/config.json` — **removed when the session ends**.
- Task list: `~/.claude/tasks/{team-name}/` — **persists locally**, never uploaded; resumed sessions keep tasks. Retention follows `cleanupPeriodDays`.

⚠️ Don't hand-edit or pre-author the team config — it holds runtime state (session IDs, tmux pane IDs) and is overwritten on the next state update. There is **no** project-level team config (`.claude/teams/teams.json` is treated as an ordinary file). The config's `members` array (name, agent ID, agent type) is readable by teammates to discover each other.

**Permissions:** Teammates start with the lead's permission mode (incl. `--dangerously-skip-permissions`). You can change individual modes *after* spawning, but **not per-teammate at spawn time**. Teammate permission requests bubble up to the lead — pre-approve common ops to reduce friction.

**Context & communication:**
- Each teammate loads project context (CLAUDE.md, MCP servers, skills) + the spawn prompt. **The lead's conversation history does NOT carry over.**
- Messages deliver automatically (no polling). Idle teammates auto-notify the lead.
- Messaging is **per-recipient by name** — to reach everyone, send one message per teammate.

---

## 10. Quality gates via hooks

Three team-specific hooks. **No matcher support**, run async, **exit code 2 blocks**, and they can only allow/block (not modify data).

| Hook            | Fires when…                          | Exit code 2 effect                              |
| :-------------- | :----------------------------------- | :---------------------------------------------- |
| `TeammateIdle`  | A teammate is about to go idle       | Keeps it working; stderr sent as feedback       |
| `TaskCreated`   | A task is being created              | Rolls back creation; stderr sent as feedback    |
| `TaskCompleted` | A task is being marked complete      | Prevents completion; stderr sent as feedback    |

Each also supports JSON output with `continue: false` (+ optional `stopReason`) or `{"decision":"block","reason":"…"}`.

**Payload fields:**
```json
// TeammateIdle
{ "hook_event_name": "TeammateIdle", "session_id": "...", "agent_type": "general-purpose", "cwd": "...", "transcript_path": "..." }

// TaskCreated
{ "hook_event_name": "TaskCreated", "task_name": "Deploy to production", "task_description": "Deploy the latest release", "session_id": "...", "cwd": "...", "transcript_path": "..." }

// TaskCompleted
{ "hook_event_name": "TaskCompleted", "task_name": "Deploy to production", "task_id": "task-12345", "session_id": "...", "cwd": "...", "transcript_path": "..." }
```

Example use: a `TaskCompleted` hook that runs tests and exits 2 (with the failure on stderr) to force the teammate to fix before the task closes.

---

## 11. Best practices (the part that matters for building good teams)

1. **Give teammates enough context.** They don't inherit conversation history — put task-specific details (file paths, constraints, tech stack, expected output format) directly in the spawn prompt.
2. **Right-size the team.** Start with **3–5 teammates**. Token cost scales linearly; coordination overhead and diminishing returns grow past that. Three focused teammates beat five scattered ones.
3. **Right-size tasks.** Aim for **5–6 tasks per teammate** — self-contained units with a clear deliverable (a function, a test file, a review). Too small → overhead dominates; too large → long unsupervised runs risk wasted effort. If the lead under-splits, tell it to break work into smaller pieces.
4. **Make teammates own disjoint files.** Two teammates editing the same file overwrite each other. Partition the work by file/module.
5. **Force parallelism when needed.** If the lead starts doing tasks itself: *"Wait for your teammates to complete their tasks before proceeding."*
6. **Monitor and steer.** Check progress, redirect bad approaches, synthesize as findings arrive. Don't let a team run unattended too long.
7. **For ambiguous bugs, structure adversarial debate** — explicitly tell teammates to disprove each other's theories. Sequential investigation anchors on the first plausible answer; surviving theories from a debate are more likely correct.

---

## 12. Troubleshooting

| Symptom | Fix |
| :------ | :-- |
| **Teammates not appearing** | In-process: check the agent panel (↑/↓, Enter). Idle rows hide after 30s — message by name to revive. Confirm the task was complex enough to warrant a team. |
| **Split panes not working** | `which tmux`; for iTerm2 verify `it2` installed + Python API enabled. |
| **Too many permission prompts** | Pre-approve common operations in permission settings before spawning. |
| **Teammates stop on errors** | Select the teammate (Enter / click pane), give direct instructions, or spawn a replacement. |
| **Lead shuts down early** | Tell it to keep going; tell it to wait for teammates instead of doing work itself. |
| **Orphaned tmux session** | `tmux ls` then `tmux kill-session -t <session-name>`. |

---

## 13. Known limitations (experimental)

- **No session resumption for in-process teammates** — `/resume` and `/rewind` don't restore them; the lead may try to message dead teammates. Fix: tell it to spawn new ones.
- **Task status can lag** — teammates sometimes don't mark tasks complete, blocking dependents. Update manually or nudge the teammate.
- **Shutdown can be slow** — teammates finish the current request/tool call first.
- **One team per session**, scoped to that session. No additional named teams, no sharing across sessions.
- **No nested teams** — only the lead manages the team; teammates can't spawn teammates.
- **Lead is fixed** — can't promote a teammate or transfer leadership.
- **Permissions set at spawn** — all start with the lead's mode (changeable individually afterward).
- **Split panes need tmux/iTerm2** — unsupported in VS Code integrated terminal, Windows Terminal, Ghostty.

---

## 14. Quick-start checklist (for this project)

- [x] `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` set in `.claude/settings.local.json`
- [ ] Restart the session so the env var loads
- [ ] (Optional) pick a display mode: `claude --teammate-mode auto`, or set `teammateMode` in settings
- [ ] (Optional) set **Default teammate model** in `/config`
- [ ] Start small: a 3-teammate research/review task with distinct lenses
- [ ] Give each teammate file ownership boundaries + a context-rich spawn prompt
- [ ] (Optional) add `TaskCompleted`/`TeammateIdle` hooks as quality gates
```
