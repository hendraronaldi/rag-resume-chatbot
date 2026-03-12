# Understand Task

I will give you a rough task description. Your job is to clarify the requirements before any implementation begins.

## Workflow

1. **Ask 3–5 clarifying questions** about:
   - Scope: What exactly should be built/changed?
   - Constraints: Any technical limitations, deadlines, or dependencies?
   - Acceptance Criteria: How will success be measured?
   - Affected modules: Which parts of the codebase will be touched?
   - Out-of-scope: What should NOT be included?

2. **Wait for my answers** before proceeding.

3. **Output a structured task summary** with:
   - **Intent**: Why are we doing this? What's the problem being solved?
   - **Scope**: What exactly is included in this task?
   - **Affected modules**: From `docs/agent-guides/entry-points.md`, list the files/modules that will need changes
   - **Out-of-scope**: What should NOT be done in this task?
   - **Acceptance Criteria**: Specific, measurable criteria for completion
   - **Risks/Open Questions**: Anything unclear that needs decision

## Important

- Do NOT write any code yet
- Ask questions first to avoid rework
- Be specific in your clarifications

## Example Output

```
## Task Summary: Add Rate Limiting

**Intent**: Prevent API abuse by limiting requests per user/IP

**Scope**:
- Add rate limiting to /query-resume endpoint
- 10 requests/minute for free tier
- 60 requests/minute for premium users

**Affected Modules**:
- main.py (add limiter middleware)
- app/agent.py (may need adjustment for caching)

**Out-of-Scope**:
- Dashboard UI for rate limit configuration
- Billing integration

**Acceptance Criteria**:
- [ ] Requests exceed limit return 429 status
- [ ] Rate limit headers present in response
- [ ] Tests pass for limit enforcement

**Open Questions**:
- Should we use Redis for distributed rate limiting?
```
