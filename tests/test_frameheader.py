"""Tests for the FITS header cards of the module and the GUI."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest
from pyobs.images import Image
from pyobs.modules.camera import BaseVideo
from pyobs.utils.enums import ImageType

from pyobs_aravis import AravisCamera


@pytest.mark.asyncio
async def test_module_header_has_instrument_gain_and_trigger_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    # AravisCamera.__init__ imports gi/Aravis, unavailable here
    camera = AravisCamera.__new__(AravisCamera)
    camera._camera_device_name = "cam0"
    camera._settings = {"Gain": 12.0, "TriggerMode": "On"}
    monkeypatch.setattr(BaseVideo, "_finish_image", AsyncMock(side_effect=lambda image, *a: (image, "x")))

    image, _ = await camera._finish_image(Image(np.zeros((2, 2), dtype=np.uint8)), False, ImageType.OBJECT)

    h = image.header
    assert h["INSTRUME"] == "cam0" and h["GAIN"] == 12.0 and h["TRIGMODE"] == "On"
    assert "XBINNING" not in h


def test_gui_header_has_exposure_time_and_gain() -> None:
    gui = pytest.importorskip("pyobs_aravis.gui")
    camera = MagicMock()
    camera.get_exposure_time.return_value = 20000.0
    camera.get_feature.return_value = 4.0
    h = gui.make_header(camera, "cam0", np.array([[1, 2], [3, 6]], dtype=np.uint8))
    assert h["EXPTIME"] == 0.02 and h["GAIN"] == 4.0 and h["INSTRUME"] == "cam0"
    assert "DATE-OBS" not in h and h["DATAMAX"] == 6.0


def test_gui_header_without_gain_feature() -> None:
    gui = pytest.importorskip("pyobs_aravis.gui")
    camera = MagicMock()
    camera.get_exposure_time.return_value = 20000.0
    camera.get_feature.side_effect = KeyError("Gain")
    h = gui.make_header(camera, "cam0", np.zeros((2, 2), dtype=np.uint8))
    assert "GAIN" not in h
