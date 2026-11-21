## Selective two-way folder sync — Windows rc7 / DreamHost Web v0.5

**Only local My Drive folders you check can synchronize.** Open **More → DreamHost Web API → Sync selected folders (Windows ↔ Web)**. Check one or
several local folders. A checked parent covers its descendants, while a checked
child excludes unselected ancestor and sibling photos; unfiled My Drive root
photos are also excluded. No all-library, watcher, or automatic background sync
is available. Each additional batch requires user confirmation.

The application creates the chosen folder paths beneath a specified web parent
(default ID 0, My Drive root) and transfers **up to 20 photos total per click**,
first from Windows to DreamHost, then web-only photographs back to Windows if
quota remains. The remote→local leg visits only web directories beneath those
chosen roots. Newly discovered web subfolders become local virtual subfolders
inside the selected trees. Downloaded originals reside in the desktop app's
private managed `web_sync_downloads/` directory, never on top of original sources.

Uploads and downloads are **additive**: existing images are not overwritten;
photo-name collisions are shown for manual review; identical SHA-256 uploads
are detected and skipped. Completed transfers are checkpointed in local SQLite,
so **Continue selected-folder sync** advances to new files on subsequent clicks.
Folder/Photo Trash and deletions, renames, cloud metadata, user permissions and
conflicting edits **are not synchronized**. Existing same-named remote folders
are reused, so choose a dedicated web parent if you don't want them mixed.

**Prerequisites:** DreamHost **web v0.5 with API v1** on a staging subdomain,
a staging database, and a write-scoped API token from `/api-tokens.php`. Windows
stores a remembered token in Credential Manager using `keyring`. No token is
written to SQLite or the connection settings. Support is limited to JPEG/PNG/WebP,
25 MiB per photo, a maximum of 20 transfer attempts per click, and bounded web
API listing. Very large remote folders require multiple manual scan runs.

**Safety:** There is no download-by-file-ID outside chosen web folders, no delete
propagation in either direction, and no automatic overwrite. A changed image
whose name is already occupied on the destination creates a conflict and needs
manual review. Local folder renaming does not rename the old web path. Keep
backups of both libraries and test with five disposable copies first. This is a
candidate release; Windows UI and live DreamHost integration are not yet verified.

---

# Guia Lanka Photo Manager — v1.0.0-rc5

## v1.0.0-rc5 — Desktop Drive-style feature parity (web v0.3)

This version updates the **Windows desktop** software to offer a local equivalent of the web app's Phase 1 file manager. Both editions can now organize a photo collection with nested folders, a My Drive view, Recent, Starred, Trash, rename/move/copy, original downloads and sorted grid/list views.

**User interface:** New My Drive/Recent/Starred/Trash sidebar destinations, folder tree and breadcrumbs, `+ New folder`, list/grid switch, sorting, and a Drive actions section under **More**. Importing a folder preserves its hierarchy as virtual folders while retaining every original image at its existing path. `Save untouched originals` makes safe filesystem copies without overwriting existing files. Explicit `Copy` stores duplicates in the application's managed local storage. Previous OpenCLIP, visual similarity, face groups, metadata and exports remain available.

**Critical safety distinction:** On desktop, rename and move **within My Drive** change SQLite catalog values, not underlying photo file paths. Trash, restore and permanent removal act on the *catalog only*; original source photos are never deleted. The pre-existing separately named **Advanced file moves** tool still requires preview/confirmation and keeps undo history. The DreamHost web library is separate; **there is no automatic desktop/web file synchronization**. Read [PLATFORM_PARITY.md](PLATFORM_PARITY.md) before relying on both editions.

**Upgrade:** Back up `%LOCALAPPDATA%\\GuiaLankaPhotoManager` and your source photos. Extract the rc5 ZIP into `C:\\GLPhoto`, replacing program files only. Run `START_WINDOWS.bat`. The SQLite database migration is additive. AI engine does not normally need reinstalling.

**Verification:** 38 local core/unit tests pass; GUI tests are included but skipped in Linux where PySide6 is unavailable. The Windows UI, network share imports and large-library performance must be verified on-device. This release is a testing candidate, **not an auto-synchronizing production deployment**.

---

## Previous release — v1.0.0-rc4

**Windows photo organizer for local Sri Lankan travel photos; source release candidate with visual similarity search.**

**v1.0.0-rc2 tagging diagnostics:** Select 2-5 photos and click **Refresh AI selected** to bypass previous cached predictions. The detailed result window distinguishes analyzed images, unclassified images, cached predictions, protected manual tags and errors. It displays the top three raw OpenCLIP activity/attraction candidates, even if no automatic tags pass the thresholds. Similarity numbers are not calibrated probabilities. Manually reviewed fields remain protected. This is a diagnostic change, not a validated improvement in actual attraction-identification accuracy.


