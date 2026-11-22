## web-0.7.1 — Edit photo navigation reliability

- Use a real photo-specific editor link in the inspector rather than a `#` link whose click handler can be stale in browser cache.
- Version the gallery and editor JavaScript asset URLs to bust old browser caches after upgrades.
- Improve editor-page errors so missing database setup is distinguishable from photo not found; authentication remains enforced.
- No photo files, edit recipes, or production data are changed by this patch.

## web-0.7.0 — Non-destructive photo editor R1
- Dedicated Editor/Admin web editor with server-rendered previews and WebP/JPEG/PNG exports.
- Versioned MySQL edit recipes, optimistic-locking conflict protection and additive migration.
- Original image bytes remain private and unchanged. Staging only until live GD/MySQL testing.

# Web v0.6.0 — safe sync metadata fill

- Adds authenticated write-token `sync&action=metadata_fill` endpoint.
- Validates exact image SHA-256; fills empty fields only; protects reviewed tags.
- Explicit source/rights validation, no modifications to folder paths or originals.
- Companion to desktop rc8 full selected-folder hierarchy and metadata sync.

# Web v0.5.0 — safe Windows companion uploads

- New write-token `POST ?resource=sync&action=preflight` validates SHA-256, file size, destination and filename before uploading.
- Desktop opt-in multipart uploads include expected SHA-256, rechecked against the uploaded bytes.
- A per-folder MySQL advisory lock serializes desktop sync requests and prevents identical uploads from racing into duplicate records.
- Duplicate checks resolve by checksum first; a different file with the same display name returns HTTP 409 (never overwrites).
- Browser uploads and all existing login/role/trash behavior unchanged.

## web-0.4.0-api1 - API v1 (staging)

- Versioned Bearer-token JSON API for browsing, folders, uploads, editing, copying, Trash, and restore.
- User-owned revocable, time-limited read/write API tokens tied to current role and password version.
- No bearer token in URL, no public CORS, no irreversible delete API.
- DB-backed request rate limits and SSH migration helper.
- Existing browser sessions remain independent of API authentication.

# Changelog

## web-0.2.0 — Invitation-only authentication and roles

- Multi-user Admin, Editor and Viewer roles with server-enforced access controls.
- Administrator account invitations, account disabling, role changes and one-time reset links.
- User account password changes and SSH-only lost-admin recovery command.
- Hashed one-time tokens, MySQL login throttling, secure session expiry and session invalidation.
- Automatic, locked migration of existing single-admin installations.
- Authentication unit and MySQL integration tests plus DreamHost deployment instructions.
- No self-registration or outgoing email required. Two-factor authentication not yet included.

# Web Edition changelog

## web-0.1.0 — DreamHost Shared Unlimited MVP

- Introduced a separate, no-build PHP/MySQL app with a modern responsive photo gallery.
- Added HTTPS-only private photo serving, installation token, password-based sign-in and CSRF protection.
- Added browser uploads and SFTP/cron import with small per-run limits and quarantine for rejected images.
- Added MySQL photo records, EXIF source details, manual tags and rights assertions.
- Added SHA256 and dHash + average-color similarity checks for exact/near duplicate images.
- Added server-side WebP/JPEG/PNG ZIP exports with a provenance CSV and custom dimensions.
- Added explicitly confirmed optional OpenAI vision classification (server-stored API key, no automatic uploads).
- Added PHP/JS lint checks and no-database smoke tests.

Not included: real face grouping, arbitrary-angle visual landmark matching, offline OpenCLIP inference, and direct Windows SQLite migration. Those capabilities require separate services or local processing.

## web-0.3.0 — Drive-style file manager

- Nested folders, breadcrumbs, rename, copy and move for photographs, bulk operations, list/grid sorting and browser folder uploads.
- Trash with individual and whole-folder restoration and explicitly confirmed administrator-only permanent deletion.
- Small original-photo/folder ZIP download, retaining rights and source manifest metadata.
- Private-originals protection: trashed photos are no longer accessible by image ID, older gallery API or export routes.
- Automated additive schema migration with a filesystem lock, plus CLI migration command.
- Existing login, roles, sessions, photo metadata, SFTP import and cloud tagging preserved.
