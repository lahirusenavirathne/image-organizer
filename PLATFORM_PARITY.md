# Desktop and Web Companion Release Policy

**Desktop:** v1.0.0-rc8 (selected-folder hierarchy and blank-only metadata, staging)  
**Web:** v0.6.0 (staging; API v1 metadata_fill)

## Selected-folder synchronization

The Windows desktop client now syncs **only user-selected local virtual folders**,
using upload and original-file download operations from DreamHost API v1. Parent selections include descendants;
choosing a child alone does not include photos from the ancestor or siblings.
Desktop root photos with no local folder are excluded. The user confirms each
20-photo batch. Checked folder IDs and remote parent folder ID are saved without secrets.
No full-library option, automatic background transfer, or deletions are exposed.
Web-only photos within selected trees are downloaded to app-managed local storage,
without overwriting external source files. Selected web child folders can be
re-created as local virtual folders beneath the selected roots.
Remote folder hierarchy is recreated beneath the chosen destination; empty descendants as well as the necessary ancestors and selected roots are created in bounded batches. Existing
folders of the same name are reused. Existing remote photos cannot be overwritten:
byte-identical SHA-256 files are skipped; same-name/different-bytes files are
conflicts. Previously transferred unchanged local files are skipped on subsequent
runs. Interrupted files retry as whole-file transfers, not byte ranges.

## Limits and platform parity

- Windows stores local files and SQLite; DreamHost uses separate private files and MySQL.
- Windows has local AI/OpenCLIP and face grouping; the PHP web app does not.
- Both support folders, rename/move/copy, recoverable Trash, original downloads,
  exports and metadata editing, but **there is no bidirectional data model**.
- Folder renames or moves do not propagate deletion or rename to old remote paths.
- Metadata fields synchronize **blank-only**, with manually reviewed values protected;
  incompatible nonempty values remain unchanged for human review. File version
  histories, GPS, faces, AI-origin status, absolute source paths and permissions
  are never synchronized. No continuous sync watchers or scheduled jobs.
- Uploaded content is restricted to JPEG/PNG/WebP, max 25 MiB per image.
- Web API authentication requires an Admin/Editor write-scoped token; this token
  can be revoked at any time.

## Release checks

Use a separate DreamHost staging subdomain, DB and file store. Back up desktop
SQLite and web database/private files, then test selected vs unselected folders,
parent/child scope, 20-photo continuation, duplicate/conflict safety, network
interruption, and token revocation. Do not merge to production before real
Windows/PySide6 and DreamHost integration verification.
