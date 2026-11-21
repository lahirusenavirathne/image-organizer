# Guia Lanka Photo Manager Web — Drive-style manager v0.3.0

## Scope

This update makes the established, already deployed photo library behave more like a file manager. It retains v0.2 authentication, the private original-image store, metadata, similar-photo search, and export presets.

New: My Drive root, nested folders, folder breadcrumbs, folder creation/rename/move, uploading into a chosen folder, browser folder uploads (where supported), photo renaming, moving and copying, grid/list view, sorting, recent files, Trash, restoration, and administrator-confirmed permanent deletion. Folder ZIPs and batch original downloads are limited to 24 images to avoid long PHP requests on shared hosting.

**Not included:** generic documents (this is still a photo manager), real-time team collaboration, synchronization, offline caching, file-version history, automatic Trash emptying, advanced photo editing, or reliable semantic recognition of different angles of landmarks. Those are future phases.

## Before upgrading the working DreamHost installation

**Do not overwrite live files without a backup.** In your DreamHost site:

1. Export the MySQL database as an SQL backup using phpMyAdmin.
2. Back up `/home/USERNAME/glphoto/web/private/` off-site, especially the originals and `config.php`.
3. Verify that the hosting web directory is `glphoto/web/public`, while private images stay outside it.
4. Download a copy of the existing v0.2 source or save the current Git commit SHA for rollback.
5. Deploy the v0.3 code to a **staging clone and test database** first if possible. Do not point a staging clone at the production MySQL database or private originals.

When the code is installed in `~/glphoto/web/`, the migration can be run explicitly from the repository root using a matching PHP CLI binary (substitute the actual DreamHost PHP version):

```sh
cd ~/glphoto
/usr/local/php84/bin/php web/bin/migrate_drive.php
```

Alternatively, the first authenticated request performs this schema migration with a filesystem lock. The migration adds only folder/trash columns and a `folders` table; it does not move original files or erase existing records. If migration fails, check the DreamHost PHP error log and restore from the database/source backups.

**Do not run `install.php` again on an existing installation.**

## Access permissions

- Admin: all actions, including permanent deletion from Trash and importing SFTP batches.
- Editor: create/upload/rename/move/copy/soft-delete/restore photos and folders; export.
- Viewer: browse folders, view non-trashed photos and inspect details. No uploads, editing, ZIP downloads, export, Trash access, or permanent deletion.

All changes require a valid authenticated session and CSRF token. Permissions are enforced server-side, not just in the web interface.

## Rollout test on a staging copy

1. Log in as an administrator. Existing five photos should still appear under **My Drive**.
2. Create folders **Sri Lanka**, **Sigiriya**, and **Wildlife**, including one nested folder.
3. Upload five copies of known test images into a folder; test the browser folder uploader too.
4. Rename a photo and folder; confirm the original image data remains unchanged.
5. Move a photo between folders, then copy it. Verify that the two entries can be managed separately.
6. Test grid/list view and sort by name, date and size.
7. Move a photo to Trash, confirm its direct preview link no longer works, then restore it.
8. Move a folder with photos to Trash, verify descendants are hidden, then restore the complete folder tree.
9. Download one original file and a small folder ZIP. Check filenames and source/copyright manifest.
10. As an admin, permanently delete **a copied test file** after confirming `DELETE PERMANENTLY`. Verify restoration is no longer possible.
11. Test with a Viewer account to confirm editing, Trash and ZIP downloads are inaccessible even by direct requests.
12. Confirm authentication, AI tagging and existing 272 × 300 WebP export still work.

## Shared hosting constraints

- Maximum 25 MiB per image, 28 megapixels, JPEG/PNG/WebP only; PHP's `upload_max_filesize` and `post_max_size` may be lower.
- Up to 50 photos per move or Trash action; up to 12 copies per action; up to 24 originals in a ZIP.
- Permanent folder deletion is limited to folders containing no more than 25 photos and 25 nested folders per request. Larger folders remain recoverable in Trash until an appropriately designed batch cleanup workflow is deployed.
- No background persistent processes. Uploads occur in separate HTTP requests, and bulk import uses the existing bounded SFTP importer.
- Uploads from the browser folder chooser preserve relative folder hierarchy up to eight levels. Support varies by browser; manual folder creation is a fallback.
- Existing authentication session timeouts and v0.2 user roles remain unchanged.

## Version control

This code is separate from the Windows photo manager. Keep `private/config.php`, original images, thumbnails and migration markers out of Git. If you update the GitHub repository with these files, the DreamHost deployment can use `git pull` after backups. Source-controlled changes alone do not deploy to the live DreamHost server.

## Testing limitations

PHP and JavaScript lint and non-database unit/smoke checks are run in the development container. Live MySQL migrations, image processing via GD, and end-to-end browser functionality still require a DreamHost staging test before production deployment.
