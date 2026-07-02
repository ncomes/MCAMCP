"""MCA MCP — Model Context Protocol servers for DCC applications.

Provides standalone MCP servers that let AI assistants (Claude Code and other
MCP clients) drive Maya, Unreal Engine, and Blender.  Each DCC server is
self-contained and runs in its own process against the ``mcp`` package.

Subpackages
-----------
- ``mca_mcp.common``  — shared tool discovery, transport, schema, and Claude
  Code registration helpers used by the DCC servers.
- ``mca_mcp.maya``    — Maya MCP server (builds on MayaMCP's tool set).
- ``mca_mcp.unreal``  — Unreal Engine MCP server (in-repo ``unreal_tools/``).
- ``mca_mcp.blender`` — Blender MCP server (tools defined inline).

Side effects
------------
Importing this package has no side effects.  Deployment and Claude Code
registration are performed explicitly through :mod:`install.cli`.
"""

# Single source of truth for the package version.  Consumers (pyproject,
# installer, servers) import from here.
__version__ = "0.1.0"
