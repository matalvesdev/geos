"""GEOS Auto-Update module.

Provides `geos update` command to check and install the latest version
from GitHub releases or PyPI. Also includes version checking utilities.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .util import now_iso


REPO_URL = "https://github.com/matalvesdev/geos"
RAW_BASE = f"{REPO_URL}/raw/main"


def get_current_version() -> str:
    """Return the current installed GEOS version."""
    return __version__


def get_latest_version_from_github() -> str | None:
    """Fetch the latest version from GitHub repository's __init__.py."""
    try:
        import urllib.request
        import urllib.error
        
        url = f"{RAW_BASE}/geos/__init__.py"
        req = urllib.request.Request(url, headers={"User-Agent": f"GEOS-CLI/{__version__}"})
        
        with urllib.request.urlopen(req, timeout=10) as response:
            content = response.read().decode("utf-8")
            
        # Parse __version__ from the file
        for line in content.splitlines():
            if line.startswith("__version__"):
                # Extract version string
                parts = line.split("=")
                if len(parts) == 2:
                    version = parts[1].strip().strip('"').strip("'")
                    return version
    except Exception:
        pass
    return None


def get_latest_version_from_pypi() -> str | None:
    """Fetch the latest version from PyPI."""
    try:
        import urllib.request
        import urllib.error
        
        url = "https://pypi.org/pypi/geos/json"
        req = urllib.request.Request(url, headers={"User-Agent": f"GEOS-CLI/{__version__}"})
        
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            return data.get("info", {}).get("version")
    except Exception:
        pass
    return None


def check_for_updates(silent: bool = False) -> tuple[bool, str | None, str | None]:
    """Check if a newer version is available.
    
    Returns:
        Tuple of (update_available, current_version, latest_version)
    """
    current = get_current_version()
    latest = get_latest_version_from_github()
    
    if latest is None:
        latest = get_latest_version_from_pypi()
    
    if latest is None:
        if not silent:
            print(f"  ! Could not check for updates")
        return False, current, None
    
    update_available = latest != current
    return update_available, current, latest


def update_geos(force: bool = False, use_pip: bool = False) -> bool:
    """Update GEOS to the latest version.
    
    Args:
        force: Force update even if already up to date
        use_pip: Use pip install instead of git pull
        
    Returns:
        True if update was successful, False otherwise
    """
    from .formatting import (status_ok, status_warn, status_error, value, bold, 
                             success, error, warning, print_kv)
    
    current = get_current_version()
    latest = get_latest_version_from_github()
    
    if latest is None:
        latest = get_latest_version_from_pypi()
        use_pip = True  # Fall back to pip if GitHub fails
    
    if latest is None:
        print(f"  {status_error()} Could not determine latest version")
        return False
    
    if current == latest and not force:
        print(f"  {status_ok()} Already up to date ({value(current)})")
        return True
    
    print(f"  {status_warn()} Update available: {value(current)} → {value(latest)}")
    
    try:
        if use_pip:
            # Use pip to install from PyPI
            cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "geos"]
        else:
            # Use pip to install from GitHub
            cmd = [sys.executable, "-m", "pip", "install", 
                   "--upgrade", f"git+{REPO_URL}@main"]
        
        print(f"  Updating...")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        
        if result.returncode == 0:
            new_version = get_current_version()
            print(f"  {status_ok()} Updated to {value(new_version)}")
            print(f"  {warning('Restart your shell or run:')} geos --version")
            return True
        else:
            print(f"  {status_error()} Update failed:")
            print(f"    {result.stderr[:200] if result.stderr else 'Unknown error'}")
            return False
            
    except Exception as exc:
        print(f"  {status_error()} Update failed: {exc}")
        return False


def cmd_update(args: argparse.Namespace) -> int:
    """CLI handler for `geos update`."""
    import argparse
    
    from .formatting import (heading, status_ok, status_warn, status_error, 
                             badge_version, value, bold, success, error, print_kv)
    
    print(heading(f"GEOS Update", level=2))
    print()
    
    current = get_current_version()
    print_kv("Current version", value(current))
    print()
    
    if args.check_only:
        update_available, _, latest = check_for_updates(silent=False)
        if update_available:
            print(f"  {status_warn()} Update available: {value(current)} → {value(latest)}")
            print(f"  Run: {bold('geos update')} to install")
        else:
            print(f"  {status_ok()} You're up to date!")
        return 0
    
    success_update = update_geos(force=args.force, use_pip=args.pip)
    return 0 if success_update else 1
