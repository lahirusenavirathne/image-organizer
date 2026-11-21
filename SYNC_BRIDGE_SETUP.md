# Additive two-way selected-folder sync — Windows rc7 / DreamHost Web v0.5 (staging)

## Prerequisites

1. Leave the production website unchanged. Install/verify DreamHost web v0.5 with API v1
   on a *staging* subdomain, separate MySQL database and private photo store.
2. Back up `%LOCALAPPDATA%\GuiaLankaPhotoManager` and all source photos.
3. Update the desktop source in `C:\GLPhoto`, run `INSTALL_WINDOWS.bat` if needed
   for the keyring dependency, then run `START_WINDOWS.bat`.
4. Create a short-lived **write-scoped** token from the staging app's
   `/api-tokens.php` page. Never paste a real token into chat or GitHub.

## Select precisely which folders are eligible

1. In desktop My Drive, import some test folders if needed. Root-level unfiled
   photos are *not* part of the selective-sync scope.
2. Open **More → DreamHost Web API → Sync selected folders (Windows ↔ Web)**.
   Check ONLY the local folders you want to transfer. A checked folder includes
   its descendants; unselected sibling/ancestor photos are never uploaded.
3. Enter the staging web app URL and write token. Choose the **remote parent folder
   ID** where the selected trees will be created (`0` means My Drive root).
4. Review the confirmation list of selected folders and accept to upload the first
   up-to-20-transfer batch. Uploads run first; remaining quota can download
   web-only photographs from those same selected folder trees. No deletions or replacements.
5. To transfer remaining eligible uploads or web-only photos, choose **Continue selected-folder sync**.
   The same selection is reused; no unselected folders are considered. You will
   confirm every additional batch. A separate batch may create additional web
   subfolders when those paths are needed.
6. Inspect web folders, photo counts and filenames after each batch. If an unchanged
   file already transferred, it is skipped. Conflicts must be reviewed manually.
7. To change the scope, return to **Choose folders and sync to web** and change
   the checkboxes. The previous scope is not a persistent permission grant to a
   background process; syncing only occurs on explicit clicks.

## Operational limitations

- This version can download web-only photos within chosen trees, but does not mirror removals, update cloud metadata,
  or rename prior web folders after local renames/moves. Downloaded originals are
  stored under `web_sync_downloads/` in the Windows app data folder, not copied over source files.
- Same-named destination folders are reused; choose a dedicated web parent to
  avoid mixing desktop uploads with other users' files.
- An edited photo using an already occupied filename will generate a conflict,
  not silently overwrite the web original.
- Only JPEG/PNG/WebP files up to 25 MiB can transfer; up to 20 transfers per manually
  confirmed action. Unsupported photos are skipped. Local SQLite retains
  success/failure checkpoints, not the token or photo content.
- Live DreamHost/PySide6 testing is required before a production release.
