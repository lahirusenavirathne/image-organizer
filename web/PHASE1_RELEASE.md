# Guia Lanka Photo Studio — Phase 1A staging update (web-0.8.0-phase1a)

The first editing-workflow milestone implements Undo/Redo, zoom/pan, before/after split comparison, browser-local custom presets, and JPEG/WebP quality for both Download edited copy and Save as copy.

## Safe rollout on DreamHost

1. Back up the MySQL database and web/private (including original photographs).
2. Use a staging checkout and staging database. No schema migration is needed for Phase 1A.
3. Check that PHP GD is installed and supports JPEG and WebP.
4. Open a test photo, adjust its tone, press Undo and Redo, inspect with Zoom and drag-to-pan.
5. Turn on Before/After and drag the comparison slider. Crop and rotate are aligned, but tonal edits are omitted in the before layer.
6. Create a named local preset, apply it, and reload the page to confirm it remains in this browser. These presets are not stored in the database or synced across devices.
7. Export a JPEG and WebP at 40 and 95 quality and compare sizes. Test Save as copy and verify it inserts a new library photo while leaving the original unchanged.
8. Confirm a Viewer cannot access the editor or its action endpoint, and that CSRF is required.
9. Confirm older saved recipe settings load normally.

## In this release

- Undo/Redo: undo stack up to 100 recipe snapshots, hotkeys Ctrl/Cmd+Z and Ctrl+Y/Cmd+Shift+Z, grouped slider drags
- Zoom/pan: Fit, 150%, 200%, 300%; pointer dragging is visual only and not saved to the edit recipe
- Before/after: privately server-rendered original tones with the same crop and rotation as the edited preview; split slider
- Custom presets: up to 10 named recipes saved to this browser's localStorage
- Export quality: JPEG/WebP quality 40–100; PNG remains lossless
- No database schema changes or original-file modifications

## Remains in Phase 1

Interactive crop boundary dragging, free-form crop and arbitrary-angle straighten. The existing center crop/90-degree rotate are unchanged.

## Verification limits

All available PHP unit tests and PHP/JS syntax checks passed. GD rendering, MySQL transactions, and an authenticated DreamHost browser session could not be tested in this environment. Verify on staging before a live deployment.
