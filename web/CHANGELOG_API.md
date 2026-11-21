## web-0.4.0-api1 - Versioned REST API (staging)

- New dedicated JSON API at `public/api/v1/index.php`, independent of cookie-session browser endpoints.
- Read and write Bearer tokens, scoped to existing Viewer/Editor/Admin roles, expiring in 1-90 days.
- One-time token display, revocation, invalidation after account changes, and per-token request throttling.
- Read/search/paginate photos; list/create/rename/move folders; authenticated original/thumbnail fetch.
- Photo uploads, metadata updates, copies, Trash and restore. No permanent-delete API.
- Additive schema migration for token tables, testing instructions and documented curl examples.
- Windows desktop automatic synchronization remains future work; web v0.3 file-manager prerequisites retained.
