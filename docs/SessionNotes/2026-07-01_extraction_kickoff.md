# Session Notes — 2026-07-01 — MCAMCP Extraction Kickoff

**Repo:** `E:\Projects\MCAMCP` (new, this session)
**Source repo:** `E:\Projects\MCAEditor`
**Goal:** Extract the DCC MCP servers (Maya, Unreal, Blender) out of MCAEditor
into this standalone, shareable package so any project can use them.

---

## TL;DR — where we are

- Phases **0 (scaffold)** and **1 (shared `common/` + tests)** are DONE and committed.
- Everything is a **copy** — MCAEditor was NOT modified. The editor still works as-is.
- **Not yet pushed to GitHub** — blocked on repo creation (see "Blockers").
- Next up: **Phase 2** — vendor Maya's `mayatools/` (decision §4.2 in the plan).

---

## What exists in this repo

```
MCAMCP/
├── pyproject.toml            # pip-installable, per-DCC extras, `mca-mcp` console script
├── README.md                 # layout + install/run docs
├── LICENSE                   # MIT + MayaMCP attribution
├── .gitignore / .gitattributes  # LF normalization (cross-platform)
├── .venv/                    # dev venv (gitignored) — Python 3.10.8 + mcp + pytest
├── docs/
│   ├── migration_plan.md     # THE PLAN — 7 phases, read this first
│   └── SessionNotes/         # this file
├── install/                  # placeholder for the installer CLI (Phase 4)
├── tests/
│   └── test_discovery.py     # 6 tests, all passing
└── mca_mcp/
    ├── __init__.py           # __version__ = "0.1.0"
    ├── common/
    │   ├── __init__.py
    │   └── discovery.py      # ✅ shared OperationsManager (extracted)
    ├── maya/server.py        # ✅ wired to common; needs mayatools/ (Phase 2)
    ├── unreal/
    │   ├── server.py         # ✅ wired to common; RUNS + discovers 89 tools
    │   └── unreal_tools/     # 89 tool files (pycache stripped)
    └── blender/server.py     # copied, NOT yet wired to common (Phase 3)
```

## Git state

- Commits on branch `main`:
  - `d249b0b` Scaffold mca-mcp: extract DCC MCP servers from MCAEditor
  - `044865b` Phase 1: extract shared tool discovery into common/
- Remote `origin` set to `git@github.com:ncomes/MCAMCP.git` (SSH auth verified),
  **but the GitHub repo does not exist yet** — nothing pushed.

## What Phase 1 actually did

- Confirmed the two `OperationsManager` classes (Maya + Unreal servers) were
  **byte-identical apart from docstrings** (diff verified).
- Moved it to `mca_mcp/common/discovery.py`, DCC-agnostic.
- Change of behavior: `find_tools(tool_dirs, skip_tools=None)` — the skip set is
  now passed by the caller (Maya passes `{"generate_scene", "__init__"}`;
  `__init__` is always skipped internally).
- Both servers: added a `sys.path` shim + `from mca_mcp.common.discovery import
  OperationsManager`, pass `SKIP_TOOLS` explicitly, and removed the now-dead
  discovery-only imports (`inspect`, `get_origin`, `func_metadata`, `Context`,
  `importlib`, `importlib.util`).
- **Verified:** both servers import cleanly, unreal discovers all 89 tools via the
  shared class, `compileall` passes, 6/6 tests green.

## How to run things (dev venv)

```bash
cd E:/Projects/MCAMCP
DVPY=.venv/Scripts/python.exe

# tests
$DVPY -m pytest tests/ -v

# prove unreal discovery end-to-end
$DVPY -c "import os; from mca_mcp.unreal.server import OperationsManager, SKIP_TOOLS; \
m=OperationsManager(); m.find_tools([os.path.abspath('mca_mcp/unreal/unreal_tools')], skip_tools=SKIP_TOOLS); \
print(len(m.get_tools()), 'tools')"
```

- Dev venv was created from the MayaMCP venv's Python 3.10.8:
  `C:\Users\ncomes\Documents\mca_preferences\MCAEditor\mcp_servers\MayaMCP\.venv\Scripts\python.exe`
- `pip install mcp pytest` into `.venv` (network was available).

---

## Blockers (do first tomorrow)

**Publish to GitHub.** `gh` is not authenticated in the Claude Code environment,
and creating a *new* repo needs the API (SSH can only push to an existing repo).
Two ways to unblock:

- **Option A:** run `! gh auth login`, then have Claude run
  `gh repo create ncomes/MCAMCP --private --source=E:/Projects/MCAMCP --push`.
- **Option B:** manually create an empty `ncomes/MCAMCP` on github.com (no
  README/license), then `git push -u origin main`.

Default to **private** (WIP); flip public later with `gh repo edit --visibility public`.

---

## Next steps (roadmap)

| Phase | Status | Notes |
|---|---|---|
| 0 — Scaffold | ✅ | committed `d249b0b` |
| 1 — Shared `common/` + tests | ✅ | committed `044865b` |
| 2 — Maya `mayatools/` vendoring | ⏭ NEXT | decision §4.2 below |
| 3 — Blender server → wire to common | pending | blender server not yet using common |
| 4 — Standalone `install/cli.py` | pending | the bulk; port from MCAEditor `mcp_setup.py` |
| 5 — Editor shim + rebuild all 3 Maya versions | pending | MCAEditor `mcp_setup.py` → thin shim |
| 6 — Unreal C++ bridge → GitHub Releases | pending | `mca_unreal/MCAEditorScripting` per-UE zips |
| 7 — Docs + publish | pending | |

### Decision needed to start Phase 2 (§4.2 in migration_plan.md)
Maya's tools come from cloning PatrickPalmer/MayaMCP today. For a shareable package:
- **(A) Vendor** the patched `mayatools/` into `mca_mcp/maya/mayatools/`
  — recommended (offline, no git needed, patches pre-applied). Add a
  `tools/sync_mayamcp.py` helper for upstream re-sync. Keep MayaMCP MIT attribution.
- **(B) Keep cloning** at install time (needs git + network).

**Recommendation: (A).** Awaiting Nathan's confirmation before proceeding.

### Reference: source files still living in MCAEditor
- `mca_core/mcp_setup.py` (1217 lines) — installer/orchestrator to port in Phase 4.
- `mca_core/mcp_editor_server.py` — STAYS in MCAEditor (editor-coupled, not moving).
- `mca_core/mcp_maya_server.py`, `mcp_unreal_server.py`, `mcp_blender_server.py`
  — the originals we copied from (still present; removal happens in Phase 5).
- Editor trigger/call sites to update in Phase 5: `mca_qt/editor_panel.py:4020`
  and `get_mcp_server_status()` in the 4 adapter files.
- Unreal C++ bridge: `mca_unreal/MCAEditor.uplugin`,
  `mca_unreal/Source/MCAEditorScripting/`.
