# MCA MCP

Model Context Protocol (MCP) servers that let AI assistants — Claude Code and
any other MCP client — drive **Maya**, **Unreal Engine**, and **Blender**.

Extracted from the [MCA Editor](https://github.com/ncomes/MCAEditor) so any
project can use the DCC servers independently.

---

## Status

✅ **Standalone and usable.** All three DCC servers run without the MCA Editor,
Maya's tool set is vendored, and the `mca-mcp` installer registers the servers
with Claude Code (global or per-project) from a plain `git clone`. Remaining
work is the Unreal C++ bridge release channel and PyPI publishing — see
`docs/migration_plan.md`.

Tool counts: **Unreal 89**, **Maya 17** (vendored MayaMCP set), **Blender 14**.

---

## Layout

```
mca_mcp/
  common/        # shared discovery, transport, schema, Claude Code registration
  maya/          # Maya server  (builds on MayaMCP's tool set)
  unreal/        # Unreal server + unreal_tools/  (89 tools)
  blender/       # Blender server (tools defined inline)
install/         # `mca-mcp install|status|uninstall` CLI
tests/           # unit tests for the common layer
docs/            # migration plan + design notes
```

## Install

**From a git clone (no PyPI needed):**

```bash
git clone git@github.com:ncomes/MCAMCP.git
cd MCAMCP

# Build the shared MCP venv and register a server with Claude Code.
python -m install.cli install maya            # or: unreal | blender | all
python -m install.cli status
python -m install.cli uninstall unreal
```

**As an installed package:**

```bash
pip install mca-mcp            # core + all servers importable
pip install "mca-mcp[maya]"    # Maya only

mca-mcp install all            # `mca-mcp` console script once pip-installed
mca-mcp status
```

The installer builds one shared venv (default `~/.mca-mcp/venv`, override with
`--venv` or `$MCA_MCP_VENV`) containing the `mcp` runtime, then registers each
server in `~/.claude.json`. Use `--scope project [--project-dir DIR]` to scope a
server to a single project instead of globally. Restart Claude Code (or reload
MCP servers) afterward.

## Running a server directly

```bash
python -m mca_mcp.unreal.server --tool-dir mca_mcp/unreal/unreal_tools
python -m mca_mcp.maya.server
python -m mca_mcp.blender.server
```

## DCC bridges

- **Maya** — uses [PatrickPalmer/MayaMCP](https://github.com/PatrickPalmer/MayaMCP)
  tool set (MIT). The patched `mayatools/` are vendored under `mca_mcp/maya/`.
- **Unreal** — requires the `MCAEditorScripting` C++ bridge plugin, distributed
  separately as prebuilt `.uplugin` releases per UE version. The Python
  `unreal_tools/` ship in this package.
- **Blender** — talks to Blender over a socket; no compiled bridge.

## License

MIT. Maya tool set derives from MayaMCP (MIT) — see `LICENSE` and attribution.
