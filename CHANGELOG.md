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
