# Guia Lanka Photo Manager - API v1 (testing release)

This is an **authenticated, versioned HTTP JSON API** for the DreamHost PHP edition.
It is intended for a future Windows desktop companion or approved integrations.
It does **not** activate automatic photo synchronization or provide real-time event feeds.

## Deployment prerequisites

- Web app **v0.3.0** file manager, PHP 8.2+, MySQL, private image storage and HTTPS.
- Back up MySQL and `web/private/` before the upgrade.
- Deploy the API files alongside the existing `web/` folder (do not expose `private/`).
- Run the additive migration using the PHP CLI version configured on DreamHost:

  ```sh
  cd ~/glphoto
  /usr/local/php84/bin/php web/bin/migrate_api.php
  ```

- Open `https://photos.guialankatours.com/api-tokens.php` while signed in to create a token.
  The creation form requires your current password. The token appears **once**, must be
  stored in a secret manager, and cannot be recovered afterward. Revoke lost tokens.
- Issue distinct, short-lived tokens for each device. Use **read** tokens for integrations
  that only browse or preview. The role of the owner is always enforced on the server.
- If Bearer tokens produce HTTP 401 on DreamHost, confirm Apache forwards the
  `Authorization` request header to PHP. The updated `.htaccess` includes a
  guarded `SetEnvIfNoCase` rule; verify using a test token instead of weakening login rules.

## API location and authentication

Base endpoint (stable even without Apache URL rewriting):

```
https://photos.guialankatours.com/api/v1/index.php
```

Use query parameters `resource`, `id`, `action` as shown below. The HTTP method is
part of the operation. `Content-Type: application/json` is required for JSON writes;
uploads use `multipart/form-data`.

Every request (including reads) must include:

```
Authorization: Bearer glpm_v1_<64-hex-characters>
```

Never put a token in a URL, browser JavaScript, issue report, GitHub repository, or log.
The API does not authenticate with browser cookies and exposes no cross-origin access
headers. Store the token in Windows Credential Manager or a similarly protected store.

```
curl -sS -H 'Authorization: Bearer YOUR_TOKEN' \
 'https://photos.guialankatours.com/api/v1/index.php?resource=me'
```

All JSON responses use `data` (and sometimes `meta`) or `error.code` / `error.message`.
HTTP 401 is missing/invalid/expired/revoked token; 403 is insufficient scope/role;
422 is invalid JSON or input; 429 is the per-token request limit (120 per 5 min).

## Windows companion synchronization (Web v0.5.0)

Authenticated **write** token required. The preflight operation is idempotent
and non-destructive. A folder must already exist; the root is `null`.

```http
POST /api/v1/index.php?resource=sync&action=preflight
Authorization: Bearer glpm_v1_<64 hex characters>
Content-Type: application/json

{"name":"Sigiriya.jpg","sha256":"<SHA-256 lowercase hex>","file_size":728311,"folder_id":null}
```

The `data.decision` response is `upload`, `duplicate`, or `conflict`, with
`remote_id` of any matching photo and `folder_id`. A `duplicate` means the same
binary SHA-256 exists in this folder; the desktop client records it as complete.
A `conflict` means a *different* image occupies the same name; the client
holds it for manual review rather than overwriting or silently renaming.

For a `decision=upload`, send the same SHA-256 as a multipart form field along
with `photo` and `folder_id` to `POST ?resource=photos`.
The server verifies the bytes' hash and takes a per-folder MySQL lock while
checking for duplicates and saving. It returns `201` with `decision=uploaded`,
`200` with `decision=duplicate` when a previous upload completed, or `409`
with `name_conflict`. Clients should retry a lost response by invoking
**preflight again**, not blindly uploading. No permanent deletion is exposed.

**Scope:** Retriable whole-image transfers, not chunked/byte-offset resumption.
Do not claim live bidirectional synchronization. Every sync batch is initiated
by the user, preserving the privacy and resource limits of shared hosting.

## Endpoints

All URLs below are relative to the API base and use query-string arguments.

