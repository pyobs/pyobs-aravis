import logging
import numpy as np
import threading
from datetime import datetime
import time
from typing import Tuple
import aravis

from pyobs.modules.camera import BaseWebcam
from pyobs.images import Image
from pyobs.utils.enums import ExposureStatus


log = logging.getLogger(__name__)


class AravisCamera(BaseWebcam):
    """A pyobs module for Aravis cameras."""
    __module__ = 'pyobs_aravis'

    def __init__(self, device: str, *args, **kwargs):
        """Initializes a new AravisCamera.

        Args:
            device: Name of camera to connect to.
        """
        BaseWebcam.__init__(self, *args, **kwargs)

        # variables
        self._device_name = device
        self._camera = None

        # thread
        self.add_thread_func(self._capture)

    def open(self):
        """Open module."""
        BaseWebcam.open(self)

        # list devices
        ids = aravis.get_device_ids()
        if self._device_name not in ids:
            raise ValueError('Could not find given device name in list of available cameras.')

    def close(self):
        """Close the module."""
        BaseWebcam.close(self)

        # stop camera
        self._camera.stop_acquisition()
        self._camera.shutdown()

    def _capture(self):
        # open camera
        self._camera = aravis.Camera(self._device_name)

        # start acquisition
        self._camera.start_acquisition_continuous(nb_buffers=2)

        # loop until closing
        last = time.time()
        while not self.closing.is_set():
            # read frame
            frame = self._camera.pop_frame()

            # if time since last image is too short, wait a little
            if time.time() - last < self._interval:
                self.closing.wait(0.01)
                continue
            last = time.time()

            # process it
            self._set_image(frame)

        # release camera
        self._camera.stop_acquisition()


__all__ = ['AravisCamera']
