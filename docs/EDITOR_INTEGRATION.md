# Phase 5 — Point the MCA Editor back at `mca-mcp`

This is the ready-to-apply plan for shrinking the MCA Editor's
`mca_core/mcp_setup.py` (1217 lines) to a thin shim that delegates Maya + Unreal
to this package, while keeping the **editor-coupled `MCAEditorMCP` server local**
(it does not move — it talks to the editor's JSON-RPC API).

Nothing here has been applied to the editor yet. The one thing that gates it is
**how the editor's Python imports `mca_mcp`** (§1). Everything else (§2–§4) is
ready.

> **Verified 2026-07-02 against a LIVE Maya session:** the package's Maya server,
> launched under the shared venv (`~/.mca-mcp/venv`), completed a full MCP
> handshake AND executed a real tool (`list_objects_by_type cameras`) against a
> running Maya — returning the identical result as the current deployment. The
> extracted server is production-equivalent, not just protocol-valid. (Unreal +
> Blender were proven at the protocol level; no live UE/Blender was open.)
>
> **Apply on a CLEAN working tree.** As of this writing MCAEditor `main` has
> ~29 files of unrelated uncommitted WIP. Commit/stash that first, then apply
> this on its own branch so the shim is reviewable in isolation. `mcp_setup.py`
> and `venv_manager.py` were both clean (untouched by that WIP).

---

## 1. Decision: how the editor depends on the package

The editor's Python (the managed venv in `mca_core/venv_manager.py`) must be able
to `import mca_mcp`. **Verified mechanism:** `venv_manager` pip-installs every
`REQUIRED_PACKAGES` entry into the managed venv (`.venv-3.X`) and injects that
venv's `site-packages` onto Maya's `sys.path` at startup — so a new entry there
becomes importable inside the editor with no other change. The map is
`pip-spec → import-name`; add `mca_mcp` as the import-name. Pick the pip-spec:

| Option | `REQUIRED_PACKAGES` entry | Trade-off |
|---|---|---|
| **A. Local path (recommended for this machine)** | `"E:/Projects/MCAMCP": "mca_mcp"` | Works today, no network/auth. `MCAMCP` is a **private** repo, so a git URL needs credentials at install time; the source is already local. Couples the editor to that checkout path (documented). |
| **B. Git SSH URL** | `"mca-mcp @ git+ssh://git@github.com/ncomes/MCAMCP.git": "mca_mcp"` | No path coupling, any machine. Needs the SSH key available to the venv's pip at install (private repo). Best once the checkout isn't guaranteed local. |
| **C. Submodule** | add `third_party/MCAMCP` to `sys.path` | Versioned lockstep, offline. Adds submodule discipline. |

> **Note:** the MCP servers run in their OWN venv (the shared `~/.mca-mcp/venv`,
> resolved by `mca_mcp.common.venv.default_venv_dir()` — the same venv the CLI and
> the Bot Town registration use). This §1 decision is only about the *editor
> process* importing the package to call the shim helpers. The two venvs are
> separate.

---

## 2. What the package already gives the shim

No new package code is required. The shim composes these:

```python
from mca_mcp import servers                     # DCC registry + server_script_path()
from mca_mcp.common import venv as mcp_venv      # ensure_venv()
from mca_mcp.common import registration          # register_server() / is_registered()
```

- `servers.server_script_path("maya")` → absolute path to the vendored
  `mca_mcp/maya/server.py` (Maya tools are vendored beside it).
- `servers.server_name("unreal")` → `"MCAUnrealMCP"`.
- `mcp_venv.ensure_venv(venv_dir)` → idempotently builds a venv with `mcp`,
  returns its Python path.
- `registration.register_server(name, command, args, scope, project_dir)` →
  writes `~/.claude.json` (global or project scope).

---

## 3. The shim (`mca_core/mcp_setup.py`)

Keep the module's public surface **identical** — the 5 call sites (editor_panel
+ 4 adapters) stay unchanged. Only the bodies change.

