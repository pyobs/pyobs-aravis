# Design/planning docs

Layout mirrors `pyobs-core`'s `specs/`. Docs that span `pyobs-core` and this repo live in
`pyobs-core`'s `specs/` and are listed at the bottom.

## Plans

- [plans/2026-09-29-frames-migration.md](plans/2026-09-29-frames-migration.md):
  **proposed, not started**. Move `AravisCamera` from the deprecated `_set_image()` shim to
  `BaseVideo.frames()`: one reader thread per activation, acquisition restart plus
  settings-generation bump on every image-affecting setting, estimated start times until a
  hardware check shows device timestamps are usable. Breaking for subclasses that override
  `_capture()`.

## Specs in `pyobs-core` about `pyobs-aravis`

- `pyobs-core/specs/design/basevideo-frame-source.md`: the `frames()` contract this repo
  migrates to (step 2 of its migration order).
