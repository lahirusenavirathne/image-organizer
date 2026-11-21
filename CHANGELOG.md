# v1.0.0-rc6 — DreamHost Web companion (manual upload)

- Added HTTPS API v1 connection, scoped Bearer token with Windows Credential Manager storage (optional).
- Added selected-photo uploads (max 20 per run), SHA-256 preflight, conflict review, and durable SQLite retry queue.
- Same-content photos are recognized as already present. Different-content, same-name photos are never overwritten.
- Source images remain untouched; the client never calls remote deletion endpoints.
- Scope: manual one-way upload only; failed whole files are retried, not byte-range chunks or live two-way sync.

## v1.0.0-rc5 — Drive-style Desktop Folder Management

- Virtual folder hierarchy, folder tree, folder import, breadcrumbs, My Drive, Recent, Starred, and Trash views.
- Photo display rename, virtual folder moves, explicit managed local copies, and safe untouched-original exports.
- Recovery and catalog-only purge: originals are never silently deleted; existing advanced physical moves retain explicit review and undo.
- SQLite additive schema migration; original paths, face indexing, visual embeddings and AI review remain intact.
- Matching workflow with web Phase 1 v0.3; automatic desktop/web synchronization is not implemented.
- Added core safety tests and Windows GUI smoke tests.

## 1.0.0-rc4 — Modern native desktop interface

- Implemented persistent light navigation matching the approved gallery concept.
- Added live search, filter toggle, rich rounded image cards, full-preview dialog and responsive card density.
- Retained all existing AI/visual-match/face/move/export operations in compact toolbar and organized More menu.
- Added single-photo metadata inspector and fixed rights status persistence.
- Added optional Qt offscreen integration tests for Windows CI.
- Image originals are not modified; tagging is still review-first and the app remains a release candidate.

## 1.0.0-rc3 — Local visual similarity search and trusted photo references

- Added **Index selected** and **Index whole library** to compute and cache local OpenCLIP image embeddings with SHA-256 and dHash fingerprints.
- Added **Find similar photos** with side-by-side previews: exact byte duplicates, likely edited copies, and visually similar photographs are separate categories.
- Added color-distance filtering to reduce dHash false matches for substantially different images with identical shape signatures.
- Added **Save as reference** and **Match reference examples**: user-provided examples of Sri Lankan attractions, activities and locations can help identify similar imagery. Labels are copied only after explicit visual review and confirmation.
- Added six regression tests (29 total passing), safe database migrations and a dedicated visual-match guide.
- Similarity scores are cosine values, **not calibrated probabilities**. Recognition of the same landmark from another viewpoint is not guaranteed. No original files are moved or deleted by these tools.

## 1.0.0-rc2 - Classification diagnostics

- Explain empty tagging: top candidate similarity scores, threshold reasons and per-photo outcomes.
- Separate analyzed, unclassified, protected, cached and failed photos in the result dialog.
- Add **Refresh AI selected** to recompute local predictions without cached results.
- Protect manually approved tags; no change to move/export safety or cloud behavior.
- Diagnostic results are not evidence of higher recognition accuracy; keep location suggestions tentative.

# Changelog

## v1.0.0-rc1 — Windows release candidate
- CI on Windows and Linux; Windows GUI smoke test and PyInstaller artifact workflow.
- Preserved local-only face grouping, explicit cloud photo upload, and safe move/undo behavior.
- Upgraded documentation, installation guidance, versioning and test suite.
- **Not signed or production-certified**; real Windows hardware and AI model downloads still need verification.

## v0.4 — Travel website image exports
- Added deterministic SEO filenames, bilingual English/Spanish alt text in CSV export manifests.
- Added portrait gallery preset, crop/pad controls, source provenance and rights status.

## v0.3 — Library review
- Added SHA-256 exact duplicate detection and perceptual near-duplicate candidate review.
- Added local image quality heuristic, caching, and rights status: Unknown / Verified / Permission required.
- Added library buttons for quality scans, duplicate reports and AI suggestion review queues.

## v0.2 — Reliable image recognition
- Added local/cloud suggestion cache keyed to image metadata and model identity.
- Avoids repeated paid API requests for unchanged photos; protects manual/approved tags.
- Added explicit AI review status, confidence fields, and migration from the v0.1.2 database.

## v0.1.2 — Prior MVP
- Import, Qt gallery, GPS/EXIF metadata, local OpenCLIP activity recognition, OpenCV face grouping,
  opt-in OpenAI vision requests, reviewed file moves with undo, and custom-size exports.
