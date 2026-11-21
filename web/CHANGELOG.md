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
