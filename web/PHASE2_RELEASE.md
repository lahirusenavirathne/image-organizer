# Phase 2A — Professional Tone & Color (DreamHost staging)

**Version:** `web-0.9.0-phase2a`. Includes Phase 1B interactive crop/straighten, previous upload, metadata, undo/redo, presets, and Save as copy.

## Included

- Live RGB histogram and approximate black/white clipping percentages from rendered preview (computed **within the logged-in browser**, not uploaded separately).
- White and black points; smooth parametric tone curve with separate shadow/midtone/highlight adjustments.
- Temperature (existing Warmth) plus new green/magenta Tint; Vibrance preserving previously saturated areas.
- Independent hue/saturation/luminance for Red, Orange, Yellow, Green, Cyan, Blue, Purple and Magenta. Color-family boundaries feather together; changes do not invent detail.
- Neutral defaults exactly match the old recipe values; saved recipes, local presets, comparison, downloads and Save as copy continue to work.

## Not yet included

- True detail processing: clarity, texture and dedicated luminance/chroma noise reduction (Phase 2B).
- White balance neutral-point picker and high-precision color-managed output.
- Editable per-channel RGB curves and RAW image support.

## Deployment

1. Back up production/source, private originals, thumbnails and database. **Use staging initially**, not your live Photo Manager.
2. SSH into DreamHost and update from the feature branch after its GitHub commit has been published. Check `cat web/VERSION`.
3. No database migration is required. The existing `photo_edit_recipes.recipe_json` column remains compatible.
4. Sign in as Editor/Admin. Test old saved Phase 1B crop and color edits; test a green/wildlife image, blue-sky image, and low-light image. Exercise histogram, curve sliders and selected HSL channels.
5. Test Save adjustments, reload, Undo/Redo, preset save/apply, Before/After, Download edited copy, and Save as copy. Verify saved copy differs from the original and the original hash is unchanged.
6. Monitor PHP error logs and process time for large exports on shared hosting. Keep export within existing 2.5 MP cap and avoid excessively large image batches.

## QA limitations

- Automated PHP unit tests and syntax checks can run locally.
- The local CLI does not include PHP GD or MySQL; **actual PHP image rendering and the MySQL save path must be verified on DreamHost staging**.
- The browser histogram is sampled from the rendered preview and is indicative, not an ICC-profile-aware histogram.
