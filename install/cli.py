"""
Standalone command-line installer for the ``mca-mcp`` DCC MCP servers.

Registers the Maya / Unreal / Blender MCP servers with Claude Code so any
project can use them, without the MCA Editor.  It does two things:

    1. Builds one shared virtual environment with the ``mcp`` runtime.
    2. Registers each requested server in ``~/.claude.json`` — pointing Claude
       Code at the venv's Python and the server's ``server.py`` inside this
       package.  Each server carries a ``sys.path`` shim, so it imports the
       shared ``mca_mcp.common`` package straight from wherever this package
       lives (a git clone or a pip install) — no PyPI publish required.

Usage::

    mca-mcp install maya|unreal|blender|all [--scope global|project]
                                            [--project-dir DIR]
                                            [--venv DIR]
    mca-mcp status
    mca-mcp uninstall maya|unreal|blender|all [--scope ...] [--project-dir ...]

When run from a git checkout without installing the package, invoke the same
entry point as a module from the repo root::

    python -m install.cli install all

Dependencies:
    - stdlib only; imports ``mca_mcp.common.venv`` and
      ``mca_mcp.common.registration`` from this package.

Environment variables:
    - ``MCA_MCP_VENV`` — override the default venv directory (``~/.mca-mcp/venv``).

Gotchas:
    - The Maya server additionally needs its vendored ``mayatools/`` beside it
      (shipped in this package) — nothing extra to install.
"""

import argparse
import logging
import os
import sys

# Make the sibling ``mca_mcp`` package importable when this file is run as a
# plain script (``python install/cli.py``) from the repo root.  When invoked
# via the console entry point or ``python -m install.cli`` the package is
# already importable and this is a harmless no-op.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from mca_mcp import servers as server_registry
from mca_mcp.common import registration
from mca_mcp.common import venv as venv_helpers


# --- Constants ----------------------------------------------------------------

# The DCC registry is defined once in ``mca_mcp.servers`` so the installer and
# any embedding app (e.g. the MCA Editor shim) agree on names + module paths.
# Aliased here under the historical name used throughout this module.
_DCC_REGISTRY = server_registry.SERVERS

# Default location for the shared MCP venv.  Overridable via ``--venv`` or the
# ``MCA_MCP_VENV`` environment variable so the editor shim can point it at the
# old ``mca_preferences`` location later.
_DEFAULT_VENV = os.environ.get(
    "MCA_MCP_VENV", os.path.join(os.path.expanduser("~"), ".mca-mcp", "venv")
)

logger = logging.getLogger("mca_mcp.install")


# --- Helpers ------------------------------------------------------------------

def _resolve_dccs(target):
    """
    Expand a target token into the list of DCC keys it refers to.

    :param str target: One of ``maya``, ``unreal``, ``blender``, or ``all``.
    :return: Ordered list of DCC keys.
    :rtype: list
    :raises SystemExit: If the target is unknown.
    """
    if target == "all":
        return list(_DCC_REGISTRY.keys())
    if target in _DCC_REGISTRY:
        return [target]
    raise SystemExit("Unknown DCC %r (expected: maya, unreal, blender, all)" % target)


def _server_script_path(dcc):
    """
    Resolve the absolute path to a DCC server's ``server.py`` file.

    Thin wrapper over :func:`mca_mcp.servers.server_script_path` so callers in
    this module keep the historical private name.

    :param str dcc: The DCC key.
    :return: Absolute path to the server module file.
    :rtype: str
    :raises RuntimeError: If the module cannot be located.
    """
    return server_registry.server_script_path(dcc)


# --- Commands -----------------------------------------------------------------

def cmd_install(args):
    """
    Build the shared venv and register the requested DCC server(s).

    :param argparse.Namespace args: Parsed CLI arguments.
    :return: Process exit code.
    :rtype: int
    """
    dccs = _resolve_dccs(args.target)
    venv_dir = args.venv or _DEFAULT_VENV

    # Build (or reuse) the one shared venv with the mcp runtime.
    print("Ensuring MCP venv at %s ..." % venv_dir)
    try:
        python = venv_helpers.ensure_venv(venv_dir)
    except RuntimeError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 1
    print("  venv Python: %s" % python)

    # Register each requested server against that venv Python.
    for dcc in dccs:
        server_name = _DCC_REGISTRY[dcc]["server_name"]
        try:
            script_path = _server_script_path(dcc)
        except RuntimeError as exc:
            print("ERROR: %s" % exc, file=sys.stderr)
            return 1

        registration.register_server(
            server_name,
            command=python,
            args=[script_path],
            scope=args.scope,
            project_dir=args.project_dir,
        )
        scope_label = args.scope
        if args.scope == "project":
            scope_label = "project:%s" % os.path.abspath(args.project_dir or os.getcwd())
        print("  registered %-14s -> %s  [%s]" % (server_name, script_path, scope_label))

    print("Done.  Restart Claude Code (or reload MCP servers) to pick up the changes.")
    return 0


