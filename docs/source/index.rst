pyobs-aravis
############

This is a `pyobs <https://www.pyobs.org>`_ (`documentation <https://docs.pyobs.org>`_) module for Aravis network
cameras.


Example configuration
*********************

This is an example configuration, tested on a TIS 23GP031::

    class: pyobs_iagvt.fibercamera.FiberCamera
    device: The Imaging Source Europe GmbH-DMK 23GP031-00000000
    centre: [947.0, 839.0]
    rotation: -97.07
    flip: True
    filenames: /camera/pyobs-{DAY-OBS|date:}-{FRAMENUM|string:04d}.fits
    video_path: /camera/video.mjpg

    buffers: 5
    settings:
      Gain: 0
      BlackLevel: 0
      FPS: 15

    # location
    timezone: utc
    location:
      longitude: 9.944333
      latitude: 51.560583
      elevation: 201.

    # communication
    comm:
      jid: test@example.com
      password: ***

    # virtual file system
    vfs:
      class: pyobs.vfs.VirtualFileSystem
      roots:
        cache:
          class: pyobs.vfs.HttpFile
          upload: http://localhost:37075/


Available classes
*****************

There is one single class for Aravis network cameras.

AravisCamera
============
.. autoclass:: pyobs_aravis.AravisCamera
   :members:
   :show-inheritance:
