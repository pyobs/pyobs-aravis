# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Entries for releases before this file existed were generated from commit subjects.

## [2.1.2] - 2026-09-29

- Change settings during acquisition without restarting it

## [2.1.1] - 2026-09-29

- Stop frames() from hanging forever when the reader thread fails

## [2.1.0] - 2026-09-29

- Migrate AravisCamera to BaseVideo.frames()
- specs: plan for migrating AravisCamera to BaseVideo.frames()
- Stop _wait_for_frame from leaking a polling thread on every timeout (#56)

## [2.0.4] - 2026-09-28

- Maintenance release (dependency and metadata updates only).

## [2.0.3] - 2026-09-28

- Add IResettable.reset() override to restore exposure time
- Deliver every frame to _set_image() instead of throttling in _capture()

## [2.0.2] - 2026-09-03

- Add INSTRUME/GAIN/TRIGMODE FITS headers (#872)

## [2.0.1] - 2026-09-01

- Maintenance release (dependency and metadata updates only).

## [2.0.0] - 2026-08-26

- Require stable pyobs-core>=2.0.0
- Gate auto-merge on the PR author, not the event actor
- Enable Dependabot auto-merge for patch/minor updates
- Camera driver/GUI split: offload sync SDK calls, locking, socket + pixel-format fixes (#41)
- Guard Camera stream access against concurrent shutdown()
- Allow connecting to a camera by IP without broadcast discovery
- pyrefly: exclude gui.py from type checking
- Add baseline test suite and CI (pytest, pyrefly), grouped Dependabot
- Upgrade uv.lock to clear open Dependabot alerts
- Require pyobs-core>=2.0.0.dev48
- Add dependabot.yml, targeting develop for PRs
- Publish initial IExposureTime state at open(), like IGain already does
- Drop the <3.14 upper bound on requires-python
- Don't let a slow/hung pop_frame() call freeze the module's event loop
- Don't let blocking device discovery freeze the module's event loop
- Don't let a hung camera SDK call freeze the whole module
- Stop clobbering Module.name with the camera's device string
- Don't let a failed camera shutdown leave the module stuck
- Cache exposure time on AravisCamera so it's readable after being set
- Fix docs example config and add missing requirements.txt
- Document the aravis-gui script in the README
- Add GUI script for Aravis cameras
- Fix ruff workflow failing when .venv already exists
- Switch PyGObject to a system dependency and update README
- migrated to Ruff and updated modules to pyobs 2.0 API
- add ruff workflow

## [1.2.1] - 2026-07-09

- Maintenance release (dependency and metadata updates only).

## [1.1.4] - 2025-08-07

- ignore exceptions
- new lock file

## [1.1.3] - 2025-07-07

- .

## [1.1.2] - 2025-07-07

- fixed bug

## [1.1.1] - 2025-07-07

- migrated to uv

## [1.1.0] - 2025-07-07

- migrated to uv

## [1.0.0] - 2022-09-13

- added license
- example config
- moved import of aravis into methods
- added apt package
- fixed rtd
- basic docs

## [0.15.3] - 2022-01-07

- Pop frame from camera every loop

## [0.15.2] - 2022-01-06

- some fixes
- added black and pre-commit to dev dependencies
- added .pre-commit-config.yaml
- running black

## [0.15.1] - 2021-12-30

- async

## [0.15.0] - 2021-12-29

- changed used Python version to 3.9
- Pushed requirements to Python>=3.9 and astropy>=5.0, closes #55
- removed self.closing in all Modules
- renamed github secret var

## [0.14.1] - 2021-11-29

- fixed bug with race condition
- implemented sleep mechanism for video devices
- logging
- moved some code
- poetry and github action
- v0.14
- Added type hints
- more logging
- force version again
- removed Aravis version requirement
- init _settings as {} if None are given
- renamed ICameraExposureTime to IExposureTime
- Aravis settings in yaml
- copied aravis.py from repo into here
- cleanup
- if no device is given, module starts anyway. Helpful for testing
- renamed IWebcam->IVideo and BaseWebcam->BaseVideo
- added get/set_exposure_time
- removed unused imports
- first commit
