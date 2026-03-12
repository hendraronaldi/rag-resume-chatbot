# Phase SOP — AI-Assisted Development Workflow

> Save to: `docs/agent-guides/sop-phases.md`
> Companion files: `sop.md` (branch/commit rules), `AGENTS.md` (agent config)

---

## Phase SOP Index

- [Phase Boundary Rules](#phase-boundary-rules) — read this first
- [Phase 1: PRE-DEVELOPMENT](#phase-1--pre-development)
- [Phase 2: PLANNING](#phase-2--planning)
- [Phase 3: DEVELOPMENT](#phase-3--development)
- [Phase 4: TESTING](#phase-4--testing)
- [Phase 5: DOCUMENTATION](#phase-5--documentation)
- [Phase 6: CONTEXT UPDATE](#phase-6--context-update)
- [Phase 7: PR / HANDOFF](#phase-7--pr--handoff)
- [Phase Flow Summary](#phase-flow-summary)

---

## Phase Boundary Rules

> These apply across ALL phases. Violating these is the #1 cause of broken agentic workflows.

### Rule 1 — Fresh Session at Every Phase Boundary

Each phase starts a new OpenCode session.
Never carry context across phase boundaries.
Order: PRE-DEVELOPMENT → PLANNING → DEVELOPMENT → TESTING → DOCUMENTATION → CONTEXT UPDATE → PR

### Rule 2 — Compact Before Closing

At the end of each phase, the agent writes a compact summary artifact to disk.
The next phase reads only that artifact plus relevant guide files.
Never feed the next phase the full conversation history.

### Rule 3 — Human Gate at Every Phase Boundary

| Phase End       | Gate Artifact    | Human Action                            |
|-----------------|------------------|-----------------------------------------|
| PRE-DEVELOPMENT | proposal.md      | Read and approve before planning starts |
| PLANNING        | tasks.md         | Review and approve before dev starts    |
| TESTING         | test-coverage.md | Spot-check AC coverage                  |
| PR              | PR description   | Read and approve before submitting      |

### Rule 4 — Files Are the Memory, Not the Context Window

`progress.md`, `tasks.md`, `research-notes.md`, `lessons.md` — these survive between sessions.
If it is not written to a file, it does not exist in the next session.
The context window is working memory. Your files are the persistent brain.

### Rule 5 — Stay Below 40% Context Utilization

If a session feels long or heavy (many tool calls, long file reads), compact immediately.
Write progress to disk. Close session. Start fresh.
This prevents reasoning degradation that occurs when the context window fills up.

### Rule 6 — Read .gitignore Before Any File Operation

Every agent, every session, every phase.
If a task requires touching a .gitignore-matched path — STOP and report to human immediately.
Never bypass this rule regardless of urgency.

---

## Phase 1 — PRE-DEVELOPMENT

**Goal:** Understand the task completely before any plan or code is written.
**Agent:** `plan`
**Entry condition:** You have a task description (even messy or incomplete)
**Exit condition:** `openspec/changes/{feature}/proposal.md` exists and is human-approved

---

### Steps

#### 1.1 — Start Fresh Session

Open a new OpenCode session.
Switch to `plan` agent.
Do not reuse a session from any previous work.

#### 1.2 — Prime Context

Run: `/prime-context`

Agent reads and confirms loading of:
- `docs/agent-guides/architecture.md`
- `docs/agent-guides/entry-points.md`
- `docs/agent-guides/sop.md`
- `docs/agent-guides/sop-phases.md`

Agent output must confirm: "I have read [list files]. Ready for task input."
If agent does not confirm — explicitly prompt it to read each file before continuing.

#### 1.3 — Input Processing

Run: `/understand-task`

Paste your raw input. It can be messy, incomplete, or in rough note form.

Agent must:
1. Restate what it understood in 2–3 sentences
2. Ask 3–5 clarifying questions covering:
   - Scope: what exactly should change?
   - Constraints: performance, security, backward compatibility?
   - Affected modules: which parts of the system are involved?
   - Edge cases: what unusual inputs or states must be handled?
   - Definition of done: how do we know this is complete?
3. Wait for human answers before proceeding

Human rule: answer each clarifying question explicitly, even if the answer is "not relevant."
Do not let the agent assume answers and proceed.

#### 1.4 — PRD Generation

Run: `/generate-prd`

Agent generates `openspec/changes/{feature}/proposal.md` with these sections:

```
# Proposal: {feature name}
## Background
  Why does this work exist? What problem does it solve?
## Problem Statement
  Specific description of what is broken or missing.
## Proposed Solution
  High-level approach. No implementation details yet.
## Scope — What IS Included
  Explicit list of what will be built or changed.
## Out of Scope — What Is NOT Included
  Explicit list of what will not be touched in this task.
## Acceptance Criteria
  1. [ ] {testable, specific condition}
  2. [ ] {testable, specific condition}
  ...
## Risks and Open Questions
  - {risk or unknown that needs resolution}
## Affected Modules (from entry-points.md)
  - {module}: {why affected}
```

Agent saves file to: `openspec/changes/{feature}/proposal.md`

#### 1.5 — Human Review

Read `proposal.md` yourself. Ask:
- Does this match what I actually want?
- Is the out-of-scope section correct?
- Are the acceptance criteria testable and complete?
- Are there risks I need to resolve before planning?

If no → correct the file directly. Do not ask the agent to guess corrections.
If yes → explicitly tell the agent: "proposal.md approved. Proceed to compact."

#### 1.6 — Compact and Close

Agent writes `openspec/changes/{feature}/pre-dev-summary.md`:

```
# Pre-Development Summary
## Task Understood
  {2–3 sentence summary of what is being built}
## Key Constraints
  {list of constraints confirmed in clarifying questions}
## Approved ACs
  {copy of acceptance criteria from proposal.md}
## Risks to Watch
  {any open risks flagged}
## Next Phase
  Planning — read proposal.md + pre-dev-summary.md to begin
```

Close this session.

---

### Phase 1 Rules

- Never skip the clarifying questions step. Assumptions made here become bugs in development.
- The out-of-scope section is as important as scope. It prevents mid-task scope creep.
- If the agent proposes a solution in this phase — redirect it. This phase is for understanding, not solving.
- proposal.md is the contract for all future phases. Treat changes to it as scope changes requiring re-approval.

---

## Phase 2 — PLANNING

**Goal:** Turn the approved PRD into a zero-ambiguity, executable task list.
**Agent:** `plan` (research subagent for codebase analysis)
**Entry condition:** `proposal.md` is human-approved
**Exit condition:** `tasks.md`, `design.md`, `risks.md` exist, human-reviewed, branch created

---

### Steps

#### 2.1 — Start Fresh Session

Open a new OpenCode session.
Switch to `plan` agent.

#### 2.2 — Load Planning Context

Agent reads (in this order):
- `openspec/changes/{feature}/proposal.md`
- `openspec/changes/{feature}/pre-dev-summary.md`
- `docs/agent-guides/architecture.md`
- `docs/agent-guides/entry-points.md`
- `docs/agent-guides/conventions.md`

Nothing else. Do not load the full codebase at this stage.

#### 2.3 — Research Impact (Subagent)

Agent spawns or switches to `research` subagent.
Research agent searches the codebase for:
- Files and modules directly touched by the proposed change
- Shared utilities used by affected modules
- Existing tests for affected code
- DB schema or API contracts that may change
- Any code that calls into the modules being changed

Research agent writes findings to:
`openspec/changes/{feature}/research-notes.md`

```
# Research Notes
## Files Directly Affected
  - {file}: {reason}
## Shared Dependencies
  - {module}: {who uses it, what breaks if it changes}
## Existing Test Coverage
  - {test file}: covers {what}
## Contract Changes
  - {API/DB change}: {impact}
## Unknowns Requiring Investigation
  - {question}: {what needs to be answered}
```

Research subagent closes after writing this file.
Plan agent reads `research-notes.md` to continue.

#### 2.4 — Design Decisions

Agent writes `openspec/changes/{feature}/design.md`:

```
# Technical Design
## Approach Chosen
  {description of the approach}
## Alternatives Considered
  - {alternative}: rejected because {reason}
## Data Model Changes
  {schema changes, migrations needed, or "none"}
## API Contract Changes
  {endpoint changes, or "none"}
## Patterns to Follow
  {reference to specific patterns in conventions.md}
## Task Dependencies
  {which tasks must complete before others can start}
```

#### 2.5 — Task Breakdown

Agent writes `openspec/changes/{feature}/tasks.md`:

Rules for every task entry:
- Format: `[ ] {verb} {what} in {specific file or module}`
- One task = one logical change = one future commit
- Tasks ordered by dependency (blocked tasks come after their blockers)
- Each task must be independently verifiable
- No task should require more than 2 hours of agent work
- If a task is vague → split it until it is concrete

```
# Task List: {feature name}
## Tasks
[ ] Create {model/schema} in {file}
[ ] Add {function} to {module}
[ ] Update {existing function} in {file} to handle {case}
[ ] Add {route/endpoint} in {router file}
[ ] Write unit tests for {module} in {test file}
[ ] Write integration tests for {boundary} in {test file}
[ ] Update {doc file} with {change}

## Notes
  {any cross-task dependency notes}
```

#### 2.6 — Risk Assessment

Agent writes `openspec/changes/{feature}/risks.md`:

```
# Risk Assessment
## Risk Register
| Risk | Severity | Mitigation |
|------|----------|------------|
| {breaking change description} | high/med/low | {how to mitigate} |
| {shared module impact} | high/med/low | {how to mitigate} |
| {DB migration data loss} | high/med/low | {how to mitigate} |
| {performance impact} | high/med/low | {how to mitigate} |
| {security surface change} | high/med/low | {how to mitigate} |

## High-Severity Risks — Resolve Before Development
  {list any high risks that need a plan before coding starts}
```

#### 2.7 — Human Review

Read all three files:
- `tasks.md`: are tasks atomic, ordered correctly, and concrete?
- `design.md`: does the approach make sense? Any better alternatives?
- `risks.md`: any high-severity risk needing a mitigation plan before coding?

Correct any issues directly in the files before proceeding.
Do not start development with unresolved high-severity risks.

#### 2.8 — Create Feature Branch

Run: `/new-branch`

Agent reads `sop.md` for branch naming rules.
Agent asks: "What is the ticket ID and short feature name?"
Agent outputs the exact git command — human runs it.

```
git checkout develop
git pull origin develop
git checkout -b feature/{ticket-id}-{short-description}
```

Confirm branch was created: `git branch --show-current`

#### 2.9 — Compact and Close

Agent writes `openspec/changes/{feature}/planning-summary.md`:

```
# Planning Summary
## Branch
  feature/{ticket-id}-{short-description}
## Total Tasks
  {count} tasks in tasks.md
## Key Design Decision
  {one-sentence summary of approach}
## Highest Risk
  {top risk and its mitigation}
## Next Phase
  Development — read tasks.md + design.md + planning-summary.md to begin
```

Close this session.

---

### Phase 2 Rules

- Tasks must be written so that an agent with zero prior context can execute them by reading `tasks.md` alone.
- Never bundle more than one logical change per task.
- If the research subagent finds something that invalidates the proposal — stop planning, go back to Phase 1 and update `proposal.md`.
- Branch must exist before development starts. No exceptions.

---

## Phase 3 — DEVELOPMENT

**Goal:** Implement each task cleanly, one commit at a time.
**Agent:** `build` (default agent)
**Entry condition:** `tasks.md` human-approved, feature branch created
**Exit condition:** All tasks `[x]`, all commits pass lint and build

---

### Steps

#### 3.1 — Start Fresh Session

Open a new OpenCode session.
Switch to `build` agent (this is the default).
Confirm you are on the correct feature branch: `git branch --show-current`

#### 3.2 — Load Development Context

Agent reads (in this order):
1. `openspec/changes/{feature}/tasks.md`
2. `openspec/changes/{feature}/design.md`
3. `openspec/changes/{feature}/planning-summary.md`
4. `docs/agent-guides/conventions.md`
5. `docs/agent-guides/build-and-test.md`
6. `docs/agent-guides/sop.md`
7. `.gitignore` — ALWAYS before touching any file

Agent confirms: "I have read context. I am on branch {name}. First task is: {task}."

#### 3.3 — Pick One Task

Agent picks the FIRST unchecked `[ ]` task from `tasks.md`.
Agent announces: "Working on task N: {description}"
Agent does NOT start the next task until current task is committed.

One task at a time. No multitasking.

#### 3.4 — Verify Approach Before Writing

Before writing any code, agent searches the codebase for:
- Existing similar patterns to follow (not invent from scratch)
- Functions or modules this task depends on
- Tests for code adjacent to the change

Agent announces findings:
"I found {pattern/function} in {file}. I will follow this pattern."

If the intended approach contradicts `design.md` — STOP.
Report the discrepancy to human. Wait for resolution before proceeding.

#### 3.5 — Implement

Agent implements only the current task.
Agent follows `conventions.md` exactly for:
- Naming (variables, functions, classes, files)
- Import style and order
- Error handling patterns
- Folder structure

If the task requires a pattern not in `conventions.md`:
1. Propose the pattern to human
2. Get explicit approval
3. Then implement
4. Later add the pattern to `conventions.md` in the context update phase

#### 3.6 — Self-Review Before Commit

Agent runs through this checklist before committing:

```
[ ] Does this change match the task description exactly?
[ ] Does it follow naming conventions from conventions.md?
[ ] Does it introduce any new external dependency?
    If yes → flag to human before committing
[ ] Does it touch any .gitignore-matched path?
    If yes → STOP immediately and report to human
[ ] Is this the minimum change needed to complete the task?
[ ] Would another developer understand this without asking questions?
```

If any answer is NO → resolve before committing.

#### 3.7 — Run Lint and Build

Agent runs commands from `build-and-test.md` (lint + build only, not full test suite).

All lint errors must be fixed before commit.
Build must succeed before commit.
If lint or build fails → fix in same session, do not commit broken code.

#### 3.8 — Commit

Format from `sop.md`:
```
{type}({scope}): {short description}
```

Agent also checks off the completed task in `tasks.md`:
Change `[ ]` to `[x]` for the current task.
Include `tasks.md` in the same commit.

```
git add {changed files} tasks.md
git commit -m "{type}({scope}): {description}"
```

#### 3.9 — Context Check (Every 3 Tasks)

After every 3 committed tasks, check session health.
If session history is long or context feels heavy:

Agent writes `openspec/changes/{feature}/progress.md`:

```
# Development Progress
## Completed Tasks
  [x] Task 1: {description} — commit {short hash}
  [x] Task 2: {description} — commit {short hash}
  [x] Task 3: {description} — commit {short hash}
## Remaining Tasks
  [ ] Task 4: {description}
  ...
## Current Branch
  feature/{ticket-id}-{description}
## Known Gotchas Discovered
  - {anything surprising found during implementation}
## Next Session Instruction
  Read tasks.md + progress.md. Continue from task 4.
```

Close session. Start new session. New session reads `tasks.md` + `progress.md` only to resume.

#### 3.10 — Repeat Until Done

Repeat steps 3.3 through 3.9 until all tasks in `tasks.md` are `[x]`.

Final verification:
```
git log --oneline
```
Confirm one commit per task. Confirm conventional commit format on each.

---

### Phase 3 Rules

- Progress lives in files and git history — not in the context window. Always write progress.md before closing a long session.
- Never let the agent self-approve touching a new external dependency. Always surface to human.
- If the agent gets stuck on a task for more than 3 iterations — stop, escalate to human, do not let it spiral.
- Never commit directly to `main` or `develop`. Verify branch before every commit.
- A commit with failing lint or failing build is not acceptable. Fix first, commit second.

---

## Phase 4 — TESTING

**Goal:** Prove correctness of all changes before documentation or review.
**Agent:** `test`
**Entry condition:** All tasks `[x]`, build passes
**Exit condition:** Unit + integration tests pass, `test-coverage.md` exists

---

### Steps

#### 4.1 — Start Fresh Session

Open a new OpenCode session.
Switch to `test` agent.

#### 4.2 — Load Test Context

Agent reads:
- `openspec/changes/{feature}/tasks.md` (what was built)
- `openspec/changes/{feature}/proposal.md` (ACs to verify)
- `.opencode/skills/unit-testing/SKILL.md`
- `.opencode/skills/integration-testing/SKILL.md`
- `docs/agent-guides/build-and-test.md`

#### 4.3 — Unit Tests

For every new or changed function/module:

Rules:
- Test file lives next to src file (or in `__tests__/` — check conventions.md)
- Each AC from `proposal.md` must have at least one test
- Test naming must describe behavior, not implementation:
  - GOOD: `should return 401 when token is expired`
  - BAD: `test_auth` or `testLogin`
- Test coverage per function:
  - Happy path (expected normal usage)
  - At least 2 edge cases (boundary values, empty input, invalid input)
  - At least 1 error/failure case
- No real network calls. No real database. Mock all external dependencies.

#### 4.4 — Run Unit Tests

Agent runs exact command from `build-and-test.md`.
All tests must pass — zero tolerance for skipped or failing tests.

If failures:
- Fix in same session before moving on
- Do not proceed to integration tests with failing unit tests

#### 4.5 — Integration Tests

Rules:
- Test the integration boundary: API → service, service → DB, service → external API
- All third-party APIs and external queues must be mocked
- Use test database or in-memory database. Never touch production or staging data.
- Each test must be fully independent — no shared state between tests
- Each test must clean up after itself (teardown/reset)
- Tests must be runnable in isolation without external services being live

#### 4.6 — Run Integration Tests

Agent runs integration test command from `build-and-test.md`.
All must pass before proceeding.
If failures → fix before proceeding to documentation.

#### 4.7 — AC Coverage Map

Agent reads each AC from `proposal.md`.
For each AC, identifies: which test(s) verify it?

Agent writes `openspec/changes/{feature}/test-coverage.md`:

```
# Test Coverage Map
## AC Coverage
| # | Acceptance Criterion | Test File | Test Name | Status |
|---|----------------------|-----------|-----------|--------|
| 1 | {AC text}            | {file}    | {name}    | PASS   |
| 2 | {AC text}            | {file}    | {name}    | PASS   |

## Uncovered ACs
  {AC number}: {reason — manual-only, deferred, or needs fix}

## Coverage Gaps
  {any logic paths with no test coverage and why}
```

Any AC with no automated test must have an explicit documented reason.
"I forgot" is not a valid reason.

#### 4.8 — Commit Tests

Tests are committed separately from implementation:

```
git add {test files} test-coverage.md
git commit -m "test({scope}): add unit and integration tests for {feature}"
```

---

### Phase 4 Rules

- Tests written after code still count — but they must exist before the review phase.
- A test that always passes regardless of logic is worse than no test. The agent must verify tests can actually fail by confirming they fail when the implementation is intentionally broken, if feasible.
- Integration tests must run locally without live external services.
- Do not proceed to documentation with any failing test.

---

## Phase 5 — DOCUMENTATION

**Goal:** Sync all human-readable documentation with what was actually built.
**Agent:** `docs`
**Entry condition:** All tests pass, `test-coverage.md` exists
**Exit condition:** Docstrings, README, and CHANGELOG updated and committed

---

### Steps

#### 5.1 — Start Fresh Session

Open a new OpenCode session.
Switch to `docs` agent.

#### 5.2 — Load Documentation Context

Agent reads:
- `openspec/changes/{feature}/proposal.md` (what was intended)
- `openspec/changes/{feature}/tasks.md` (what was built)
- `git diff HEAD~{n}..HEAD` (actual code changes)

Agent does NOT read architecture.md or conventions.md unless needed.
Docs agent touches only markdown files, comments, and docstrings.

#### 5.3 — Inline Documentation

For every new or changed function, class, or module:

Rules:
- Docstring must describe: what it does, parameters, return value, exceptions raised
- If behavior changed → update the existing docstring to match current behavior
- Remove any comment that no longer matches the code — stale comments are worse than no comments
- Document the WHY, not the WHAT. The code shows what. The comment explains why.
- Do NOT add obvious comments like `# increment counter` on `counter += 1`

#### 5.4 — README Update

Update README only if:
- New feature is user-facing or API-facing
- Setup or install steps changed
- New environment variable is required
- New CLI command was added
- Public API contract changed

Do NOT update README for:
- Internal refactors
- Test additions
- Dependency updates that have no user-visible effect

#### 5.5 — CHANGELOG Update

Add entry under `## [Unreleased]` section.
Use Keep a Changelog format:

```markdown
## [Unreleased]
### Added
- {description of new feature} ({ticket-id})
### Changed
- {description of changed behavior} ({ticket-id})
### Fixed
- {description of bug fix} ({ticket-id})
### Removed
- {description of removed feature} ({ticket-id})
```

One line per logical change. Keep entries concise.
Do not write paragraphs in the CHANGELOG.

#### 5.6 — Commit

Documentation commit is separate from implementation and test commits:

```
git add {doc files, README, CHANGELOG}
git commit -m "docs({scope}): update documentation and changelog for {feature}"
```

Verify: no source files (`.ts`, `.js`, `.py`, `.go`, etc.) appear in this commit.

---

### Phase 5 Rules

- Docs agent must never touch implementation files. If it tries — stop it.
- Outdated documentation is actively harmful to future agents and developers. Treat doc accuracy as a hard requirement, not optional.
- If a function's behavior is too complex to document in a few lines, that is a signal the function needs to be refactored — log it in `lessons.md` in the next phase.

---

## Phase 6 — CONTEXT UPDATE

**Goal:** Keep agent-guides and AGENTS.md accurate so future tasks benefit from what was learned.
**Agent:** `context-updater`
**Entry condition:** Documentation committed
**Exit condition:** `docs/agent-guides/` updated, `lessons.md` written, changes committed

---

### Steps

#### 6.1 — Start Fresh Session

Open a new OpenCode session.
Switch to `context-updater` agent.

#### 6.2 — Analyze What Changed

Agent runs:
```
git log --oneline HEAD~{n}..HEAD
git diff HEAD~{n}..HEAD
```

Where `{n}` is the total number of commits made during this feature (implementation + tests + docs).

Agent builds an internal list of: what changed, which modules were affected, what patterns were introduced.

#### 6.3 — Audit Each Agent-Guide File

Agent checks each file in `docs/agent-guides/` for staleness:

**architecture.md**
- New modules or services added?
- Existing services removed or renamed?
- Data flow changed?
- New external dependencies added?

**entry-points.md**
- New API routes registered?
- New CLI commands added?
- New event listeners or cron jobs?
- New main module exports?

**conventions.md**
- New patterns introduced in this task?
- Anti-patterns encountered that should be warned against?
- New import style or naming convention observed?

**build-and-test.md**
- New test commands added to package.json / Makefile?
- Existing commands changed?
- New environment variables required to run tests?

Agent updates only the stale sections.
Do not rewrite sections that are still accurate.
Do not reformat or restructure files unnecessarily.

#### 6.4 — Update AGENTS.md

If the agent discovered operational surprises during development — things that weren't obvious from reading the codebase — add them to AGENTS.md under a `## Known Gotchas` section:

```markdown
## Known Gotchas
- {file or module}: {what is surprising or non-obvious about it}
- {build step}: {non-obvious prerequisite or failure mode}
- {test setup}: {specific environment state required}
```

#### 6.5 — Write Lessons Learned

Agent writes `openspec/changes/{feature}/lessons.md`:

```
# Lessons Learned: {feature}
## What Took Longer Than Expected
  {description and root cause}
## What Almost Went Wrong
  {near-miss and how it was caught}
## New Patterns Discovered or Introduced
  {pattern name and where it was added to conventions.md}
## What Would Make the Next Similar Task Faster
  {concrete suggestion}
## Agent-Guide Files Updated
  - {file}: {what was updated}
```

#### 6.6 — Commit Context Updates

```
git add docs/agent-guides/ AGENTS.md openspec/changes/{feature}/lessons.md
git commit -m "chore(context): update agent-guides after {feature}"
```

---

### Phase 6 Rules

- This phase is non-negotiable. Skipping it is technical debt on the AI system itself.
- Every PR review comment in the future that says "this doesn't follow our pattern" is evidence that Phase 6 was skipped or done poorly.
- Context update commits belong on the feature branch, not directly on develop.
- If nothing changed in a guide file — do not update it. Unnecessary churn makes diffs noisy.

---

## Phase 7 — PR / HANDOFF

**Goal:** Produce a clean, self-documented, reviewable PR. Verify SOP compliance before any human reviewer sees it.
**Agent:** `review` (read-only)
**Entry condition:** Context update committed
**Exit condition:** All compliance checks PASS, PR description written, feature archived

---

### Steps

#### 7.1 — Start Fresh Session

Open a new OpenCode session.
Switch to `review` agent (read-only, no file writes).

#### 7.2 — Run Pre-PR Compliance Check

Run: `/pre-pr-check`

Agent reads:
- `openspec/changes/{feature}/tasks.md`
- `openspec/changes/{feature}/proposal.md`
- `openspec/changes/{feature}/test-coverage.md`
- `git log` for this branch
- `git diff develop..HEAD` (all changes in this branch)

Agent outputs PASS or FAIL for each item:

```
PRE-PR COMPLIANCE CHECK — {feature}

[ ] All tasks in tasks.md are marked [x]
[ ] All ACs from proposal.md have corresponding tests in test-coverage.md
[ ] All unit tests pass (verify from last test run output)
[ ] All integration tests pass
[ ] Every commit message follows conventional commits format
[ ] No commits made directly to main or develop
[ ] Branch name matches sop.md naming pattern
[ ] README updated (or explicitly N/A with reason)
[ ] CHANGELOG updated under [Unreleased]
[ ] No .gitignore-matched files were touched
[ ] docs/agent-guides/ updated (context-update commit exists)
[ ] lessons.md written
[ ] AGENTS.md updated if new gotchas were discovered

RESULT: {X of 13 checks PASS}
```

#### 7.3 — Fix All Failures

Any FAIL item must be resolved before generating the PR description.
Return to the appropriate phase to fix:
- Missing test → back to Phase 4
- Missing docs → back to Phase 5
- Stale agent-guides → back to Phase 6
- Wrong commit format → `git rebase -i` to fix commit messages (human does this)

Do not submit a PR with known violations.

#### 7.4 — Generate PR Description

Once all checks PASS, agent generates the PR description.

Agent reads: `tasks.md` + `proposal.md` + `git log --oneline`

```markdown
## Summary
{1 paragraph: what was built and why — from proposal.md background}

## Changes
{bullet list of what changed — derived from tasks.md completed items}
- {module/file}: {what changed}

## How to Test
{exact commands to run tests locally}
{any environment setup required}

## Acceptance Criteria
{copy of ACs from proposal.md as a checklist}
- [ ] {AC 1}
- [ ] {AC 2}

## Related
Ticket: {ticket-id}
Spec: openspec/changes/{feature}/proposal.md
```

Agent saves PR description to: `openspec/changes/{feature}/pr-description.md`

#### 7.5 — Archive Feature

Run inside OpenCode: `/opsx:archive`

OpenSpec closes the change cleanly:
- Moves `openspec/changes/{feature}/` to `openspec/archive/{feature}/`
- Updates `openspec/specs/` with any living spec document changes

Commit the archive:
```
git add openspec/
git commit -m "chore(openspec): archive {feature} after PR ready"
```

#### 7.6 — Human Final Review

Human reads `pr-description.md`.
Ask: does this accurately and completely describe the work done?

If no → correct `pr-description.md` directly. Do not change code.
If yes → this branch is ready for review.

Human creates the PR on the remote using `pr-description.md` as the PR body.

---

### Phase 7 Rules

- The review agent must never suggest "let's just skip that check." All 13 items must PASS.
- The PR description must be written from files and git log — not from the agent's memory of the conversation.
- A PR that fails the pre-PR check is not ready for human review. Fix it, don't submit it.

---

## Phase Flow Summary

```
INPUT (messy or structured)
  │
  ▼
PHASE 1: PRE-DEVELOPMENT
  Agent: plan
  Output: proposal.md
  Gate: human approves proposal.md
  │
  ▼
PHASE 2: PLANNING
  Agent: plan + research subagent
  Output: tasks.md, design.md, risks.md, branch created
  Gate: human reviews tasks.md
  │
  ▼
PHASE 3: DEVELOPMENT
  Agent: build (default)
  Loop: one task → lint/build → commit → repeat
  Output: all tasks [x], clean commits on feature branch
  │
  ▼
PHASE 4: TESTING
  Agent: test
  Output: unit + integration tests pass, test-coverage.md
  Gate: all ACs covered
  │
  ▼
PHASE 5: DOCUMENTATION
  Agent: docs
  Output: docstrings, README, CHANGELOG updated
  │
  ▼
PHASE 6: CONTEXT UPDATE
  Agent: context-updater
  Output: agent-guides updated, lessons.md written
  │
  ▼
PHASE 7: PR / HANDOFF
  Agent: review
  Output: all compliance checks PASS, pr-description.md, feature archived
  Gate: human approves PR description
  │
  ▼
BRANCH READY FOR REVIEW
```

### Artifact Map (Files Produced Per Feature)

```
openspec/changes/{feature}/
  proposal.md          ← Phase 1: approved PRD
  pre-dev-summary.md   ← Phase 1: compact handoff
  research-notes.md    ← Phase 2: codebase impact analysis
  design.md            ← Phase 2: technical approach
  tasks.md             ← Phase 2: executable task list (updated through Phase 3)
  risks.md             ← Phase 2: risk register
  planning-summary.md  ← Phase 2: compact handoff
  progress.md          ← Phase 3: mid-development compact (if needed)
  test-coverage.md     ← Phase 4: AC-to-test mapping
  lessons.md           ← Phase 6: lessons learned
  pr-description.md    ← Phase 7: PR body

docs/agent-guides/      ← updated in Phase 6
  architecture.md
  entry-points.md
  conventions.md
  build-and-test.md

AGENTS.md               ← updated in Phase 6 (known gotchas)
```

---

*This document is a living SOP. Update it when a phase consistently produces poor results or when a better workflow is discovered. Log the change in lessons.md and update conventions.md if it reflects a new pattern.*