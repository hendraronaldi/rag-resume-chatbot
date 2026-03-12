# SOP — Development Standards

## Branching Strategy: Gitflow

### Permanent Branches (NEVER commit directly, NEVER delete)
- master        → production-ready code only
- develop     → integration branch, all features merge here

### Working Branches (agent always works here)
- feature/    → new features, branched from develop
- bugfix/     → bug fixes, branched from develop
- hotfix/     → critical fixes, branched from master
- release/    → release prep, branched from develop
- chore/      → non-code tasks (deps, config, docs)

### Branch Naming Convention
Pattern: {type}/{ticket-id}-{short-description}
Examples:
  feature/APP-123-user-authentication
  bugfix/APP-456-fix-login-redirect
  hotfix/APP-789-patch-null-pointer
  chore/APP-101-update-dependencies

Rules:
- lowercase only
- hyphens only (no underscores, no spaces)
- ticket ID is required
- description max 5 words

### Branch Source Rules
| Branch type | Must branch from |
|-------------|-----------------|
| feature/    | develop         |
| bugfix/     | develop         |
| hotfix/     | master            |
| release/    | develop         |
| chore/      | develop         |

## Commit Rules

### Format: Conventional Commits
Pattern: {type}({scope}): {short description}

Types:
  feat      → new feature
  fix       → bug fix
  chore     → maintenance, deps, config
  docs      → documentation only
  refactor  → code restructure, no behavior change
  test      → adding or updating tests
  style     → formatting, no logic change
  ci        → CI/CD config changes

Examples:
  feat(auth): add JWT token refresh logic
  fix(api): handle null response from payment gateway
  chore(deps): upgrade lodash to 4.17.21
  test(user): add unit tests for registration flow

Rules:
- subject line max 72 characters
- lowercase only
- no period at end
- one logical change per commit
- body (optional): explain WHY, not WHAT

## Hard Limits for AI Agents

### NEVER do these without explicit human approval:
- git push (any remote, any branch)
- git merge
- git rebase
- git cherry-pick
- delete any branch
- modify anything in .gitignore
- commit directly to master or develop

### File and Folder Restrictions
- Read .gitignore at session start
- NEVER read, modify, or create any file or path matched by .gitignore
- If a task requires touching a .gitignore-listed path:
  STOP. Report to human. Wait for explicit approval.
- Common examples (also check actual .gitignore):
  .env, .env.*, secrets.*, *.pem, *.key, /dist, /build,
  /node_modules, /__pycache__, /coverage, *.log

### Agent Commit Checklist (run before every commit)
□ Am I on a working branch (feature/, bugfix/, hotfix/, chore/)?
□ Is this a single logical change?
□ Does commit message follow conventional commits format?
□ Have I excluded all .gitignore-matched files?
□ Am I NOT pushing, merging, or rebasing?
□ If any answer is NO → stop and report to human