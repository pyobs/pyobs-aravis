import asyncio
import sys
from typing import Any

import qasync  # type: ignore
from astropy.io import fits
from numpy.typing import NDArray
from pyobs.utils.gui.camera import DataDisplayWidget, ExposeWidget, ExposureTimeWidget, ListPickerDialog
from PySide6 import QtWidgets  # type: ignore[import-untyped]

from . import aravis


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, device: str) -> None:
        super().__init__()
        self.setWindowTitle(f"Aravis Camera — {device}")

        self.camera = aravis.Camera(device)
        self.camera.start_acquisition_continuous()

        self._last_frame: NDArray[Any] | None = None
        self._preview_task: asyncio.Task[None] | None = None

        self.central_widget = QtWidgets.QWidget()
        self.setCentralWidget(self.central_widget)
        layout = QtWidgets.QHBoxLayout(self.central_widget)

        controls = QtWidgets.QGroupBox("Camera")
        controls_layout = QtWidgets.QVBoxLayout(controls)
        self.exposure_time = ExposureTimeWidget()
        self.exposure_time.spin_exposure_time.setValue(self.camera.get_exposure_time() / 1e6)
        self.exposure_time.exposure_time_changed.connect(self._exposure_time_changed)
        controls_layout.addWidget(self.exposure_time)
        self.expose = ExposeWidget(can_abort_exposure=False)
        controls_layout.addWidget(self.expose)
        controls_layout.addStretch()
        layout.addWidget(controls)

        self.display = DataDisplayWidget()
        layout.addWidget(self.display)

        self.expose.expose_clicked.connect(self._expose_clicked)

        self._preview_task = asyncio.ensure_future(self._live_preview())

    def _exposure_time_changed(self, value: float) -> None:
        self.camera.set_exposure_time(value * 1e6)

    async def _live_preview(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            self._last_frame = await loop.run_in_executor(None, self.camera.pop_frame)  # type: ignore
            self.display.set_data(fits.PrimaryHDU(self._last_frame))
            await asyncio.sleep(0.05)

    @qasync.asyncSlot(int)  # type: ignore
    async def _expose_clicked(self, count: int) -> None:
        self.expose.start_exposure(self.exposure_time.value)
        loop = asyncio.get_running_loop()
        for _ in range(count):
            self._last_frame = await loop.run_in_executor(None, self.camera.pop_frame)  # type: ignore
        if self._last_frame is not None:
            self.display.set_data(fits.PrimaryHDU(self._last_frame))
        self.expose.set_exposures_left()

    def closeEvent(self, event: Any) -> None:
        if self._preview_task is not None:
            self._preview_task.cancel()
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