> **Release status:** All automated core tests pass in the Linux development
> environment. Windows GUI, pretrained models, OpenAI request and generated
> Windows executable still require successful runs on a Windows machine and
> GitHub Actions. Do not use on an irreplaceable library without backups.

## Modern desktop interface — v1.0.0-rc4

The Windows app now uses a **real native PySide6 light-themed desktop layout**, replacing the earlier dense dark toolbar. This is implemented code, not a mockup.

- Persistent left navigation: **All photos, Locations, Activities, People, Review tags, Exports**.
- Search as you type, collapsible location/activity filters, responsive thumbnail gallery, and a compact card toggle.
- Click a photo for a collapsible metadata inspector; double-click for an enlarged preview.
- Frequently used actions (Import, AI tag, Find similar, Export) are on the toolbar. Other existing tools are under **More** (including local AI diagnostics, cloud opt-in, face groups, safe moves, duplicates and reference matching).
- Clear ready/progress status and pagination (120 images per page).
- Fixes **rights verification status** not being persisted when Save reviewed metadata was clicked.

**Upgrade:** Download this version and replace the application source folder, keeping `%LOCALAPPDATA%\GuiaLankaPhotoManager` untouched. Run `START_WINDOWS.bat`. Normally, you do not need to reinstall AI packages. If base dependencies are missing, run `INSTALL_WINDOWS.bat` first. Keep a backup of the database before major upgrades.

**Verification:** Core unit tests pass; optional PySide6 UI smoke tests are included for Windows CI. The Qt UI could not be launched in the authoring environment because PySide6 is unavailable. Windows desktop appearance and build artifact require on-device / CI verification.

## Visually match photos — new in v1.0.0-rc3

This is **image-to-image search**, not merely guessing labels from text. The app uses three distinct types of matching:

1. **Exact duplicate:** SHA-256 finds byte-identical files, even if filenames differ.
2. **Likely edited copy:** a perceptual dHash plus average-color check finds many resized or recompressed copies. Cropping, rotations and strong color edits may not match; manually verify each candidate.
3. **Visually similar:** local OpenCLIP image embeddings retrieve photos with similar content, even when they are separate shots. A high cosine score does **not** prove the same landmark, person or ownership.

### Five-photo test procedure

1. Import a folder containing two photographs of the same place (different camera angles), a resized copy of one, an exact duplicate renamed, and an unrelated photo.
2. Select the five photos, then click **Index selected**. The first run loads the installed offline OpenCLIP model; later runs reuse fingerprints unless files change.
3. Select one photo and click **Find similar photos**. Compare exact, likely-edited and visually-similar results side-by-side.
4. Choose a photo whose attraction/activity/location you **personally verified** and click **Save as reference**. Enter its correct label.
5. Select another photo and click **Match reference examples**. Inspect suggested reference photographs and scores. **Apply selected reference label** only after confirming the match visually.
6. When satisfied, click **Index whole library** to build/search across your ~10,000 photographs. CPU-only indexing can take significant time. It is resumable and does not upload photos or alter originals.

These tools work offline and do not require an OpenAI API key. They use the local AI installation from `INSTALL_AI_WINDOWS.bat`. Source URLs and licensing are not inferred from image resemblance. A reference photo does not authorize copying its copyright information to another file.

**Limits:** The 64-bit dHash may confuse similarly structured images, and OpenCLIP may rank a different waterfall, temple or national park highly. Its cosine scores are not calibrated confidence values; always review matches before adding precise attraction names or moving files. The reference workflow transfers labels only after an explicit approval. No neural biometric recognition is used for matching people here; face grouping remains a separate local tool.

## Versioned improvements

- **v1.0.0-rc4:** Replaces dense toolbar with native light sidebar, photo cards, smart filters and inspector.
- **v1.0.0-rc3:** Adds side-by-side visual duplicate/similar-photo matching and user-verified reference examples.
- **v0.2:** Caches unchanged AI classifications (local and cloud), protects manually
  approved tags, tracks suggestion review and supports first-run diagnostics.
- **v0.3:** Duplicate candidate review (SHA-256 and perceptual hash), image
  quality scoring, rights status and review queue. Duplicate matches never delete files.
- **v0.4:** SEO-oriented filenames and bilingual English/Spanish alt suggestions
  in the export manifest; custom dimensions, WebP/JPEG/PNG/TIFF and gallery preset.
