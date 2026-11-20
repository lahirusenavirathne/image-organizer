# Guia Lanka Photo Manager — DreamHost Web Edition (MVP 0.1)

A **private, responsive photo-library web app** designed for existing DreamHost **Shared Unlimited** plans. This implementation is separate from the Windows desktop program and does not replace it. The desktop code remains in the repository root; this web edition lives in `web/`.

**Technology:** PHP 8.2+ (FastCGI), MySQL (PDO), GD, PHP ZIP and cURL (for optional OpenAI). No Node server, Python model server, Composer, database triggers or background daemon required.

## Included and not included

| Included in this MVP | Not included / limitation |
| --- | --- |
| Password-protected image library | No multi-user permissions or 2FA yet |
| Responsive modern photo grid and detail inspector | No browser-based facial recognition |
| Upload JPEG, PNG and WebP | HEIC/TIFF upload not implemented |
| Search, location/activity/rights/source fields | No automatic reverse-image search or copyright verification |
| EXIF camera/date/artist/copyright import when embedded | Unknown source/ownership remains unknown |
| Exact SHA-256 duplicates and dHash similar-photo candidates | dHash cannot reliably link completely different angles of the same landmark |
| Resized WebP/JPEG/PNG ZIP exports + provenance CSV | Crop uses center rather than AI subject detection |
| Optional explicitly approved OpenAI visual tagging | No OpenCLIP/face inference on Shared Hosting |
| Private originals and authenticated image previews | No automatic desktop-to-web database migration |
| Small SFTP import batches and optional cron importer | Shared hosting must not be used for uncontrolled CPU-heavy processing |

**Privacy:** Uploaded originals live outside the public web root. All preview/original requests require a logged-in session. OpenAI tagging is disabled until you manually configure a key and confirm each selected batch; the app sends up to 5 resized images per click and does not send original metadata. Faces may still be visible in pixels.

**Safety:** Tagging and exporting do not modify originals. Importing files from `private/incoming` *moves* them to the managed private originals directory, so keep a separate local backup. Treat all rights statuses as human-verified assertions, not AI results.

## DreamHost setup

