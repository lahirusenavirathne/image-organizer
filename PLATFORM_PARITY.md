# Desktop / DreamHost Web Feature Parity Policy

**Companion versions:** Windows desktop `1.0.0-rc5`, DreamHost web `web-0.3.0` (web release currently in staging branch).

## Two products, matching user workflows

| Workflow | Windows desktop rc5 | DreamHost PHP web v0.3 |
|---|---|---|
| Password-protected access / team roles | Local Windows account; no web roles | Admin / Editor / Viewer sign-in |
| Import folders with subfolders | Yes, indexes existing files without moving them | Yes, uploads copies into private web storage |
| Browse nested folders / breadcrumbs | Yes, SQLite virtual folders | Yes, MySQL virtual folders |
| Search, sort, grid/list, recent | Yes | Yes |
| Star / favorites | Yes | See v0.3 web release features |
| Rename, move, copy | Virtual display rename, virtual move, physical copies in app directory | Web-managed operations |
| Trash, restore, remove from catalog | Yes; NEVER unlinks external originals | Web-managed Trash and permanent deletion |
| Download / export | Save untouched originals; WebP/JPEG/PNG/TIFF and CSV | Download original; WebP/JPEG/PNG and ZIP manifest |
| Local OpenCLIP visual matching | Yes | No; hash-based image matching only |
| Face grouping | Yes, offline | Not included |
| Web sharing, team accounts, audit | Not yet applicable to offline desktop | User roles; richer sharing later |
| Automatic library synchronization | **Not implemented** | **Not implemented** |

### Critical behavior differences

- **Offline local files:** The desktop application keeps the user's original paths untouched. Drive folders are stored as catalog metadata in local SQLite. Deleting from Trash removes catalog records, not image bytes on disk. Only explicitly requested copies are created under `%LOCALAPPDATA%/GuiaLankaPhotoManager/managed_copies`.
- **Hosted files:** The web edition stores images in DreamHost private storage and uses MySQL. It is a **different library**, even when file and folder labels match.
- **No silent network access:** Desktop recognition is offline by default. No automatic uploads of client or guest images and no copying of web passwords into the desktop app.
- **No automatic sync:** Moving a photo into an offline desktop folder does not update the website, and changing a web folder does not change a Windows folder.
- **Future synchronization:** Needs versioned authenticated API tokens with revocation, client-side opt-in per local folder, content hashes, resumable upload/download, conflict resolution, deletion tombstones, and per-user audit records. A simple `git pull` updates *application source*, not photo libraries.

## Rules for future changes

1. For any shared capability, assess both desktop and web implementations; update their release notes and parity table together.
2. Keep authentication, storage and image processing platform-specific where justified, but provide equivalent user-facing commands where feasible.
3. Never equate feature parity with data synchronization. Obtain explicit consent before any guest photos or metadata leave the local machine.
4. Add tests for import, folder hierarchy, copy, Trash / restore, permissions, and backup/rollback considerations.
5. Avoid automatic physical deletes or unreviewed modifications to originals.

## Windows upgrade

Back up `%LOCALAPPDATA%/GuiaLankaPhotoManager/` including the SQLite database. Keep your photo source directory backup. Extract rc5 to `C:\GLPhoto` (replace app code, not the data directory) and run `START_WINDOWS.bat`. Existing AI packages can be reused. The first launch performs additive SQLite schema migration for desktop virtual folders and Trash. Desktop Qt UI needs Windows testing before production rollout.
