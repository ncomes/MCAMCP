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

## Phase 5 prep (same session, package-side only)

Did the **safe, decision-independent** half of Phase 5 without touching the live
editor:

- NEW `mca_mcp/servers.py` — single source of truth for the DCC registry
  (registration names + server module paths) + `server_script_path()`. Lives
  under `mca_mcp` so an embedding app (the editor) only needs `import mca_mcp`,
  never the top-level `install` package. `install/cli.py` now aliases this
  (`_DCC_REGISTRY = servers.SERVERS`) — one source, verified by a test.
- NEW `docs/EDITOR_INTEGRATION.md` — the **exact ready-to-apply shim** for
  `mca_core/mcp_setup.py`: delegates Maya + Unreal to the package, keeps the
  editor-coupled `MCAEditorMCP` server local, preserves all 3 public signatures
  so the 5 call sites (editor_panel:4020 + 4 adapters) stay unchanged.

**Why the live editor was NOT modified:** MCAEditor (`E:\Projects\MCAEditor`, a
git repo, files writable — no P4 lock) is a working production orchestrator whose
final step can only be validated in a real Maya session (rebuild 3 Maya versions,
confirm servers connect). Two things gate applying it:
  1. **One decision** — how the editor's Python imports the *unpublished* package
     (git URL after push = recommended / local editable now / submodule). Asked
     Nathan; no answer yet, so I did not guess and rewire a live file.
  2. **The GitHub push** — the clean dependency (git URL) needs the repo pushed
     first (still blocked on `gh auth`).

When Nathan picks the dependency mechanism, applying the shim is a ~15-min flip
using §3–§4 of `docs/EDITOR_INTEGRATION.md`.

## Published to GitHub + Bot Town cutover (later same session)

- **Pushed** to https://github.com/ncomes/MCAMCP. Nathan pre-created the repo with
  an MIT `LICENSE` stub ("Initial commit"). Rebased the 5 local commits onto it
  (resolved the add/add LICENSE conflict in favor of the local one — it carries
  Nathan's name + the required MayaMCP attribution). Linear history, root commit
  preserved.
- **Real MCP handshake proof** (not just import): launched each `server.py` under
  the installer venv (`~/.mca-mcp/venv`) via an `mcp` stdio client and ran
  `initialize` + `list_tools`. Results: **unreal 91, maya 17, blender 14**.
- **Fixed a real pre-existing bug** the handshake exposed: the Blender server's
  `main()` referenced `mcp.server.stdio` / `InitializationOptions` /
  `NotificationOptions` that were only imported inside `_create_server`, so it
  crashed at startup with `NameError` and never spoke MCP. Import-only tests
  missed it. Fixed by importing them at module scope (as Maya/Unreal do). Added a
  parametrized `test_server_speaks_mcp_over_stdio[maya|unreal|blender]` regression
  test that does the full handshake — 23 tests green.
- Stopped tracking the `*.log` files the servers write next to `server.py`
  (gitignored).

### Live registration state after this session (`~/.claude.json`, backed up first)

| Scope | Servers | Points at |
|---|---|---|
| **global** | MCAMayaMCP, MCAUnrealMCP, MCAEditorMCP | editor deployment (UNCHANGED) |
| **project E:/Projects/MCAEditor** | same three | editor deployment (UNCHANGED) |
| **project E:/Projects/OrangeSlice** | MCAUnrealMCP, MCAMayaMCP | **the package** (`E:/Projects/MCAMCP`) via `~/.mca-mcp/venv` |

So **Bot Town now dogfoods the package** (project scope overrides global for
OrangeSlice), while the editor + every other project stay on the deployment —
isolated and reversible. Takes effect on the next Claude Code restart. Backup:
`~/.claude.json.bak-<epoch>`. Revert = delete the two OrangeSlice project entries.
NOT verified against a live Unreal editor (none was running) — the server code is
byte-identical to the deployment Bot Town already used, and the MCP handshake
passed.

### MCA Editor — still on its own deployment (Phase 5 not applied)

The editor is unchanged and working. Cutting it over to the package is Phase 5
(`docs/EDITOR_INTEGRATION.md`), now unblocked by the push.

**Proven against LIVE Maya (2026-07-02):** with Maya running, the package's Maya
server (under `~/.mca-mcp/venv`) completed an MCP handshake AND executed a real
tool (`list_objects_by_type cameras`) against it, returning the same result as
the deployment. So the extracted server is production-equivalent — the only
unproven part of Phase 5 is the editor *wiring*, not the server.

**Why the shim was NOT applied this session:** MCAEditor `main` had ~29 files of
unrelated uncommitted WIP (17 new / 11 modified / 1 deleted — possibly a
concurrent session). `mcp_setup.py` + `venv_manager.py` themselves were clean, but
I will not branch/commit Phase 5 into a dirty tree and risk entangling that work.
Also, the editor is a built Maya plugin — applying the shim can't be validated
without a rebuild + Maya restart (Nathan's step) regardless.

**Ready-to-apply state:** the full 152-line shim in `EDITOR_INTEGRATION.md`
compiles clean, uses lazy `mca_mcp` imports (a missing package never blocks the
editor), shares the one `~/.mca-mcp/venv` via `default_venv_dir()`, keeps the
`MCAEditorMCP` server running from its local source, and preserves all 3 public
signatures. Recommended dependency for this machine (private repo): local path
`"E:/Projects/MCAMCP": "mca_mcp"` in `venv_manager.REQUIRED_PACKAGES`. Apply on a
clean tree, on a branch — see the §4 checklist.

### Not addressed (intentionally)
- `common/transport.py` / `common/schema.py` were in the original plan but the
  transport/quoting logic still lives inline in each server and works; leave it
  until there's a reason to de-dupe. Discovery was the only real duplication.
- The MCAEditor originals (`mcp_maya_server.py`, etc.) are untouched and still
  deployed — removal happens in Phase 5, not before the editor shim exists.
