# Phase 5 — Point the MCA Editor back at `mca-mcp`

This is the ready-to-apply plan for shrinking the MCA Editor's
`mca_core/mcp_setup.py` (1217 lines) to a thin shim that delegates Maya + Unreal
to this package, while keeping the **editor-coupled `MCAEditorMCP` server local**
(it does not move — it talks to the editor's JSON-RPC API).

Nothing here has been applied to the editor yet. The one thing that gates it is
**how the editor's Python imports `mca_mcp`** (§1). Everything else (§2–§4) is
ready.

---

## 1. Decision: how the editor depends on the package

The editor's Python (the managed venv in `mca_core/venv_manager.py`,
`REQUIRED_PACKAGES`) must be able to `import mca_mcp`. Pick one:

| Option | How | Trade-off |
|---|---|---|
| **A. Git URL (recommended)** | After the GitHub push, add `mca-mcp @ git+https://github.com/ncomes/MCAMCP.git` to `REQUIRED_PACKAGES`. | Cleanest, robust, no path coupling, matches "any project can use it". Needs the repo pushed first. |
| **B. Local editable** | `pip install -e E:/Projects/MCAMCP` into the editor venv. | Works today with no publish; reversible. Hard-couples the editor to that checkout path on this machine until swapped to A. |
| **C. Submodule** | `git submodule add …/MCAMCP third_party/MCAMCP` + add its dir to `sys.path`. | Versioned lockstep, offline. Adds submodule discipline to the editor repo. |

> **Note:** the servers themselves run in their OWN venv (built by the installer,
> with just `mcp`). This decision is only about the *editor process* being able to
> import the package to call the shim helpers below. The two venvs are separate.

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

from mca_core import get_prefs_dir
from mca_mcp import servers
from mca_mcp.common import venv as mcp_venv
from mca_mcp.common import registration

logger = logging.getLogger(__name__)

# One shared venv for all three servers, in the editor's prefs dir (unchanged
# location family — no more MayaMCP clone, tools are vendored in the package).
_MCP_DIR = os.path.join(get_prefs_dir(), "mcp_servers")
_VENV_DIR = os.path.join(_MCP_DIR, "venv")

# The editor MCP server STAYS here (coupled to the editor JSON-RPC API).
_EDITOR_MCP_SERVER_NAME = "MCAEditorMCP"
_EDITOR_SERVER_SOURCE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "mcp_editor_server.py"
)

# Register at project scope for the editor repo, matching current behavior.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _register_all(dccs, include_editor, status_callback=None):
    """Build the shared venv and register the requested servers."""
    def _status(msg):
        logger.info(msg)
        if status_callback:
            try:
                status_callback(msg)
            except Exception:
                pass

    try:
        _status("Setting up MCP server venv...")
        python = mcp_venv.ensure_venv(_VENV_DIR)

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
    """Report install/registration state in the shape adapters expect."""
    venv_ready = mcp_venv.venv_ready(_VENV_DIR)

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
    result["venv_path"] = _VENV_DIR if os.path.isdir(_VENV_DIR) else None
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

## 4. Rollout checklist (when the dependency decision is made)

1. Wire the dependency (§1) into `venv_manager.REQUIRED_PACKAGES` (or submodule).
2. Replace `mca_core/mcp_setup.py` with the shim (§3). Keep
   `mcp_editor_server.py` in place.
3. Delete the now-unused `mcp_maya_server.py`, `mcp_unreal_server.py`,
   `mcp_blender_server.py`, and `unreal_tools/` from the editor repo (they live
   in the package now). **Keep** `mcp_editor_server.py`.
4. Rebuild all three Maya versions (2024/2025/2026), clear the extraction cache.
5. In a real Maya session: launch, confirm `ensure_maya_mcp` runs, then in Claude
   Code verify `MCAMayaMCP`, `MCAUnrealMCP`, `MCAEditorMCP` all connect and list
   tools. (This is the step that needs a human + Maya — it can't be unit-tested.)
6. Optional: delete the stale `mca_preferences/mcp_servers/mca_*_server.py` +
   `MayaMCP/` clone.

Until step 5 passes in real Maya, keep the old `mcp_setup.py` recoverable (git
revert) — it is the fallback.
