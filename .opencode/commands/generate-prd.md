# Generate PRD

From the task summary, generate a Product Requirements Document (PRD).

## Input

A structured task summary from the `understand-task` command, containing:
- Intent
- Scope
- Affected modules
- Out-of-scope
- Acceptance Criteria

## Task

Generate a PRD document and save it to:
```
openspec/changes/{feature}/proposal.md
```

## PRD Template

```markdown
# Proposal: {Feature Name}

## Background
{Why this feature is needed. What problem does it solve?}

## Problem Statement
{Detailed description of the problem or gap being addressed}

## Proposed Solution
{How the feature will solve the problem}

## Scope

### In Scope
- {Specific items included}

### Out of Scope
- {Explicitly excluded items}

## Acceptance Criteria

| # | Criterion | Testable |
|---|-----------|----------|
| 1 | {Criterion 1} | {How to verify} |
| 2 | {Criterion 2} | {How to verify} |

## Affected Modules

| Module | Changes |
|--------|---------|
| {file 1} | {what changes} |
| {file 2} | {what changes} |

## Technical Considerations

- {Technical constraints or decisions}

## Risks

- {Risk 1 and mitigation}
- {Risk 2 and mitigation}

## Open Questions

- {Question 1}
- {Question 2}

## Timeline Estimate

- Research/Design: {X} hours
- Implementation: {X} hours
- Testing: {X} hours
- Total: {X} hours
```

## Save Location

The file should be saved to:
```
openspec/changes/<feature-name>/proposal.md
```

Where `<feature-name>` is the kebab-case name of the feature (e.g., `add-rate-limiting`).

## Next Step

After generating the PRD, ask if the user wants to proceed to design or if changes are needed.
