# Update Context

After completing a task or group of commits, update the project's documentation to capture new learnings.

## Switch to context-updater Agent

Use the `context-updater` subagent type to perform this task.

## Steps

1. **Run git diff** to see what changed:
   ```bash
   git diff HEAD~{n}..HEAD
   ```
   Where `{n}` is the number of recent commits to review (usually 3-5).

2. **Identify changes** that may require documentation updates:
   - New dependencies added
   - New build/test commands
   - New conventions or patterns
   - Changes to architecture
   - Lessons learned during implementation

3. **Update stale docs** in `docs/agent-guides/`:
   - `architecture.md` — If system design changed
   - `entry-points.md` — If new endpoints/routes added
   - `conventions.md` — If new patterns established
   - `sop.md` — If process changed
   - `build-and-test.md` — If commands changed

4. **Log new patterns** to `conventions.md`:
   - What worked well
   - What to avoid
   - New patterns discovered

## What to Look For

- New environment variables added
- New dependencies (requirements.txt)
- New files added to project structure
- Changes to API endpoints
- New testing patterns
- Configuration changes
- Gotchas or common pitfalls discovered

## Output

After updating, summarize:
- Which files were modified
- What new information was added
- Any changes to recommended practices

## Important

- Only update documentation files
- Do NOT modify code
- Be concise in updates — capture essentials only
- If uncertain whether something should be documented, ask me first
