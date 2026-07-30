#!/usr/bin/env python3
"""Package the Forge SD plugin for Krita Plugin Importer.

Creates a ZIP file that can be imported directly into Krita using the
Plugin Importer feature. The ZIP contains the plugin folder and the
required .desktop file at the top level.

Usage:
    python scripts/package.py
    python scripts/package.py --version 1.2.0
    python scripts/package.py --output dist/
"""

from __future__ import annotations

import argparse
import os
import sys
import zipfile
from pathlib import Path

# Resolve the project root (parent of scripts/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Files/dirs to include at the top level of the ZIP
PLUGIN_ENTRIES = [
    "forge/",
    "forge.desktop",
]

# Directories to exclude from the forge/ folder
EXCLUDE_DIRS = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".git",
    ".gitignore",
    "tests",
    "docs",
    "scripts",
    ".omo",
    ".serena",
    ".rooroo",
    ".roomodes",
    "readme_imgs",
}

# File extensions to exclude
EXCLUDE_EXTENSIONS = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".so",
    ".dylib",
    ".log",
    ".tmp",
    ".swp",
    ".bak",
    ".orig",
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
}


def _get_version() -> str:
    """Read version from forge/version.py without importing it."""
    version_file = PROJECT_ROOT / "forge" / "version.py"
    if version_file.exists():
        for line in version_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("__version__"):
                # Extract version string from: __version__ = "1.0.0"
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return "0.0.0"


def _should_exclude(path: Path) -> bool:
    """Check if a file should be excluded from the package."""
    # Check excluded extensions
    if path.suffix.lower() in EXCLUDE_EXTENSIONS:
        return True

    # Check if any parent dir is excluded
    for part in path.parts:
        if part in EXCLUDE_DIRS:
            return True

    return False


def _collect_forge_files() -> list[Path]:
    """Collect all files inside the forge/ directory."""
    forge_dir = PROJECT_ROOT / "forge"
    files = []

    for root, dirs, filenames in os.walk(forge_dir):
        root_path = Path(root)

        # Skip excluded directories in-place
        dirs[:] = [
            d for d in dirs
            if d not in EXCLUDE_DIRS
        ]

        for filename in filenames:
            file_path = root_path / filename
            rel_path = file_path.relative_to(PROJECT_ROOT)

            if not _should_exclude(rel_path):
                files.append(rel_path)

    return sorted(files)


def create_package(
    output_dir: Path | None = None,
    version: str | None = None,
) -> Path:
    """Create a ZIP file for Krita Plugin Importer.

    Args:
        output_dir: Directory to write the ZIP to. Defaults to dist/.
        version: Version string. If None, reads from forge/version.py.

    Returns:
        Path to the created ZIP file.
    """
    if version is None:
        version = _get_version()

    if output_dir is None:
        output_dir = PROJECT_ROOT / "dist"

    output_dir.mkdir(parents=True, exist_ok=True)

    zip_name = f"forge-sd-krita-{version}.zip"
    zip_path = output_dir / zip_name

    print(f"Packaging forge-sd-krita v{version}")
    print(f"Output: {zip_path}")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add forge.desktop at the root level
        desktop_file = PROJECT_ROOT / "forge.desktop"
        if desktop_file.exists():
            zf.write(desktop_file, "forge.desktop")
            print(f"  + forge.desktop")

        # Add forge/ directory recursively
        forge_files = _collect_forge_files()
        for file_rel in forge_files:
            file_abs = PROJECT_ROOT / file_rel
            zf.write(file_abs, str(file_rel))
            print(f"  + {file_rel}")

        print(f"\nPackage created: {zip_path}")

        # Print summary
        total_size = zip_path.stat().st_size
        print(f"Size: {total_size:,} bytes ({total_size / 1024:.1f} KB)")

        # List contents
        print(f"\nContents ({len(forge_files) + 1} files):")
        for info in sorted(zf.infolist(), key=lambda i: i.filename):
            print(f"  {info.filename}")

    return zip_path


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Package Forge SD plugin for Krita Plugin Importer"
    )
    parser.add_argument(
        "--version",
        type=str,
        default=None,
        help="Version string (default: read from forge/version.py)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output directory (default: dist/)",
    )

    args = parser.parse_args()

    try:
        zip_path = create_package(
            output_dir=args.output,
            version=args.version,
        )
        print(f"\nDone! Import {zip_path.name} in Krita via:")
        print("  Settings > Manage Resources > Import Plugin")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
