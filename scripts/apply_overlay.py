#!/usr/bin/env python3
"""Inject Spanish-study v2 into pinned Morphe v1.41.0 source.

The script is intentionally anchor-guarded: an upstream source mismatch fails the build
rather than silently producing a bundle with hooks in the wrong place.
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
    pkg = ext_java / "app/morphe/extension/youtube/patches/voiceovertranslation"
    vot = pkg / "VoiceOverTranslationPatch.java"
    sheet = pkg / "VotBottomSheet.java"
    translator = pkg / "TranscriptTranslator.java"
    fetcher = pkg / "TranscriptFetcher.java"
    tts = pkg / "TtsEngine.java"

    for required in (vot, sheet, translator, fetcher, tts):
        if not required.is_file():
            raise RuntimeError(f"Required Morphe source file not found: {required}")

    target_pkg = ext_java / "app/spanishstudy/vot"
    target_pkg.mkdir(parents=True, exist_ok=True)
    sources = sorted(overlay_src.glob("app/spanishstudy/vot/*.java"))
    if not sources:
        raise RuntimeError(f"No overlay Java sources found under {overlay_src}")
    for src in sources:
        shutil.copy2(src, target_pkg / src.name)
        print(f"copied: {src.name}")

    # ---- Existing study UI / transcript hooks -------------------------------------------------
    replace_once(vot, "import app.morphe.extension.youtube.shared.VideoState;\n",
                 "import app.morphe.extension.youtube.shared.VideoState;\nimport app.spanishstudy.vot.SpanishStudyController;\n",
                 "VoiceOverTranslationPatch import")

    replace_once(vot, '''                if (playerType == PlayerType.NONE) {
                    currentVideoId = "";
                    segments = new ArrayList<>();
                    TtsPrefetcher.clear();
                }''', '''                if (playerType == PlayerType.NONE) {
                    currentVideoId = "";
                    segments = new ArrayList<>();
                    TtsPrefetcher.clear();
                    SpanishStudyController.onVideoCleared();
                }''', "clear study overlay when player closes")

    replace_once(vot, '''        currentVideoId = videoId;
        segments = new ArrayList<>();
        httpErrorDialogShownThisVideo = false;''', '''        currentVideoId = videoId;
        segments = new ArrayList<>();
        SpanishStudyController.onVideoCleared();
        httpErrorDialogShownThisVideo = false;''', "clear old study data on new video")

    replace_once(vot, '''        videoPositionHint = timeMs;
        // Video state can be null until the overlay is activated the first time.''', '''        videoPositionHint = timeMs;
        SpanishStudyController.onVideoTimeChanged(timeMs);
        // Video state can be null until the overlay is activated the first time.''', "feed playback time to matching subtitles")

    replace_once(vot, '''        sessionEnabled = false;
        Settings.VOT_SESSION_ENABLED.save(false);
        stopTts();''', '''        sessionEnabled = false;
        Settings.VOT_SESSION_ENABLED.save(false);
        stopTts();
        SpanishStudyController.onSessionDisabled();''', "hide study subtitles when session is disabled")

    replace_once(vot, '''        stopTts();
        segments = new ArrayList<>();
        lastSpokenIndex = -1;
        // Without this, in-flight onUpdate callbacks for the old language would restore''', '''        stopTts();
        segments = new ArrayList<>();
        SpanishStudyController.onVideoCleared();
        lastSpokenIndex = -1;
        // Without this, in-flight onUpdate callbacks for the old language would restore''', "clear study data when transcript reloads")

    replace_once(vot, '''                                segments = updated;
                            }''', '''                                segments = updated;
                                SpanishStudyController.onTranscriptUpdated(updated);
                            }''', "publish translated batch to study tools")

    replace_once(vot, '''                        if (segments.isEmpty()) segments = fetched;
                        TtsPrefetcher.updateVideo(videoId, segments);''', '''                        if (segments.isEmpty()) segments = fetched;
                        SpanishStudyController.onTranscriptUpdated(segments);
                        TtsPrefetcher.updateVideo(videoId, segments);''', "publish completed translated transcript")

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

    /** Speaks vocabulary with the exact VoT target language and selected voice. */
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
        PlayerVolumePatch.setDuckMultiplier(Settings.VOT_ORIGINAL_AUDIO_VOLUME.get() / 100.0f);

        if (TTS_ENGINE_SYSTEM.equals(voice)) {
            ensureTts();
            if (!ttsReady) {
                isTestSpeaking = false;
                PlayerVolumePatch.clearDuckMultiplier();
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
    replace_once(vot,
                 "    /** Lazily creates the System TTS instance and wires its completion listener. Idempotent. */\n",
                 study_methods + "    /** Lazily creates the System TTS instance and wires its completion listener. Idempotent. */\n",
                 "add study-facing VoT APIs")

    replace_once(sheet, "import app.morphe.extension.youtube.shared.PipDismissHelper;\n",
                 "import app.morphe.extension.youtube.shared.PipDismissHelper;\nimport app.spanishstudy.vot.SpanishStudyController;\n",
                 "VotBottomSheet import")

    replace_once(sheet, '''        translationRow.setOnClickListener(v -> showTranslationServicePicker(context, mainRef[0]));
        refreshTranslation.run();''', '''        translationRow.setOnClickListener(v -> showTranslationServicePicker(context, mainRef[0]));
        refreshTranslation.run();

        LinearLayout studyRow = makeValueRow(context, fg, "Spanish study tools");
        ((TextView) studyRow.getTag()).setText("Gemini · synced subtitles · vocabulary");
        studyRow.setOnClickListener(v -> {
            if (mainRef[0] != null) mainRef[0].dismiss();
            SpanishStudyController.showTools(Utils.getActivity());
        });''', "create Spanish study tools row")

    replace_once(sheet, '''        content.addView(translationRow);
        content.addView(engineRow);
        content.addView(makeDivider(context, fg));''', '''        content.addView(translationRow);
        content.addView(engineRow);
        content.addView(studyRow);
        content.addView(makeDivider(context, fg));''', "add Spanish study tools row")

    # ---- Direct Gemini provider override -------------------------------------------------------
    replace_once(translator, "import app.morphe.extension.youtube.settings.Settings;\n",
                 "import app.morphe.extension.youtube.settings.Settings;\nimport app.spanishstudy.vot.GeminiTranslator;\n",
                 "TranscriptTranslator Gemini import")

    replace_once(translator,
                 "    private static final int OPENROUTER_MAX_BATCH_CHARS = 1_500;\n",
                 "    private static final int OPENROUTER_MAX_BATCH_CHARS = 1_500;\n    private static final int GEMINI_MAX_BATCH_CHARS = 900;\n",
                 "Gemini batch budget")

    replace_once(translator, '''        final boolean isMyMemory = service.equals(TRANSLATION_SERVICE_MY_MEMORY);
        final boolean isOpenRouter = service.equals(TRANSLATION_SERVICE_OPENROUTER);
        final int maxBatchChars = isMyMemory ? MYMEMORY_MAX_CHARS
                : isOpenRouter ? OPENROUTER_MAX_BATCH_CHARS
                  : GOOGLE_MAX_BATCH_CHARS;''', '''        final boolean isMyMemory = service.equals(TRANSLATION_SERVICE_MY_MEMORY);
        final boolean isOpenRouter = service.equals(TRANSLATION_SERVICE_OPENROUTER);
        final boolean isGemini = GeminiTranslator.isEnabled();
        final int maxBatchChars = isGemini ? GEMINI_MAX_BATCH_CHARS
                : isMyMemory ? MYMEMORY_MAX_CHARS
                : isOpenRouter ? OPENROUTER_MAX_BATCH_CHARS
                  : GOOGLE_MAX_BATCH_CHARS;''', "select Gemini batch size")

    replace_once(translator, '''        final int batchDelay = isMyMemory ? MYMEMORY_INTER_BATCH_DELAY_MS
                : isOpenRouter ? OPENROUTER_INTER_BATCH_DELAY_MS
                  : GOOGLE_INTER_BATCH_DELAY_MS;''', '''        final int batchDelay = isGemini ? 0
                : isMyMemory ? MYMEMORY_INTER_BATCH_DELAY_MS
                : isOpenRouter ? OPENROUTER_INTER_BATCH_DELAY_MS
                  : GOOGLE_INTER_BATCH_DELAY_MS;''', "remove Gemini inter-batch delay")

    replace_once(translator, '''                if (isOpenRouter && firstBatchAfterReposition) {
                    capFirstBatch(batches, batchDone, index);
                }''', '''                if ((isOpenRouter || isGemini) && firstBatchAfterReposition) {
                    capFirstBatch(batches, batchDone, index);
                }''', "small first Gemini batch")

    replace_once(translator, '''        String service = Settings.VOT_TRANSLATION_SERVICE.get();
        if (service.equals(TRANSLATION_SERVICE_MY_MEMORY)) {''', '''        if (GeminiTranslator.isEnabled()) {
            return GeminiTranslator.translateBatch(videoId, segments, targetLang);
        }
        String service = Settings.VOT_TRANSLATION_SERVICE.get();
        if (service.equals(TRANSLATION_SERVICE_MY_MEMORY)) {''', "delegate batches to direct Gemini")

    # ---- Shorter source/TTS chunks for faster resynchronization -------------------------------
    replace_once(fetcher, "    private static final int MAX_SENTENCE_CHARS = 300;\n",
                 "    private static final int MAX_SENTENCE_CHARS = 180;\n",
                 "shorter punctuated speech chunks")
    replace_once(fetcher, "    private static final long MIN_SEGMENT_DURATION_MS = 2_000;\n",
                 "    private static final long MIN_SEGMENT_DURATION_MS = 1_200;\n",
                 "allow shorter speech segments")
    replace_once(fetcher, "    private static final int MAX_UNPUNCTUATED_CHARS = 200;\n",
                 "    private static final int MAX_UNPUNCTUATED_CHARS = 120;\n",
                 "shorter ASR speech chunks")

    # ---- Edge word-boundary metadata drives rolling subtitle synchronization ------------------
    replace_once(tts, "import android.util.Base64;\n",
                 "import android.util.Base64;\n\nimport org.json.JSONArray;\nimport org.json.JSONObject;\n",
                 "TtsEngine JSON imports")
    replace_once(tts, "import app.morphe.extension.shared.Utils;\n",
                 "import app.morphe.extension.shared.Utils;\nimport app.spanishstudy.vot.SpanishStudyController;\n",
                 "TtsEngine study import")
    replace_once(tts, '\\"wordBoundaryEnabled\\":\\"false\\"',
                 '\\"wordBoundaryEnabled\\":\\"true\\"',
                 "enable Edge word boundaries")
    replace_once(tts, '''                    ByteArrayOutputStream audioOut = new ByteArrayOutputStream();
                    collectAudio(persistentIn, audioOut);''', '''                    ByteArrayOutputStream audioOut = new ByteArrayOutputStream();
                    SpanishStudyController.beginWordTimings(text);
                    collectAudio(persistentIn, audioOut, text);''', "start word timing capture")
    replace_once(tts,
                 "    private void collectAudio(InputStream in, ByteArrayOutputStream audioOut) throws IOException {\n",
                 "    private void collectAudio(InputStream in, ByteArrayOutputStream audioOut, String sourceText) throws IOException {\n",
                 "pass source text into Edge metadata parser")
    replace_once(tts, '''            if (opcode == 0x1) { // text frame
                if (new String(payload, StandardCharsets.UTF_8).contains("Path:turn.end")) break;
            } else if (opcode == 0x2 && payload.length > 2) { // binary audio frame''', '''            if (opcode == 0x1) { // text frame
                String frame = new String(payload, StandardCharsets.UTF_8);
                if (frame.contains("Path:audio.metadata")) publishWordBoundaries(sourceText, frame);
                if (frame.contains("Path:turn.end")) break;
            } else if (opcode == 0x2 && payload.length > 2) { // binary audio frame''', "parse Edge metadata text frames")

    word_parser = r'''
    private void publishWordBoundaries(String sourceText, String frame) {
        try {
            int bodyAt = frame.indexOf("\r\n\r\n");
            if (bodyAt < 0 || bodyAt + 4 >= frame.length()) return;
            JSONObject root = new JSONObject(frame.substring(bodyAt + 4));
            JSONArray metadata = root.optJSONArray("Metadata");
            if (metadata == null || metadata.length() == 0) return;

            java.util.ArrayList<String> words = new java.util.ArrayList<>();
            java.util.ArrayList<Long> starts = new java.util.ArrayList<>();
            java.util.ArrayList<Long> durations = new java.util.ArrayList<>();
            for (int i = 0; i < metadata.length(); i++) {
                JSONObject item = metadata.optJSONObject(i);
                if (item == null || !"WordBoundary".equalsIgnoreCase(item.optString("Type"))) continue;
                JSONObject data = item.optJSONObject("Data");
                if (data == null) continue;
                JSONObject textObj = data.optJSONObject("text");
                if (textObj == null) textObj = data.optJSONObject("Text");
                String word = textObj == null ? "" : textObj.optString("Text", "");
                if (word.isBlank()) continue;
                words.add(word);
                starts.add(Math.max(0L, data.optLong("Offset", 0L) / 10_000L));
                durations.add(Math.max(0L, data.optLong("Duration", 0L) / 10_000L));
            }
            if (words.isEmpty()) return;
            String[] w = words.toArray(new String[0]);
            long[] s = new long[starts.size()];
            long[] d = new long[durations.size()];
            for (int i = 0; i < starts.size(); i++) {
                s[i] = starts.get(i);
                d[i] = durations.get(i);
            }
            SpanishStudyController.onWordTimings(sourceText, w, s, d);
        } catch (Exception ex) {
            Logger.printDebug(() -> "Edge word-boundary parse failed", ex);
        }
    }

'''
    replace_once(tts, "    private void readFully(InputStream in, byte[] buf) throws IOException {\n",
                 word_parser + "    private void readFully(InputStream in, byte[] buf) throws IOException {\n",
                 "add Edge word-boundary parser")

    print("Spanish study v2 overlay integration complete")


if __name__ == "__main__":
    main()