- **v1.0.0-rc1:** Windows+Linux tests, Windows GUI smoke test, reproducible
  PyInstaller build workflow and versioned release documentation.

## Getting started

Clone or download this repository into `C:\GLPhoto` and run
`INSTALL_WINDOWS.bat` followed by `START_WINDOWS.bat`. Offline attraction
recognition additionally requires `INSTALL_AI_WINDOWS.bat` and first-time
model download. For face groups, download OpenCV face models from within the app.

**Data:** Photo library and face embeddings remain in
`%LOCALAPPDATA%\GuiaLankaPhotoManager`. The virtual environment uses
`%LOCALAPPDATA%\GLPvenv` to reduce Windows path-length errors. Existing photo
libraries from v0.1.2 are migrated automatically without deleting records.

**Privacy/cost:** Local tagging and face grouping do not call OpenAI.
`Cloud AI selected` explicitly asks for a key and consent before sending up
up to 50 selected resized photographs to OpenAI. Cached identical model/image
results avoid repeated calls unless refreshed. Resized images may still contain
people. API usage may incur charges; there is **no guaranteed monetary hard cap**.

**Safe handling:** Photo moves require an explicit preview and confirmation;
collisions never overwrite another file; undo is recorded. Exports create new
files and a provenance/copyright manifest. 'Verified' rights status is a user
assertion and is not inferred from visual content. Keep backups before bulk moves.

**Windows package:** The `.github/workflows/ci.yml` workflow builds an unsigned
Windows folder artifact using PyInstaller when CI succeeds. This is not a
signed installer and does not bundle heavyweight OpenCLIP model weights.

---

## Previous MVP documentation

# Guia Lanka Photo Manager

**Legacy v0.1.2 setup reference (retained for troubleshooting)**

A desktop app for classifying and organizing local travel photography, especially Sri Lankan attractions and experiences. The app indexes photos in a local SQLite database, presents a visual photo gallery, optionally suggests activities and attractions with local or cloud vision models, groups similar faces locally, and exports new images at precise dimensions in selected formats.

**Important status:** The core non-UI modules have automated tests. The PySide6 GUI, OpenCLIP pretrained model downloads, OpenCV face model downloads, OpenAI requests, and Windows executable build have **not yet been tested on a Windows computer**. This is an implementable MVP source project, **not** a signed or production-certified installer.

## Run on Windows

1. Install **64-bit Python 3.11, 3.12 or 3.13** from https://www.python.org/downloads/windows/ (include the Python launcher).
2. Extract this ZIP to a normal local directory (for example `C:\GLPhoto`).
3. Double-click **`INSTALL_WINDOWS.bat`**. It creates a Python environment in `%LOCALAPPDATA%\GLPvenv` (a short path that avoids PySide6 MAX_PATH installation failures) and installs PySide6, Pillow, NumPy and OpenCV. Internet is needed for this one-time install.
4. To use **AI image recognition**, you must also run **`INSTALL_AI_WINDOWS.bat`**. The base installer does not include the large recognition model. Run **`DIAGNOSE_AI_WINDOWS.bat`** to verify libraries and model download; it saves a troubleshooting report to `%TEMP%\GLPhoto_AI_Diagnostics.txt`.
5. Double-click **`START_WINDOWS.bat`**.
6. Click **+ Add folder** and choose an image folder. This indexes files and metadata without relocating them.
7. Select one or more images in **Photo Library**. `Ctrl+A` selects all **on the visible page**. Browse 120 images per page.
8. Review location, activity, attraction, photographer, copyright, license, and source URL on the right. Click **Save reviewed metadata** to protect manual tags from future AI updates.

