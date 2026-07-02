"""Unit tests for :mod:`mca_mcp.common.discovery`.

Verifies that :class:`OperationsManager` discovers the in-repo Unreal tool set,
generates JSON schemas from function signatures, honors the skip list, and
tolerates a broken tool file without aborting the whole scan.

Run with::

    python -m pytest tests/test_discovery.py -v

Requires the ``mcp`` package on the path (e.g. the MayaMCP venv).
"""

# --- Imports ---------------------------------------------------------------
# stdlib
import os
import sys

# Ensure the package root is importable when pytest is launched from anywhere.
_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

# local
from mca_mcp.common.discovery import OperationsManager

# --- Constants -------------------------------------------------------------
# The real Unreal tool tree ships in the package — use it as the fixture.
UNREAL_TOOLS_DIR = os.path.join(_PKG_ROOT, "mca_mcp", "unreal", "unreal_tools")


# --- Tests -----------------------------------------------------------------

def test_discovers_unreal_tools():
    """Discovery finds a substantial set of tools from the real tree."""
    mgr = OperationsManager()
    mgr.find_tools([UNREAL_TOOLS_DIR])
    tools = mgr.get_tools()
    # The tree currently ships ~89 tool files; assert a healthy lower bound so
    # the test survives additions/removals without being brittle.
    assert len(tools) >= 50, "expected many tools, got {}".format(len(tools))


def test_known_tool_has_schema():
    """A known tool exposes a JSON input schema with its declared parameters."""
    mgr = OperationsManager()
    mgr.find_tools([UNREAL_TOOLS_DIR])

    tool = mgr.get_tool("bp_connect_pins")
    assert tool is not None, "bp_connect_pins should be discovered"

    schema = tool.inputSchema
    assert schema.get("type") == "object"
    props = schema.get("properties", {})
    # These are the documented parameters of bp_connect_pins.
    for expected in ("asset_path", "source_node_id", "source_pin",
                     "target_node_id", "target_pin"):
        assert expected in props, "missing param '{}' in schema".format(expected)


def test_description_comes_from_docstring():
    """The tool description is populated from the function docstring."""
    mgr = OperationsManager()
    mgr.find_tools([UNREAL_TOOLS_DIR])
    tool = mgr.get_tool("bp_connect_pins")
    assert tool.description and "pin" in tool.description.lower()


def test_skip_list_excludes_named_tool(tmp_path):
    """Filenames in the skip set are not registered."""
    # Write two trivial tool files into a temp dir.
    good = tmp_path / "good_tool.py"
    good.write_text("def good_tool(x: int):\n    '''A good tool.'''\n    return x\n",
                    encoding="utf-8")
    skipme = tmp_path / "skip_me.py"
    skipme.write_text("def skip_me():\n    '''Should be skipped.'''\n    return 1\n",
                      encoding="utf-8")

    mgr = OperationsManager()
    mgr.find_tools([str(tmp_path)], skip_tools={"skip_me"})

    assert mgr.has_tool("good_tool")
    assert not mgr.has_tool("skip_me")


def test_broken_tool_does_not_abort_scan(tmp_path):
    """A tool file that raises on import is skipped without killing discovery."""
    broken = tmp_path / "broken_tool.py"
    broken.write_text("raise RuntimeError('boom at import')\n", encoding="utf-8")
    fine = tmp_path / "fine_tool.py"
    fine.write_text("def fine_tool():\n    '''Fine.'''\n    return True\n",
                    encoding="utf-8")

    mgr = OperationsManager()
    mgr.find_tools([str(tmp_path)])

    # The broken file is skipped; the good one still registers.
    assert not mgr.has_tool("broken_tool")
    assert mgr.has_tool("fine_tool")


def test_init_files_always_skipped(tmp_path):
    """``__init__`` is skipped even when not in the caller's skip set."""
    init = tmp_path / "__init__.py"
    init.write_text("def __init__():\n    return None\n", encoding="utf-8")
    real = tmp_path / "real_tool.py"
    real.write_text("def real_tool():\n    '''Real.'''\n    return 1\n",
                    encoding="utf-8")

    mgr = OperationsManager()
    mgr.find_tools([str(tmp_path)])

    assert not mgr.has_tool("__init__")
    assert mgr.has_tool("real_tool")
