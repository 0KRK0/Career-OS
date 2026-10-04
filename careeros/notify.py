"""Desktop pop-ups (Windows toast) + in-app notification feed."""
from __future__ import annotations

import os
import subprocess
import sys

from . import db
from .config import settings

PS = r"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$t = [System.Security.SecurityElement]::Escape($env:CO_TITLE)
$b = [System.Security.SecurityElement]::Escape($env:CO_BODY)
$u = [System.Security.SecurityElement]::Escape($env:CO_URL)
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml("<toast activationType='protocol' launch='$u' scenario='reminder'><visual><binding template='ToastGeneric'><text>$t</text><text>$b</text></binding></visual><actions><action content='Open Career OS' activationType='protocol' arguments='$u'/><action content='Later' activationType='system' arguments='dismiss'/></actions></toast>")
$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe').Show($toast)
"""


def toast(title: str, body: str, path: str = "") -> None:
    s = settings()
    url = f"http://127.0.0.1:{s.get('port', 8765)}/{path}"
    if not (s.get("notify") or {}).get("toast", True):
        return
    if sys.platform != "win32":
        print(f"[notify] {title}: {body}")
        return
    env = dict(os.environ, CO_TITLE=title[:120], CO_BODY=body[:300], CO_URL=url)
    try:
        subprocess.Popen(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", PS],
                         env=env, creationflags=0x08000000, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def notify(key: str, title: str, body: str, path: str = "", popup: bool = True) -> None:
    """Show once per key (so you aren't spammed)."""
    if db.notify_once(key, title, body) and popup:
        toast(title, body, path)
