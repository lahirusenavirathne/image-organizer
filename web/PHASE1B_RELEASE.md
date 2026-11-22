# Phase 1B — Interactive Crop & Straighten

Development release `web-0.8.1-phase1b`, based on `web-0.8.0-phase1a.1`.

## What changed

- **Edit crop on image** turns on a visible crop rectangle over an uncropped preview. Drag corner handles to resize, or the center to reposition. Keyboard arrow keys work on focused handles (Shift for a larger step). **Done cropping** shows the actual result.
- Aspect presets include original proportions, freeform, square, 4:3, 3:2, 16:9, and 272:300. Selecting a preset resets the manual crop rectangle to the preset-centered area; drag handles to refine it.
- Fine straighten from −15.0° through +15.0° in 0.1-degree increments. Positive values are clockwise. Straightening is applied after the 90°-increment rotation and before crop.
- Crop rectangles use integer thousandths (0..1000) and are validated on the PHP server, remain part of saved non-destructive recipes, and are used by preview, download, and **Save as copy**.
- Older stored recipes use their existing centered-crop semantics without a migration. Before/after previews retain matching geometry.

## DreamHost staging test

1. Back up the repository, MySQL database, and private photo store; use a staging clone and separate database if available.
2. `cd /home/glphoto/glphoto && git fetch origin && git switch feature/photo-editor-phase1-v0.8 && git pull --ff-only`
3. Confirm `cat web/VERSION` is `web-0.8.1-phase1b`, open editor, and hard-refresh.
4. On a landscape test photo, turn on crop mode, drag from all four corners, move the selection and try the keyboard arrows. Switch aspect presets. Click Done cropping.
5. Set straighten to 3.5° and check the preview; undo/redo the adjustment. Reopen edit crop and move/resize; save the recipe, refresh, and verify it remains.
6. Compare before/after and ensure the crop/angle alignment is identical. Export a WebP, then Save as copy, and confirm both have the selected crop and straighten. Confirm the source original remains unchanged.
7. Test a portrait original and a square original; on a mobile-width browser check that handles remain usable. Verify no browser-console or PHP error log errors.
8. Run `php web/tests/editor_crop_unit.php` and the existing PHP unit tests on DreamHost.

**Limits:** PHP GD renders previews at bounded resolution; exports remain limited to 2.5 megapixels for shared hosting. The interactive crop is a straight rectangular region, not perspective correction. Touch and drag need live browser verification.