The catalog, face embeddings, face models, and thumbnails are stored in `%LOCALAPPDATA%\GuiaLankaPhotoManager\` (on Windows). The image originals remain in their chosen folders until you explicitly approve moves.

## Installer fix originally introduced in v0.1.1 (PySide6 path-length error)

Windows can fail installing PySide6 when the environment is nested in a long Downloads path, with an error involving `qml\Qt\labs\assetdownloader` and `No such file or directory`. This release keeps the environment in `%LOCALAPPDATA%\GLPvenv`, independent of the extracted project location. All launch, AI installation and EXE build scripts use that path. You **do not have to enable Windows long paths** or move the source folder for this specific error.

If upgrading from v0.1.0, extract this ZIP into a *new* folder or replace all four `.bat` files and add `ENV_CONFIG.bat`, then rerun `INSTALL_WINDOWS.bat`. If an incomplete `.venv` folder remains inside the old project, it can be deleted; this release does not use it. If the error persists, try extracting the whole application to `C:\GLPhoto` and rerunning the installer.

## AI options

### GPS / metadata / manual classification (base installation)

- Imports JPG/JPEG, PNG, WebP, TIFF and BMP. Supports HEIC/HEIF only if optional `pillow-heif` is installed.
- Reads image width, height, camera, artist and copyright from standard EXIF, plus selected embedded XMP fields.
- Converts GPS EXIF coordinates into **approximate nearby Sri Lankan location hints**. This is *not* exact landmark verification; coordinates are never uploaded automatically.
- Stores original folder path, original file path, recorded source URL, photographer, license and copyright. **An original website, photographer or copyright holder cannot be reliably deduced from pixels alone.** If source metadata is absent, enter it manually. No reverse-image-search service is currently connected.
- Supports manual activity labels and attraction tags.

### Local Sri Lanka visual recognition (separate setup required)

**Why tagging might appear broken in v0.1.1:** The base setup installs the photo library, not the optional OpenCLIP AI packages. If you click `AI tag selected` without having run `INSTALL_AI_WINDOWS.bat`, classification cannot start. Even after packages install, first-time pretrained weights require internet.

1. **Close** the photo manager and run **`INSTALL_AI_WINDOWS.bat`**. This installs CPU-only PyTorch, torchvision and OpenCLIP; it is a **large download**. Wait for the final `SUCCESS` confirmation. 
2. Run **`DIAGNOSE_AI_WINDOWS.bat`**. It tests the actual model and writes `%TEMP%\GLPhoto_AI_Diagnostics.txt`. It will say `AI diagnostic PASSED` or include the precise failure. You can send that log for support; it contains library versions and computer paths but no source photos or API key.
3. Restart **`START_WINDOWS.bat`**. At the top, an **AI status banner** indicates whether the packages are missing. Click **Test local AI** to verify end-to-end image classification.
4. Import a few pictures, select **2-5 images**, and click **AI tag selected**. The first run downloads trained model weights; later runs can classify offline. The application now shows a summary of activity tags, tentative landmark matches, uncertain images, skipped manual tags and errors. Tags are also visible under image filenames in the gallery.
5. **Review the results**: activity suggestions use a more permissive similarity threshold, and exact landmarks remain conservative. A filename or GPS hint is not proof that an attraction is pictured. Saving reviewed metadata prevents later AI overwriting it.

If the AI packages are listed as installed but model testing fails, provide the `GLPhoto_AI_Diagnostics.txt` report. If `Processed 0 photos` appears, verify that photos were selected and were not already manually tagged. You do not need an OpenAI API key for local classification.

If you upgraded from v0.1.1, extract v0.1.2 into a new folder and run the new scripts. **The existing photo database is retained** in `%LOCALAPPDATA%\GuiaLankaPhotoManager`, and the Python environment remains `%LOCALAPPDATA%\GLPvenv`. No reimport is normally necessary.

The activity vocabulary covers safaris, elephants, leopards, birding, hiking, beaches, surfing, temples, historical ruins, train rides, tea plantations, waterfalls, village activities, boat rides, snorkeling, cooking classes and more. The landmark catalog includes Sigiriya, Dambulla, Polonnaruwa, Anuradhapura, Nine Arch Bridge, Little Adam's Peak, Ella Rock, Ravana Falls, Galle Fort, Temple of the Tooth, Yala, Wilpattu, Udawalawe, Minneriya, Kaudulla, Trincomalee and more. Edit `app/catalog.py` to customize this list.

**For a batch of 10,000 photos, CPU-based model inference can be slow**. Start with a sample of 100–200 photos to verify tags and measure throughput. There is no calibrated landmark certainty score in this MVP.

### Local face grouping (optional)

1. Click **Get face models**, approve downloading the official OpenCV YuNet and SFace ONNX weights (~37 MB combined).
2. Click **Group faces** to process all not-yet-scanned images. This can take a long time for 10,000 photos.
3. Switch to **People / Face Groups**, rename groups if desired, and double-click one to see its photos.

Face embeddings and group names are stored locally. No face data is sent to cloud AI. Face similarity matching can incorrectly combine different people or split the same person; group labels should be manually verified. The MVP offers group browsing and renaming, not merge/split/correction controls yet. Obtain appropriate permission before processing other people's faces, particularly customers or children.

### Cloud vision (optional, explicitly confirmed)

1. Select up to 50 photos on the visible page.
2. Click **Cloud AI selected** and provide your OpenAI API key (held in memory for this operation only; not saved).
3. Confirm the privacy/cost dialog; only these selected photos, resized to max 1024 pixels, are sent to the OpenAI Responses API using the specified vision-capable model.
4. Cloud recognition suggests activities, landmark and rough location. It never asserts source or copyright and does not identify people.

Requires an external OpenAI account/API key, network access and may incur API charges. Check the selected model's current availability and pricing with the API provider. No cloud call occurs during scanning or face grouping. Cloud requests do not preserve original embedded metadata, but the image pixels themselves might disclose private information.

## Review-before-move workflow

1. Select the photos you want to organize.
2. Click **Review moves** and select a destination directory.
3. Inspect the **full source-to-destination preview**. The proposed path is `destination / Location / PrimaryActivity / OriginalFilename` (sanitized for Windows). Unknown categories use `Location Unknown` and `Activity Unknown`.
4. Approve. The app refuses to overwrite existing destination files; filename conflicts get numbered suffixes when the preview is generated. It rechecks destinations when executing.
5. **Undo last moves** restores the most recent batch where original paths are free.

**Create a backup before mass-moving a production photo library.** This MVP records moves and offers undo, but a power failure or disk failure during a cross-drive move can still leave a partial copy or require manual repair. Try a small test folder first.

## Image exports

Select photos and click **Export selected**. Choose a preset or enter custom pixel dimensions and an output format.

| Setting | Supported choices |
|---|---|
| Dimensions | Custom W x H, including 272 x 300, 1200 x 800, 1080 x 1080, 1080 x 1350, 1920 x 1080 |
| Resize behavior | Crop to fill exact dimensions; Pad to fit exact dimensions; set one dimension to 0 to preserve aspect ratio |
| Formats | WebP, JPEG, PNG, TIFF |
| Quality | Adjustable for WebP and JPEG |
| Collision safety | No overwrites; generated names get numeric suffixes |
| Metadata | Exported pixels strip source metadata by default. A separate UTF-8 CSV export manifest records source, photographer, copyright, license, activity and location. |

**This is a resize/re-encode export, not permission to use an image.** Copyright and licensing must be independently verified. Original photos remain untouched by export.

## Windows EXE packaging

An **experimental** `BUILD_WINDOWS_EXE.bat` script builds a local Windows application folder using PyInstaller. Run it on Windows after installation. Output should be under `dist\GuiaLankaPhotoManager\`. This cannot be built or verified from the Linux development environment used to produce this ZIP. The optional OpenCLIP/PyTorch model may require build-specific dependency adjustments and results in a large package; for initial testing, use the Python launcher scripts.

## Tests

From the project root in a Python environment with Pillow and NumPy:

```shell
python -m pytest tests -q
```

The 11 automated tests cover importing/rescanning, manual tag protection, SQLite search, safe path sanitization, preview/commit/undo moves, exact-size WebP/JPEG/PNG export, copyright/source manifests, GPS hints and changed-image invalidation, plus AI score selection, manual-tag protection, missing dependencies and per-file error reporting. The actual Windows Qt GUI and pretrained OpenCLIP model load still require on-device verification. `DIAGNOSE_AI_WINDOWS.bat` now performs the missing real-model test.

## Limitations and recommended next phase

- Add asynchronous thumbnail generation and virtualized browsing for very large pages.
- Add explicit face group merge/split, side-by-side verification, and deletion of biometric embeddings.
- Add configurable offline model thresholds and human-review queues; curate location-specific recognition examples to improve Sri Lanka attraction accuracy.
- Add duplicate detection, IPTC/XMP metadata coverage, batch manual editing and comprehensive source audit logs.
- Add adjustable export naming templates, sharpening and batch folders; embed copyright metadata optionally while stripping GPS.
- Build and test on Windows 11 and publish a signed installer with an update mechanism.

## Code layout

- `app/ui.py` – Qt gallery, filters, review dialogs and export UI
- `app/db.py` – persistent SQLite catalog, search and indexing
- `app/metadata.py` – local EXIF/XMP import
- `app/catalog.py` – Sri Lanka-specific vocabulary and approximate GPS areas
- `app/recognition.py` – on-demand local OpenCLIP and optional cloud analysis
- `app/ai_doctor.py` – setup diagnostics, compatible imports, optional model smoke test
- `app/faces.py` – local YuNet/SFace face embedding and matching
- `app/operations.py` – move/undo and non-destructive image exports
- `tests/` – automated non-GUI tests

### Framework/model references

- Qt for Python / PySide6: https://doc.qt.io/qtforpython-6/
- OpenCV Zoo YuNet and SFace: https://github.com/opencv/opencv_zoo
- OpenCV face tutorial: https://docs.opencv.org/4.x/d0/dd4/tutorial_dnn_face.html
- OpenCLIP: https://github.com/mlfoundations/open_clip

Review third-party dependency and model licenses separately before commercial redistribution.
