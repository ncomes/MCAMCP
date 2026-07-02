"""
Virtual-environment helpers for the standalone ``mca-mcp`` installer.

Each DCC MCP server runs as its own process, launched by Claude Code with a
Python interpreter that has the ``mcp`` package available.  Rather than depend
on whatever Python happens to be on the user's PATH, the installer builds a
single dedicated virtual environment and installs ``mcp`` into it.  The same
venv is reused for every DCC server, so this only runs once per machine.

This module is intentionally editor-agnostic: it knows nothing about Maya's
``mayapy`` or the MCA Editor's preference directories.  A standalone user has a
normal system Python, which is all we need.

Dependencies:
    - stdlib only (``subprocess``, ``venv`` via the interpreter, ``shutil``)

Gotchas:
    - On Windows every ``subprocess.run`` uses ``CREATE_NO_WINDOW`` so the
      installer never flashes a console window when driven from a GUI.
"""

import logging
import os
import platform
import shutil
import subprocess


# Suppress the transient console window on Windows when spawned from a GUI.
_CREATION_FLAGS = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0

# Module-level logger.  Callers configure handlers/levels.
logger = logging.getLogger("mca_mcp.venv")


def find_system_python():
    """
    Find a Python 3.10+ interpreter suitable for building the MCP venv.

    Search order is the Windows launcher (``py -3``) first on Windows, then the
    common ``python`` / ``python3`` names on PATH.  The current interpreter
    running the installer is used as a final fallback — if the user launched us,
    it is by definition a working Python.

    :return: Absolute path to a Python executable, or None if none qualifies.
    :rtype: str or None
    """
    candidates = []

    if platform.system() == "Windows":
        # The Windows launcher is the most reliable way to resolve a real 3.10+.
        candidates.append(["py", "-3"])
        candidates.append(["python"])
        candidates.append(["python3"])
    else:
        candidates.append(["python3"])
        candidates.append(["python"])

    for cmd in candidates:
        exe = _resolve_python_executable(cmd)
        if exe:
            return exe

    # Fallback: the interpreter running this installer.  It launched us, so it
    # exists and is almost certainly >= 3.10 (our own requires-python floor).
    import sys

    if os.path.isfile(sys.executable):
        logger.debug("Falling back to the running interpreter: %s", sys.executable)
        return sys.executable

    logger.warning("No Python 3.10+ interpreter could be located")
    return None


def _resolve_python_executable(cmd):
    """
    Verify a candidate Python command is 3.10+ and resolve its real executable.

    :param list cmd: The command prefix to probe (e.g. ``["py", "-3"]``).
    :return: Absolute path to the interpreter, or None if unusable / too old.
    :rtype: str or None
    """
    try:
        # Ask the candidate for its own ``sys.executable`` and version tuple in
        # one shot.  This resolves launcher shims (``py -3``) to a real path.
        probe = subprocess.run(
            cmd + ["-c", "import sys; print(sys.executable); print('%d.%d' % sys.version_info[:2])"],
            check=True,
            timeout=15,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=_CREATION_FLAGS,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError, FileNotFoundError):
        return None

    lines = probe.stdout.decode(errors="replace").strip().splitlines()
    if len(lines) < 2:
        return None

    exe_path = lines[0].strip()
    version_str = lines[1].strip()

    # Enforce the 3.10 floor (our servers use 3.10 syntax + typing features).
    try:
        major_str, minor_str = version_str.split(".")[:2]
        major = int(major_str)
        minor = int(minor_str)
    except ValueError:
        return None

    if (major, minor) < (3, 10):
        logger.debug("Skipping Python %s (need 3.10+): %s", version_str, exe_path)
        return None

    if not os.path.isfile(exe_path):
        return None

    logger.debug("Found Python %s at %s", version_str, exe_path)
    return exe_path


def venv_python(venv_dir):
    """
    Return the path to the Python executable inside a venv directory.

    :param str venv_dir: The virtual-environment root directory.
    :return: Absolute path to the venv's Python (may not exist yet).
    :rtype: str
    """
    if platform.system() == "Windows":
        return os.path.join(venv_dir, "Scripts", "python.exe")
    return os.path.join(venv_dir, "bin", "python")


