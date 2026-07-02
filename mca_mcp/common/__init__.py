"""Shared building blocks for the MCA DCC MCP servers.

This package holds the code that is common across the Maya, Unreal, and Blender
servers so it lives in exactly one place:

- ``discovery``    — walk a tool directory, import tool modules, and build the
  MCP ``Tool`` list with JSON schemas generated from function signatures and
  docstrings.
- ``transport``    — socket send/recv helpers and argument serialization used to
  ship calls into the running DCC.
- ``schema``       — docstring/signature -> JSON schema helpers.
- ``registration`` — read/write Claude Code's ``~/.claude.json`` to register or
  remove MCP servers.
- ``venv``         — create the shared venv and install the ``mcp`` package.

Nothing here imports from any specific DCC server, so the modules can be unit
tested in isolation without Maya, Unreal, or Blender present.
"""
