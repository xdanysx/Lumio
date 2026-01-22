# focus_lock.py
from __future__ import annotations

from typing import List, Optional, cast

from PySide6.QtCore import Qt, QTimer, QObject
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QWidget


class BlackOverlay(QWidget):
    def __init__(self, screen, parent=None):
        super().__init__(parent)
        self._screen = screen
        self.setWindowTitle("Focus Overlay")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setWindowFlag(Qt.WindowType.Tool, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setStyleSheet("background: black;")

    def show_on_screen(self):
        geo = self._screen.geometry()
        self.setGeometry(geo)
        self.show()
        self.raise_()


class FocusLockManager(QObject):
    def __init__(self, main_window, enabled: bool = False, reactivate_minutes: int = 5):
        super().__init__(main_window)
        self.main_window = main_window
        self.enabled = enabled
        self.reactivate_ms = int(reactivate_minutes * 60 * 1000)

        self._overlays: List[BlackOverlay] = []
        self._lock_active = False

        self._reactivate_timer = QTimer(self)
        self._reactivate_timer.setSingleShot(True)
        self._reactivate_timer.timeout.connect(self._on_reactivate_timeout)

        app = QGuiApplication.instance()
        if app is not None:
            gui_app = cast(QGuiApplication, app)
            gui_app.applicationStateChanged.connect(self._on_app_state_changed)

    def set_enabled(self, enabled: bool):
        self.enabled = enabled
        if not enabled:
            self.disable_lock()

    def enable_lock(self):
        if not self.enabled or self._lock_active:
            return
        self._lock_active = True
        self._reactivate_timer.stop()

        self._destroy_overlays()
        for screen in QGuiApplication.screens():
            ov = BlackOverlay(screen)
            ov.show_on_screen()
            self._overlays.append(ov)

        self.main_window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()

    def disable_lock(self):
        if not self._lock_active:
            self._reactivate_timer.stop()
            return
        self._lock_active = False
        self._reactivate_timer.stop()
        self._destroy_overlays()

        self.main_window.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, False)
        self.main_window.show()

    def schedule_reactivate_if_inactive(self):
        if not self.enabled:
            return
        self._reactivate_timer.start(self.reactivate_ms)

    def cancel_reactivate(self):
        self._reactivate_timer.stop()

    def _on_reactivate_timeout(self):
        app = QGuiApplication.instance()
        if app is None:
            return

        gui_app = cast(QGuiApplication, app)
        if gui_app.applicationState() != Qt.ApplicationState.ApplicationActive:
            self.enable_lock()

    def _on_app_state_changed(self, state: Qt.ApplicationState):
        if state == Qt.ApplicationState.ApplicationActive:
            self.cancel_reactivate()

    def _destroy_overlays(self):
        for ov in self._overlays:
            try:
                ov.hide()
                ov.deleteLater()
            except Exception:
                pass
        self._overlays = []
