"""
Claude Code MCP-server registration for the standalone ``mca-mcp`` installer.

Claude Code discovers MCP servers from ``~/.claude.json``.  A server can be
registered at two scopes:

    - **global** — top-level ``mcpServers`` map; the server is available in
      every project.
    - **project** — under ``projects[<dir>].mcpServers``; the server only
      appears when Claude Code is opened in that project directory.

This module is a thin, well-tested wrapper over that JSON file.  The core
functions operate on an explicit config-file path so they can be unit-tested
against a temporary file; the convenience wrappers default to the real
``~/.claude.json``.

Ported and generalized from the MCA Editor's ``mcp_setup.py`` — the editor
coupling (repo-root detection, ``get_prefs_dir``) is gone; scope and project
directory are explicit arguments.

Dependencies:
    - stdlib only (``json``, ``os``)

Gotchas:
    - Project keys in ``~/.claude.json`` use forward slashes even on Windows.
      We normalize to forward slashes on write and match both variants on read.
    - A malformed existing config is never silently overwritten — callers get
      an exception rather than losing the user's other MCP registrations.
"""

import json
import logging
import os


# Module-level logger.  Callers configure handlers/levels.
logger = logging.getLogger("mca_mcp.registration")


def default_config_path():
    """
    Return the path to Claude Code's user config file.

    :return: Absolute path to ``~/.claude.json``.
    :rtype: str
    """
    return os.path.join(os.path.expanduser("~"), ".claude.json")


def _normalize_project_key(project_dir):
    """
    Normalize a project directory to the forward-slash form Claude Code uses.

    :param str project_dir: A filesystem directory (any slash style).
    :return: Absolute path with forward slashes.
    :rtype: str
    """
    return os.path.abspath(project_dir).replace("\\", "/")


def _match_project_key(config, project_dir):
    """
    Find the existing project key in the config that matches ``project_dir``.

    Claude Code may store the key with forward slashes, backslashes, or a
    normalized form depending on how it was created.  We check all three so we
    never create a duplicate entry for a project that already exists.

    :param dict config: The parsed config.
    :param str project_dir: The project directory to match.
    :return: The matching existing key, or the normalized key if none exists.
    :rtype: str
    """
    projects = config.get("projects", {}) or {}

    forward = _normalize_project_key(project_dir)
    if forward in projects:
        return forward

    backward = forward.replace("/", "\\")
    if backward in projects:
        return backward

    normalized = os.path.normpath(forward)
    if normalized in projects:
        return normalized

    # No existing entry — use the canonical forward-slash form for a new one.
    return forward


def read_config(config_path=None):
    """
    Read and parse the Claude Code config, returning an empty dict if absent.

    :param str config_path: Config file path.  Defaults to ``~/.claude.json``.
    :return: The parsed config (empty dict if the file does not exist).
    :rtype: dict
    :raises ValueError: If the file exists but contains invalid JSON.
    """
    if config_path is None:
        config_path = default_config_path()

    if not os.path.isfile(config_path):
        return {}

    try:
        with open(config_path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError as exc:
        # Refuse to proceed rather than clobber a config we can't parse — the
        # user may have valuable unrelated MCP registrations in there.
        raise ValueError("Cannot parse %s: %s" % (config_path, exc)) from exc


def write_config(config, config_path=None):
    """
    Write the config back to disk with stable 2-space indentation.

    :param dict config: The config to serialize.
    :param str config_path: Config file path.  Defaults to ``~/.claude.json``.
    """
    if config_path is None:
        config_path = default_config_path()

    parent = os.path.dirname(os.path.abspath(config_path))
    if parent:
        os.makedirs(parent, exist_ok=True)

    with open(config_path, "w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2)


def _servers_map(config, scope, project_dir, create=False):
    """
    Return the ``mcpServers`` dict for the requested scope.

    :param dict config: The parsed config (mutated in place when ``create``).
    :param str scope: ``"global"`` or ``"project"``.
    :param str project_dir: Project directory (required for project scope).
    :param bool create: If True, create the intermediate structure and return
        a live reference for mutation.  If False, return a read-only view (may
        be an empty dict when nothing is registered).
    :return: The scope's ``mcpServers`` dict.
    :rtype: dict
    :raises ValueError: If scope is invalid or project_dir is missing.
    """
    if scope == "global":
        if create:
            return config.setdefault("mcpServers", {})
        return config.get("mcpServers", {}) or {}

    if scope == "project":
        if not project_dir:
            raise ValueError("project scope requires a project_dir")
        key = _match_project_key(config, project_dir)
        if create:
            projects = config.setdefault("projects", {})
            entry = projects.setdefault(key, {})
            return entry.setdefault("mcpServers", {})
        entry = (config.get("projects", {}) or {}).get(key, {}) or {}
        return entry.get("mcpServers", {}) or {}

    raise ValueError("Unknown scope: %r (expected 'global' or 'project')" % scope)


def is_registered(server_name, scope="global", project_dir=None, config_path=None):
    """
    Check whether a server is registered at the requested scope.

    :param str server_name: The registration name (e.g. ``MCAMayaMCP``).
    :param str scope: ``"global"`` or ``"project"``.
    :param str project_dir: Project directory (required for project scope).
    :param str config_path: Config file path.  Defaults to ``~/.claude.json``.
    :return: True if the server exists in that scope's ``mcpServers``.
    :rtype: bool
    """
    try:
        config = read_config(config_path)
    except ValueError:
        return False
    servers = _servers_map(config, scope, project_dir, create=False)
    return server_name in servers


def register_server(server_name, command, args, scope="global", project_dir=None, config_path=None):
    """
    Register (or update) an MCP server in the Claude Code config.

    Writes directly to ``~/.claude.json`` — deterministic and unit-testable,
    with no dependency on the ``claude`` CLI being on PATH.

    :param str server_name: The registration name (e.g. ``MCAMayaMCP``).
    :param str command: The interpreter/executable that launches the server.
    :param list args: Argument list passed to the command (e.g. the server .py).
    :param str scope: ``"global"`` or ``"project"``.
    :param str project_dir: Project directory (required for project scope).
    :param str config_path: Config file path.  Defaults to ``~/.claude.json``.
    :return: The server-config dict that was written.
    :rtype: dict
    """
    config = read_config(config_path)

    # Forward slashes keep the entry stable and cross-platform-readable.
    server_config = {
        "command": command.replace("\\", "/"),
        "args": [str(arg).replace("\\", "/") for arg in args],
    }

    servers = _servers_map(config, scope, project_dir, create=True)
    servers[server_name] = server_config

    write_config(config, config_path)
    logger.info("Registered %s at %s scope", server_name, scope)
    return server_config


def unregister_server(server_name, scope="global", project_dir=None, config_path=None):
    """
    Remove an MCP server registration from the requested scope.

    :param str server_name: The registration name to remove.
    :param str scope: ``"global"`` or ``"project"``.
    :param str project_dir: Project directory (required for project scope).
    :param str config_path: Config file path.  Defaults to ``~/.claude.json``.
    :return: True if an entry was removed, False if it was not present.
    :rtype: bool
    """
    try:
        config = read_config(config_path)
    except ValueError:
        return False

    servers = _servers_map(config, scope, project_dir, create=False)
    if server_name not in servers:
        return False

    del servers[server_name]
    write_config(config, config_path)
    logger.info("Unregistered %s from %s scope", server_name, scope)
    return True
