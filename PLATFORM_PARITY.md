# Desktop and Web Companion Release Policy

**Desktop:** v1.0.0-rc6 (staging)  
**Web:** v0.5.0 (staging; includes API v1 plus safe desktop transfer preflight)

## Shared workflows

- Both apps support folders, file rename, move, copy, recoverable Trash and original-file downloads.
- Windows keeps local photographs and SQLite; DreamHost stores a separate private photo library in MySQL.
- New: Windows can explicitly upload up to 20 selected images per batch using a short-lived write API token.
- Existing web content is checked by SHA-256 per destination folder; duplicate images are skipped and name collisions are reported, never overwritten.
- A local SQLite queue records completed, failed, uploading and conflicting photos. 'Resume' safely retries whole photos.
- API tokens can be stored only in Windows Credential Manager or held in memory for the current app session.
- Upload and resume actions are **manual**, and never delete or change remote originals or send photos to OpenAI.

## Not yet synchronized

- Remote-to-desktop downloads, background jobs, byte-range resume of one large file,
  automatic folder-tree mirroring, edit/metadata reconciliation, automatic local/cloud deletions,
  exact file-version history, and face-recognition integration are NOT implemented.
- The existing web/API file limit remains 25 MiB and JPEG/PNG/WebP only.
- User account login is separate from API token authentication.

## Release checks

- Run desktop regression and API/PHP tests, then test with 5 disposable images and a separate DreamHost staging database.
- Verify timeout recovery, duplicate upload prevention, filename conflicts, expired/revoked tokens,
  and original-photo preservation before merging to `main`.
- Back up the live web DB, private file directory, and desktop SQLite database before any upgrade.
