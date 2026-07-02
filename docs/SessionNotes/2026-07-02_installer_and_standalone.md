# Session Notes — 2026-07-02 — Standalone-usable: Maya vendored + installer CLI

**Repo:** `E:\Projects\MCAMCP`
**Goal for the session:** Verify the extracted MCP still works after last night's
isolation from MCAEditor, then "finish it up" so it's a standalone project any
project can install and use.

---

## TL;DR — where we are now

- **Nothing was broken.** The live/registered MCP servers (`MCAMayaMCP`,
  `MCAUnrealMCP`, `MCAEditorMCP` in `~/.claude.json`) still point at the untouched
  MCAEditor deployment under `~/Documents/mca_preferences/MCAEditor/mcp_servers/`.
  The extraction in `E:\Projects\MCAMCP` is a clean parallel copy — it did not
  touch or re-register anything the editor uses.
- **Phases 2, 3, 4 are now DONE.** The package is standalone-usable from a plain
  `git clone`. 19 unit tests green.
- **Still not pushed to GitHub** — same blocker as yesterday (`gh` not
  authenticated in this environment). See "Publish" below.

## What got done this session

### Phase 2 — Maya `mayatools/` vendored ✅
- Decision §4.2 resolved as **(A) vendor** (matches the plan's recommendation and
  what `pyproject.toml` package-data already assumed).
- Copied the 17 patched tool `.py` files from the deployed
  `MayaMCP/src/mayatools/` into `mca_mcp/maya/mayatools/` (subdirs `material/`,
  `object/`, `scene/` + the `thirdparty/` placeholder), stripping `__pycache__`.
- Vendored MayaMCP's MIT `LICENSE` as `mca_mcp/maya/mayatools/MAYAMCP_LICENSE`.
- Updated `mca_mcp/maya/server.py` `__main__`: `default_tool_dir` now **prefers
  the vendored `mayatools/`** beside the server, falling back to the legacy
  `MayaMCP/src/mayatools` path so the same file still works in the old editor
  deployment. Verified: Maya discovers **17 tools** from the vendored dir.

### Phase 3 — Blender ✅
- Blender's tools are inline (`@server.list_tools()` in `_create_server`), so it
  was already self-contained. Verified it lists **14 tools** standalone.

### Phase 4 — Standalone installer CLI ✅ (the bulk)
Ported the venv + `~/.claude.json` registration logic out of MCAEditor's
`mca_core/mcp_setup.py` (1217 lines) into two small, editor-decoupled modules,
plus a CLI:

- `mca_mcp/common/venv.py` — `find_system_python` (3.10+ probe, no mayapy/editor
  coupling), `create_venv`, `pip_install`, `ensure_venv` (idempotent). Builds one
  shared venv with the `mcp` runtime.
- `mca_mcp/common/registration.py` — pure, unit-testable `~/.claude.json`
  read/write. Supports **global** and **project** scope; forward-slash
  normalization; never clobbers unrelated config; malformed config raises instead
  of overwriting.
- `install/cli.py` — `mca-mcp install maya|unreal|blender|all`, `status`,
  `uninstall`, with `--scope global|project`, `--project-dir`, `--venv`. Resolves
  each server's `server.py` via `importlib` (works from source OR pip install).

**Key insight that makes `git clone` "just work":** each server's `sys.path` shim
computes `_PKG_ROOT` from its own file location and imports `mca_mcp.common` from
there. So the installer only needs a venv with `mcp` + the registered path to
`server.py`; no PyPI publish, no `pip install` of this package required.

## How it was verified (do this again if you touch these paths)

```bash
cd E:/Projects/MCAMCP
DVPY=.venv/Scripts/python.exe

# 1. Unit tests (6 discovery + 10 registration + 3 servers)
$DVPY -m pytest tests/ -q            # -> 19 passed

# 2. Read-only status against the real ~/.claude.json
$DVPY -m install.cli status

# 3. ACCEPTANCE: build a venv with ONLY mcp, boot each server under it,
#    confirm discovery works through the sys.path shim.
#    (Done this session in scratchpad: unreal=89, maya=17 tools.)
```

The venv builder was proven end-to-end (found `C:\Python310\python.exe`, created
the venv, `pip install mcp`, `import mcp` OK), and both discovery servers booted
under that venv and found their full tool sets.

## Files added/changed this session

- NEW `mca_mcp/common/venv.py`
- NEW `mca_mcp/common/registration.py`
- NEW `install/cli.py`  (was just a placeholder `install/__init__.py` before)
- NEW `tests/test_registration.py` (10 tests), `tests/test_servers.py` (3 tests)
- NEW `mca_mcp/maya/mayatools/**` (17 tools + MAYAMCP_LICENSE)
- EDIT `mca_mcp/maya/server.py` (prefer vendored tool dir)
- EDIT `README.md` (real install quickstart, status), `docs/migration_plan.md`
  (status banner)

## Publish (still the blocker)

`gh` is not authenticated in the Claude Code environment, and creating a *new*
GitHub repo needs the API. Unblock either way:

- **Option A:** `! gh auth login`, then
  `gh repo create ncomes/MCAMCP --private --source=E:/Projects/MCAMCP --push`.
- **Option B:** create an empty `ncomes/MCAMCP` on github.com, then
  `git push -u origin main` (remote `origin` is already set to the SSH URL).

Default **private** while WIP; flip public later.

## Next steps (roadmap)

| Phase | Status | Notes |
|---|---|---|
| 0 — Scaffold | ✅ | |
| 1 — Shared `common/discovery` | ✅ | |
| 2 — Maya `mayatools/` vendoring | ✅ | this session |
| 3 — Blender standalone | ✅ | this session (was already inline) |
| 4 — Installer CLI | ✅ | this session |
| 5 — MCA Editor shim back to package | pending | shrink `mcp_setup.py` to re-export `ensure_maya_mcp`/`ensure_unreal_mcp`/`get_mcp_server_status`; point deploy dir at `mca_preferences`; rebuild Maya 2024/25/26 |
| 6 — Unreal C++ bridge → GitHub Releases | pending | `MCAEditorScripting` per-UE zips |
| 7 — Docs + PyPI publish | pending | tag v0.1.0 |

### Not addressed (intentionally)
- `common/transport.py` / `common/schema.py` were in the original plan but the
  transport/quoting logic still lives inline in each server and works; leave it
  until there's a reason to de-dupe. Discovery was the only real duplication.
- The MCAEditor originals (`mcp_maya_server.py`, etc.) are untouched and still
  deployed — removal happens in Phase 5, not before the editor shim exists.
