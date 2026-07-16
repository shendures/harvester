# Documentation Guide — Writing and Updating Mechanics for `guidelines/` Documents

> The documents inside `guidelines/` form an interconnected system of project records and
> guidelines. This document is a meta-guide covering "which md file to update, when, and in what
> format, when code or a feature changes" (§1–§9), and "how to write and maintain comments/
> docstrings in the source code" (§10).
> Consult this document first whenever you create or edit an md document or a code comment.

---

## Table of Contents

1. [Document Map](#1-document-map)
2. [Code Change → Documentation Mapping](#2-code-change--documentation-mapping)
3. [HISTORY.md Writing Rules](#3-historymd-writing-rules)
4. [ISSUES.md Writing Rules](#4-issuesmd-writing-rules)
5. [PROJECT_REPORT.md Writing Rules](#5-project_reportmd-writing-rules)
6. [Deep-Dive Document Writing Rules](#6-deep-dive-document-writing-rules)
7. [Cross-Reference Integrity Principles](#7-cross-reference-integrity-principles)
8. ["Last Updated" Field Rules](#8-last-updated-field-rules)
9. [Documentation Update Checklist](#9-documentation-update-checklist)
10. [In-Code Comment Writing and Maintenance Principles](#10-in-code-comment-writing-and-maintenance-principles)

---

## 1. Document Map

Documents in `guidelines/` fall into two groups with different characters. Understanding this
distinction first tells you which rules apply.

### 1.1 Static Rulebooks — "Do it this way"

| Document | Role |
|---|---|
| `CODING_GUIDE.md` | Language-neutral coding principles + this project's own conventions (explicitly marked as such) |
| `GIT_GUIDE.md` | Git branch/commit/PR workflow rules |

- **Have no `최신 갱신` ("Last Updated") field** — they hold rules, not project state, so you
  only edit them when a rule itself changes.
- Have no cross-references to other documents (a `관련 문서`, "Related Documents", section) —
  each is a self-contained rulebook.
- `GIT_GUIDE.md` ends with `## 9. Checklist` (a checkbox list). This document follows the same
  pattern (see §9).

### 1.2 Living Project-State Documents — "What's the current state of things"

| Document | Role |
|---|---|
| `PROJECT_REPORT.md` | Architecture / file-structure snapshot |
| `HISTORY.md` | Chronicle of completed work (table format) |
| `ISSUES.md` | Resolved / unresolved / deferred status of discovered issues |
| `PREPROCESS.md` | Deep dive dedicated to the refine-rules subsystem — similar documents may appear for other subsystems in the future (see §6) |

- All of them carry a **`최신 갱신` ("Last Updated") field** (see §8).
- They **cross-reference each other** — e.g. `PREPROCESS.md`'s `관련 문서` ("Related Documents")
  section, the `함께 관리되는 문서` ("Documents Managed Together") note at the top of
  `PROJECT_REPORT.md`, etc.
- They risk **silently going stale** when the code changes — always follow the re-verification
  principles in §5–§7 when touching a document in this group.

### 1.3 Out of Scope for This Guide

| Document | Reason |
|---|---|
| `WORK_FLOW.md` | Customer-facing business process document — unrelated to code changes |
| `STUDY.md` | Personal study notes, `.gitignore`'d (untracked by git) — not a project record |

These two documents are not covered by the "code change → documentation update" mechanism. If you
ever need to touch them, judge each on its own purpose.

---

## 2. Code Change → Documentation Mapping

Which documents to update, by kind of work:

| Work | Update target |
|---|---|
| Bug-fix / feature commit | Add a table row to `HISTORY.md` (§3) |
| Newly discovered unresolved problem | Register it in `ISSUES.md` §2 (list) (§4) |
| An existing issue gets resolved | Move it from `ISSUES.md` §2 to §1 (table), update the `현황` ("Status") count (§4) |
| File deleted/created, large-scale refactor, function signature change | Update the relevant table in `PROJECT_REPORT.md` (file size, function list, etc.) (§5) |
| A specific subsystem's behavior changes | Update the matching deep-dive document (e.g. `PREPROCESS.md`), or consider creating one if none exists (§6) |
| `develop→main` release PR | Add a release row to `HISTORY.md` + update the `현재 브랜치 상태` ("Current Branch Status") section (§3) |
| New convention/rule finalized | `CODING_GUIDE.md` (project-specific section) or `GIT_GUIDE.md` |
| Lines added/removed in a `.py` file (refactor, function moved, etc.) | Detect and fix whether any file:line citations in documents referencing that file have shifted (§6.1) |

The same piece of work often spans multiple documents (e.g. a bug fix → adding a `HISTORY.md` row
+ moving an `ISSUES.md` entry, at the same time). Use the §9 checklist to avoid missing one.

---

## 3. HISTORY.md Writing Rules

`HISTORY.md` records one completed unit of work as one table row.

- **Schema**: `날짜 | PR/커밋 | 항목 | 배경·원인 | 수정·내용 | 검증` (Date | PR/Commit | Item |
  Background/Cause | Change/Content | Verification) — 6 fixed columns.
- **One row = one unit of work**: several closely related commits (e.g. a feature implementation +
  a follow-up bug fix + a doc sync) get grouped into a single row, listed as `(commit hashes)`. If
  they aren't closely related, split them into separate rows.
- **Docs-only commits**: documentation sync that rides along with a related feature commit (e.g. a
  commit that updates `PROJECT_REPORT.md` after a feature change) gets folded briefly into that
  feature row's "수정·내용" (Change/Content) column. Documentation work that has independent
  significance on its own (a new guide, a large-scale reorganization, etc.) gets its own row.
- **Releases must also be recorded as a row each** (`develop→main` PR merge). Summarize the key
  changes included in the "수정·내용" column, and if relevant, confirm nothing has been missed
  since the previous release.
- For early entries whose date isn't stated in the commit message, use `~date*` notation plus a
  footnote explaining the basis for the estimate.
- When a table cell needs to list several sub-items, use `<br>` for line breaks or circled numbers
  (①②③, etc.) to separate them — never use a literal `|` character inside a cell, since it breaks
  the table.
- The **`현재 브랜치 상태`** ("Current Branch Status") section at the bottom keeps a table of the
  latest release's `main`/`develop` commit hashes and sync status — update it on every release.

---

## 4. ISSUES.md Writing Rules

`ISSUES.md`'s format differs by status — **it is not unified into a single table.**

- **§1 Resolved Issues (table)**: 6 columns, `# | 이슈 | 위치 | 원인 | 해결 | PR/커밋` (# | Issue |
  Location | Cause | Fix | PR/Commit). When an issue is resolved, add a row here.
- **§2 Unresolved/Deferred Issues (list + detailed prose)**: written as a `### Item name — Status
  (Date)` heading, followed by `위치 / 상세 / 사유·필요 조치` (Location / Details / Reason &
  Required Action) bullets. **Why not a table**: an in-progress issue often needs multi-paragraph
  narrative — cause analysis, alternatives considered, residual risk — and compressing that into a
  table cell loses too much information.
- **Numbering scheme**: circled-number markers (①②③…㉑㉒…) are assigned cyclically in discovery
  order. When an issue is resolved and moves from §2 to §1, its number is kept unchanged.
- **Move procedure**: when an issue is resolved, delete the §2 entry and add a row to the §1 table.
  Never leave it in both places at once.
- Keep the **`현황`** ("Status") field at the top (`Resolved N · Unresolved N · Deferred N`)
  matching the actual counts every time you add, move, or resolve an issue.

---

## 5. PROJECT_REPORT.md Writing Rules

`PROJECT_REPORT.md` is an architecture snapshot, which makes it **the document most prone to going
stale**. Cases actually found in this session:

- Already-deleted files (`frames_tmp.py`, `spiders/sample.py`) were still sitting in the file
  list/line-count table
- Already-fixed bugs (`RandomCookieMiddleware`, `DelaySchedulerMiddleware`) were still marked
  `"⚠️ 반환값 이슈"` (lit. "⚠️ Return-value issue") / `"⚠️ 미로드"` (lit. "⚠️ Not loaded")
- A deleted function (`engine.run_login()`) was still sitting in the function-list table as-is
- File line counts were off from the real values by as much as 121 lines

**Principle**: when updating this document, don't trust the existing prose — always re-verify with
the following:

- `wc -l <file>` — accuracy of the line-count table
- `ls` / `git log --follow` — whether the file actually still exists and hasn't been deleted
- `grep -n "^def \|^class "` etc. — whether the function/class list matches the current code
- The corresponding issue's status in `ISSUES.md` (✅ resolved or not) — whether a "⚠️" warning is
  still valid
- `git log` — whether any commits have been missed since the last documentation update (especially
  file deletions/renames/large refactors)

---

## 6. Deep-Dive Document Writing Rules

Documents like `PREPROCESS.md` that go deep into a specific subsystem (e.g. the refine rules).

- File:line citations (e.g. `trigger.py:1042`) go stale the instant the code changes. Re-verify
  every cited line number against the actual code whenever you update the document — this session
  found and fixed 6 stale line-number citations in `PREPROCESS.md`.
- A feature can get added without ever making it into the document (e.g. the scheduled auto-save
  fixed rule set and the Before/After comparison-tab integration were entirely missing from
  `PREPROCESS.md`). When updating a deep-dive document, sweep the related code in full (trace
  relevant function/constant call sites with `grep`) to check nothing is missing.
- Once a new subsystem gets complex enough (a plugin mechanism, a multi-stage pipeline, etc.), you
  can create a similar standalone deep-dive document. When you do, add it to the §1.2 document map,
  and check with the user whether it should also be registered in `CLAUDE.md`'s reference list.
- Explicitly link related documents at the top, e.g. "Implementation history: `HISTORY.md`
  (relevant PR/commit); issue status: `ISSUES.md`."

### 6.1 Detecting Line-Number Drift Caused by Code Edits

The first bullet above ("re-verify whenever you update the document") is **reactive** — you only
learn something is stale if you happen to reopen that document. But the drift actually happens
**the moment a line is added or removed in the code**. It happens just the same in code work with
no plan to touch documentation at all (a bug fix, a refactor, moving a function, etc.), and if left
alone it quietly accumulates until someone next opens that document (see the 2026-07-16 session,
where 12 such spots had accumulated before they were all found and fixed at once).

**Check the following after code work (before committing, or before wrapping up the session)**:

1. Identify which `.py` files had their **line count change** this session (additions/deletions,
   not a plain content substitution).
2. For each such file, run `grep -rn "<filename>\.py:[0-9]" guidelines/*.md` to find every document
   passage that cites it.
3. Any cited line number that points **below (after) the edit point** is a suspect — citations
   pointing above (before) the edit point are unaffected and don't need checking.
4. Don't fix a suspect citation with arithmetic (e.g. "removed 10 lines, so subtract 10") — errors
   compound easily if the same file was edited more than once in the same session. Instead,
   re-find the function/class/constant name mentioned alongside the citation via
   `grep -n "^def name\|^class name\|^name ="` and **replace it with its current actual
   location**.
5. Do this check not only "when you also plan to edit the document this time," but after **every**
   code task that added or removed lines in referenced code. Even in a session that won't touch
   documentation at all, check for drift, and fix it on the spot if you find it.

---

## 7. Cross-Reference Integrity Principles

Cross-references between documents (section numbers, file:line, document names) break the moment
either side changes.

- **If you renumber a section in one document** (e.g. `ISSUES.md` §5→§6), you must search for
  documents that reference that section — with something like `grep -rn "ISSUES.md.*§5\|이슈.*§5"`
  — and update them together. This session discovered, only after the fact, that `PREPROCESS.md`'s
  `§4`/`§6` references had actually broken once `ISSUES.md` was reorganized.
- **If a document folder moves or a filename changes** (e.g. `systems/`→`guidelines/`), search for
  and update every document's path references along with `CLAUDE.md`'s reference list.
- **When citing a commit hash or PR number**, re-confirm the actual commit message with
  `git show -s --format='%s'` before writing it down — never from memory or a guess.

---

## 8. "Last Updated" Field Rules

- Format is `YYYY-MM-DD HH:MM` (record hours:minutes, not just the date).
- Update it **only when content substantively changes** — you don't need to bump it for a trivial
  change like a typo fix, but any "reflect a code change" work covered by this guide is always
  grounds for an update.
- If you update several living documents (§1.2) together in one session, they don't all need to
  carry the same timestamp — record each document's actual last-edited time.

---

## 9. Documentation Update Checklist

Check before finishing md document work:

- [ ] Did you open the code directly and re-verify it, rather than trusting the existing document
      prose as-is? (§5)
- [ ] Has this work been reflected as a table row in `HISTORY.md`? (§3)
- [ ] Have new/resolved issues been reflected in `ISSUES.md`, and does the `현황` ("Status") count
      match? (§4)
- [ ] Is the relevant description in `PROJECT_REPORT.md` (file list, line counts, function table,
      issue warning text) still accurate? (§5)
- [ ] Does the relevant deep-dive document (`PREPROCESS.md`, etc.) need an update, and are its
      file:line citations still accurate? (§6)
- [ ] If any `.py` file's line count changed this session, did you check whether the line numbers
      in document passages citing that file have shifted? (§6.1)
- [ ] Are cross-references between documents (section numbers, file:line, paths) still intact? (§7)
- [ ] Did you update the `최신 갱신` ("Last Updated") field? (§8)
- [ ] If you also modified the code itself, did you check the comments/docstrings describing that
      code per the §10 criteria?

---

## 10. In-Code Comment Writing and Maintenance Principles

This section is about comments/docstrings/runtime messages inside source code (`.py`), not about
`guidelines/` md documents. It's grounded in the 2026-07-15 session, where scanning the whole
project (~8,000 lines) turned up 11 comments that had drifted from the actual code — 4 of which
were describing dead code that couldn't even be reached anymore.

### 10.1 Fix the Comment in the Same Change That Fixes the Code

When you change a function/variable's behavior, default value, count, or what it refers to
(another function/class, a config key, a file path), update every comment/docstring describing
that code **within that same change**. Putting it off for "cleanup later" leaves two mutually
contradictory comments coexisting in the same file (an actual case: in `layout.py`, one line
described the `fill_null` default as `""` (empty), while five lines above it still said `"—"`).

Watch especially closely for missed comment updates when changing:

- Function/class renames, file/folder moves (e.g. `CustomRuleStorage`→`CustomModuleStorage`,
  `custom_rules/{seq_no}.py`→`custom_rules/{kind}/{seq_no}.py`)
- Default-value changes (e.g. `fill_value` `"—"` → `""`)
- Rule/item count changes (e.g. refine rules going from 6 to 7)
- Logic moved to a different class/module (Mixin-pattern cleanup, etc.) — the pre-move comment is
  often still sitting at the old location after the move.

### 10.2 Types of "Stale Comments"

The following are actually discovered cases, categorized by type. Suspect and check for these
types right after a code review or a large-scale refactor.

| Type | Example |
|---|---|
| Default value/count mismatch | The comment states an old number/string as-is (comment says `"기본 1.5s"`, lit. "default 1.5s", while the code actually has `setValue(0.5)`) |
| Referenced-name mismatch | A runtime warning mentions `PROXY_LIST`, but the actual config key is `ip_list` |
| Pattern/syntax description mismatch | The input pattern a docstring describes doesn't match the real regex (documented as `${item1,item2}` but the regex only matches `${keywords:item1,item2}`) |
| Architecture description mismatch | Describes rendering logic as hardcoded in `engine.py`, when it has actually since moved to a plugin approach |
| Orphaned label | A `"( CASE 1 )"`-style label with no matching `"CASE 2"` anywhere in the project |
| Describing dead code as if it were alive | A docstring claims `"이 메서드는 X 시그널을 받아 처리한다"` (lit. "this method receives and handles signal X"), but that signal is actually wired to a different method, so this one crashes on a nonexistent attribute reference if it's ever invoked |

### 10.3 When You Discover Dead Code

If you find that the behavior a comment describes never actually executes (no call site, another
method handles the same signal instead, or the referenced attribute doesn't exist on the class):

1. Confirm with `grep`, across every actual call site/signal connection, that it's "truly dead
   code" (don't guess — it's easy to be fooled if another class happens to have a method of the
   same name).
2. If the user asked you to "just fix the comment," limit yourself to correcting it truthfully
   (e.g. `"미사용 — 호출되지 않음, 이유: ..."`, lit. "Unused — never called, because …") and don't
   delete the code itself — deleting code is a harder-to-revert change than fixing a comment, so
   wait for a separate request.
3. If you do get a deletion request, also check for and clean up any other methods/fields that were
   used only by that dead code (secondary orphans). Actual case: deleting one dead method revealed
   3 more methods in the same class with the identical problem (a reference to a nonexistent
   attribute); deleting all 4 then left 2 instance fields — used only by those methods — completely
   orphaned, and those were removed as well. Re-confirm with `grep` at every step that something is
   "truly unused elsewhere."

### 10.4 How to Run a Large-Scale Comment Audit

When checking comment-to-code consistency across the whole project (a periodic check, right after
a large refactor, etc.):

- Split the work by file group and run parallel investigations (e.g. Explore agents), but give each
  agent specifics on "what refactoring happened recently" (class renames, default-value changes,
  architecture shifts) — without that context, they can't reliably pinpoint the relevant stale
  comments.
- Any item an agent flags as "confidence: low/medium" must be independently re-verified by reading
  the code directly before you fix it — don't take an agent's report at face value.
- Separate style opinions (e.g. `"이 주석은 없어도 된다"`, lit. "this comment isn't needed") from
  factual errors (stale comments), and fix **only the factual errors**. Don't act on style opinions
  unless separately requested.
- After fixing, run `python3 -m py_compile <file>` (or the equivalent static syntax check for the
  language) on every changed file to confirm there are no syntax errors.
