"""Standalone-readiness tests for the three DCC servers.

Guards that each server ships everything it needs to run without the MCA
Editor:

    - Maya discovers its VENDORED ``mayatools/`` (Phase 2 extraction).
    - Blender lists its inline tool set.
    - The installer registry resolves every server's ``server.py`` on disk.

Run with::

    python -m pytest tests/test_servers.py -v

Requires the ``mcp`` package on the path.
"""

# --- Imports ---------------------------------------------------------------
# stdlib
import asyncio
import os
import sys

# Ensure the package root is importable when pytest is launched from anywhere.
_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)


# --- Maya --------------------------------------------------------------------

def test_maya_discovers_vendored_tools():
    """The Maya server finds its vendored mayatools tree (no MayaMCP clone)."""
    from mca_mcp.maya.server import OperationsManager, SKIP_TOOLS

    tools_dir = os.path.join(_PKG_ROOT, "mca_mcp", "maya", "mayatools")
    assert os.path.isdir(tools_dir), "vendored mayatools/ must ship in the package"

    mgr = OperationsManager()
    mgr.find_tools([tools_dir], skip_tools=SKIP_TOOLS)
    tools = mgr.get_tools()
    # The vendored MayaMCP set is ~17 tools; assert a healthy lower bound.
    assert len(tools) >= 15, "expected the vendored Maya tools, got {}".format(len(tools))
    # A representative tool from each category should be present.
    names = {t.name for t in tools}
    for expected in ("create_object", "create_material", "scene_new"):
        assert expected in names, "missing vendored Maya tool '{}'".format(expected)


# --- Blender -----------------------------------------------------------------

def test_blender_lists_inline_tools():
    """The Blender server lists its inline (self-contained) tool set."""
    from mca_mcp.blender import server as blender_server
    from mcp.types import ListToolsRequest

    srv = blender_server._create_server(9999)

    async def _list():
        result = await srv.request_handlers[ListToolsRequest](
            ListToolsRequest(method="tools/list")
        )
        return result.root.tools

    tools = asyncio.run(_list())
    assert len(tools) >= 10, "expected the inline Blender tools, got {}".format(len(tools))
    names = {t.name for t in tools}
    assert "blender_execute_python" in names


# --- Installer registry ------------------------------------------------------

def test_installer_resolves_all_server_scripts():
    """The installer can locate every DCC server.py on disk."""
    from install.cli import _DCC_REGISTRY, _server_script_path

    for dcc in _DCC_REGISTRY:
        path = _server_script_path(dcc)
        assert os.path.isfile(path), "server script for {} not found: {}".format(dcc, path)


def test_shared_registry_is_single_source():
    """install.cli resolves through mca_mcp.servers (one source of truth)."""
    from mca_mcp import servers
    import install.cli as cli

    # The CLI's registry IS the package registry object, not a copy.
    assert cli._DCC_REGISTRY is servers.SERVERS

    # Every DCC resolves a real server file, and names are stable/expected.
    expected = {"maya": "MCAMayaMCP", "unreal": "MCAUnrealMCP", "blender": "MCABlenderMCP"}
    for dcc in servers.dcc_keys():
        assert servers.server_name(dcc) == expected[dcc]
        assert os.path.isfile(servers.server_script_path(dcc))
