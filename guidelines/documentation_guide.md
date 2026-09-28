# Documentation Guide — Writing and Updating Mechanics for `guidelines/` Documents

> Meta-guide for `guidelines/`: which md file to update, when, and in what format when code or a
> feature changes (§1–§9), plus in-code comment/docstring writing and maintenance (§10).
> Consult this document first whenever you create or edit an md document or a code comment.

---

## 1. Document Map

### 1.1 Static Rulebooks — "Do it this way"

`CODING_GUIDE.md`/`GIT_GUIDE.md` used to hold these rules as committed md files; they were
deleted and delegated to the Claude Code skill system (commit `6bcdbbf`, "코딩/Git 가이드를
skill로 위임, 대체된 guidelines 문서 삭제"). The rules now live as skills the assistant
invokes per `CLAUDE.md`'s "Required Skill Invocations":

| Skill (`~/.claude/skills/`) | Role | Invoked when (per `CLAUDE.md`) |
|---|---|---|
| `clean-code-standards` | Language-neutral coding principles + this project's conventions | Writing new code or modifying existing code |
| `pyqt-uiux` | PyQt-specific UI/UX rules (widgets, layouts, signals/slots, threading, stylesheets) | On top of `clean-code-standards`, when the work touches PyQt |
| `git-workflow` | Git branch/commit/PR workflow rules | Commits/branches/PRs, WSL↔Windows sync work |
| `code-housekeeping` | Code cleanup/optimization guidance | Optimizing or cleaning up existing code (not a like-for-like swap) |

No `최신 갱신` field and no cross-references to these — they're not `guidelines/` documents;
consult `CLAUDE.md` for the authoritative invocation conditions.

### 1.2 Living Project-State Documents — "What's the current state of things"

| Document | Role |
|---|---|
| `architecture.md` | System architecture — process boundaries, layering, execution/data flow, core design principles |
| `project_report.md` | New-developer onboarding overview — what the project is, tech stack, quick directory map, pointers to deep-dive docs |
| `history.md` | Chronicle of completed work (table format) |
| `issues.md` | Resolved / unresolved / deferred status of discovered issues |
| `preprocess.md` | Deep dive on the refine-rules subsystem (model for future subsystem docs, §6) |
| `build_guide.md` | Deep dive on the Windows exe/installer build pipeline |

All carry a **`최신 갱신`** field (§8) and **cross-reference each other**. They risk **silently
going stale** when the code changes — always follow the re-verification principles in §5–§7.

### 1.3 Out of Scope

| Document | Reason |
|---|---|
| `work_flow.md` | Customer-facing business process document — unrelated to code changes |
| `study.md` | Personal study notes, `.gitignore`'d — not a project record |
| `study_wsl_db_connect.md` | Personal study notes on WSL→Windows DB connectivity, `.gitignore`'d — not a project record |

Not covered by the "code change → documentation update" mechanism; judge each on its own purpose.

---

## 2. Code Change → Documentation Mapping

| Work | Update target |
|---|---|
| Bug-fix / feature commit | Add a table row to `history.md` (§3) |
| Newly discovered unresolved problem | Register in `issues.md` §2 (list) (§4) |
| An existing issue gets resolved | Move `issues.md` §2→§1, update `현황` count (§4) |
| File deleted/created, large refactor, signature change | Update the module's section in `../MODULE_SPEC.md` (§2); update `project_report.md` §1/§3 only if the top-level directory map or scale table changed |
| Process boundary / layering / execution flow changes | Update `architecture.md` (§5) |
| A subsystem's behavior changes | Update the matching deep-dive doc, or create one (§6) |
| `develop→main` release PR | Add a release row to `history.md`, with the resulting `main` hash inline (§3) |
| New convention/rule finalized | Update the relevant skill under `~/.claude/skills/` (§1.1) or `CLAUDE.md` |
| Lines added/removed in a `.py` file | Check whether file:line citations shifted (§6.1) |

The same work often spans several documents (e.g. a bug fix → `history.md` row + `issues.md`
entry moved). Use the §9 checklist to avoid missing one.

---

## 3. history.md Writing Rules

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
- **Releases track their own state inline**: a release row's "수정·내용" column states the
  resulting `main=` commit hash directly (e.g. `` develop→main 머지(main=`c91a435`) `` ) —
  there's no separate branch-status section elsewhere in the file to keep in sync.

---

## 4. issues.md Writing Rules

Format differs by status — **not a single unified table**.

- **§1 Resolved (table)**: `# | 이슈 | 위치 | 원인 | 해결 | PR/커밋` — add a row when resolved.
- **§2 Unresolved/Deferred (list + prose)**: `### Item name — Status (Date)` heading, then
  `위치 / 상세 / 사유·필요 조치` bullets. A table cell can't hold the multi-paragraph cause
  analysis/alternatives/residual-risk narrative these often need — hence the prose format.
- **Numbering**: circled markers (①②③…㉑㉒…) assigned cyclically by discovery order; unchanged when
  an issue moves §2→§1.
- **Move procedure**: delete the §2 entry and add the §1 row — never leave it in both places.
- Keep **`현황`** (`Resolved N · Unresolved N · Deferred N`) matching actual counts on every change.
- **§3 Security/operational observations (bullet list)**: a third, standing section for
  security/ops findings that aren't per-issue bugs (e.g. a plaintext secret, missing test
  coverage) — not part of the §1/§2 resolved/unresolved lifecycle, so entries here don't move
  or get numbered; update in place when the underlying observation changes.

---

## 5. project_report.md / architecture.md Writing Rules

Both follow the same re-verification principle: don't trust existing prose, re-verify against
the actual code. `project_report.md` is the onboarding overview (top-level directory map,
scale table, doc-map links); `architecture.md` snapshots process boundaries/layering/execution
flow. Since project_report.md no longer carries per-file function/class tables (moved to
`../MODULE_SPEC.md`), its main staleness risk is the §1 directory-map/scale table and the §2
doc-map links pointing at documents that moved or were renamed.

**Principle**: don't trust existing prose — re-verify with:

- `wc -l <file>` — line-count accuracy for the §1 scale table
- `ls` / `git log --follow` — directories listed in §1/§3 still exist, not deleted/renamed
- Each §2 doc-map link actually resolves to an existing file
- `git log` — any large refactor since the last doc update that changed the top-level layout

For `architecture.md` specifically, its diagrams cite concrete class/method names (e.g.
`MultiprocessWorker._handle_line()`) — when those are renamed/moved, re-verify with `grep -n` the
same way §6.1 does for deep-dive file:line citations.

---

## 6. Deep-Dive Document Writing Rules

Documents like `preprocess.md` that go deep into one subsystem.

- File:line citations go stale the instant code changes — re-verify every cited line whenever the
  document is updated (a past session found 6 stale citations in `preprocess.md` this way).
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

- **Renumbering a section** (e.g. `issues.md` §5→§6): `grep -rn "issues.md.*§5\|이슈.*§5"` across
  documents and update every reference together (a past session found `preprocess.md`'s §4/§6
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
- [ ] Reflected as a `history.md` row? (§3)
- [ ] New/resolved issues reflected in `issues.md`, `현황` count matching? (§4)
- [ ] `project_report.md` §1 directory map/scale table and §2 doc-map links still accurate? (§5)
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
