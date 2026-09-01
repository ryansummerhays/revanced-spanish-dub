#!/usr/bin/env python3
"""Inject the Spanish-study overlay into a pinned Morphe source checkout.

Fails loudly when upstream source does not match the expected v1.41.0 anchors.
That is intentional: a failed build is safer than silently generating a bundle
whose hooks landed in the wrong place.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly 1 anchor in {path}, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"patched: {label}")


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: apply_overlay.py <morphe-root> <overlay-src-root>")

    root = Path(sys.argv[1]).resolve()
    overlay_src = Path(sys.argv[2]).resolve()
    ext_java = root / "extensions/youtube/src/main/java"
    vot = ext_java / "app/morphe/extension/youtube/patches/voiceovertranslation/VoiceOverTranslationPatch.java"
    sheet = ext_java / "app/morphe/extension/youtube/patches/voiceovertranslation/VotBottomSheet.java"

    if not vot.is_file() or not sheet.is_file():
        raise RuntimeError("Morphe Voice-over-Translation source files were not found")

    target_pkg = ext_java / "app/spanishstudy/vot"
    target_pkg.mkdir(parents=True, exist_ok=True)
    sources = sorted(overlay_src.glob("app/spanishstudy/vot/*.java"))
    if not sources:
        raise RuntimeError(f"No overlay Java sources found under {overlay_src}")
    for src in sources:
        shutil.copy2(src, target_pkg / src.name)
        print(f"copied: {src.name}")

    replace_once(vot, "import app.morphe.extension.youtube.shared.VideoState;\n", "import app.morphe.extension.youtube.shared.VideoState;\nimport app.spanishstudy.vot.SpanishStudyController;\n", "VoiceOverTranslationPatch import")

    replace_once(vot, '''                if (playerType == PlayerType.NONE) {\n                    currentVideoId = "";\n                    segments = new ArrayList<>();\n                    TtsPrefetcher.clear();\n                }''', '''                if (playerType == PlayerType.NONE) {\n                    currentVideoId = "";\n                    segments = new ArrayList<>();\n                    TtsPrefetcher.clear();\n                    SpanishStudyController.onVideoCleared();\n                }''', "clear study overlay when player closes")

    replace_once(vot, '''        currentVideoId = videoId;\n        segments = new ArrayList<>();\n        httpErrorDialogShownThisVideo = false;''', '''        currentVideoId = videoId;\n        segments = new ArrayList<>();\n        SpanishStudyController.onVideoCleared();\n        httpErrorDialogShownThisVideo = false;''', "clear old study data on new video")

    replace_once(vot, '''        videoPositionHint = timeMs;\n        // Video state can be null until the overlay is activated the first time.''', '''        videoPositionHint = timeMs;\n        SpanishStudyController.onVideoTimeChanged(timeMs);\n        // Video state can be null until the overlay is activated the first time.''', "feed playback time to matching subtitles")

    replace_once(vot, '''        if (!sessionEnabled) {\n            stopTts();\n            lastSpokenIndex = -1;''', '''        if (!sessionEnabled) {\n            stopTts();\n            SpanishStudyController.onSessionDisabled();\n            lastSpokenIndex = -1;''', "hide study subtitles when session is disabled")

    replace_once(vot, '''        stopTts();\n        segments = new ArrayList<>();\n        lastSpokenIndex = -1;\n        // Without this, in-flight onUpdate callbacks for the old language would restore''', '''        stopTts();\n        segments = new ArrayList<>();\n        SpanishStudyController.onVideoCleared();\n        lastSpokenIndex = -1;\n        // Without this, in-flight onUpdate callbacks for the old language would restore''', "clear study data when transcript reloads")

    replace_once(vot, '''                                segments = updated;\n                            }''', '''                                segments = updated;\n                                SpanishStudyController.onTranscriptUpdated(updated);\n                            }''', "publish translated batch to study tools")

    replace_once(vot, '''                        if (segments.isEmpty()) segments = fetched;\n                        TtsPrefetcher.updateVideo(videoId, segments);''', '''                        if (segments.isEmpty()) segments = fetched;\n                        SpanishStudyController.onTranscriptUpdated(segments);\n                        TtsPrefetcher.updateVideo(videoId, segments);''', "publish completed translated transcript")

    study_methods = r'''
    /** Snapshot consumed by the optional Spanish study UI. */
    public static List<TranscriptSegment> getTranslatedSegmentsSnapshot() {
        Utils.verifyOnMainThread();
        return new ArrayList<>(segments);
    }

    /** @return true while the current transcript is still being fetched/translated. */
    public static boolean isTranscriptLoading() {
        return isLoading;
    }

    /** @return current YouTube video id for vocabulary export filenames. */
    public static String getCurrentVideoIdForStudy() {
        return currentVideoId;
    }

    /**
     * Speaks arbitrary vocabulary using the exact VoT target language and selected voice.
     * This keeps pre-study pronunciation consistent with the voice heard during dubbing.
     */
    public static void speakPreviewText(String text) {
        Utils.verifyOnMainThread();
        if (text == null || text.trim().isEmpty()) return;

        stopTts();
        final String lang = resolveTargetLang();
        final String voice = resolveVoice(lang);
        if (voice == null) return;

        final float volume = Settings.VOT_TRANSLATION_VOLUME.get() / 100.0f;
        final long testId = ++currentTestId;
        isTestSpeaking = true;
        lastTestVoiceId = voice;
        VotOriginalVolumePatch.setAudioMultiplier(Settings.VOT_ORIGINAL_AUDIO_VOLUME.get() / 100.0f);

        if (TTS_ENGINE_SYSTEM.equals(voice)) {
            ensureTts();
            if (!ttsReady) {
                isTestSpeaking = false;
                VotOriginalVolumePatch.clearAudioMultiplier();
                return;
            }
            updateTtsLanguage();
            Bundle params = new Bundle();
            params.putFloat(TextToSpeech.Engine.KEY_PARAM_VOLUME, volume);
            tts.setSpeechRate(1.0f);
            final long playbackId = ttsEngine.markBusy();
            tts.speak(text, TextToSpeech.QUEUE_FLUSH, params,
                    VOT_TEST_ID_PREFIX + testId + "_" + playbackId);
            return;
        }

        ttsEngine.speak(text, voice, lang, volume, () -> updateIsTestSpeaking(testId));
    }

'''
    replace_once(vot, "    /** Lazily creates the System TTS instance and wires its completion listener. Idempotent. */\n", study_methods + "    /** Lazily creates the System TTS instance and wires its completion listener. Idempotent. */\n", "add study-facing VoT APIs")

    replace_once(sheet, "import app.morphe.extension.youtube.shared.PipDismissHelper;\n", "import app.morphe.extension.youtube.shared.PipDismissHelper;\nimport app.spanishstudy.vot.SpanishStudyController;\n", "VotBottomSheet import")

    replace_once(sheet, '''        translationRow.setOnClickListener(v -> showTranslationServicePicker(context, mainRef[0]));\n        refreshTranslation.run();''', '''        translationRow.setOnClickListener(v -> showTranslationServicePicker(context, mainRef[0]));\n        refreshTranslation.run();\n\n        LinearLayout studyRow = makeValueRow(context, fg, "Spanish study tools");\n        ((TextView) studyRow.getTag()).setText("Subtitles · vocabulary");\n        studyRow.setOnClickListener(v -> {\n            if (mainRef[0] != null) mainRef[0].dismiss();\n            SpanishStudyController.showTools(Utils.getActivity());\n        });''', "create Spanish study tools row")

    replace_once(sheet, '''        content.addView(translationRow);\n        content.addView(engineRow);\n        content.addView(makeDivider(context, fg));''', '''        content.addView(translationRow);\n        content.addView(engineRow);\n        content.addView(studyRow);\n        content.addView(makeDivider(context, fg));''', "add Spanish study tools row")

    print("Spanish study overlay integration complete")


if __name__ == "__main__":
    main()
