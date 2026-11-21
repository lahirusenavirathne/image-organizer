# Guia Lanka Photo Manager — Windows ↔ DreamHost Bridge (Staging)

**Windows rc6 / DreamHost Web v0.5 / API v1**

## What it does

A **manual, one-way desktop-to-web upload bridge**. The Windows app uses a scoped,
revocable API token to upload selected JPEG/PNG/WebP photographs into a specific
web folder. Each photo is checked by SHA-256 and filename before transmission;
retrying an interrupted upload is safe because the web server checks again under
an advisory lock. A SQLite queue records completed, failed and conflicting photos.

- Files on the PC are never moved or deleted by this feature.
- Existing web images are never overwritten, permanently deleted or renamed.
- Same SHA-256 in the destination folder: considered already on the web.
- Same filename with different bytes: conflict, skipped for human review.
- Up to **20 photographs per manual batch**, each up to **25 MiB**.
- A network interruption retries the **whole photograph**. Byte-range resume is
  not implemented and should not be claimed.
- API tokens are kept in Windows Credential Manager via `keyring` when you check
  "Remember". Otherwise the token stays in memory for the app session.
- No automatic background sync, bidirectional downloads, folder-tree mirroring,
  metadata reconciliation, cloud AI requests or deletion propagation yet.

## Web staging deployment — keep production untouched

1. Back up your current web database and `web/private` photo files. Use a **separate
   staging website, database and private photo storage**, not live originals.
2. Clone the staging GitHub branch or extract the new web ZIP into its own staging
   directory. Point the staging subdomain web root **only** at `web/public`.
3. Configure PHP 8.2+, MySQL, GD, fileinfo, ZIP and HTTPS.
4. Install the web app; then, if needed, run the additive migrations:

   ```sh
   /usr/local/php84/bin/php web/bin/migrate_drive.php
   /usr/local/php84/bin/php web/bin/migrate_api.php
   ```

   Replace `php84` with the version on your DreamHost user account.
5. Log in as an Editor or Admin and open `/api-tokens.php`. Create a short-lived
   **write** token. Copy it once into Windows; never paste it into GitHub, chat,
   screenshots, or public logs. Revoke it in the web interface after testing.
6. Check `/api/v1/index.php?resource=me` with the token from a trusted local
   terminal if desired. Public unauthenticated requests must return HTTP 401.

## Windows staging installation

1. Back up `%LOCALAPPDATA%\GuiaLankaPhotoManager` and your photos.
2. Close the Windows app, replace application source with desktop rc6, then run
   `INSTALL_WINDOWS.bat` to install the `keyring` package. AI models normally do
   not require reinstalling. Run `START_WINDOWS.bat`.
3. In **More → DreamHost Web API → Test web API connection**, enter your *staging*
   website URL and write token. Enable remembering the token only on your own PC.
4. Select five **disposable copies** of test photographs. Choose **Upload selected
   photos to web**, keep folder ID `0` (web root), and confirm.
5. Verify all five appear in staging My Drive. Run the same selected batch again:
   the client must recognize already-uploaded SHA-256s without duplicating files.
6. Simulate a network interruption during one upload; use **Resume
   failed/interrupted web uploads**. Upload success despite lost response should
   reconcile through preflight.
7. Try two different photos with the same filename in the same target folder.
   The second must be reported as a conflict, with no overwrite. To fix it,
   rename its *local display name* manually and retry that photo.
8. Revoke the token on the web and ensure further attempts fail authorization.
9. Compare private file counts with DB photo counts before and after. Check
   Viewer role cannot issue write tokens or upload photos.

## Production rollout policy

This release is a source **testing candidate**, not an independently verified
production deployment. Validate both web PHP/MySQL on DreamHost and the Windows
PySide6 GUI/Windows Credential Manager before merging changes into `main` or
replacing `photos.guialankatours.com`. Preserve backups throughout testing.
