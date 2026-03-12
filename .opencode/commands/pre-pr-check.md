# Pre-PR Check

Before submitting a Pull Request, verify all requirements are met.

## Switch to Review Mode

Act as a code reviewer. Check each item below and report PASS or FAIL.

## Checklist

### Implementation
- [ ] All Acceptance Criteria from `tasks.md` are implemented
- [ ] Code matches the design in `design.md` (if exists)
- [ ] No TODO comments left in code

### Testing
- [ ] Unit tests pass (`pytest tests/unit/` or `pytest`)
- [ ] Integration tests pass (`pytest tests/integration/`)
- [ ] New tests added for new functionality

### Documentation
- [ ] README updated if needed (new setup steps, env vars)
- [ ] CHANGELOG updated with changes
- [ ] Docstrings added/updated on new functions
- [ ] API changes documented (if applicable)

### Code Quality
- [ ] Commit messages follow `sop.md` conventional commits format
- [ ] No sensitive paths modified without approval
- [ ] No hardcoded secrets or API keys

### Context
- [ ] `context-updater` agent has been run to update docs
- [ ] Any new patterns logged to `conventions.md`

## Report Format

```
## Pre-PR Check Report

| Item | Status | Notes |
|------|--------|-------|
| All ACs implemented | PASS/FAIL | |
| Unit tests pass | PASS/FAIL | |
| Integration tests pass | PASS/FAIL | |
| README updated | PASS/FAIL | |
| CHANGELOG updated | PASS/FAIL | |
| Commit messages follow format | PASS/FAIL | |
| Context updated | PASS/FAIL | |

## Summary

PASS: Ready for PR
FAIL: Address issues above before submitting
```

## Action

If FAIL, list the specific items that need fixing and ask me to address them before proceeding.
