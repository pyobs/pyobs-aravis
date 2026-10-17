# Design/planning docs

Layout mirrors `pyobs-core`'s `specs/`. Docs that span `pyobs-core` and this repo live in
`pyobs-core`'s `specs/` and are listed at the bottom.

## Plans

- [plans/2026-09-29-frames-migration.md](plans/2026-09-29-frames-migration.md):
  **implemented** (released in v2.1.0, refined in v2.1.2). Moved `AravisCamera` from the deprecated
  `_set_image()` shim to `BaseVideo.frames()`: one reader thread per activation, settings-generation
  bump on every image-affecting setting, estimated start times. Settings are applied while streaming
  (restart only as fallback). Breaking for subclasses that override `_capture()`. Phase 0 hardware
  checks and device timestamps still open.

## Specs in `pyobs-core` about `pyobs-aravis`

- `pyobs-core/specs/design/basevideo-frame-source.md`: the `frames()` contract this repo
  migrates to (step 2 of its migration order).
