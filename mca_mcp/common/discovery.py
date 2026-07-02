"""Shared MCP tool discovery for the MCA DCC servers.

Walks one or more tool directories, dynamically imports each ``.py`` file, and
builds an MCP :class:`~mcp.types.Tool` for every function whose name matches its
filename (e.g. ``create_actor.py`` exports ``create_actor``).  The JSON input
schema is generated from the function's signature and type annotations via
``func_metadata`` — the same mechanism FastMCP uses internally.

This module is DCC-agnostic: it never imports ``maya``, ``unreal``, or ``bpy``.
Each server instantiates :class:`OperationsManager`, points it at its own tool
directory, and passes the set of filenames to skip.  Extracted from the
previously-duplicated ``OperationsManager`` that lived in both the Maya and
Unreal servers (verified byte-identical apart from comments).

Dependencies
------------
- ``mcp`` — provides ``Tool``, ``Context``, and ``func_metadata``.

Side effects
------------
:meth:`OperationsManager.find_tools` imports arbitrary tool modules via
``importlib``.  Tool modules are expected to keep DCC imports (``import maya``,
``import unreal``) inside their function bodies so that discovery — which runs in
the MCP server process, not inside the DCC — does not fail at import time.
"""

# --- Imports ---------------------------------------------------------------
# stdlib
import importlib.util
import inspect
import logging
import os
from typing import get_origin

# third-party (mcp package)
from mcp.server.fastmcp.server import Context
from mcp.server.fastmcp.utilities.func_metadata import func_metadata
from mcp.types import Tool

# --- Module Logger ---------------------------------------------------------
# Namespaced under the package so a server's logging config controls verbosity.
logger = logging.getLogger("mca_mcp.common.discovery")


# --- Tool Discovery --------------------------------------------------------

class OperationsManager:
    """
    Discovers MCP tools from one or more tool directory trees.

    Walks directories for ``.py`` files, dynamically loads each module, inspects
    the function signature, and builds MCP ``Tool`` objects with JSON schemas.
    Adapted from MayaMCP's ``OperationsManager`` with defensive improvements
    (caller-supplied skip list, per-tool error isolation).
    """

    def __init__(self):
        """Initialize empty tool and path registries."""
        # Maps tool name -> source .py path (used to re-read source at call time).
        self._paths = {}
        # Maps tool name -> MCP Tool object (schema + description).
        self._tools = {}

    def has_tool(self, name):
        """
        Check if a tool is registered.

        :param str name: Tool name.
        :return: True if the tool exists.
        :rtype: bool
        """
        return name in self._tools

    def get_tool(self, name):
        """
        Get a Tool by name.

        :param str name: Tool name.
        :return: The Tool object, or None if not found.
        :rtype: Tool or None
        """
        return self._tools.get(name)

    def get_file_path(self, name):
        """
        Get the source file path for a tool.

        :param str name: Tool name.
        :return: Absolute path to the .py file, or None.
        :rtype: str or None
        """
        return self._paths.get(name)

    def get_tools(self):
        """
        Return all registered tools.

        :return: List of Tool objects.
        :rtype: list
        """
        return list(self._tools.values())

    def find_tools(self, tool_dirs, skip_tools=None):
        """
        Walk one or more directories and register all valid tool files.

        Each ``.py`` file must contain a function whose name matches the
        filename (e.g. ``create_actor.py`` exports ``create_actor``).  Files
        whose stem appears in ``skip_tools`` are silently ignored — callers pass
        DCC-specific skip sets (e.g. Maya skips the broken ``generate_scene``).

        :param list tool_dirs: List of directory paths to scan (recursively).
        :param set skip_tools: Set of filename stems to skip.  ``__init__`` is
            always skipped even if not present.  Defaults to an empty set.
        """
        # Normalize the skip set and always exclude package __init__ files.
        skip = set(skip_tools) if skip_tools else set()
        skip.add("__init__")

        for tool_dir in tool_dirs:
            if not os.path.isdir(tool_dir):
                logger.warning("Tool directory not found, skipping: %s", tool_dir)
                continue

            # Recurse so tools can be organized into category subdirectories.
            for root, dirs, files in os.walk(tool_dir):
                for filename in files:
                    if not filename.endswith(".py"):
                        continue

                    name = os.path.splitext(filename)[0]

                    # Skip known-bad or non-tool files.
                    if name in skip:
                        logger.debug("Skipping tool '%s' (in skip list)", name)
                        continue

                    path = os.path.join(root, filename)
                    tool = self._load_tool(name, path)

                    # Only register tools that loaded and produced a schema.
                    if tool:
                        self._paths[name] = path
                        self._tools[name] = tool
                        logger.debug("Registered tool: %s", name)

        logger.info("Discovered %d tools from %d directories.",
                     len(self._tools), len(tool_dirs))

    def _load_tool(self, name, filepath):
        """
        Load a single tool file and build an MCP Tool from its function signature.

        Uses ``importlib`` to load the module, finds the function matching the
        filename, inspects its signature via ``func_metadata()``, and creates a
        ``Tool`` with the function's docstring as description and its parameter
        annotations as the JSON input schema.  Any failure (import error, missing
        function, unschemable signature) is logged and returns ``None`` so one
        bad tool never aborts discovery of the rest.

        :param str name: Expected function name (matches filename stem).
        :param str filepath: Absolute path to the .py file.
        :return: MCP Tool object, or None on failure.
        :rtype: Tool or None
        """
        # Import the module in isolation so tool files don't pollute sys.modules
        # under a shared name.
        try:
            spec = importlib.util.spec_from_file_location(name, filepath)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            fn = getattr(module, name)
        except Exception as exc:
            logger.warning("Failed to load tool '%s' from %s: %s", name, filepath, exc)
            return None

        func_doc = fn.__doc__ or ""

        # Inspect the signature for an MCP Context parameter so it can be excluded
        # from the public JSON schema (it's injected by the framework, not the LLM).
        sig = inspect.signature(fn)
        context_kwarg = None
        for param_name, param in sig.parameters.items():
            # Parameterized generics (e.g. list[str]) are not classes — skip them.
            if get_origin(param.annotation) is not None:
                continue
            try:
                if issubclass(param.annotation, Context):
                    context_kwarg = param_name
                    break
            except TypeError:
                # Annotation is not a class (e.g. a bare string) — skip.
                continue

        # Build the pydantic-backed JSON schema from the function signature.
        try:
            func_arg_metadata = func_metadata(
                fn,
                skip_names=[context_kwarg] if context_kwarg is not None else [],
            )
            parameters = func_arg_metadata.arg_model.model_json_schema()
        except Exception as exc:
            logger.warning("Failed to extract schema for tool '%s': %s", name, exc)
            return None

        return Tool(
            name=name,
            description=func_doc,
            inputSchema=parameters,
        )
