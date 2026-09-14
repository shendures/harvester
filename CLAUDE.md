# CLAUDE.md

- The instant any prompt request is given in this project, you MUST invoke the
  `andrej-karpathy-skills:karpathy-guidelines` skill via the `Skill` tool immediately and
  follow that skill's instructions. This applies to every request, not just ones that
  touch code.
- Before working on any request, consult `MODULE_SPEC.md` to identify the module(s) that
  match the instructed task, then proceed with the work based on that module scope.


## Required Skill Invocations
- Invoke the `clean-code-standards` skill whenever you write new code or modify/edit existing code, and if that work also involves PyQt (widgets, layouts, signals/slots, threading in a GUI, stylesheets, etc.), additionally invoke the `pyqt-uiux` skill on top of `clean-code-standards` — but not for requests that merely discuss or plan the project at large without touching code.
- Invoke the `code-housekeeping` skill when optimizing or cleaning up code within the project, and do not invoke it merely because one implementation, library, or tool is being swapped for another with equivalent behavior (e.g., porting a script from one language/tool to another).
- For commits/branches/PRs and WSL↔Windows sync work, invoke the `git-workflow` skill.


## Project References

- Project Report: 'guidelines/PROJECT_REPORT.md'
- History: 'guidelines/HISTORY.md'
- Issues & Backlog: 'guidelines/ISSUES.md'
- Documentation Guide: 'guidelines/DOCUMENTATION_GUIDE.md'


## Etc

- When receiving a request or question via a prompt in this project, responses must be written in Korean.
