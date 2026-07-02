"""
Single source of truth for the DCC MCP servers this package ships.

Both the standalone installer (``install/cli.py``) and any external consumer
(e.g. the MCA Editor's thin shim) resolve server metadata and on-disk paths
through here, so the Claude Code registration names and server-module locations
are defined in exactly one place.

Keeping this under ``mca_mcp`` (rather than the top-level ``install`` package)
means an embedding application only needs to ``import mca_mcp`` — it never has
to depend on the installer CLI package.

Dependencies:
    - stdlib only (``importlib.util``, ``os``).
"""

import importlib.util
import os


# Registration names Claude Code displays, plus the import path of each server
# module.  Names are kept identical to the historical MCA Editor names so
# existing docs / muscle memory still apply.
SERVERS = {
    "maya": {
        "server_name": "MCAMayaMCP",
        "module": "mca_mcp.maya.server",
    },
    "unreal": {
        "server_name": "MCAUnrealMCP",
        "module": "mca_mcp.unreal.server",
    },
    "blender": {
        "server_name": "MCABlenderMCP",
        "module": "mca_mcp.blender.server",
    },
}


def dcc_keys():
    """
    Return the list of supported DCC keys in a stable order.

    :return: ``["maya", "unreal", "blender"]``.
    :rtype: list
    """
    return list(SERVERS.keys())


def server_name(dcc):
    """
    Return the Claude Code registration name for a DCC.

    :param str dcc: The DCC key (``maya`` / ``unreal`` / ``blender``).
    :return: The registration name (e.g. ``MCAMayaMCP``).
    :rtype: str
    :raises KeyError: If the DCC key is unknown.
    """
    return SERVERS[dcc]["server_name"]


def server_script_path(dcc):
    """
    Resolve the absolute path to a DCC server's ``server.py`` file.

    Uses the import system so the path is correct whether this package is a git
    checkout or an installed wheel.

    :param str dcc: The DCC key (``maya`` / ``unreal`` / ``blender``).
    :return: Absolute path to the server module file.
    :rtype: str
    :raises KeyError: If the DCC key is unknown.
    :raises RuntimeError: If the module cannot be located on disk.
    """
    module_name = SERVERS[dcc]["module"]
    spec = importlib.util.find_spec(module_name)
    if spec is None or not spec.origin:
        raise RuntimeError("Could not locate server module %s" % module_name)
    return os.path.abspath(spec.origin)
