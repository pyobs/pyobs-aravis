"""Smoke tests: importing the package must not require gi/Aravis; instantiating the
driver does (AravisCamera.__init__ pulls in the vendored aravis.py -> gi -> Aravis
typelib), so the instantiate test skips when gi isn't available.

In CI the pytest workflow installs python3-gi + gir1.2-aravis-0.8 (mirroring
ruff.yml), so the instantiate test actually runs there.
"""

import pytest
from pyobs.interfaces import IExposureTime, IVideo
from pyobs.modules import Module

from pyobs_aravis import AravisCamera


def test_import_module_without_native() -> None:
    assert AravisCamera is not None


def test_instantiate_camera() -> None:
    pytest.importorskip("gi")

    camera = AravisCamera(device="test-camera")
    assert isinstance(camera, Module)
    assert isinstance(camera, IExposureTime)
    assert isinstance(camera, IVideo)
