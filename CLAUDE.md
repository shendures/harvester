# CLAUDE.md

## Required Skill Invocations

- The instant any prompt request is given in this project, you MUST invoke the
  `andrej-karpathy-skills:karpathy-guidelines` skill via the `Skill` tool first — before
  any other tool call, investigation, or response. This applies to every request, not
  just ones that touch code.
- Invoke the `coding-guide` skill whenever you write, modify, refactor, or review code, or check the state/correctness of existing code — but not for requests that merely discuss or plan the project at large without reading or touching code.
- If the task also involves PyQt (widgets, layouts, signals/slots, threading in a GUI, stylesheets, etc.), additionally invoke the `pyqt-uiux` skill on top of `coding-guide`.
- If the task involves refactoring existing code, additionally invoke the `refactoring` skill on top of `coding-guide`.
- For commits/branches/PRs and WSL↔Windows sync work, invoke the `git-workflow` skill.


## Project References

- Project Report: 'guidelines/PROJECT_REPORT.md'
- History: 'guidelines/HISTORY.md'
- Issues & Backlog: 'guidelines/ISSUES.md'
- Documentation Guide: 'guidelines/DOCUMENTATION_GUIDE.md'


## Etc

- When receiving a request or question via a prompt in this project, responses must be written in Korean.
