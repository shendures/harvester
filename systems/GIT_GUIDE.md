# Core Git Rules (Summary for Claude Code)

> A condensed reference for managing Git/GitHub safely and efficiently during "vibe coding" with Claude Code.

## 1. Three Core Principles
1. **Commit often, in meaningful units** — one commit per feature/bugfix/refactor. Never dump a whole day's work into one commit.
2. **Always stay in a revertible state** — commit (checkpoint) before letting Claude Code make any large change.
3. **Use branches lightly and often** — do experiments and big refactors on a separate branch.

## 2. Initial Project Setup (only if no git repo exists)
```bash
git init
git branch -M main
```
- `.gitignore`: use the Python template from gitignore.io (toptal)
- Draft a README (purpose, how to run, key commands)
- Connect to GitHub:
```bash
gh repo create [project-name] --private --source=. --remote=origin
git push -u origin main
```

## 3. Commit Strategy When Working with Claude Code
- **Separate commits before/after AI work**: checkpoint commit → let Claude Code work → review diff → commit, or `git reset --hard HEAD~1` to undo
- **Commit messages**: Conventional Commits format `<type>[scope]: <description>`
  - Types: `feat` `fix` `refactor` `style` `docs` `test` `chore` `wip` `ci`
- You can delegate commit-message writing to Claude Code ("commit the current changes using conventional commits based on the diff") — but review the diff first
- When multiple features are touched in one session, explicitly ask Claude Code to commit each feature separately

## 4. Branch Strategy
| Prefix | Purpose |
|---|---|
| feat/ | Feature development |
| fix/ | Bug fix |
| experiment/ | Experimental attempt |
| refactor/ | Structural improvement |

- `main` should always stay in a working state
- Always branch off for experimental requests
```bash
git checkout -b feat/feature-name
# after work
git checkout main
git merge feat/feature-name
git branch -d feat/feature-name
```

## 5. Common Situations & Fixes
| Situation | Command |
|---|---|
| Discard all uncommitted changes | `git checkout -- .` |
| Fully revert to previous commit | `git reset --hard HEAD~1` |
| Revert while keeping history | `git revert HEAD` |
| Restore only one file to a prior state | `git checkout HEAD~1 -- path/to/file` |
| Temporarily switch branches | `git stash` → work → `git stash pop` |

**If a secret (e.g. `.env`) was accidentally committed**: rotating the key/credential immediately is the top priority — clearing it from history alone doesn't undo exposure. Then stop tracking it:
```bash
git rm --cached .env
echo ".env" >> .gitignore
git commit -m "chore: stop tracking .env"
```
For full history removal, use `git filter-repo` or BFG Repo-Cleaner — back up the repo first and proceed carefully.

## 6. How to Instruct Claude Code Effectively
- ✅ Good: "Review current changes and commit them by feature using conventional commits", "Create branch feat/search and work there"
- ❌ Bad: "Just clean up git however you want" (vague → risk of force push or history loss)

### ⚠️ Commands That Always Require Human Approval
| Command | Risk |
|---|---|
| `git push --force` | Can overwrite remote history and destroy collaborators' work |
| `git reset --hard` | Permanently deletes uncommitted work |
| `git branch -D` | Force-deletes an unmerged branch |
| `git filter-repo` | Rewrites entire history, hard to undo |

## 7. GitHub Tips
- Track changes per feature via PRs: `gh pr create --title "..." --body "..."`
- Manage work units with Issues → give context like "start working on Issue #12"
- Set up GitHub Actions to auto-run tests/lint on every push

## 8. Checklist
- [ ] `.gitignore` ready and current state committed before starting
- [ ] Checkpoint commit before big tasks; experiments on a separate branch
- [ ] Meaningful commit message per completed unit + push regularly
- [ ] Force push / hard reset always reviewed by a human first
- [ ] Rotate credentials immediately if a secret gets committed
