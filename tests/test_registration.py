"""Unit tests for :mod:`mca_mcp.common.registration`.

Exercises the ``~/.claude.json`` read/write logic against a temporary config
file so the real user config is never touched.  Covers global + project scope
registration, idempotent updates, scope isolation, unregister, and the
malformed-config guard.

Run with::

    python -m pytest tests/test_registration.py -v
"""

# --- Imports ---------------------------------------------------------------
# stdlib
import json
import os
import sys

# third-party
import pytest

# Ensure the package root is importable when pytest is launched from anywhere.
_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

# local
from mca_mcp.common import registration


# --- Tests -----------------------------------------------------------------

def test_register_global_scope(tmp_path):
    """A global registration lands in the top-level mcpServers map."""
    cfg = str(tmp_path / "claude.json")
    registration.register_server(
        "MCAMayaMCP", command="C:/venv/python.exe",
        args=["C:/pkg/mca_mcp/maya/server.py"], scope="global", config_path=cfg,
    )

    data = json.loads(open(cfg, encoding="utf-8").read())
    entry = data["mcpServers"]["MCAMayaMCP"]
    assert entry["command"] == "C:/venv/python.exe"
    assert entry["args"] == ["C:/pkg/mca_mcp/maya/server.py"]


def test_register_normalizes_backslashes(tmp_path):
    """Windows backslash paths are stored with forward slashes."""
    cfg = str(tmp_path / "claude.json")
    registration.register_server(
        "MCAUnrealMCP", command=r"C:\venv\python.exe",
        args=[r"C:\pkg\mca_mcp\unreal\server.py"], scope="global", config_path=cfg,
    )
    entry = registration.read_config(cfg)["mcpServers"]["MCAUnrealMCP"]
    assert "\\" not in entry["command"]
    assert "\\" not in entry["args"][0]


def test_register_project_scope(tmp_path):
    """A project registration lands under projects[<dir>].mcpServers."""
    cfg = str(tmp_path / "claude.json")
    project = str(tmp_path / "myproj")
    registration.register_server(
        "MCABlenderMCP", command="py", args=["s.py"],
        scope="project", project_dir=project, config_path=cfg,
    )

    key = os.path.abspath(project).replace("\\", "/")
    data = registration.read_config(cfg)
    assert "MCABlenderMCP" in data["projects"][key]["mcpServers"]
    # It must NOT leak into global scope.
    assert "MCABlenderMCP" not in data.get("mcpServers", {})


def test_is_registered_scope_isolation(tmp_path):
    """is_registered distinguishes global from project scope."""
    cfg = str(tmp_path / "claude.json")
    project = str(tmp_path / "proj")
    registration.register_server(
        "MCAMayaMCP", command="py", args=["s.py"],
        scope="project", project_dir=project, config_path=cfg,
    )
    assert registration.is_registered("MCAMayaMCP", scope="project",
                                      project_dir=project, config_path=cfg)
    assert not registration.is_registered("MCAMayaMCP", scope="global", config_path=cfg)


def test_register_preserves_existing_entries(tmp_path):
    """Registering one server does not clobber unrelated config content."""
    cfg = str(tmp_path / "claude.json")
    # Seed with an unrelated server + arbitrary top-level key.
    seed = {"mcpServers": {"SomeOtherMCP": {"command": "x", "args": []}},
            "numStartups": 42}
    with open(cfg, "w", encoding="utf-8") as handle:
        json.dump(seed, handle)

    registration.register_server(
        "MCAMayaMCP", command="py", args=["s.py"], scope="global", config_path=cfg,
    )
    data = registration.read_config(cfg)
    assert "SomeOtherMCP" in data["mcpServers"]      # untouched
    assert "MCAMayaMCP" in data["mcpServers"]         # added
    assert data["numStartups"] == 42                  # unrelated key preserved


def test_register_is_idempotent_update(tmp_path):
    """Re-registering the same name updates in place, no duplicate."""
    cfg = str(tmp_path / "claude.json")
    registration.register_server("MCAMayaMCP", command="old", args=["a.py"],
                                 scope="global", config_path=cfg)
    registration.register_server("MCAMayaMCP", command="new", args=["b.py"],
                                 scope="global", config_path=cfg)
    servers = registration.read_config(cfg)["mcpServers"]
    assert servers["MCAMayaMCP"]["command"] == "new"


def test_unregister_removes_entry(tmp_path):
    """unregister removes the entry and reports whether it existed."""
    cfg = str(tmp_path / "claude.json")
    registration.register_server("MCAMayaMCP", command="py", args=["s.py"],
                                 scope="global", config_path=cfg)
    assert registration.unregister_server("MCAMayaMCP", scope="global", config_path=cfg)
    assert not registration.is_registered("MCAMayaMCP", scope="global", config_path=cfg)
    # Second removal is a no-op returning False.
    assert not registration.unregister_server("MCAMayaMCP", scope="global", config_path=cfg)


def test_missing_config_is_empty(tmp_path):
    """Reading a nonexistent config yields an empty dict, not an error."""
    cfg = str(tmp_path / "does_not_exist.json")
    assert registration.read_config(cfg) == {}
    assert not registration.is_registered("MCAMayaMCP", config_path=cfg)


def test_malformed_config_raises(tmp_path):
    """A corrupt config raises rather than being silently overwritten."""
    cfg = str(tmp_path / "claude.json")
    with open(cfg, "w", encoding="utf-8") as handle:
        handle.write("{ this is not valid json ")
    with pytest.raises(ValueError):
        registration.read_config(cfg)


def test_project_scope_requires_dir(tmp_path):
    """Project scope without a project_dir is a clear error."""
    cfg = str(tmp_path / "claude.json")
    with pytest.raises(ValueError):
        registration.register_server("MCAMayaMCP", command="py", args=["s.py"],
                                     scope="project", project_dir=None, config_path=cfg)
