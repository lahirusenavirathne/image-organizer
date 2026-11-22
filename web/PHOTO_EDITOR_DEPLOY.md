# Guia Lanka Photo Manager — Photo editor R1 (STAGING)

**Versions:** Windows **1.0.0-rc9**; DreamHost Web **v0.7.0**.

This update builds on Windows rc8 / Web v0.6 (selected-folder metadata synchronization). The existing production installation and GitHub `main` are unchanged. Both applications have a dedicated, non-destructive **single-photo editor**. Edit settings are small JSON recipes rather than altered image originals.

## Capabilities

- 90° rotation; **center-crop presets**: original, square, 4:3, 3:2, 16:9, 272:300.
- Exposure, contrast, highlights, shadows, saturation, warmth and sharpening sliders; before/after preview; reset sliders.
- Save recipe locally to SQLite (Windows) or to MySQL (Web), **without modifying the source**.
- Export an **edited copy** to JPEG, PNG or WebP; Windows accepts up to 8000 px per side / 32 MP; Web is intentionally limited to 2500 px per side / 2.5 MP, suitable for DreamHost shared hosting.
- Web Editor/Admin access and CSRF protection. A per-photo revision check rejects concurrent overwrites of saved recipes.
- The export file is not automatically added to your Drive catalog; it is downloaded or saved separately. Source EXIF metadata remains in the original, but derived copies do not carry full EXIF or rights metadata. Keep the original and its license/provenance record.

**Not included in R1:** freehand crop, healing/retouching, RAW editing, pixel-accurate color matching across Pillow and GD, HDR or ICC-managed color grading, batch application of saved recipes, synchronized edit recipes, or video editing. These are subsequent editor milestones. In particular, Windows and Web share recipe *names and numerical ranges* but their pixel kernels can differ; visually compare an export on both before using it professionally.

## Windows installation and pilot

1. Back up `%LOCALAPPDATA%\GuiaLankaPhotoManager` and all source photos. Close the application.
2. Extract the Windows rc9 ZIP to your application source folder, e.g. `C:\GLPhoto`. Do not delete your existing `%LOCALAPPDATA%` data folder.
3. Run `START_WINDOWS.bat` (`INSTALL_WINDOWS.bat` if base dependencies are missing).
4. Select **one** imported photograph, then **Edit photo** in the toolbar or **More → Edit selected photograph (non-destructive)**.
5. Change crop/rotation/sliders and compare the original. Choose **Save adjustments** to persist recipe only, or **Export edited copy…** to create a new file.
6. For the first test, export a 272 × 300 WebP, re-open the original and compare checksums and pixel dimensions. Test that choosing an existing file path is refused.

## DreamHost staging installation

1. **Back up** MySQL and the entire `web/private/` directory including originals. Use a separate staging domain/database/private photo directory.
2. Deploy Web v0.7 source with `web/public/` as the only publicly accessible document root.
3. Confirm PHP 8.2+ and the GD extension (JPEG, PNG, WebP enabled). Existing migrations from earlier versions may also be required.
4. Run the additive editor migration from the repository root:

   ```sh
   /usr/local/php84/bin/php web/bin/migrate_editor.php
   ```

   Replace `php84` and your working directory with your DreamHost configuration.
5. Sign in as an Editor or Admin. Choose a photo and click **Edit photo** in the details sidebar.
6. Change sliders, use **Show unedited original**, save, reload, and export a 272 × 300 WebP.
7. Test Viewer cannot visit `editor.php` or call `editor_action.php`. Test that editing or exporting a photo in Trash is denied. Verify that an invalid CSRF token is denied.
8. Open the same photo in two browser sessions, save a recipe in the first, then attempt saving in the second; a conflict should be reported until reloaded.
9. Confirm that original image SHA-256 is unchanged and the web photo remains private to authenticated users.

## Validation

- Windows: `PYTHONPATH=. python -m pytest -q` (run from desktop project directory).
- PHP editor logic: `php tests/editor_unit.php` (run from web project directory).
- PHP syntax: `find private public bin tests -name '*.php' -print0 | xargs -0 -n1 php -l`.
- JS syntax: `node --check public/assets/editor.js`.
- Live PHP/GD rendering, MySQL migration, desktop Qt appearance and color fidelity need explicit tests on DreamHost / Windows, not just syntax and mock unit checks.

Do not deploy to `photos.guialankatours.com` or merge into main until those tests are complete.
