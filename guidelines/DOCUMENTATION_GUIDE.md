# Documentation Guide — Writing and Updating Mechanics for `guidelines/` Documents

> Meta-guide for `guidelines/`: which md file to update, when, and in what format when code or a
> feature changes (§1–§9), plus in-code comment/docstring writing and maintenance (§10).
> Consult this document first whenever you create or edit an md document or a code comment.

---

## 1. Document Map

### 1.1 Static Rulebooks — "Do it this way"

| Document | Role |
|---|---|
| `CODING_GUIDE.md` | Language-neutral coding principles + this project's own conventions |
| `GIT_GUIDE.md` | Git branch/commit/PR workflow rules |

No `최신 갱신` field (rules, not state) and no cross-references — each is self-contained.
`GIT_GUIDE.md` ends with `## 9. Checklist`; this document follows the same pattern (§9).

### 1.2 Living Project-State Documents — "What's the current state of things"

| Document | Role |
|---|---|
| `PROJECT_REPORT.md` | Architecture / file-structure snapshot |
| `HISTORY.md` | Chronicle of completed work (table format) |
| `ISSUES.md` | Resolved / unresolved / deferred status of discovered issues |
| `PREPROCESS.md` | Deep dive on the refine-rules subsystem (model for future subsystem docs, §6) |
| `BUILD_GUIDE.md` | Deep dive on the Windows exe/installer build pipeline |

All carry a **`최신 갱신`** field (§8) and **cross-reference each other**. They risk **silently
going stale** when the code changes — always follow the re-verification principles in §5–§7.

### 1.3 Out of Scope

| Document | Reason |
|---|---|
| `WORK_FLOW.md` | Customer-facing business process document — unrelated to code changes |
| `STUDY.md` | Personal study notes, `.gitignore`'d — not a project record |

Not covered by the "code change → documentation update" mechanism; judge each on its own purpose.

---

## 2. Code Change → Documentation Mapping

| Work | Update target |
|---|---|
| Bug-fix / feature commit | Add a table row to `HISTORY.md` (§3) |
| Newly discovered unresolved problem | Register in `ISSUES.md` §2 (list) (§4) |
| An existing issue gets resolved | Move `ISSUES.md` §2→§1, update `현황` count (§4) |
| File deleted/created, large refactor, signature change | Update `PROJECT_REPORT.md` (§5) |
| A subsystem's behavior changes | Update the matching deep-dive doc, or create one (§6) |
| `develop→main` release PR | Add a release row to `HISTORY.md` + update `현재 브랜치 상태` (§3) |
| New convention/rule finalized | `CODING_GUIDE.md` (project-specific section) or `GIT_GUIDE.md` |
| Lines added/removed in a `.py` file | Check whether file:line citations shifted (§6.1) |

The same work often spans several documents (e.g. a bug fix → `HISTORY.md` row + `ISSUES.md`
entry moved). Use the §9 checklist to avoid missing one.

---

## 3. HISTORY.md Writing Rules

One completed unit of work = one table row.

- **Schema**: `날짜 | PR/커밋 | 항목 | 배경·원인 | 수정·내용 | 검증` — 6 fixed columns.
- **One row = one unit of work**: closely related commits (feature + follow-up fix + doc sync) group
  into one row as `(commit hashes)`; unrelated commits get separate rows.
- **Docs-only commits**: doc sync riding along with a feature commit folds into that row's
  "수정·내용" column. Independently significant doc work (new guide, large reorg) gets its own row.
- **Releases are a row too** (`develop→main` merge) — summarize key changes, confirm nothing since
  the previous release was missed.
- Early entries with no dated commit message: use `~date*` plus a footnote explaining the estimate.
- Several sub-items in one cell: use `<br>` or circled numbers (①②③) — never a literal `|`.
- The **`현재 브랜치 상태`** section at the bottom tracks the latest release's `main`/`develop`
  hashes and sync status — update it on every release.

---

## 4. ISSUES.md Writing Rules

Format differs by status — **not a single unified table**.

- **§1 Resolved (table)**: `# | 이슈 | 위치 | 원인 | 해결 | PR/커밋` — add a row when resolved.
- **§2 Unresolved/Deferred (list + prose)**: `### Item name — Status (Date)` heading, then
  `위치 / 상세 / 사유·필요 조치` bullets. A table cell can't hold the multi-paragraph cause
  analysis/alternatives/residual-risk narrative these often need — hence the prose format.
- **Numbering**: circled markers (①②③…㉑㉒…) assigned cyclically by discovery order; unchanged when
  an issue moves §2→§1.
- **Move procedure**: delete the §2 entry and add the §1 row — never leave it in both places.
- Keep **`현황`** (`Resolved N · Unresolved N · Deferred N`) matching actual counts on every change.

---

## 5. PROJECT_REPORT.md Writing Rules

An architecture snapshot — **the document most prone to going stale**. Cases actually found:
already-deleted files still listed, already-fixed bugs still marked "⚠️", a deleted function still
in the function table, line counts off by over 100.

**Principle**: don't trust existing prose — re-verify with:

- `wc -l <file>` — line-count accuracy
- `ls` / `git log --follow` — file still exists, not deleted
- `grep -n "^def \|^class "` — function/class list matches current code
- The issue's status in `ISSUES.md` (✅ resolved?) — is a "⚠️" warning still valid
- `git log` — any commits missed since the last doc update (deletions/renames/large refactors)

---

## 6. Deep-Dive Document Writing Rules

Documents like `PREPROCESS.md` that go deep into one subsystem.

