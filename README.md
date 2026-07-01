*pyobs* for Aravis cameras
==========================

This is a [pyobs](https://www.pyobs.org) module for cameras supported by the
[Aravis](https://github.com/AravisProject/aravis) library (GenICam/GigE Vision/USB3 Vision cameras).


System dependencies
--------------------
Aravis and its GObject introspection bindings are not pip-installable, so they need to be installed via your
system's package manager before installing *pyobs-aravis*.

On Debian/Ubuntu:

    sudo apt-get install python3-gi python3-gi-cairo gir1.2-aravis-0.8

This provides:
* **Aravis** itself, together with its GObject introspection typelib (`gir1.2-aravis-0.8`).
* **PyGObject** (`python3-gi`, `python3-gi-cairo`), the `gi` module used to access Aravis from Python.

Since these packages are installed system-wide, your virtual environment needs access to the system
site-packages so it can find the `gi` module.


Install *pyobs-aravis*
-----------------------
Clone the repository:

    git clone https://github.com/pyobs/pyobs-aravis.git
    cd pyobs-aravis

Create a virtual environment with access to the system site-packages and install the package with
[uv](https://docs.astral.sh/uv/):

    uv venv --system-site-packages
    uv sync

Alternatively, with plain `venv`/`pip`:

    python3 -m venv --system-site-packages .venv
    source .venv/bin/activate
    pip install .


GUI
---
For testing a camera without a full *pyobs* setup, install the optional `gui` extra:

    uv sync --system-site-packages --extra gui

and run:

    uv run aravis-gui


Dependencies
------------
* [pyobs-core](https://github.com/pyobs/pyobs-core) for the core functionality.
* [numpy](https://numpy.org/) for handling image data.
* [Aravis](https://github.com/AravisProject/aravis) and [PyGObject](https://pygobject.readthedocs.io/) for
  accessing the camera, installed via the system's package manager (see above).
