# CLAUDE.md

- Before working on any request, consult `MODULE_SPEC.md` to identify the module(s) that
  match the instructed task, then proceed with the work based on that module scope.
- Respond to all requests or questions in Korean.


## Required Skill Invocations

- Invoke the `clean-code-standards` skill whenever you write new code or modify/edit existing code, and if that work also involves PyQt (widgets, layouts, signals/slots, threading in a GUI, stylesheets, etc.), additionally invoke the `pyqt-uiux` skill on top of `clean-code-standards` — but not for requests that merely discuss or plan the project at large without touching code.
- Invoke the `code-housekeeping` skill when optimizing or cleaning up code within the project, and do not invoke it merely because one implementation, library, or tool is being swapped for another with equivalent behavior (e.g., porting a script from one language/tool to another).
- For commits/branches/PRs and WSL↔Windows sync work, invoke the `git-workflow` skill.


## Project References

- Project Report: 'guidelines/project_report.md'
- Architecture: 'guidelines/architecture.md'
- History: 'guidelines/history.md'
- Issues & Backlog: 'guidelines/issues.md'
- Documentation Guide: 'guidelines/documentation_guide.md'
