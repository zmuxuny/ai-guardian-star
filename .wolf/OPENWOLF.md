# OpenWolf Slim Protocol

OpenWolf is an on-demand project index and durable-notes layer. Keep it quiet during normal work.

## Context

- Use `.wolf/anatomy.md` for unfamiliar areas, repository-wide work, or locating likely files.
- Use targeted search when the file or symbol is already known.
- Read `.wolf/cerebrum.md` only when prior project decisions or conventions may affect the task.
- Do not read or update OpenWolf files for simple questions or unrelated tooling work.

## Anatomy

- Treat anatomy descriptions as routing hints, not source-of-truth code.
- Run `openwolf scan` after structural changes such as creating, deleting, renaming, or moving several files.
- Do not rescan after ordinary edits.
- Generated dependencies, build outputs, caches, and preview artifacts must stay excluded.

## Durable Notes

Update `.wolf/cerebrum.md` only for durable, non-obvious project knowledge:

- a user correction or stable workflow preference;
- a project convention not evident from the code;
- a verified dependency or platform constraint;
- a significant technical decision and its reason.

Do not record routine actions, temporary diagnostics, generic tooling behavior, or facts already captured by claude-mem.

## Bug Log

Use `.wolf/buglog.json` only for confirmed product defects or recurring project-specific failures after the root cause is known. Do not log shell quoting errors, unavailable local tools, failed exploratory commands, or transient test failures.

## Session Notes

Add one concise entry to `.wolf/memory.md` only after substantial code, configuration, architecture, or design work, or when the user asks to wrap up. Read-only investigation and simple conversations require no OpenWolf write.

## Design QC

For explicit UI or design review, run `openwolf designqc`, inspect the captured pages, apply approved changes, then rerun it for verification. Keep captures limited to relevant routes and viewports.

## Reframe

Read `.wolf/reframe-frameworks.md` only when the user asks to select, change, or migrate the UI framework.