def venv_ready(venv_dir):
    """
    Check whether a venv exists and already has ``mcp`` importable.

    Cheap enough to call on every install so the operation stays idempotent —
    a second ``install`` run with a ready venv does no subprocess work.

    :param str venv_dir: The virtual-environment root directory.
    :return: True if the venv's Python can import ``mcp``.
    :rtype: bool
    """
    python = venv_python(venv_dir)
    if not os.path.isfile(python):
        return False

    try:
        subprocess.run(
            [python, "-c", "import mcp"],
            check=True,
            timeout=30,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=_CREATION_FLAGS,
        )
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return False


def create_venv(venv_dir, base_python=None):
    """
    Create the virtual environment if it does not already exist.

    :param str venv_dir: Destination directory for the venv.
    :param str base_python: Interpreter to build from.  Auto-detected if None.
    :return: Absolute path to the venv's Python executable.
    :rtype: str
    :raises RuntimeError: If no suitable base Python is found or creation fails.
    """
    python = venv_python(venv_dir)
    if os.path.isfile(python):
        logger.debug("Venv already present: %s", venv_dir)
        return python

    if base_python is None:
        base_python = find_system_python()
    if not base_python:
        raise RuntimeError("No Python 3.10+ interpreter found to build the MCP venv")

    os.makedirs(os.path.dirname(os.path.abspath(venv_dir)) or ".", exist_ok=True)
    logger.info("Creating MCP venv at %s (base: %s)", venv_dir, base_python)

    try:
        subprocess.run(
            [base_python, "-m", "venv", venv_dir],
            check=True,
            timeout=180,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=_CREATION_FLAGS,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        # Surface pip/venv stderr so a failed build is diagnosable.
        detail = getattr(exc, "stderr", b"")
        detail = detail.decode(errors="replace") if isinstance(detail, bytes) else str(exc)
        raise RuntimeError("Failed to create venv at %s: %s" % (venv_dir, detail)) from exc

    if not os.path.isfile(python):
        raise RuntimeError("Venv created but interpreter missing at %s" % python)

    return python


def pip_install(venv_dir, packages):
    """
    Install packages into the venv with pip.

    :param str venv_dir: The virtual-environment root directory.
    :param list packages: Package specifiers to install (e.g. ``["mcp>=1.0.0"]``).
    :raises RuntimeError: If pip fails.
    """
    python = venv_python(venv_dir)
    if not os.path.isfile(python):
        raise RuntimeError("Cannot pip-install: venv Python missing at %s" % python)

    logger.info("Installing into venv: %s", ", ".join(packages))
    try:
        subprocess.run(
            [python, "-m", "pip", "install", "--upgrade"] + list(packages),
            check=True,
            timeout=600,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=_CREATION_FLAGS,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        detail = getattr(exc, "stderr", b"")
        detail = detail.decode(errors="replace") if isinstance(detail, bytes) else str(exc)
        raise RuntimeError("pip install failed (%s): %s" % (", ".join(packages), detail)) from exc


def ensure_venv(venv_dir, packages=None, base_python=None):
    """
    Idempotently create the venv and ensure the required packages are present.

    This is the one call the installer needs: it builds the venv on first run
    and is a near-no-op afterwards (a single ``import mcp`` probe).

    :param str venv_dir: Destination directory for the venv.
    :param list packages: Packages the venv must provide.  Defaults to ``mcp``.
    :param str base_python: Interpreter to build from.  Auto-detected if None.
    :return: Absolute path to the venv's Python executable.
    :rtype: str
    """
    if packages is None:
        packages = ["mcp>=1.0.0"]

    # Fast path: an existing, satisfied venv skips all subprocess work.
    if venv_ready(venv_dir):
        logger.debug("Venv already satisfies requirements: %s", venv_dir)
        return venv_python(venv_dir)

    create_venv(venv_dir, base_python=base_python)
    pip_install(venv_dir, packages)
    return venv_python(venv_dir)
