from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
from pathlib import Path

from app.config.settings import SettingsStore
from app.controller import ApplicationController
from app.desktop.instance import SingleInstance
from app.desktop.tray import TrayService
from app.web.server import LocalDashboardServer

LOG = logging.getLogger("organizepro")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OrganizePro — safe Windows file organization utility")
    parser.add_argument("--tray", action="store_true", help="Start minimized to the system tray")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the dashboard at startup")
    parser.add_argument("--port", type=int, default=0, help="Dashboard port (0 selects a free local port)")
    parser.add_argument("--once", action="store_true", help="Organize existing files once (requires --confirm)")
    parser.add_argument("--dry-run", action="store_true", help="Preview existing files without moving them")
    parser.add_argument("--confirm", action="store_true", help="Confirm a one-time existing-file organization")
    parser.add_argument("--version", action="version", version="OrganizePro 0.0.1")
    return parser.parse_args(argv)


def run_app(args: argparse.Namespace) -> int:
    settings = SettingsStore()
    instance = SingleInstance("OrganizePro.Desktop.Instance", settings.directory)
    if not instance.acquire():
        LOG.warning("Another OrganizePro instance is already running.")
        return 0
    controller = None
    server = None
    tray = TrayService({}, lambda: {"running": False})
    shutdown = threading.Event()
    stopped = False

    def stop_app(*_args) -> None:
        nonlocal stopped
        if stopped:
            return
        stopped = True
        shutdown.set()
        try:
            if controller is not None:
                controller.close()
        finally:
            try:
                tray.stop()
            finally:
                try:
                    if server is not None:
                        server.stop()
                finally:
                    instance.release()

    try:
        controller = ApplicationController(settings)
        if args.dry_run:
            report = controller.dry_run_existing()
            print(report["message"], report["count"])
            controller.close(); instance.release(); stopped = True
            return 0
        if args.once:
            if not args.confirm:
                raise ValueError("--once requires --confirm. Use --dry-run to preview without moving files.")
            report = controller.organize_existing()
            print(report["message"], report["organized"])
            controller.close(); instance.release(); stopped = True
            return 0
        server = LocalDashboardServer(controller, port=args.port)
        url = server.start()
        actions = controller.tray_actions(server)
        actions["exit"] = stop_app
        tray.actions = actions
        icon_file = Path(__file__).resolve().parent / "assets" / "tray.png"
        if getattr(sys, "frozen", False):
            icon_file = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "assets" / "tray.png"
        tray_ready = tray.start(icon_file)
        if settings.get("auto_start_monitoring", False):
            try:
                controller.start_monitoring()
            except Exception:
                LOG.exception("Automatic monitoring startup failed")
        launch_to_tray = bool(args.tray or settings.get("start_minimized", False))
        if launch_to_tray and not tray_ready:
            if args.no_browser:
                raise RuntimeError("System tray initialization failed and --no-browser prevents dashboard fallback.")
            LOG.warning("System tray unavailable; opening dashboard instead of hiding the application.")
            import webbrowser
            webbrowser.open(url)
        elif not args.no_browser and not launch_to_tray and bool(settings.get("open_dashboard_on_start", True)):
            import webbrowser
            webbrowser.open(url)
        LOG.info("OrganizePro is running. Dashboard: %s", url)
        try:
            signal.signal(signal.SIGINT, stop_app); signal.signal(signal.SIGTERM, stop_app)
        except ValueError:
            pass
        shutdown.wait()
        return 0
    except KeyboardInterrupt:
        stop_app(); return 0
    except Exception:
        LOG.exception("Application startup failed")
        stop_app(); return 1
    finally:
        if not stopped:
            stop_app()


def main(argv: list[str] | None = None) -> int:
    return run_app(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