| Method | Query parameters | Required scope / role | Operation |
|---|---|---|---|
| POST | `resource=sync&action=preflight` | Write / Editor | SHA-256 duplicate/conflict preflight (desktop transfer) |
| GET | `resource=me` | Read / Viewer | Account, role, token scope, API version |
| GET | `resource=folders&parent_id=root` | Read / Viewer | List direct child folders, up to 500 |
| GET | `resource=folders&id=123` | Read / Viewer | Folder details + breadcrumbs |
| POST | `resource=folders` | Write / Editor | Create folder, JSON `{ "name":"Yala", "parent_id":null }` |
| PATCH | `resource=folders&id=123` | Write / Editor | Rename or move folder, JSON `name` and/or `parent_id` |
| DELETE | `resource=folders&id=123` | Write / Editor | Move folder and children to Trash |
| POST | `resource=folders&id=123&action=restore` | Write / Editor | Restore trashed folder |
| GET | `resource=photos&page=1&per_page=48` | Read / Viewer | Paginated photo metadata, up to 100 per page |
| GET | `resource=photos&folder_id=root` | Read / Viewer | Restrict to root folder; numeric folder ID also supported |
| GET | `resource=photos&q=elephant` | Read / Viewer | Search names, locations, attractions and activities |
| GET | `resource=photos&id=123` | Read / Viewer | One active photo's metadata and SHA-256 |
| GET | `resource=photos&trash=1` | Write / Editor | List trashed photo metadata |
| POST | `resource=photos` | Write / Editor | Upload 1 image (multipart `photo`, optional `folder_id`) |
| PATCH | `resource=photos&id=123` | Write / Editor | Update metadata, rename and/or move using JSON object |
| POST | `resource=photos&id=123&action=copy` | Write / Editor | Copy with JSON `{"folder_id":null}` |
| DELETE | `resource=photos&id=123` | Write / Editor | Move photo to Trash |
| POST | `resource=photos&id=123&action=restore` | Write / Editor | Restore trashed photo |
| GET | `resource=files&id=123&variant=thumb` | Read / Viewer | Authenticated JPEG thumbnail bytes |
| GET | `resource=files&id=123&variant=original` | Write / Editor | Authenticated original bytes |

No permanent-delete endpoint in v1; use the existing administrator UI with explicit
confirmation. No public signup, user management API, face-recognition endpoint, OpenAI
batch endpoint, or unrestricted server-side directory access is exposed here.

### Examples

List 25 photos:

```bash
curl -sS -H "Authorization: Bearer $GLPM_TOKEN" \
 'https://photos.guialankatours.com/api/v1/index.php?resource=photos&page=1&per_page=25'
```

Create a folder:

```bash
curl -sS -X POST -H "Authorization: Bearer $GLPM_TOKEN" \
 -H 'Content-Type: application/json' \
 -d '{"name":"Sigiriya","parent_id":null}' \
 'https://photos.guialankatours.com/api/v1/index.php?resource=folders'
```

Upload one JPEG to folder 123:

```bash
curl -sS -X POST -H "Authorization: Bearer $GLPM_TOKEN" \
 -F 'folder_id=123' -F 'photo=@sample.jpg' \
 'https://photos.guialankatours.com/api/v1/index.php?resource=photos'
```

Rename a photo (does not rename the private stored filename):

```bash
curl -sS -X PATCH -H "Authorization: Bearer $GLPM_TOKEN" \
 -H 'Content-Type: application/json' -d '{"original_name":"Elephants in Yala.jpg"}' \
 'https://photos.guialankatours.com/api/v1/index.php?resource=photos&id=123'
```

Download an original as an editor:

```bash
curl -sS -H "Authorization: Bearer $GLPM_TOKEN" \
 'https://photos.guialankatours.com/api/v1/index.php?resource=files&id=123&variant=original' \
 -o original.jpg
```

## Operational safeguards

- Generated tokens are 256-bit random values; only SHA-256 token digests are stored.
- Tokens expire after 1, 7, 30 or 90 days; at most 10 active tokens per user.
- Tokens are invalidated by password changes, disabling a user, or explicit revocation.
- Server role + token scope apply to every operation; credentials never go to JS.
- HTTPS and private image storage remain mandatory; images cannot be accessed by URL without a valid token.
- The API does not set `Access-Control-Allow-Origin`, so third-party browser origins are not granted cross-origin access.
- Rate limit is 120 calls per token per five minutes, enforced in MySQL.
- Upload file formats and maximum bytes/pixels use existing validated web ingestion.
- Permanent deletion deliberately omitted; folder and photo deletions are recoverable Trash moves.
- Records contain `sha256` for deduplication, but this API is not a complete conflict-resolving synchronization service.

## Validation before production use

Run unit checks:

```sh
php web/tests/api_unit.php
php web/tests/api_http_smoke.php
find web/private web/public/api web/bin -name '*.php' -print0 | xargs -0 -n1 php -l
```

Then, on a **separate staging database and photo store**, test:

1. Login and API token creation, wrong password rejection and one-time reveal.
2. Read token list metadata, reject write operations with HTTP 403.
3. Upload a safe test photo as Editor and retrieve it with a bearer token.
4. Confirm anonymous and revoked tokens receive 401, including image downloads.
5. Trash/restore a test photo and verify binary access is denied while trashed.
6. Disable a user and confirm their token immediately stops working.
7. Confirm web app browser auth, permissions, exports and original images remain unchanged.

**Limitations:** PHP syntax/unit tests do not replace a live DreamHost/MySQL security
and storage test. No photo-library synchronization is enabled by installing this API.
