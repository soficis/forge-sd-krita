"""Update checker for the Forge SD Krita plugin.

Checks GitHub releases for newer versions and notifies the user.
Does NOT auto-install updates for security reasons.

Usage:
    # As a library:
    from scripts.update_checker import check_for_update
    result = check_for_update()

    # From command line:
    python scripts/update_checker.py
"""

from __future__ import annotations

import json
import sys
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Optional

# Default GitHub repo (can be overridden)
DEFAULT_GITHUB_REPO = "DrCyanide/forge-sd-krita"

# GitHub API endpoint for releases
GITHUB_API_URL = "https://api.github.com/repos/{repo}/releases/latest"

# Timeout for HTTP requests (seconds)
REQUEST_TIMEOUT = 5


@dataclass
class UpdateInfo:
    """Information about an available update."""

    current_version: str
    latest_version: str
    release_url: str
    release_notes: str

    @property
    def update_available(self) -> bool:
        """Check if an update is available."""
        return _parse_version(self.latest_version) > _parse_version(self.current_version)


def _parse_version(version_str: str) -> tuple[int, ...]:
    """Parse a version string like '1.2.3' into a tuple of integers."""
    try:
        return tuple(int(x) for x in version_str.strip().split("."))
    except (ValueError, AttributeError):
        return (0,)


def _fetch_json(url: str) -> Optional[dict]:
    """Fetch JSON from a URL with error handling."""
    try:
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "forge-sd-krita-plugin",
            },
        )
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, OSError):
        return None


def check_for_update(
    current_version: str,
    repo: str = DEFAULT_GITHUB_REPO,
) -> Optional[UpdateInfo]:
    """Check GitHub for a newer version of the plugin.

    Args:
        current_version: The currently installed version string.
        repo: GitHub repository in "owner/repo" format.

    Returns:
        UpdateInfo if an update is available, None otherwise.
    """
    url = GITHUB_API_URL.format(repo=repo)
    data = _fetch_json(url)

    if data is None:
        return None

    # Extract latest version from tag (strip leading 'v' if present)
    tag_name = data.get("tag_name", "")
    latest_version = tag_name.lstrip("v")

    if not latest_version:
        return None

    release_url = data.get("html_url", "")
    release_notes = data.get("body", "")

    info = UpdateInfo(
        current_version=current_version,
        latest_version=latest_version,
        release_url=release_url,
        release_notes=release_notes[:500],  # Truncate long notes
    )

    return info if info.update_available else None


def format_update_message(info: UpdateInfo) -> str:
    """Format an update notification message for the user."""
    msg = f"Forge SD Plugin Update Available\n"
    msg += f"Current: v{info.current_version}\n"
    msg += f"Latest:  v{info.latest_version}\n"
    msg += f"Download: {info.release_url}"
    return msg


def main() -> None:
    """CLI entry point for checking updates."""
    # Try to import version from the plugin
    try:
        sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
        from forge.version import __version__ as current_version
    except ImportError:
        print("Error: Could not read version from forge/version.py", file=sys.stderr)
        sys.exit(1)

    print(f"Current version: v{current_version}")
    print(f"Checking for updates...")

    info = check_for_update(current_version)

    if info is None:
        print("You are running the latest version!")
    else:
        print(f"\n{format_update_message(info)}")
        if info.release_notes:
            print(f"\nRelease notes:\n{info.release_notes}")


if __name__ == "__main__":
    main()
