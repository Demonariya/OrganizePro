from __future__ import annotations

import logging
import sys

LOG = logging.getLogger("organizepro.notifications")


def notify(title: str, message: str, enabled: bool = True) -> None:
    if not enabled:
        return
    if sys.platform == "win32":
        try:
            from winotify import Notification
            Notification(app_id="OrganizePro", title=title, msg=message, duration="short").show()
            return
        except Exception as exc:
            LOG.debug("Windows toast notification unavailable: %s", exc)
    LOG.info("%s: %s", title, message)
