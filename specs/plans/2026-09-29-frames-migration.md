# AravisCamera: migrate to `BaseVideo.frames()`

Status: proposed (2026-09-29). Not started.

Needs pyobs-core `>=2.13.0` (`frames()`, `Frame`, `_new_generation()`, PR #926). No pyobs-core
changes.

Related: pyobs-core `specs/design/basevideo-frame-source.md` (the `frames()` contract, step 2 of
its migration order), issue #56.

## Problem

`AravisCamera` still runs its own `_capture()` loop and pushes frames via the deprecated
`_set_image()` shim. With pyobs-core 2.13.0 that means:

1. **No real exposure start.** The shim only estimates it from `_exposure_time`
   (`start_source=estimated`).
2. **No settings generation.** `AravisCamera` never calls `_new_generation()`, so every frame gets
   generation 0 and the `generation` check in `BaseVideo._started_after()` always passes. The
   time check alone is not enough when the exposure time goes *down*: switch 10s -> 0.1s at t0,
   an old 10s frame started at t0-5 arrives at t0+5, gets an estimated start of t0+4.9 (the
   estimate uses the *new* `_exposure_time`) and is accepted as a new-settings frame. Same gap for
   `grab_stack()`'s "generation changed mid-stack" check.
3. **Thread-per-frame polling.** `_wait_for_frame()` spawns one daemon thread per delivered frame.
   The leak itself (#56) is fixed separately (stop flag, see Prerequisites), but a thread stuck
   *inside* `try_pop_frame()` still holds `_device_lock`, and every later poll thread piles up
   behind it.
4. **Deprecation warning** on every module start.

## Prerequisites

- #56 fix in `_wait_for_frame()`/`_run_blocking()` plus tests (done, uncommitted as of
  2026-09-29). Worth releasing on its own before this plan.

## Design decisions

1. **One long-lived reader thread per activation, not one per frame.** `frames()` starts a daemon
   thread that polls `try_pop_frame()` under `_device_lock` and hands frames to the event loop
   via `loop.call_soon_threadsafe()` into a small `asyncio.Queue`. The `finally` of `frames()`
   sets a stop event and does not join (a hung SDK call must not block deactivation). At most one
   stuck thread per activation, instead of one per poll.
2. **Acquisition moves into `frames()`**, per the core contract: `start_acquisition_continuous()`
   at the top, `stop_acquisition()` in `finally`. `_open_camera()` only connects and applies
   `settings`. A crash in `frames()` then gets a clean acquisition restart via `BaseVideo`'s
   back-off loop.
3. **Settings changes restart acquisition** (stop, set, flush queued buffers, start), then bump the
   generation. That's the only deterministic way to know which frames were taken with the new
   settings without per-frame chunk data: the stream holds up to `buffers` (default 5) frames
   exposed with the old settings, plus the one currently exposing. Cost is one restart per change
   (duration unknown, measure in Phase 0). Rejected: on-the-fly change plus time-based skipping,
   which needs trustworthy start times (see 5) and is fragile with queued buffers.
4. **Generation is stamped at pop time, bumped after the restart.** The reader reads
   `self._generation` when it pops a frame. The setter bumps it on the event loop after the
   restart returns. Frames popped between restart and bump get the old generation, which is
   conservative (one extra frame skipped), never wrong.
5. **Start times: `estimated` by default.** `ArvBuffer.get_timestamp()` is, as far as I know, the
   camera's own clock (ns since power-on or since the last timestamp reset) unless the camera
   runs PTP, and the point in the exposure where it's latched is model-dependent (**unverified**).
   So `Frame.start=None`, and `exposure_time` is the value **read back** from the camera after
   setting it (cameras quantize), not the requested one. Device timestamps are Phase 3, only if
   Phase 0 shows they're usable.
6. **Every image-affecting setting bumps the generation.** In `AravisCamera` that's
   `set_exposure_time()` and a (re)connect with `settings` applied (bump in `_activate_camera()`).
   A helper `_apply_settings(func)` does lock + restart + `func()` + read back + bump, so
   subclasses with their own setters (gain, ROI, ...) use it instead of calling `set_feature`
   directly.
7. **Breaking change for subclasses.** `_capture()` and `_wait_for_frame()` go away, and so does
   the `add_background_task(self._capture)` registration. A subclass that overrides `_capture()`
   would silently stop running its loop (no error). Such subclasses must move to a `frames()`
   override that wraps `super().frames()`. Note this in the changelog, and consider a check in
   `__init__` that logs an error if `type(self)._capture` is overridden.

## Phase 0: hardware check (before coding)

- [ ] Time an acquisition restart (stop, set `ExposureTime`, start, first frame) on real
      cameras. If it's seconds rather than ~100ms, revisit decision 3.
- [ ] Check whether the cameras expose PTP (`arv-tool-0.8 -a <ip> features | grep -i -E
      "ptp|1588"`), and compare `buf.get_timestamp()` / `buf.get_system_timestamp()` against host
      time over a few minutes (offset, drift). Result decides whether Phase 3 happens.
- [ ] Confirm whether the `ExposureTime` read-back differs from the requested value
      (quantization), to know whether decision 5's read-back matters in practice.

## Phase 1: implementation

- [ ] Bump pin to `pyobs-core>=2.13.0`.
- [ ] `_open_camera()`: drop `start_acquisition_continuous()`.
- [ ] New `async def frames()`: start acquisition (via `_run_blocking`, under `_device_lock`),
      start the reader thread, `yield Frame(data, start=None, exposure_time=<read-back>,
      generation=<stamped at pop>)` from the queue; `finally`: stop event, `stop_acquisition()`
      via `_run_blocking` (timeout logged, not raised).
- [ ] Reader thread: poll `try_pop_frame()` under `_device_lock`, 10ms sleep when empty, exit on
      stop event or `self._camera is None`. Queue bounded (e.g. `maxsize=buffers`), drop oldest
      when full, so a stalled event loop can't grow memory. (`_array_from_buffer_address()`
      already copies before the buffer is pushed back, so ownership per the core contract is
      fine.)