```python
"""MCA Core — MCP setup shim.

Maya + Unreal MCP servers now live in the standalone ``mca-mcp`` package.
This module delegates their venv + registration to that package and keeps the
editor-coupled ``MCAEditorMCP`` server local (it is not shareable).
"""

import logging
import os
import threading

logger = logging.getLogger(__name__)

# The editor MCP server STAYS here (coupled to the editor JSON-RPC API). It is
# standalone (zero mca_core imports) so it runs from its source path — no copy.
_EDITOR_MCP_SERVER_NAME = "MCAEditorMCP"
_EDITOR_SERVER_SOURCE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "mcp_editor_server.py"
)

# Register at project scope for the editor repo, matching current behavior.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _register_all(dccs, include_editor, status_callback=None):
    """Build the shared venv and register the requested servers.

    ``mca_mcp`` is imported LAZILY here (not at module scope) so that if the
    package isn't installed yet — first launch, a failed venv install — importing
    this module still succeeds and the editor is never blocked. Matches the old
    module's "failures are logged, never block the editor" contract.
    """
    def _status(msg):
        logger.info(msg)
        if status_callback:
            try:
                status_callback(msg)
            except Exception:
                pass

    try:
        from mca_mcp import servers
        from mca_mcp.common import venv as mcp_venv
        from mca_mcp.common import registration
    except ImportError as exc:
        logger.warning("mca-mcp not importable yet (%s) — skipping MCP setup", exc)
        _status("MCP setup: mca-mcp package not available yet")
        return

    try:
        _status("Setting up MCP server venv...")
        # Shared venv — same one the CLI + Bot Town registration use.
        python = mcp_venv.ensure_venv(mcp_venv.default_venv_dir())

        # Maya / Unreal come from the package.
        for dcc in dccs:
            name = servers.server_name(dcc)
            script = servers.server_script_path(dcc)
            registration.register_server(
                name, command=python, args=[script],
                scope="project", project_dir=_REPO_ROOT,
            )
            _status("Registered %s" % name)

        # The editor server stays local — register it against the same venv.
        if include_editor:
            registration.register_server(
                _EDITOR_MCP_SERVER_NAME, command=python,
                args=[_EDITOR_SERVER_SOURCE_PATH],
                scope="project", project_dir=_REPO_ROOT,
            )
            _status("Registered %s" % _EDITOR_MCP_SERVER_NAME)

        _status("Setup complete!")
    except Exception as exc:
        logger.warning("MCP setup failed: %s", exc, exc_info=True)
        _status("MCP setup: error (check logs)")


def ensure_maya_mcp(background=True, status_callback=None):
    """Register the Maya (package) + Editor (local) MCP servers."""
    args = (["maya"], True, status_callback)
    if background:
        threading.Thread(target=_register_all, args=args,
                         name="MCP-Setup", daemon=True).start()
    else:
        _register_all(*args)


def ensure_unreal_mcp(background=True, status_callback=None):
    """Register the Unreal (package) MCP server."""
    args = (["unreal"], False, status_callback)
    if background:
        threading.Thread(target=_register_all, args=args,
                         name="MCP-Unreal-Setup", daemon=True).start()
    else:
        _register_all(*args)


def get_mcp_server_status():
    """Report install/registration state in the shape adapters expect.

    Lazy-imports mca_mcp; if the package isn't available it returns a safe
    "not installed" stub (the adapters already tolerate this in try/except).
    """
    try:
        from mca_mcp import servers
        from mca_mcp.common import venv as mcp_venv
        from mca_mcp.common import registration
    except ImportError:
        return {"name": "MCAMayaMCP", "installed": False, "registered": False,
                "server_path": None, "venv_path": None, "clone_path": None,
                "editor": {"name": _EDITOR_MCP_SERVER_NAME, "installed": False,
                           "registered": False, "server_path": _EDITOR_SERVER_SOURCE_PATH},
                "unreal": {"name": "MCAUnrealMCP", "installed": False,
                           "registered": False, "server_path": None}}

    venv_dir = mcp_venv.default_venv_dir()
    venv_ready = mcp_venv.venv_ready(venv_dir)

    def _server_block(dcc, description):
        name = servers.server_name(dcc)
        try:
            script = servers.server_script_path(dcc)
        except Exception:
            script = None
        return {
            "name": name,
            "description": description,
            "installed": bool(script) and venv_ready,
            "registered": registration.is_registered(
                name, scope="project", project_dir=_REPO_ROOT),
            "server_path": script,
        }

    maya = _server_block("maya", "MCP server for Maya scene manipulation")
    editor_registered = registration.is_registered(
        _EDITOR_MCP_SERVER_NAME, scope="project", project_dir=_REPO_ROOT)

    # Preserve the historical top-level = Maya shape + editor/unreal sub-dicts.
    result = dict(maya)
    result["venv_path"] = venv_dir if os.path.isdir(venv_dir) else None
    result["clone_path"] = None  # MayaMCP clone retired (tools vendored)
    result["editor"] = {
        "name": _EDITOR_MCP_SERVER_NAME,
        "description": "MCP server for editor control via Claude Code",
        "installed": os.path.isfile(_EDITOR_SERVER_SOURCE_PATH) and venv_ready,
        "registered": editor_registered,
        "server_path": _EDITOR_SERVER_SOURCE_PATH,
    }
    result["unreal"] = _server_block("unreal", "MCP server for Unreal Engine")
    return result
```