- File:line citations go stale the instant code changes — re-verify every cited line whenever the
  document is updated (a past session found 6 stale citations in `PREPROCESS.md` this way).
- A feature can ship without ever making it into the document — when updating, sweep related code
  in full (`grep` relevant call sites) to check nothing is missing.
- Once a subsystem is complex enough (plugin mechanism, multi-stage pipeline), create a standalone
  deep-dive doc: add it to §1.2's map and ask the user whether to register it in `CLAUDE.md`.
- Link related documents explicitly at the top (implementation history, issue status).

### 6.1 Detecting Line-Number Drift Caused by Code Edits

Re-verifying "when you update the document" is reactive — drift happens the moment a line is
added/removed in code, even with no plan to touch documentation, and quietly accumulates (one
session found 12 stale spots at once).

**After code work (before committing / wrapping up)**:

1. Identify `.py` files whose **line count changed** this session.
2. For each, `grep -rn "<filename>\.py:[0-9]" guidelines/*.md` to find citing passages.
3. A citation pointing **below** the edit point is suspect; one above is unaffected.
4. Don't fix by arithmetic (errors compound across multiple edits) — re-find the actual
   function/class/constant via `grep -n "^def name\|^class name\|^name ="` and cite its current
   location.
5. Do this after **every** code task that adds/removes lines in referenced code, even sessions with
   no planned doc work — fix drift on the spot if found.

---

## 7. Cross-Reference Integrity Principles

- **Renumbering a section** (e.g. `ISSUES.md` §5→§6): `grep -rn "ISSUES.md.*§5\|이슈.*§5"` across
  documents and update every reference together (a past session found `PREPROCESS.md`'s §4/§6
  references broken only after the fact).
- **Moving a folder or renaming a file** (e.g. `systems/`→`guidelines/`): search and update every
  document's path references plus `CLAUDE.md`'s reference list.
- **Citing a commit hash or PR number**: re-confirm with `git show -s --format='%s'` — never from
  memory or a guess.

---

## 8. "Last Updated" Field Rules

- Format: `YYYY-MM-DD HH:MM` (hours:minutes, not just the date).
- Update only when content substantively changes — skip for a typo fix, but any "reflect a code
  change" work per this guide is always grounds for an update.
- Updating several living documents (§1.2) in one session doesn't require the same timestamp on
  each — record each document's actual last-edited time.

---

## 9. Documentation Update Checklist

- [ ] Re-verified against the actual code rather than trusting existing prose? (§5)
- [ ] Reflected as a `HISTORY.md` row? (§3)
- [ ] New/resolved issues reflected in `ISSUES.md`, `현황` count matching? (§4)
- [ ] `PROJECT_REPORT.md` description (file list, line counts, function table, issue warnings)
      still accurate? (§5)
- [ ] Relevant deep-dive doc updated, file:line citations still accurate? (§6)
- [ ] If a `.py` file's line count changed this session, checked citing documents for shifted line
      numbers? (§6.1)
- [ ] Cross-references between documents (section numbers, file:line, paths) still intact? (§7)
- [ ] Updated the `최신 갱신` field? (§8)
- [ ] If code itself changed, checked comments/docstrings per §10 criteria?

---

## 10. In-Code Comment Writing and Maintenance Principles

Covers comments/docstrings/runtime messages in `.py` source, not `guidelines/` md documents.
Grounded in a session where scanning ~8,000 lines turned up 11 drifted comments, 4 describing dead
code no longer reachable.

### 10.1 Fix the Comment in the Same Change That Fixes the Code

When a function/variable's behavior, default, count, or reference target changes, update every
describing comment/docstring **within that same change** — deferring it leaves two contradictory
comments coexisting (an actual case: one line said a default was `""`, five lines above still said
`"—"`).

Watch especially for: renames/moves (class or file), default-value changes, rule/item count changes,
logic moved to a different class/module (the pre-move comment often stays at the old location).

### 10.2 Types of "Stale Comments"

| Type | Example |
|---|---|
| Default value/count mismatch | Comment states an old number/string the code no longer has |
| Referenced-name mismatch | Warning mentions `PROXY_LIST`; actual config key is `ip_list` |
| Pattern/syntax mismatch | Docstring pattern doesn't match the real regex |
| Architecture mismatch | Describes logic as hardcoded when it's since moved to a plugin |
| Orphaned label | A `"( CASE 1 )"` label with no matching `"CASE 2"` anywhere |
| Dead code described as live | Docstring claims a handler runs, but it's wired to a different method |

### 10.3 When You Discover Dead Code

1. Confirm with `grep` across every call site/signal connection that it's truly dead — don't guess.
2. If asked to "just fix the comment," correct it truthfully (e.g.
   `"미사용 — 호출되지 않음, 이유: ..."`) without deleting the code — deletion is harder to revert,
   so wait for a separate request.
3. On a deletion request, also check for secondary orphans (fields/methods used only by that dead
   code) — an actual case cascaded from 1 dead method to 4 methods and 2 orphaned fields. Re-confirm
   with `grep` at every step.

### 10.4 How to Run a Large-Scale Comment Audit

- Split by file group and parallelize (e.g. Explore agents), but brief each agent on what refactoring
  happened recently (renames, default changes, architecture shifts) — without that context they
  can't reliably spot stale comments.
- Re-verify any "confidence: low/medium" finding by reading the code directly before fixing it.
- Separate style opinions from factual errors — fix only the factual errors unless asked otherwise.
- After fixing, run `python3 -m py_compile <file>` on every changed file to confirm no syntax errors.