- [ ] No-frame watchdog: log a warning after `_FRAME_WAIT_TIMEOUT` without frames (keeps
      today's "Timed out waiting for a frame" signal), don't raise.
- [ ] `_apply_settings(func)` helper (decision 6); `set_exposure_time()` uses it; bump generation
      in `_activate_camera()` after connect.
- [ ] Delete `_capture()`, `_wait_for_frame()`, the `add_background_task(self._capture)`
      registration and the per-frame use of `_run_blocking` (keep `_run_blocking` itself for
      one-off SDK calls). Changelog entry for decision 7.
- [ ] Tests (no gi/Aravis, fake camera object like the existing tests): frames delivered in
      order; `aclose()` stops the reader thread (`threading.active_count()` back to baseline);
      `set_exposure_time()` bumps the generation and no frame popped after the bump carries the
      old one; read-back value lands in `Frame.exposure_time`; bounded queue drops oldest.
- [ ] Release, coordinated with downstream subclasses (decision 7).

## Phase 2 (optional, depends on Phase 0): device timestamps

- [ ] If PTP is available or the device clock is stable enough: map `buf.get_timestamp()` to UTC
      (PTP directly, or a latched offset via `GevTimestampControlLatch`/`GevTimestampValue`,
      re-latched periodically) and set `Frame.start`. Update the Aravis row of pyobs-core's
      `basevideo-frame-source.md` with the measured semantics.

## Verification

- [ ] `ruff`/`black`/`pyrefly` clean, full test suite passes.
- [ ] On real hardware: no `_set_image()` deprecation warning; live view and `grab_data()` work;
      after `set_exposure_time()` from long to short, `grab_data()` returns a frame whose `SETGEN`
      header matches the new generation and whose data level matches the new exposure; module
      thread count stays flat over a day (`ls /proc/<pid>/task | wc -l`), including across
      camera sleep/wake cycles; a brief network interruption produces warnings, not thread
      growth.
