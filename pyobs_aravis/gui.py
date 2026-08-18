import asyncio
import sys
import threading
from collections.abc import Callable
from typing import Any, TypeVar

import qasync  # type: ignore
from astropy.io import fits
from numpy.typing import NDArray
from pyobs.utils.gui.camera import DataDisplayWidget, ExposeWidget, ExposureTimeWidget, ListPickerDialog
from PySide6 import QtWidgets  # type: ignore[import-untyped]

from . import aravis

_T = TypeVar("_T")


async def _run_blocking(func: Callable[[], _T]) -> _T:
    """Run a blocking aravis/GLib call in a daemon thread, mirroring AravisCamera._run_blocking.

    The default ThreadPoolExecutor (what run_in_executor(None, ...) uses) is deliberately
    avoided here: its worker threads are non-daemon, so a hung GigE call would block interpreter
    shutdown instead of just this call. A fresh daemon thread per call has the same drawback the
    module accepts for the same reason.
    """
    loop = asyncio.get_running_loop()
    future: asyncio.Future[_T] = loop.create_future()

    def _wrapper() -> None:
        try:
            result = func()
        except BaseException as exc:
            loop.call_soon_threadsafe(future.set_exception, exc)
        else:
            loop.call_soon_threadsafe(future.set_result, result)

    threading.Thread(target=_wrapper, daemon=True).start()
    return await future


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, device: str) -> None:
        super().__init__()
        self.setWindowTitle(f"Aravis Camera — {device}")

        self.camera: aravis.Camera | None = None
        self._last_frame: NDArray[Any] | None = None
        self._preview_task: asyncio.Task[None] | None = None

        self.central_widget = QtWidgets.QWidget()
        self.setCentralWidget(self.central_widget)
        layout = QtWidgets.QHBoxLayout(self.central_widget)

        controls = QtWidgets.QGroupBox("Camera")
        controls_layout = QtWidgets.QVBoxLayout(controls)
        self.exposure_time = ExposureTimeWidget()
        self.exposure_time.exposure_time_changed.connect(self._exposure_time_changed)
        controls_layout.addWidget(self.exposure_time)
        self.expose = ExposeWidget(can_abort_exposure=False)
        controls_layout.addWidget(self.expose)
        controls_layout.addStretch()
        layout.addWidget(controls)

        self.display = DataDisplayWidget()
        layout.addWidget(self.display)

        self.expose.expose_clicked.connect(self._expose_clicked)

        self._init_task = asyncio.ensure_future(self._init_camera(device))

    async def _init_camera(self, device: str) -> None:
        # Camera construction + start_acquisition_continuous are blocking (GigE discovery and
        # handshake can take seconds), so run them off the Qt thread rather than in __init__.
        self.camera = await _run_blocking(lambda: aravis.Camera(device))
        await _run_blocking(self.camera.start_acquisition_continuous)
        exposure_time = await _run_blocking(self.camera.get_exposure_time)
        self.exposure_time.spin_exposure_time.setValue(exposure_time / 1e6)
        self._preview_task = asyncio.ensure_future(self._live_preview())

    @qasync.asyncSlot(float)  # type: ignore
    async def _exposure_time_changed(self, value: float) -> None:
        if self.camera is not None:
            await _run_blocking(lambda: self.camera.set_exposure_time(value * 1e6))

    async def _live_preview(self) -> None:
        while True:
            if self.camera is None:
                await asyncio.sleep(0.05)
                continue
            self._last_frame = await _run_blocking(self.camera.pop_frame)
            self.display.set_data(fits.PrimaryHDU(self._last_frame))
            await asyncio.sleep(0.05)

    @qasync.asyncSlot(int)  # type: ignore
    async def _expose_clicked(self, count: int) -> None:
        if self.camera is None:
            return
        self.expose.start_exposure(self.exposure_time.value)
        for _ in range(count):
            self._last_frame = await _run_blocking(self.camera.pop_frame)
        if self._last_frame is not None:
            self.display.set_data(fits.PrimaryHDU(self._last_frame))
        self.expose.set_exposures_left()

    def closeEvent(self, event: Any) -> None:
        self._init_task.cancel()
        if self._preview_task is not None:
            self._preview_task.cancel()
        if self.camera is not None:
            self.camera.stop_acquisition()
            self.camera.shutdown()
        super().closeEvent(event)


async def async_main(app: QtWidgets.QApplication) -> None:
    devices: list[str] = aravis.get_device_ids()
    if not devices:
        QtWidgets.QMessageBox.critical(None, "Error", "No Aravis devices found.")
        return

    device_picker = ListPickerDialog(devices)
    if device_picker.exec() != QtWidgets.QDialog.DialogCode.Accepted:
        print("No device selected. Exiting...")
        return
    device_name = devices[device_picker.comboBox().currentIndex()]

    app_close_event = asyncio.Event()
    app.aboutToQuit.connect(app_close_event.set)
    window = MainWindow(device_name)
    window.show()
    await app_close_event.wait()


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    with qasync.QEventLoop(app) as loop:
        loop.run_until_complete(async_main(app))


if __name__ == "__main__":
    main()