1. Choose a dedicated subdomain, e.g. `photos.yourdomain.com`. In DreamHost **Manage Websites**, add the subdomain with **Custom Setup** and PHP 8.2+; enable HTTPS (Let's Encrypt).
2. Create a MySQL database and user via the DreamHost control panel. Note the **MySQL hostname**, database name, username and password. DreamHost's database server is separate from the web server; don't assume the host is `localhost`.
3. Upload the **whole project folder** using SFTP under your web user, for example `/home/USERNAME/glphoto/`:

   ```text
   /home/USERNAME/glphoto/
     public/             <- ONLY this directory is web-accessible
       index.php
       install.php
       api.php
       image.php
       export.php
       assets/
     private/            <- database config + user photos; NOT public
       bootstrap.php
       config.example.php
       images.php
       schema.sql
       incoming/         <- created on first use
       originals/        <- created on first use
       thumbnails/       <- created on first use
       rejected/         <- invalid SFTP imports for manual review
     bin/import_batch.php
   ```

4. In **Manage Websites > Manage > Settings > Directories > Modify**, set the web directory to **`glphoto/public`** (the exact field is relative to the site's SFTP user's home folder). Do not set the project root or `glphoto/private` as the web directory. Save.
5. Open `https://photos.yourdomain.com/install.php`. Before setup works, it creates `private/install-token.txt`; retrieve that random token via SFTP. Enter it in the setup form with the database details and an administrator password of 14+ characters.
6. Setup creates tables and `private/config.php`, removes the token, then redirects to login. Keep private/config.php secret; it holds MySQL credentials. Back up the private directory securely.
7. Sign in and upload **5 test photographs** before moving thousands. Check thumbnails, detail saving, search, similar-image search and a 272 × 300 WebP export.

**Required extensions:** `pdo_mysql`, `gd`, `fileinfo`, `zip`. `exif` is recommended; `curl` is required for optional cloud tagging. DreamHost documents GD/WebP as available by default, but verify extensions on your assigned PHP version.

**Deployment is not automatic:** this repository and ZIP do not have access to your DreamHost SFTP/MySQL credentials. You must upload and configure the site; do not paste passwords here.

## Import a large library (10,000 images)

Uploading 10,000 images one by one over HTTP is not recommended on shared hosting. Instead:

- Use SFTP to upload a **copy** of the photographs into `/home/USERNAME/glphoto/private/incoming/` (subfolders supported).
- Log into the application and click **Import SFTP batch** to import up to 12 images per action, or use a DreamHost cron task to import 20 images per run without keeping a process alive.
- Example cron command for PHP 8.4 (confirm your version/path in DreamHost):

  ```sh
  /usr/local/php84/bin/php /home/USERNAME/glphoto/bin/import_batch.php
  ```

- A 5-minute cron interval is a *starting point*; adjust frequency for your hosting resource constraints. Do not run multiple imports concurrently. Log output in DreamHost cron settings.
- The importer moves images out of `incoming` into the private library; it never overwrites stored image files and quarantines failed image imports into `private/rejected` for manual review. It does **not** remove your local backup.

The legacy “Unlimited” plan still has fair-use CPU, RAM, I/O and storage constraints. Monitor account usage and keep copies outside DreamHost. This is an operational photo library, not an unlimited archival/backup service.

## Optional OpenAI tagging

Edit the **private** `config.php` over SFTP and set `openai_api_key` to your key; don't put it in `public/` or JavaScript. The API uses `gpt-4.1-mini` and requires PHP cURL and outbound HTTPS. One image is resized to 768 × 768, without EXIF, for each request; manual confirmation is required before any upload. You pay OpenAI separately. There is no monetary hard cap; keep the key disabled until you've set a budget/alert on the OpenAI Platform.

AI can suggest an activity or attraction but cannot establish ownership, precise GPS position from generic scenery, or identify real people. Save reviewed tags manually.

## Image exports

Select up to 12 photos, choose one of the presets or exact custom dimensions, choose WebP/JPEG/PNG, and download a ZIP. A CSV manifest includes original file name, source URL/folder, copyright, photographer, license and declared rights status. Image exports center-crop to the requested aspect ratio, strip embedded EXIF, and leave originals untouched.

## Production limitations and follow-up work

- **Shared hosting vs Windows:** offline OpenCLIP and YuNet/SFace require a separate worker or local Windows computer; they are not embedded in this PHP site. Future work: import verified local labels or connect a controlled external processing service.
- **Face grouping:** not part of MVP; a private local process would be safer for guest photos.
- **Similar photographs:** hashes match duplicates/near duplicates, not arbitrary photos of the same subject under different lighting and camera angles. More advanced semantic similarity needs precomputed vectors and an external/local model.
- **Scalability:** web paging is 48 images; similarity scans up to 25,000 hashes per request and returns at most 30 candidates. Export batches are 12 images and capped at 2,500px each. Large high-resolution files can still hit shared PHP RAM limits; tune accordingly.
- **Authentication:** one administrator, salted password hashes, cookie sessions, CSRF protection, HTTPS requirement, and private storage are implemented; 2FA, server-side IP rate limiting, audit trails, data retention and access control are future production-hardening tasks.
- **Backups:** DreamHost short-term backups are not long-term archival guarantees. Back up both private images and the MySQL database yourself.

## Local checks

```sh
find public private bin -name '*.php' -print0 | xargs -0 -n1 php -l
php tests/smoke.php
node --check public/assets/app.js
```

The development runtime has PHP but **no GD or MySQL extension**, so full integration tests are not possible here. Run the upload/database/GD/cloud smoke test on your DreamHost environment before a full import.

## Useful official DreamHost documentation

- [Changing a domain's web directory](https://help.dreamhost.com/hc/en-us/articles/360041534491-Changing-the-web-directory-assigned-to-a-domain)
- [Shared Unlimited overview](https://help.dreamhost.com/hc/en-us/articles/34357904873108-Shared-Unlimited-hosting-overview)
- [PHP extensions and GD support](https://help.dreamhost.com/hc/en-us/articles/214893957-Enable-PHP-extensions-and-loaders)
- [Shared Hosting persistent process limits](https://help.dreamhost.com/hc/en-us/articles/214869648-Persistent-processes)
- [Creating cron jobs](https://help.dreamhost.com/hc/en-us/articles/215088668-Create-a-cron-job)

## Modern Web Guidance

The responsive Grid/Flexbox page structure, intrinsic image aspect ratios, native modal dialogs, accessible labels and image loading strategy follow these checked upstream guides:

- `css-layout` — https://github.com/GoogleChrome/modern-web-guidance/blob/main/skills/modern-web-guidance/guides/css/css-layout.md
- `optimize-image-priority` — https://github.com/GoogleChrome/modern-web-guidance/blob/main/skills/modern-web-guidance/guides/performance/optimize-image-priority.md
- `validate-input-after-interaction` — https://github.com/GoogleChrome/modern-web-guidance/blob/main/skills/modern-web-guidance/guides/forms/validate-input-after-interaction.md

No network assets or third-party JavaScript are loaded by the web application.