def cmd_uninstall(args):
    """
    Remove the requested DCC server registration(s) from Claude Code.

    The shared venv is left in place (harmless, and reused by other DCCs).

    :param argparse.Namespace args: Parsed CLI arguments.
    :return: Process exit code.
    :rtype: int
    """
    dccs = _resolve_dccs(args.target)
    for dcc in dccs:
        server_name = _DCC_REGISTRY[dcc]["server_name"]
        removed = registration.unregister_server(
            server_name,
            scope=args.scope,
            project_dir=args.project_dir,
        )
        state = "removed" if removed else "not registered"
        print("  %-14s %s" % (server_name, state))
    return 0


def cmd_status(args):
    """
    Print venv readiness and per-DCC registration state at both scopes.

    :param argparse.Namespace args: Parsed CLI arguments.
    :return: Process exit code.
    :rtype: int
    """
    venv_dir = args.venv or _DEFAULT_VENV
    ready = venv_helpers.venv_ready(venv_dir)
    print("MCP venv: %s  [%s]" % (venv_dir, "ready" if ready else "missing"))

    project_dir = args.project_dir or os.getcwd()
    print("Project scope dir: %s" % os.path.abspath(project_dir))
    print("")
    print("%-14s %-8s %-8s %s" % ("SERVER", "GLOBAL", "PROJECT", "SCRIPT"))
    for dcc, meta in _DCC_REGISTRY.items():
        name = meta["server_name"]
        in_global = registration.is_registered(name, scope="global")
        in_project = registration.is_registered(name, scope="project", project_dir=project_dir)
        try:
            script_path = _server_script_path(dcc)
        except RuntimeError:
            script_path = "<not found>"
        print("%-14s %-8s %-8s %s" % (
            name,
            "yes" if in_global else "-",
            "yes" if in_project else "-",
            script_path,
        ))
    return 0


# --- Argument parsing ---------------------------------------------------------

def build_parser():
    """
    Construct the argparse command-line parser.

    :return: The configured parser.
    :rtype: argparse.ArgumentParser
    """
    parser = argparse.ArgumentParser(
        prog="mca-mcp",
        description="Install the Maya / Unreal / Blender MCP servers into Claude Code.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # Shared scope options for install / uninstall.
    def add_scope_opts(sp):
        sp.add_argument(
            "--scope",
            choices=["global", "project"],
            default="global",
            help="Register globally (all projects) or only in --project-dir. Default: global.",
        )
        sp.add_argument(
            "--project-dir",
            default=None,
            help="Project directory for --scope project. Default: current directory.",
        )
        sp.add_argument(
            "--venv",
            default=None,
            help="Override the shared MCP venv directory (default: ~/.mca-mcp/venv).",
        )

    p_install = sub.add_parser("install", help="Build the venv and register server(s).")
    p_install.add_argument("target", help="maya | unreal | blender | all")
    add_scope_opts(p_install)
    p_install.set_defaults(func=cmd_install)

    p_uninstall = sub.add_parser("uninstall", help="Remove server registration(s).")
    p_uninstall.add_argument("target", help="maya | unreal | blender | all")
    add_scope_opts(p_uninstall)
    p_uninstall.set_defaults(func=cmd_uninstall)

    p_status = sub.add_parser("status", help="Show venv + registration state.")
    p_status.add_argument("--venv", default=None, help="Venv directory to check.")
    p_status.add_argument("--project-dir", default=None, help="Project dir for project-scope check.")
    p_status.set_defaults(func=cmd_status)

    return parser


def main(argv=None):
    """
    Entry point for the ``mca-mcp`` console script.

    :param list argv: Argument vector (defaults to ``sys.argv[1:]``).
    :return: Process exit code.
    :rtype: int
    """
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    parser = build_parser()
    args = parser.parse_args(argv)
    # ``project_dir`` may be absent on the status subparser default path.
    if not hasattr(args, "project_dir"):
        args.project_dir = None
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
