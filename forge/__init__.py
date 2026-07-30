from __future__ import annotations

import logging
import threading

from krita import DockWidgetFactory, DockWidgetFactoryBase, Krita

from .forge import ForgeDocker
from .version import __version__

logger = logging.getLogger(__name__)


def _check_for_updates() -> None:
    try:
        from urllib.request import Request, urlopen
        import json

        from .version import GITHUB_REPO

        url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        req = Request(
            url,
            headers={
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "forge-sd-krita-plugin",
            },
        )

        with urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))

        tag_name = data.get("tag_name", "")
        latest_version = tag_name.lstrip("v")

        if not latest_version:
            return

        current_parts = tuple(int(x) for x in __version__.split("."))
        latest_parts = tuple(int(x) for x in latest_version.split("."))

        if latest_parts > current_parts:
            release_url = data.get("html_url", "")
            _show_update_notification(__version__, latest_version, release_url)

    except Exception:
        logger.debug("Update check failed (network or GitHub unavailable)")


def _show_update_notification(
    current: str, latest: str, url: str
) -> None:
    from .qt_compat import QMessageBox

    msg = QMessageBox()
    msg.setIcon(QMessageBox.Information)
    msg.setWindowTitle("Forge SD Plugin Update")
    msg.setText(f"A new version is available!\n\n"
                f"Current: v{current}\n"
                f"Latest:  v{latest}\n\n"
                f"Visit the GitHub releases page to download.")
    msg.setInformativeText(f"Download from:\n{url}")
    msg.setStandardButtons(QMessageBox.Ok)
    msg.exec()


Krita.instance().addDockWidgetFactory(
    DockWidgetFactory(
        "forgeSD",
        DockWidgetFactoryBase.DockTornOff,
        ForgeDocker,
    )
)

_update_thread = threading.Thread(target=_check_for_updates, daemon=True)
_update_thread.start()

__all__ = ["ForgeDocker", "__version__"]
