# New Branch

Create a new git branch for the task.

## Prerequisites

1. First, read `docs/agent-guides/sop.md` for branch naming rules
2. Understand the ticket/feature context

## Questions to Ask

Before creating the branch, ask me:

1. **Ticket ID**: What is the ticket number or identifier? (e.g., TICKET-123)
2. **Feature name**: What is the feature in kebab-case? (e.g., add-rate-limiting)

## Branch Naming Convention

From `sop.md`, branches should follow:
```
{ticket-id}/{feature-name}
```

Example: `TICKET-123/add-rate-limiting`

## Output

After you provide the ticket ID and feature name, output the exact git command to create and switch to the new branch:

```bash
git checkout -b TICKET-123/add-rate-limiting
```

Also include any setup steps (e.g., pulling latest, creating from specific branch).

## Important

- Do NOT execute the git command yourself — output it for me to run
- Verify the name follows conventions in sop.md
- Ask if the branch should be created from `main` or another base branch
