#!/usr/bin/env python3
"""v2.27.0: stock Morphe v1.41.0 VOT + passive lossless bilingual subtitles.

This patch intentionally does NOT modify TranscriptTranslator, TtsEngine, TtsPrefetcher, source
segmentation, speech rate, seek behavior, Edge synthesis, cache, or prefetch. OpenRouter/Mistral
therefore behaves exactly as stock Morphe. The only additions are read-only lifecycle hooks used to
render bilingual subtitles and paginate long text instead of clipping it.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path


def rep(path: Path, old: str, new: str, label: str, count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    found = text.count(old)
    if found != count:
        raise RuntimeError(f"{label}: expected {count} anchor(s), found {found} in {path}")
    path.write_text(text.replace(old, new, count), encoding="utf-8")
    print("patched:", label)


def section(path: Path, start_marker: str, end_marker: str):
    text = path.read_text(encoding="utf-8")
    start_at = text.index(start_marker)
    start = text.rfind("\n", 0, start_at) + 1
    end = text.index(end_marker, start_at)
    return text, start, end, text[start:end]


def rep_section(path: Path, start_marker: str, end_marker: str,
                old: str, new: str, label: str, count: int = 1) -> None:
    text, start, end, body = section(path, start_marker, end_marker)
    found = body.count(old)
    if found != count:
        raise RuntimeError(f"{label}: expected {count} section anchor(s), found {found}")
    body = body.replace(old, new, count)
    path.write_text(text[:start] + body + text[end:], encoding="utf-8")
    print("patched:", label)


def copy_sources(root: Path, repo: Path) -> None:
    target = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    target.mkdir(parents=True, exist_ok=True)

    sources = {
        "SpanishStudyPrefs.java":
            repo / "overlay/v216/app/spanishstudy/vot/SpanishStudyPrefs.java",
        "SpanishStudyDiagnostics.java":
            repo / "overlay/src/app/spanishstudy/vot/SpanishStudyDiagnostics.java",
        "SubtitlePagePolicy.java":
            repo / "overlay/v224/app/spanishstudy/vot/SubtitlePagePolicy.java",
        "BilingualCardPolicy.java":
            repo / "overlay/v223/app/spanishstudy/vot/BilingualCardPolicy.java",
        "SubtitleLinePolicy.java":
            repo / "overlay/v225/app/spanishstudy/vot/SubtitleLinePolicy.java",
        "SpanishStudyController.java":
            repo / "overlay/v227/app/spanishstudy/vot/SpanishStudyController.java",
        "SpanishSubtitleOverlay.java":
            repo / "overlay/v227/app/spanishstudy/vot/SpanishSubtitleOverlay.java",
        "SpanishStudySheet.java":
            repo / "overlay/v227/app/spanishstudy/vot/SpanishStudySheet.java",
    }

    for name, src in sources.items():
        if not src.is_file():
            raise RuntimeError(f"missing source: {src}")
        shutil.copy2(src, target / name)
        print("copied:", name)


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: patch_v2270_stock_morphe_subtitles.py <morphe-root> <repo-root>")

    root = Path(sys.argv[1]).resolve()
    repo = Path(sys.argv[2]).resolve()
    copy_sources(root, repo)

    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    vot = pkg / "VoiceOverTranslationPatch.java"
    fetcher = pkg / "TranscriptFetcher.java"
    bottom_sheet = pkg / "VotBottomSheet.java"
    auto = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/AutoCaptionsPatch.java"

    for path in (vot, fetcher, bottom_sheet, auto):
        if not path.is_file():
            raise RuntimeError(f"missing Morphe source: {path}")

    rep(
        vot,
        "import app.morphe.extension.youtube.shared.VideoState;\n",
        "import app.morphe.extension.youtube.shared.VideoState;\n"
        "import app.spanishstudy.vot.SpanishStudyController;\n",
        "VOT passive subtitle import",
    )

    rep(
        vot,
        '''                    currentVideoId = "";
                    segments = new ArrayList<>();
                    TtsPrefetcher.clear();''',
        '''                    currentVideoId = "";
                    segments = new ArrayList<>();
                    TtsPrefetcher.clear();
                    SpanishStudyController.onVideoCleared();''',
        "clear subtitle overlay when player closes",
    )

    rep(
        vot,
        '''        currentVideoId = videoId;
        segments = new ArrayList<>();
        httpErrorDialogShownThisVideo = false;''',
        '''        currentVideoId = videoId;
        segments = new ArrayList<>();
        SpanishStudyController.onVideoCleared();
        httpErrorDialogShownThisVideo = false;''',
        "clear subtitle overlay on new video",
    )

    rep(
        vot,
        '''        videoPositionHint = timeMs;
        // Video state can be null until the overlay is activated the first time.''',
        '''        videoPositionHint = timeMs;
        SpanishStudyController.onVideoTimeChanged(timeMs);
        // Video state can be null until the overlay is activated the first time.''',
        "drive passive subtitle overlay from Morphe playhead",
    )

    rep_section(
        vot,
        "private static void loadTranscript(String videoId)",
        "\n    /** Lazily creates the System TTS instance",
        '''                                segments = updated;''',
        '''                                segments = updated;
                                SpanishStudyController.onTranscriptUpdated(updated);''',
        "observe progressive stock transcript snapshots",
    )

    rep_section(
        vot,
        "private static void loadTranscript(String videoId)",
        "\n    /** Lazily creates the System TTS instance",
        '''                        if (segments.isEmpty()) segments = fetched;
                        TtsPrefetcher.updateVideo(videoId, segments);''',
        '''                        if (segments.isEmpty()) segments = fetched;
                        SpanishStudyController.onTranscriptUpdated(segments);
                        TtsPrefetcher.updateVideo(videoId, segments);''',
        "observe final stock transcript snapshot",
    )

    rep(
        vot,
        '''        Settings.VOT_SESSION_ENABLED.save(false);
        stopTts();
        lastSpokenIndex = -1;''',
        '''        Settings.VOT_SESSION_ENABLED.save(false);
        stopTts();
        SpanishStudyController.onSessionDisabled();
        lastSpokenIndex = -1;''',
        "hide passive subtitles when session is disabled",
    )

    study_getters = r'''
    /** Read-only study hook: current video id. Does not mutate VOT state. */
    public static String getCurrentVideoIdForStudy() {
        return currentVideoId;
    }

    /** Read-only study hook: whether the stock transcript worker is loading. */
    public static boolean isTranscriptLoadingForStudy() {
        return isLoading;
    }

    /**
     * Read-only study hook: index Morphe is audibly speaking, or -1.
     * Used only to keep the matching subtitle visible when stock speech extends beyond the
     * source caption display window.
     */
    public static int getActiveSpokenIndexForStudy() {
        Utils.verifyOnMainThread();
        boolean active = ttsEngine.isSpeaking() || (tts != null && tts.isSpeaking());
        return active ? lastSpokenIndex : -1;
    }

    /** Read-only copy of Morphe's own estimated video timestamp for current TTS completion. */
    public static long getTtsEndVideoTimeMsForStudy() {
        Utils.verifyOnMainThread();
        return ttsEndVideoTimeMs;
    }

'''
    rep(
        vot,
        "    /** Lazily creates the System TTS instance and wires its completion listener. Idempotent. */\n",
        study_getters
        + "    /** Lazily creates the System TTS instance and wires its completion listener. Idempotent. */\n",
        "add read-only subtitle observer getters",
    )

    rep(
        fetcher,
        "import app.morphe.extension.shared.Utils;\n",
        "import app.morphe.extension.shared.Utils;\n"
        "import app.spanishstudy.vot.SpanishStudyController;\n",
        "TranscriptFetcher passive subtitle import",
    )

    rep(
        fetcher,
        "        List<TranscriptSegment> segments = fetchEnglishSegments(videoId);\n",
        "        List<TranscriptSegment> segments = fetchEnglishSegments(videoId);\n"
        "        SpanishStudyController.onSourceTranscriptFetched(segments);\n",
        "publish native Morphe source segments",
    )

    rep(
        bottom_sheet,
        "import app.morphe.extension.youtube.shared.PipDismissHelper;\n",
        "import app.morphe.extension.youtube.shared.PipDismissHelper;\n"
        "import app.spanishstudy.vot.SpanishStudyController;\n",
        "VOT bottom sheet study import",
    )

    rep(
        bottom_sheet,
        '''        translationRow.setOnClickListener(v -> showTranslationServicePicker(context, mainRef[0]));
        refreshTranslation.run();''',
        '''        translationRow.setOnClickListener(v -> showTranslationServicePicker(context, mainRef[0]));
        refreshTranslation.run();

        LinearLayout studyRow = makeValueRow(context, fg, "Spanish study");
        ((TextView) studyRow.getTag()).setText("Bilingual subtitles · diagnostics");
        studyRow.setOnClickListener(v -> {
            if (mainRef[0] != null) mainRef[0].dismiss();
            SpanishStudyController.showTools(Utils.getActivity());
        });''',
        "create passive subtitle settings row",
    )

    rep(
        bottom_sheet,
        '''        content.addView(translationRow);
        content.addView(engineRow);
        content.addView(makeDivider(context, fg));''',
        '''        content.addView(translationRow);
        content.addView(engineRow);
        content.addView(studyRow);
        content.addView(makeDivider(context, fg));''',
        "add passive subtitle settings row",
    )

    rep(
        auto,
        "import app.morphe.extension.youtube.settings.Settings;\n",
        "import app.morphe.extension.youtube.settings.Settings;\n"
        "import app.spanishstudy.vot.SpanishStudyController;\n",
        "AutoCaptions passive subtitle import",
    )

    rep(
        auto,
        '''    public static boolean disableAutoCaptions(boolean original) {
        // After the guard window (150ms), respect the user's manual CC button toggle.''',
        '''    public static boolean disableAutoCaptions(boolean original) {
        if (SpanishStudyController.suppressNativeCaptions()) return true;
        // After the guard window (150ms), respect the user's manual CC button toggle.''',
        "avoid duplicate automatic captions",
    )

    print("v2.27.0 stock Morphe + passive subtitle integration complete")


if __name__ == "__main__":
    main()
