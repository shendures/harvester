# Core Git Rules (Condensed — for Claude Code)

> Safe, efficient Git/GitHub usage during "vibe coding." Keep this short — follow every rule below.

## 1. Core Principles
1. Commit often, in meaningful units (one commit = one feature/fix/refactor). Never dump a full day's work into one commit.
2. Always stay revertible — checkpoint-commit before letting Claude Code make a large change.
3. Branch off for anything experimental or large.

## 2. First-Time Setup (only if no repo exists)
```bash
git init && git branch -M main
gh repo create [project-name] --private --source=. --remote=origin
git push -u origin main
```
`.gitignore`: Python template from gitignore.io. Draft a README (purpose, run instructions, key commands).

## 3. Commit Rules
- Checkpoint → Claude Code works → review diff → commit (or `git reset --hard HEAD~1` to undo).
- Format: Conventional Commits `<type>[scope]: <description>`
  `feat` `fix` `refactor` `style` `docs` `test` `chore` `wip` `ci`
- Claude Code may write the commit message from the diff, but you review the diff first.
- Multiple features touched in one session → commit each separately.

## 4. Branch Strategy: `feature/*` → `develop` → `main`
```
feature/* (new work)  →  develop (integration/test)  →  main (production)
```
| Branch | Role |
|---|---|
| `feature/*`, `fix/*`, `experiment/*`, `refactor/*` | New work. Branch off **`develop`**, not `main`. |
| `develop` | Integration/test. Receives merges from feature branches. Must run, not necessarily prod-ready. |
| `main` | Production. Only merges from a verified `develop`. Always deployable. |

```bash
git checkout develop && git pull origin develop
git checkout -b feature/name        # work, commit
git checkout develop && git pull origin develop && git merge feature/name
git push origin develop && git branch -d feature/name
# only when develop is verified stable:
git checkout main && git pull origin main && git merge develop && git push origin main
```

**Multi-environment (WSL + Windows):** both are separate local clones of the same remote — the remote is the only sync point.
- Push before switching environments; pull before starting work in one.
- Never work the same branch in both without pull/push in between (diverging history).
- Unexpected diffs across environments → suspect CRLF/LF, permissions, or path separators before assuming a real conflict.
- Auth (SSH keys/tokens) is per-environment, not shared.

## 5. Which Branch to Commit/Push/Pull On
**Before any commit/push/pull:** run `git status` + `git branch -vv` — never act blind.

| Branch | Commit | Push | Pull |
|---|---|---|---|
| `main` | Only merges from verified `develop` — never new/WIP work directly | Only clean, merged commits; ask user if unsure | Safe anytime, do before merging `develop` in |
| `develop` | Only merges from feature branches — don't commit new work directly | After merging a verified feature branch, to sync team/other environment | Before branching off it or merging a feature branch in (catches other-environment changes) |
| `feature/*`, `fix/*`, `refactor/*` | Free | Free, same-name remote branch | Pull `develop` periodically to avoid drift |
| `experiment/*` | Free | Free | — **never merge into `develop`/`main` directly** |
| Unrecognized branch name | — | — | **Stop, ask the user** what it's for |

**If unsure which branch matches the task** (ambiguous names, several stale branches): list branches (`git branch -vv`, `git log --all --oneline --graph -20`), summarize what each contains, and ask the user before acting.

**Multi-environment check:** before pushing, if unsure whether the other environment (WSL/Windows) pushed since your last pull, run `git fetch` and check `git log HEAD..origin/<branch>` first.

**Hard rule:** never push new/WIP work directly to `main` or `develop` without explicit user confirmation.

## 6. Common Fixes
| Situation | Command |
|---|---|
| Discard uncommitted changes | `git checkout -- .` |
| Revert to previous commit (destructive) | `git reset --hard HEAD~1` |
| Revert, keep history | `git revert HEAD` |
| Restore one file from prior commit | `git checkout HEAD~1 -- path/to/file` |
| Temp branch switch | `git stash` → work → `git stash pop` |

**Secret committed (e.g. `.env`):** rotate the credential immediately — clearing history alone doesn't undo exposure. Then:
```bash
git rm --cached .env && echo ".env" >> .gitignore && git commit -m "chore: stop tracking .env"
```
Full history removal: `git filter-repo` or BFG, backup first.

## 7. Instructing Claude Code
- ✅ "Review changes and commit by feature using conventional commits" / "Branch feature/search off develop and work there"
- ❌ "Just clean up git however you want" (vague → risk of force push or history loss)

### ⚠️ Always require human approval
`git push --force` · `git reset --hard` · `git branch -D` · `git filter-repo`

## 8. GitHub Tips
- PRs per feature: `gh pr create --title "..." --body "..."`
- Reference Issues for context ("start on Issue #12")
- GitHub Actions to auto-run tests/lint on push

## 9. Checklist
- [ ] `.gitignore` ready, current state committed before starting
- [ ] Checkpoint commit before big tasks; experiments on a separate branch
- [ ] New work branches off `develop`, not `main`; `develop` → `main` only when verified stable
- [ ] Meaningful commit per completed unit; push regularly
- [ ] Before commit/push/pull: confirm branch + role; ask user if unclear
- [ ] Before switching WSL ↔ Windows: push first; pull before starting work
- [ ] Force push / hard reset always reviewed by a human first
- [ ] Rotate credentials immediately if a secret is committed