### Behavior preserved
- Same 3 public functions, same signatures → the 5 call sites are untouched:
  `mca_qt/editor_panel.py:4020` and `get_mcp_server_status()` in the 4 adapters.
- Same background-thread semantics.
- Same `get_mcp_server_status()` dict shape (top-level Maya + `editor` + `unreal`
  sub-dicts).
- Registration still project-scoped for the editor repo.

### What changes / retires
- **No more MayaMCP git clone** — tools are vendored in the package. The old
  `_MAYAMCP_DIR` / `_clone_maya_mcp` / `_apply_patches` disappear.
- **No more server-script copying** — servers run from their package location.
- The old deploy dir `mca_preferences/mcp_servers/mca_*_server.py` files become
  stale; a one-time cleanup can delete them (optional — they're just unused).

---

## 4. Rollout checklist

0. **Start from a clean MCAEditor working tree** — commit/stash unrelated WIP,
   then do all of the below on a dedicated branch so it's reviewable in isolation.
1. Add the dependency (§1) to `venv_manager.REQUIRED_PACKAGES` — recommended:
   `"E:/Projects/MCAMCP": "mca_mcp"` (private repo → local path avoids install-time
   auth).
2. Replace `mca_core/mcp_setup.py` with the shim (§3). The 152-line shim compiles
   clean and preserves all 3 public signatures; `mcp_editor_server.py` stays.
3. Delete the now-unused `mcp_maya_server.py`, `mcp_unreal_server.py`,
   `mcp_blender_server.py`, and `unreal_tools/` from the editor repo (they live in
   the package now). **Keep** `mcp_editor_server.py`.
4. Rebuild all three Maya versions (2024/2025/2026), clear the extraction cache.
   The editor is a built plugin — source edits don't take effect until rebuild +
   Maya restart, which is why steps 4–5 can't be done from a coding session.
5. In a real Maya session: launch, confirm `ensure_maya_mcp` runs, then in Claude
   Code verify `MCAMayaMCP`, `MCAUnrealMCP`, `MCAEditorMCP` all connect and list
   tools. (Needs a human + Maya — can't be unit-tested. Note: the package Maya
   server was already proven driving a live Maya on 2026-07-02, so the risk here
   is the editor *wiring*, not the server.)
6. Optional: delete the stale `mca_preferences/mcp_servers/mca_*_server.py` +
   `MayaMCP/` clone.

Until step 5 passes in real Maya, keep the old `mcp_setup.py` recoverable (git
revert) — it is the fallback.
