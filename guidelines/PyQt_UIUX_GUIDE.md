# PyQt UI/UX Development Guide (Consolidated Edition)

> A practical guide for building maintainable, efficient UI/UX in desktop applications with PyQt5 / PyQt6 (including PySide6). This document was produced by cross-validating two draft guides and merging the essential content from both.

---

## Table of Contents

1. [Core Principles](#1-core-principles)
2. [Project Structure and Architecture](#2-project-structure-and-architecture)
3. [Layout Design — Never Use Absolute Coordinates](#3-layout-design--never-use-absolute-coordinates)
4. [Widget Selection Guide](#4-widget-selection-guide)
5. [Asynchronous Processing and Responsiveness](#5-asynchronous-processing-and-responsiveness)
6. [Visual Design and Styling (QSS)](#6-visual-design-and-styling-qss)
7. [UX Patterns and User Feedback](#7-ux-patterns-and-user-feedback)
8. [Large Datasets — Model/View Architecture](#8-large-datasets--modelview-architecture)
9. [HiDPI and Responsive UI](#9-hidpi-and-responsive-ui)
10. [Accessibility and Internationalization (i18n)](#10-accessibility-and-internationalization-i18n)
11. [Theming and Dark Mode](#11-theming-and-dark-mode)
12. [Settings Persistence and State Restoration](#12-settings-persistence-and-state-restoration)
13. [Testing and Debugging](#13-testing-and-debugging)
14. [Deployment Considerations](#14-deployment-considerations)
15. [Final Checklist](#15-final-checklist)

---

## 1. Core Principles

These are the principles both source guides converge on for every PyQt UI/UX decision.

- **Separate UI from logic**: The View should only handle display and input capture; decisions (business logic) belong in a separate layer (MVC/MVP/MVVM).
- **Responsiveness first**: The main (GUI) thread must never block. Any operation that could take longer than 0.1 seconds should be offloaded to a worker thread.
- **Layout managers are mandatory**: Use `QVBoxLayout`/`QHBoxLayout`/`QGridLayout`/`QFormLayout`, etc., instead of absolute coordinates (`move`, `setGeometry`). This ensures automatic adaptation to window resizing, DPI changes, and varying text lengths across languages.
- **Consistency**: Keep widget sizes, spacing, colors, icon styles, shortcuts, and terminology uniform across the entire app. The same action should always behave the same way.
- **Predictability**: Follow standard OS shortcuts (Ctrl+S, Ctrl+Z, etc.) and platform conventions (e.g., button ordering).
- **Feedback**: Every user action needs an immediate visual response (hover states, loading spinners, status bar messages, etc.).
- **Forgiveness**: Mistakes should be reversible (Undo/Redo, confirmation dialogs for deletions).
- **Simplicity**: Place only one primary task per screen; move secondary functions into menus or settings.

---

## 2. Project Structure and Architecture

### 2.1 Recommended Directory Structure

```
my_app/
├── main.py                 # Entry point (keep minimal)
├── app/  (or core/)
│   ├── views/               # UI definitions (widgets, windows, dialogs)
│   │   ├── main_window.py
│   │   └── settings_dialog.py
│   ├── widgets/              # Reusable custom widgets
│   ├── viewmodels/            # Screen state and logic binding (when using MVVM)
│   ├── models/                # Data models (QAbstractItemModel, etc.)
│   ├── services/               # Business logic, API, DB (Qt-independent, pure Python)
│   ├── workers/                # QThread / QRunnable workers
│   └── resources/
│       ├── icons/
│       ├── styles/              # .qss files
│       └── resources.qrc
├── ui/                      # Qt Designer .ui files (if used)
└── tests/
```

### 2.2 Choosing an Architecture Pattern

| Pattern | Best for | Characteristics |
|---|---|---|
| **Simple widgets + service separation** | Small tools, 1–3 screens | View calls service functions directly. Simplest option |
| **MVC / MVP** | Medium-sized apps, data shared across screens | A Presenter mediates between View and Model |
| **MVVM** | Apps with complex state (recommended default) | ViewModel/Controller notifies state changes via signals. Easy to test |

```
View (QWidget)  ←→  ViewModel/Controller  ←→  Model (core logic, DB, API)
   ↑ emits signals      ↑ relays signals, manages state    ↑ pure business logic
```

**Key rule**: The `services/` (or `core/`) layer must not import PyQt. This enables GUI-free unit testing and lets the logic be reused later in a CLI or web context.

> **Exception — small, single-maintainer desktop apps**: When the team doesn't practice GUI unit testing and the app is maintained by one or a few developers, a flatter **View + event-handler Mixin** split (one module defines UI layout, a parallel Mixin module owns all event-handling/business logic for those widgets) can be just as maintainable as MVVM, with less indirection. This is the pattern used in the Harvest project (`layout.py` for layout, `trigger.py` for Mixins — see its `PROJECT_REPORT.md` §2–3). Don't introduce a `services/`/ViewModel layer purely for architectural purity if there's no GUI-test payoff to justify the added indirection.

### 2.3 Loose Coupling via Signals/Slots

Widgets should not reference each other directly — communicate through signals and slots instead.

```python
# Bad — child directly manipulates the parent (tight coupling)
class ChildWidget(QWidget):
    def on_done(self):
        self.parent().status_label.setText("Done")

# Good — emit a signal, and wire it up at the assembly point above
class ChildWidget(QWidget):
    task_finished = pyqtSignal(str)

    def on_done(self):
        self.task_finished.emit("Done")

# Connected from the parent/assembly point
child.task_finished.connect(status_label.setText)
```

```python
class UserController(QObject):
    user_loaded = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def load_user(self, user_id: str):
        try:
            user = self.user_service.get_user(user_id)
            self.user_loaded.emit(user)
        except UserNotFoundError as e:
            self.error_occurred.emit(str(e))
```

- Give custom signals explicit types (`pyqtSignal(str)`, `pyqtSignal(int, str)`, etc.).
- Overusing lambdas as slots makes debugging harder — extract complex logic into named methods instead.
- Signal connections are automatically released when a widget is deleted, but explicit `disconnect()` may be needed in special cases (e.g., connections between long-lived objects).

### 2.4 Qt Designer vs. Writing Code

| Approach | Pros | Cons |
|---|---|---|
| **Qt Designer (.ui)** | Fast prototyping, easier collaboration with non-developers | Weak for dynamic UI, hard to diff/review |
| **Writing code directly** | Better version control, free-form dynamic construction | Slower initial authoring |

Recommendation: use **Designer for static screens** (e.g., settings dialogs) and **code for dynamic screens**. Loading `.ui` files at runtime with `uic.loadUi()` reduces build steps compared to converting them ahead of time with `pyuic`/`pyside6-uic`. Compile resources (icons, images) into `.qrc` to avoid path issues at deployment.

Avoid letting any single file grow past ~500 lines of UI code — split it by widget instead.

---

## 3. Layout Design — Never Use Absolute Coordinates

Absolute-coordinate placement will inevitably break with window resizing, font size differences, OS differences, and HiDPI displays.

### 3.1 Choosing a Layout

| Situation | Recommended Layout |
|---|---|
| Sequential vertical/horizontal arrangement (most screens) | `QVBoxLayout` / `QHBoxLayout` |
| **Label + input field pairs** (settings/input forms) | `QFormLayout` (mandatory) |
| Grid arrangement (calculators, dashboards) | `QGridLayout` |
| User-resizable panel splits | `QSplitter` |
| Tab-based multi-screen navigation | `QTabWidget` |
| Dockable panels (IDE-style UI) | `QDockWidget` |
| Screen switching (wizards, etc.) | `QStackedWidget` / `QStackedLayout` |

Keep nested layouts to 3–4 levels deep at most to manage complexity.

### 3.2 Practical Rules

```python
layout = QVBoxLayout(self)
layout.setContentsMargins(16, 16, 16, 16)  # Set outer margins explicitly
layout.setSpacing(8)                        # Keep widget spacing consistent

layout.addWidget(header)
layout.addWidget(content, stretch=1)        # Content takes up remaining space
layout.addStretch()                         # Or push with an empty spacer
layout.addWidget(button_bar)
```

- Set `setContentsMargins()` and `setSpacing()` explicitly to eliminate platform-default discrepancies.
- Recommended defaults: 8–16px margins, 6–12px widget spacing. **Manage spacing/margin values as constants** (e.g., `SPACING_SM = 4`, `SPACING_MD = 8`, `SPACING_LG = 16`) to keep a consistent visual rhythm across the app.
- Keep related elements close together; separate unrelated groups clearly with a `QGroupBox` or whitespace.
- Use `QSizePolicy` to explicitly define how each widget responds to window resizing.
  - Input fields: `Expanding` (horizontal) × `Fixed` (vertical)
  - Buttons: `Fixed` or `Minimum`
- Don't overuse `setMinimumSize()` / `setMaximumSize()` — reserve them for cases where truly necessary, such as preventing the layout from collapsing below a minimum window size.

### 3.3 Button Placement Conventions

The order of OK/Cancel buttons differs by OS. Don't place them manually — use `QDialogButtonBox`, which automatically follows platform conventions.

```python
buttons = QDialogButtonBox(
    QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
)
buttons.accepted.connect(self.accept)
buttons.rejected.connect(self.reject)
```

---

## 4. Widget Selection Guide

### 4.1 Input Widgets

- Short single-line text → `QLineEdit`
- Multi-line text → `QTextEdit` / `QPlainTextEdit`
- Limited choices → `QComboBox` (5 or fewer) / `QListWidget` (when multi-select is needed)
- Numeric input → `QSpinBox` / `QDoubleSpinBox` (better error prevention than free-text input)
- On/Off → `QCheckBox` (independent selection) / `QRadioButton` (mutually exclusive selection)
- Date/time → `QDateEdit`, `QTimeEdit`, `QDateTimeEdit` (leverage the calendar popup)

### 4.2 Custom Widgets

- Turn recurring UI patterns (cards, badges, custom buttons) into reusable `QWidget` subclasses.
- When implementing `paintEvent()` directly, set the `Antialiasing` render hint on `QPainter` for visual quality.

> For widgets handling large data displays (`QTableView`, etc.), see [8. Large Datasets — Model/View Architecture](#8-large-datasets--modelview-architecture).

---

## 5. Asynchronous Processing and Responsiveness

**Absolute rule**: Never run operations that could take longer than 0.1 seconds (file I/O, network requests, heavy computation) on the main (UI) thread. A frozen UI reads to users as a crashed app.

### 5.1 QThread + Worker Pattern (standard)

Prefer the `moveToThread()` approach over subclassing `QThread`.

> **Exception**: When the work must run in an isolated OS process — not just a thread — subclassing `QThread` as a thin container around a `multiprocessing.Process` is the correct pattern, not a deviation from best practice. This applies when (a) the underlying library enforces a "runs once per process" constraint (e.g., Scrapy's `CrawlerProcess`, which cannot be restarted within the same process), or (b) the task handles large-scale data, where process-level isolation gives real memory/parallelism benefits a plain `QThread` can't. Harvest's `worker.py: MultiprocessWorker(QThread)` is a real example — it wraps `multiprocessing.Process(run_spider)` so arbitrarily large Scrapy crawl results are produced outside the GUI process and streamed back over a `multiprocessing.Queue`.

```python
class Worker(QObject):
    progress = pyqtSignal(int)
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def run(self):
        try:
            for i in range(100):
                # ... actual work ...
                self.progress.emit(i + 1)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))

# Usage
self.thread = QThread()
self.worker = Worker()
self.worker.moveToThread(self.thread)
self.thread.started.connect(self.worker.run)
self.worker.finished.connect(self.thread.quit)
self.worker.finished.connect(self.on_result)
self.worker.progress.connect(self.progress_bar.setValue)
self.worker.error.connect(self.show_error)
self.thread.start()
```

### 5.2 Key Rules

- **Never touch widgets directly from a worker thread.** Always relay changes through signals to the main thread (signal/slot connections are automatically queued across threads).
- For many short-lived tasks, `QThreadPool` + `QRunnable` is a lighter-weight alternative.
- Use `QProgressBar` in determinate mode when progress is measurable, and indeterminate mode (`setRange(0, 0)`) when it isn't. Always pair long-running work with some form of progress indicator.
- Provide a **cancel button** for long operations, and disable related buttons with `setEnabled(False)` to prevent duplicate execution.
- Use `QTimer` for periodic tasks instead of `time.sleep()` loops.

### 5.3 Debouncing

For cases like search boxes where every keystroke could trigger expensive work, use a timer so the action only fires after input pauses.

```python
self.search_timer = QTimer(singleShot=True, interval=300)
self.search_timer.timeout.connect(self.do_search)
self.search_input.textChanged.connect(lambda: self.search_timer.start())
```

### 5.4 Rendering Performance

When adding/removing many widgets dynamically, wrap the changes with `setUpdatesEnabled(False)` → make changes → `setUpdatesEnabled(True)` to reduce the number of re-renders.

---

## 6. Visual Design and Styling (QSS)

### 6.1 Manage QSS in One Place

Don't scatter styles across widget code — separate them into a dedicated `.qss` file and apply it once at startup with `app.setStyleSheet()`. Prefer `objectName`-based selectors over class selectors for precise targeting of specific widgets.

```python
with open("app/resources/style.qss", encoding="utf-8") as f:
    app.setStyleSheet(f.read())
```

```css
/* style.qss */
QPushButton#primaryButton {
    background-color: #2D6CDF;
    color: white;
    border-radius: 6px;
    padding: 8px 16px;
}
QPushButton#primaryButton:hover    { background-color: #1F5BC4; }
QPushButton#primaryButton:pressed  { background-color: #16469E; }
QPushButton#primaryButton:disabled { background-color: #B0BEC5; }

QLineEdit {
    padding: 6px 8px;
    border: 1px solid #c8cdd4;
    border-radius: 4px;
}
QLineEdit:focus { border-color: #2d7ff9; }

/* Use dynamic properties for state-based styling */
QLineEdit[error="true"] { border-color: #e5484d; }
```

State-based styles can be toggled via dynamic properties.

```python
line_edit.setProperty("error", True)
line_edit.style().unpolish(line_edit)
line_edit.style().polish(line_edit)
```

> **Cautionary example**: Defining a single-source-of-truth theme class doesn't by itself guarantee consistency — it only helps if call sites actually use it. Harvest's `style.py` defines a `THEME` class and a `Parts` widget factory for exactly this purpose, but `layout.py`/`trigger.py` still call `setStyleSheet()` inline in well over a hundred places, so the same color/spacing value can drift across screens even though a single source of truth exists. Treat "we have a theme class" as necessary but not sufficient — audit for inline `setStyleSheet()` calls that bypass it.

### 6.2 Design Tokens / Color & Typography Principles

- Manage colors, font sizes, radius values, etc., as constants in a separate config (`theme.py`) so changes propagate consistently.
- **Limit the color palette to 4–6 colors**: Primary, Secondary, Background, Surface, Error/Warning/Success, Text (Primary/Secondary/Disabled).
- Ensure a **contrast ratio of at least 4.5:1** between text and background (accessibility standard).
- Use only 3–4 font size steps (e.g., body 10pt, subhead 12pt, title 15pt). Avoid hardcoding `QFont` — manage typography through QSS.
- Respect the system font (`QApplication.font()`) by default, but load custom/bundled fonts with `QFontDatabase.addApplicationFont()` so display remains consistent even on systems where the font isn't installed.

### 6.3 Icons

- Prefer **SVG** (`QIcon`) over raster (PNG) so icons stay sharp on HiDPI displays.
- For standard actions, consider `QStyle.standardIcon()` or `QIcon.fromTheme()` (Qt 6) first.
- Always provide `setToolTip()` for icon-only buttons.

---

## 7. UX Patterns and User Feedback

### 7.1 Feedback Hierarchy — Match the Tool to the Level of Interruption

| Situation | Tool | Rationale |
|---|---|---|
| Light status notification (e.g., "Saved") | `QStatusBar.showMessage(msg, 3000)` or a toast | Doesn't interrupt workflow |
| In-progress indication | `QProgressBar` / `QProgressDialog`, disabled buttons | Makes "still working" clear |
| Simple informational message | `QMessageBox.information()` | — |
| Warning | `QMessageBox.warning()` | — |
| Critical error | `QMessageBox.critical()` | — |
| User decision required | `QMessageBox.question()` | Requires an explicit choice |
| Warning before an irreversible action | Confirmation dialog + clear explanation of the outcome | "This deletion cannot be undone." |
| Input error | Inline display (field border + helper label) | Far better than a modal popup |

**Principle**: Modal dialogs (`exec()`) are a last resort. Use them only when truly necessary, and prefer status bar or toast notifications that don't interrupt the user's flow.

> **Unattended/scheduled execution paths need this rule most**: Harvest hit this directly — a `QMessageBox.warning()` shown when a scheduled (unattended) crawl produced empty data had no one present to click it, so the run appeared to hang indefinitely. The fix wasn't a UI-layer fix at all; it was a fixed, non-interactive rule set (`SCHEDULED_REFINE_RULES`) applied before that code path could be reached. **Any code path that can run without a human present must never depend on a modal being dismissed** — treat this as a hard constraint, not just a UX preference, and audit scheduled/background/CLI-triggered flows specifically for stray `QMessageBox` calls.

### 7.2 Input Validation

- Show validation **right where the input happens**, not in a popup (e.g., field border color changes).
- Use `QValidator` (`QIntValidator`, `QDoubleValidator`, `QRegularExpressionValidator`) to block invalid input proactively.
- Use `setPlaceholderText()` to hint at the expected format in advance.
- Only enable the confirm button once the whole form is valid:

```python
def update_ok_state(self):
    ok = bool(self.name.text().strip()) and self.email.hasAcceptableInput()
    self.ok_button.setEnabled(ok)
```

### 7.3 Writing Error Messages

- State **what went wrong + how to fix it**, in plain user-facing language.
  - Bad: `Error: [Errno 13] Permission denied`
  - Good: `The file couldn't be saved. Check whether it's open in another program, then try again.`
- Hide technical details behind "Show Details" (`QMessageBox.setDetailedText()`).
- Keep errors unambiguous and always point toward the next action.

### 7.4 Keyboard UX

- Every primary function should be reachable without a mouse. Prefer standard shortcuts.

```python
action_save = QAction("&Save", self)
action_save.setShortcut(QKeySequence.StandardKey.Save)  # Ctrl+S
```

- Use `setTabOrder()` to explicitly define a logical focus order.
- A dialog's default button (`setDefault(True)`) should respond to Enter, and Cancel should respond to Esc.
- Assign `&` mnemonics to menu items and labels.

### 7.5 Undo and Destructive Actions

- If your app has editing features, design `QUndoStack` + `QUndoCommand`-based Undo/Redo **in from the start**. Retrofitting it later is very difficult.
- For destructive actions like deletion, apply at least one of: (a) a confirmation dialog, (b) Undo support where possible, (c) a trash/archive mechanism.

### 7.6 Empty States

A screen with no data yet is an opportunity to guide the user on what to do next. Instead of showing a bare empty table, display guidance text plus a call-to-action button (use `QStackedLayout` to switch between the empty state and the data view).

---

## 8. Large Datasets — Model/View Architecture

Item-based widgets (`QTableWidget`/`QListWidget`) are convenient but degrade sharply in performance beyond a few hundred to a few thousand rows.

| Data scale | Recommendation |
|---|---|
| ~hundreds of rows, static | Item-based widgets like `QTableWidget` (simple) |
| Thousands of rows or more, dynamic updates | `QAbstractTableModel` + `QTableView` |
| Tree structures | `QAbstractItemModel` + `QTreeView` |
| Lists | `QAbstractListModel` + `QListView` |
| Sorting/filtering needed | Insert a `QSortFilterProxyModel` between the model and the view |
| Hundreds of thousands of rows | Lazy loading or pagination via `fetchMore()`/`canFetchMore()` |

> **Applies to Harvest — adopt, don't defer**: `MonitorPage`'s Raw/refined/comparison tables are all `QTableWidget` today (item-based), which was a reasonable starting point when result sets were small. But this is a crawler — result sets routinely reach the thousands-of-rows range as blueprints and callback URL pagination scale up, which is exactly the threshold this guide flags as `QTableWidget`'s breaking point. Treat this as a known migration target rather than a hypothetical: new large-result-set table work should go through `QAbstractTableModel` + `QTableView` (+ `QSortFilterProxyModel` for the existing sort/filter behavior) rather than extending the `QTableWidget` pattern further. The `setCellWidget`-avoidance comment already in `layout.py` shows the team has been managing `QTableWidget`'s performance ceiling by hand — the model/view switch removes the need for that kind of manual workaround.

```python
class MyTableModel(QAbstractTableModel):
    def rowCount(self, parent=QModelIndex()): return len(self._rows)
    def columnCount(self, parent=QModelIndex()): return len(self.HEADERS)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            return self._rows[index.row()][index.column()]
        return None
```

- When data changes, you must call notification methods like `beginInsertRows()`/`endInsertRows()` for the view to update efficiently. Overusing `layoutChanged` is a common cause of performance problems.
- For custom cell rendering, `QStyledItemDelegate` is much faster than inserting widgets via `setCellWidget`.

---

## 9. HiDPI and Responsive UI

### 9.1 HiDPI Scaling

**PyQt6 has HiDPI scaling enabled by default.** For PyQt5, apply the following before creating `QApplication`:

```python
import sys
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

# PyQt5 only
if hasattr(Qt, 'AA_EnableHighDpiScaling'):
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
```

- Prefer layouts, `sizeHint`, and expansion policies over hardcoded pixel sizes.
- Use SVG icons, or prepare multiple resolutions (1x, 2x, 3x).

### 9.2 Window Size and Multi-Monitor Setups

- Use `setMinimumSize()` to define the smallest window size at which the UI won't break.
- It's recommended to compute the initial window size as a proportion of the screen resolution.

```python
screen = app.primaryScreen().availableGeometry()
window.resize(int(screen.width() * 0.6), int(screen.height() * 0.7))
```

- When restoring a saved window size/position, the monitor configuration may have changed — validate that it fits within `QScreen.availableGeometry()` before applying it.

### 9.3 Font Scaling

- Use the system font by default and override only when necessary.
- Offering a user-adjustable font size setting is good practice from an accessibility standpoint.

---

## 10. Accessibility and Internationalization (i18n)

### 10.1 Accessibility

- Every primary function must be reachable via keyboard alone.
- For icon-only buttons: set both `setToolTip()` and `setAccessibleName()`.
- For complex form fields, combine `setPlaceholderText()` with `setWhatsThis()`.
- Never rely on color alone to convey status — pair it with icons/text to support color-vision deficiencies.
- Verify that focus indicators aren't being stripped out by QSS (`:focus` styling should be preserved).
- Set `setAccessibleName()` and `setAccessibleDescription()` on key interactive widgets to support screen readers.

### 10.2 Internationalization

Even if you don't support multiple languages from day one, wrapping strings in `self.tr()` costs almost nothing later on.

```python
self.label.setText(self.tr("Please select a file"))
```

- Translation workflow: `pylupdate6` → `.ts` file → translate in Qt Linguist → `lrelease` → load `.qm` (`QTranslator`).
- Translated text can run 30–50% longer than the original, so avoid fixed-width labels/buttons.
- Use `QLocale` for date/number formatting.

---

## 11. Theming and Dark Mode

- Swap between light/dark themes by treating colors as variables (e.g., generate the QSS string in Python from a palette dict) rather than hardcoding.
- Prefer `QPalette`-based semantic color roles over hardcoded colors.
- On Qt 6.5+, `QStyleHints.colorScheme()` can detect the OS dark mode setting. On older versions, estimate it from palette brightness as shown below.

```python
from PyQt6.QtGui import QPalette

def is_dark_mode(app: QApplication) -> bool:
    palette = app.palette()
    bg_color = palette.color(QPalette.ColorRole.Window)
    return bg_color.lightness() < 128
```

- Prepare separate icon sets for dark/light modes, or use SVG's `currentColor`.
- Offering Light/Dark/Follow System options in settings is standard UX.

---

## 12. Settings Persistence and State Restoration

Users expect their environment to persist across app restarts.

```python
settings = QSettings("MyCompany", "MyApp")

# On exit (closeEvent)
settings.setValue("geometry", self.saveGeometry())
settings.setValue("windowState", self.saveState())      # Toolbar/dock positions
settings.setValue("splitter", self.splitter.saveState())

# On startup
if geo := settings.value("geometry"):
    self.restoreGeometry(geo)
```

Things worth persisting: window size/position, splitter ratios, recent files list (built as `QAction`s in a menu), last-used directory, theme selection, table column widths.

> **`QSettings` vs. a JSON file + singleton store**: `QSettings` fits small, flat key-value UI state (the list above). It's the wrong tool once you need structured, versioned, or per-customer-bundled data — e.g., Harvest's `BlueprintStorage`/`CustomModuleStorage` manage nested JSON (`request_info.json`, `custom_rules/{render,refine}/{seq_no}.py`) with a seed-on-first-run policy (bundled resource → `%LOCALAPPDATA%` on first run, then that copy wins) so a customer's local edits survive re-deployment and per-customer files can be selectively bundled by `build-exe.ps1`. Use `QSettings` for simple UI state; keep domain/config data in your own JSON+singleton layer when deployment needs (per-install seeding, selective bundling) go beyond what `QSettings` was designed for.

---

## 13. Testing and Debugging

- **Logic tests**: Since `services/` has no Qt dependency, test it with plain `pytest`.
- **GUI tests**: Use `pytest-qt`'s `qtbot` to automate clicks, input, and waiting on signals.

```python
def test_ok_disabled_when_empty(qtbot):
    dialog = MyDialog()
    qtbot.addWidget(dialog)
    assert not dialog.ok_button.isEnabled()
    qtbot.keyClicks(dialog.name_input, "John Doe")
    assert dialog.ok_button.isEnabled()
```

- Verify signal emissions with `qtbot.waitSignal(worker.finished, timeout=3000)` or `QTest.qWait()`.
- Install a `sys.excepthook` so exceptions in the GUI app don't silently disappear — log them and notify the user.
- During development, attaching an event filter to `QApplication` to log signal flow can help with debugging.

---

## 14. Deployment Considerations

- **Perceived startup speed**: Use a `QSplashScreen` to mask loading time, and defer heavy initialization until after the window is shown.
- Bundle resources (icons, QSS) reliably via the Qt resource system (`.qrc`) or PyInstaller's `--add-data`. Handle runtime paths with a helper that accounts for `sys._MEIPASS`.
- Don't forget the app icon, window title, and version display (an About dialog).
- OS-specific conventions (menu bar placement, button order, file dialogs) are mostly handled automatically by Qt's standard components — **don't build a custom file dialog; use `QFileDialog`'s static methods.**

---

## 15. Final Checklist

**Architecture**
- [ ] UI, logic, and data are separated into distinct layers (`services/` does not import PyQt)
- [ ] Widget-to-widget communication happens via signals/slots
- [ ] Business logic is separated from View code

**Layout**
- [ ] Every screen is built with layout managers, not absolute coordinates
- [ ] Margins/spacing are unified via constants
- [ ] The UI doesn't break when the window is resized
- [ ] Forms use `QFormLayout`; dialog buttons use `QDialogButtonBox`

**Responsiveness**
- [ ] Any operation over 0.1 seconds runs on a worker thread
- [ ] Workers never touch widgets directly (signals only)
- [ ] Long-running tasks show progress and offer a cancel option

**Large Data**
- [ ] A Model/View architecture is used for large datasets (thousands of rows or more)

**UX**
- [ ] Every action provides feedback (status bar / progress bar / toast)
- [ ] Input validation is inline, and error messages explain how to resolve the issue
- [ ] Primary functions have standard shortcuts and are keyboard-accessible
- [ ] Destructive actions include confirmation or Undo
- [ ] Empty states include guidance

**Style and Accessibility**
- [ ] Colors/styles are unified in a QSS file
- [ ] Both dark mode and light mode are supported
- [ ] Icons/text remain sharp on HiDPI displays
- [ ] Information is never conveyed by color alone (accessibility)

**Quality and Deployment**
- [ ] Window state and user settings persist via `QSettings`
- [ ] Strings are wrapped in `self.tr()` (i18n readiness)
- [ ] A global exception hook (`sys.excepthook`) prevents silent crashes

---

*Use this document as a team standard, and revise it continuously to fit your project's needs. It applies to both PyQt5 and PyQt6; code examples use PyQt6 syntax (only enum paths differ in PyQt5 — e.g., `Qt.ItemDataRole.DisplayRole` → `Qt.DisplayRole`).*
