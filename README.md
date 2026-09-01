# ReVanced / Morphe Spanish Dub Study Bundle

Custom build overlay for Morphe's YouTube **Voice over translation** patch.

The goal is simple: the translated Spanish string that Morphe sends to TTS is also the string shown on screen, so the dub and Spanish subtitles cannot disagree because of a second translator.

## Added features

- Exact-match translated Spanish subtitle overlay.
- Whole-video vocabulary review after translation finishes.
- Offline ranking of likely tricky/repeated Spanish words.
- Persistent **Known** word list.
- **Listen** button that uses the same selected VoT Spanish voice as the dub.
- SpanishDict lookup.
- CSV, JSON and Anki TSV vocabulary exports to `Downloads/SpanishStudyVOT`.
- Export automatically omits words marked **Known**.

## Upstream target

Builds are pinned to **Morphe patches v1.41.0** so source changes upstream cannot silently move our hooks. The generated `.mpp` is a full Morphe patch bundle with these Spanish-study additions integrated into the existing **Voice over translation** patch.

Morphe v1.41.0 supports multiple YouTube versions, including stable 21.07.247, 21.04.223, 20.51.39, 20.31.42 and 20.21.37, plus newer experimental targets. Use a version listed as supported by the bundle rather than assuming your old 20.40.45 APK is compatible.

## Build

The GitHub Actions workflow:

1. Checks out this repo.
2. Checks out `MorpheApp/morphe-patches` at `v1.41.0`.
3. Copies the Spanish-study Java sources into the YouTube extension.
4. Applies guarded source edits. If an expected upstream anchor differs, the build fails instead of producing a questionable bundle.
5. Runs Morphe's normal `:patches:buildAndroid` task with Java 21.
6. Uploads the resulting `.mpp` plus SHA-256 checksum as a workflow artifact.

You can also start the workflow manually from **Actions → Build custom Spanish dub patch bundle → Run workflow**.

## In-app use after patching YouTube

1. Enable **Voice over translation**.
2. Choose Spanish as target/caption language.
3. Choose translation service and Spanish voice.
4. Open the VoT player sheet.
5. Open **Spanish study tools**.
6. Turn matching subtitles on/off.
7. Tap **Review vocabulary** before watching; the tool waits for the full translated transcript.
8. Listen to words, mark familiar ones **Known**, or export the remaining list.
9. Resume the video and use the matching Spanish subtitles with the dub.

## Licensing

This repo contains an integration overlay intended for use with Morphe's GPLv3 code. See `LICENSE-NOTES.md` and preserve upstream Morphe notices/Section 7 terms when distributing derived builds.
