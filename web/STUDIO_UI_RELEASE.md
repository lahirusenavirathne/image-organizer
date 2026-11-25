# Photo Studio UI Refresh — Web v0.9.1

This is a **staging UI redesign**, based on Photo Studio Phase 2A. It is not a screenshot-to-code pixel-exact conversion of the earlier generic visual references. It is a working UI with a neutral charcoal professional-editing layout.

## Changed

- Compact dark photo editing toolbar and full image-first workspace.
- Persistent RGB histogram and adjustment tabs on desktop; Light / Color / Crop / Detail panels are easy to reach.
- Color picker shows one of eight HSL color families at a time.
- Tone curve and color controls use a more neutral visual language.
- The editor retains Save adjustments, Save as copy, Download edited copy, Undo/Redo, manual crop, fine straighten, before/after, presets, and quality settings.
- No backend schema, authentication, or original photograph changes.

## Deploy to DreamHost staging

From the existing Git checkout:

```sh
cd /home/glphoto/glphoto
git status --short
git fetch origin
git switch feature/photo-editor-phase2-v0.9
git pull --ff-only origin feature/photo-editor-phase2-v0.9
cat web/VERSION
```

Expected: `web-0.9.1-studio-ui`. Existing users may need Ctrl+Shift+R to refresh styles and scripts.

## QA performed

- 16 PHP unit suites passed; 49 PHP files linted successfully; JavaScript syntax checks passed.
- Isolated Chromium browser tests passed at 390, 722, 1024, 1440 and 1600 px.
- Verified that Light/Color/Crop/Detail tabs open and close their intended panels, HSL color chips select the matching family, Undo works, RGB histogram updates, and no horizontal overflow occurs.
- Screenshots are from an actual browser rendering of the new UI with a mock preview image, **not** the live DreamHost website.

## Staging verification still required

- Use actual photos on DreamHost and verify PHP GD preview, recipe persistence and Save as copy with the private MySQL catalog.
- Check browser sizing against your preferred exact reference. Re-upload the reference screenshot if pixel-close matching is essential.
