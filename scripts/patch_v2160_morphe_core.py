#!/usr/bin/env python3
"""v2.16.0: keep Morphe v1.41.0 VOT architecture and add only isolated study/integrity hooks."""
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


def copy_sources(root: Path, legacy_overlay: Path, clean_overlay: Path) -> None:
    target = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    target.mkdir(parents=True, exist_ok=True)
    for name in (
        "DubTextSanitizer.java",
        "OpenRouterOutputGuard.java",
        "SpanishStudyDiagnostics.java",
    ):
        src = legacy_overlay / "app/spanishstudy/vot" / name
        if not src.is_file():
            raise RuntimeError(f"missing shared source: {src}")
        shutil.copy2(src, target / name)
        print("copied:", name)
    for name in (
        "OpenRouterBudget.java",
        "OpenRouterTelemetry.java",
        "SpanishStudyPrefs.java",
        "SpanishStudyController.java",
        "SpanishStudySheet.java",
        "SpanishSubtitleOverlay.java",
    ):
        src = clean_overlay / "app/spanishstudy/vot" / name
        if not src.is_file():
            raise RuntimeError(f"missing v2.16 source: {src}")
        shutil.copy2(src, target / name)
        print("copied:", name)


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit("usage: patch_v2160_morphe_core.py <morphe-root> <legacy-overlay-src> <v216-overlay-src>")

    root = Path(sys.argv[1]).resolve()
    legacy_overlay = Path(sys.argv[2]).resolve()
    clean_overlay = Path(sys.argv[3]).resolve()
    copy_sources(root, legacy_overlay, clean_overlay)

    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    vot = pkg / "VoiceOverTranslationPatch.java"
    translator = pkg / "TranscriptTranslator.java"
    fetcher = pkg / "TranscriptFetcher.java"
    sheet = pkg / "VotBottomSheet.java"
    auto = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/AutoCaptionsPatch.java"
    for path in (vot, translator, fetcher, sheet, auto):
        if not path.is_file():
            raise RuntimeError(f"missing Morphe source: {path}")

    # ------------------------------------------------------------------------------------------
    # Morphe orchestrator: lifecycle + subtitle observer hooks only.
    # ------------------------------------------------------------------------------------------
    rep(vot,
        "import app.morphe.extension.youtube.shared.VideoState;\n",
        "import app.morphe.extension.youtube.shared.VideoState;\n"
        "import app.spanishstudy.vot.DubTextSanitizer;\n"
        "import app.spanishstudy.vot.OpenRouterTelemetry;\n"
        "import app.spanishstudy.vot.SpanishStudyController;\n"
        "import app.spanishstudy.vot.SpanishStudyDiagnostics;\n",
        "VOT study/integrity imports")

    rep(vot,
        "    private static boolean sessionEnabled = Settings.VOT_SESSION_ENABLED.get();\n",
        "    private static volatile boolean sessionEnabled = Settings.VOT_SESSION_ENABLED.get();\n",
        "publish session state across worker threads")

    rep(vot,
        '''                if (playerType == PlayerType.NONE) {\n                    currentVideoId = "";\n                    segments = new ArrayList<>();\n                    TtsPrefetcher.clear();\n                }''',
        '''                if (playerType == PlayerType.NONE) {\n                    currentVideoId = "";\n                    segments = new ArrayList<>();\n                    TtsPrefetcher.clear();\n                    SpanishStudyController.onVideoCleared();\n                }''',
        "clear subtitle overlay with player")

    rep(vot,
        '''        currentVideoId = videoId;\n        segments = new ArrayList<>();\n        httpErrorDialogShownThisVideo = false;''',
        '''        currentVideoId = videoId;\n        segments = new ArrayList<>();\n        SpanishStudyController.onVideoCleared();\n        OpenRouterTelemetry.resetSession();\n        httpErrorDialogShownThisVideo = false;''',
        "reset study and usage state on new video")

    rep(vot,
        '''        videoPositionHint = timeMs;\n        // Video state can be null until the overlay is activated the first time.''',
        '''        videoPositionHint = timeMs;\n        SpanishStudyController.onVideoTimeChanged(timeMs);\n        // Video state can be null until the overlay is activated the first time.''',
        "drive subtitles from Morphe playhead")

    rep(vot,
        '''        sessionEnabled = true;\n        Settings.VOT_SESSION_ENABLED.save(true);\n        if (!currentVideoId.isEmpty() && segments.isEmpty() && !isLoading) {''',
        '''        sessionEnabled = true;\n        Settings.VOT_SESSION_ENABLED.save(true);\n        TtsPrefetcher.triggerRescan();\n        if (!currentVideoId.isEmpty() && segments.isEmpty() && !isLoading) {''',
        "wake native TTS prefetcher when VOT is re-enabled")

    rep(vot,
        '''        sessionEnabled = false;\n        Settings.VOT_SESSION_ENABLED.save(false);\n        stopTts();\n        lastSpokenIndex = -1;''',
        '''        sessionEnabled = false;\n        Settings.VOT_SESSION_ENABLED.save(false);\n        TranscriptTranslator.requestAbort();\n        stopTts();\n        TtsPrefetcher.clear();\n        segments = new ArrayList<>();\n        SpanishStudyController.onSessionDisabled();\n        lastSpokenIndex = -1;''',
        "hard-stop translation and TTS work when VOT is disabled")

    rep(vot,
        '''        stopTts();\n        segments = new ArrayList<>();\n        lastSpokenIndex = -1;\n        // Without this, in-flight onUpdate callbacks for the old language would restore''',
        '''        stopTts();\n        segments = new ArrayList<>();\n        SpanishStudyController.onVideoCleared();\n        lastSpokenIndex = -1;\n        // Without this, in-flight onUpdate callbacks for the old language would restore''',
        "clear subtitles on transcript reload")

    # Scope all loadTranscript mutations to avoid touching unrelated conditions.
    rep_section(vot,
        "private static void loadTranscript(String videoId)",
        "\n    /** Lazily creates the System TTS instance",
        '''                            if (videoId.equals(currentVideoId) && loadLang.equals(resolveTargetLang())) {''',
        '''                            if (Settings.VOT_ENABLED.get() && sessionEnabled\n                                    && videoId.equals(currentVideoId) && loadLang.equals(resolveTargetLang())) {''',
        "gate progressive transcript publication by active VOT session")

    rep_section(vot,
        "private static void loadTranscript(String videoId)",
        "\n    /** Lazily creates the System TTS instance",
        '''                                segments = updated;''',
        '''                                segments = updated;\n                                SpanishStudyController.onTranscriptUpdated(updated);''',
        "publish Morphe progressive snapshot to subtitles")

    rep_section(vot,
        "private static void loadTranscript(String videoId)",
        "\n    /** Lazily creates the System TTS instance",
        '''                            return !videoId.equals(currentVideoId)\n                                    || VideoState.getCurrent() == VideoState.ENDED;''',
        '''                            return !Settings.VOT_ENABLED.get()\n                                    || !sessionEnabled\n                                    || !videoId.equals(currentVideoId)\n                                    || VideoState.getCurrent() == VideoState.ENDED;''',
        "cancel native translation when VOT session is off")

    rep_section(vot,
        "private static void loadTranscript(String videoId)",
        "\n    /** Lazily creates the System TTS instance",
        '''                    if (videoId.equals(currentVideoId) && loadLang.equals(resolveTargetLang())) {''',
        '''                    if (Settings.VOT_ENABLED.get() && sessionEnabled\n                            && videoId.equals(currentVideoId) && loadLang.equals(resolveTargetLang())) {''',
        "gate final transcript publication by active VOT session")

    rep_section(vot,
        "private static void loadTranscript(String videoId)",
        "\n    /** Lazily creates the System TTS instance",
        '''                        if (segments.isEmpty()) segments = fetched;\n                        TtsPrefetcher.updateVideo(videoId, segments);''',
        '''                        if (segments.isEmpty()) segments = fetched;\n                        SpanishStudyController.onTranscriptUpdated(segments);\n                        TtsPrefetcher.updateVideo(videoId, segments);''',
        "publish final Morphe snapshot to subtitles")

    rep_section(vot,
        "private static void loadTranscript(String videoId)",
        "\n    /** Lazily creates the System TTS instance",
        '''                    if (!currentVideoId.isEmpty() && Settings.VOT_ENABLED.get()\n                            && (!currentVideoId.equals(videoId)''',
        '''                    if (!currentVideoId.isEmpty() && Settings.VOT_ENABLED.get() && sessionEnabled\n                            && (!currentVideoId.equals(videoId)''',
        "prevent background translator resurrection while VOT is off")

    study_api = r'''
    /** Current video id exposed only to the local diagnostics UI. */
    public static String getCurrentVideoIdForStudy() {
        return currentVideoId;
    }

    /** Whether Morphe's native transcript fetch/translation worker is active. */
    public static boolean isTranscriptLoading() {
        return isLoading;
    }

'''
    rep(vot,
        "    /** Lazily creates the System TTS instance and wires its completion listener. Idempotent. */\n",
        study_api + "    /** Lazily creates the System TTS instance and wires its completion listener. Idempotent. */\n",
        "add read-only study diagnostics APIs")

    rep_section(vot,
        "private static void speak(TranscriptSegment seg, int index)",
        "\n    private static void triggerNextSegmentCheck()",
        '''        Logger.printDebug(() -> "Speak: " + seg);\n        String lang = resolveTargetLang();''',
        '''        Logger.printDebug(() -> "Speak: " + seg);\n        final String safeSpeech = DubTextSanitizer.cleanForSpeech(seg.text);\n        if (safeSpeech == null || !safeSpeech.equals(seg.text)) {\n            SpanishStudyDiagnostics.record("TTS-SANITIZE", "blocked residual protocol text index=" + index);\n            triggerNextSegmentCheck();\n            return;\n        }\n        String lang = resolveTargetLang();''',
        "last-resort protocol firewall before native Morphe TTS")

    # ------------------------------------------------------------------------------------------
    # Keep Morphe caption segmentation exactly as-is; only publish the resulting source list.
    # ------------------------------------------------------------------------------------------
    rep(fetcher,
        "import app.morphe.extension.shared.Utils;\n",
        "import app.morphe.extension.shared.Utils;\nimport app.spanishstudy.vot.SpanishStudyController;\n",
        "TranscriptFetcher subtitle import")
    rep(fetcher,
        "        List<TranscriptSegment> segments = fetchEnglishSegments(videoId);\n",
        "        List<TranscriptSegment> segments = fetchEnglishSegments(videoId);\n        SpanishStudyController.onSourceTranscriptFetched(segments);\n",
        "publish native Morphe source segments")

    # ------------------------------------------------------------------------------------------
    # Add a small study row to Morphe's own VOT bottom sheet; no replacement settings UI.
    # ------------------------------------------------------------------------------------------
    rep(sheet,
        "import app.morphe.extension.youtube.shared.PipDismissHelper;\n",
        "import app.morphe.extension.youtube.shared.PipDismissHelper;\nimport app.spanishstudy.vot.SpanishStudyController;\n",
        "VotBottomSheet study import")
    rep(sheet,
        '''        translationRow.setOnClickListener(v -> showTranslationServicePicker(context, mainRef[0]));\n        refreshTranslation.run();''',
        '''        translationRow.setOnClickListener(v -> showTranslationServicePicker(context, mainRef[0]));\n        refreshTranslation.run();\n\n        LinearLayout studyRow = makeValueRow(context, fg, "Spanish study");\n        ((TextView) studyRow.getTag()).setText("Bilingual subtitles · diagnostics");\n        studyRow.setOnClickListener(v -> {\n            if (mainRef[0] != null) mainRef[0].dismiss();\n            SpanishStudyController.showTools(Utils.getActivity());\n        });''',
        "create study row")
    rep(sheet,
        '''        content.addView(translationRow);\n        content.addView(engineRow);\n        content.addView(makeDivider(context, fg));''',
        '''        content.addView(translationRow);\n        content.addView(engineRow);\n        content.addView(studyRow);\n        content.addView(makeDivider(context, fg));''',
        "add study row without altering Morphe controls")

    # Suppress only automatically-enabled native captions while our own bilingual overlay is visible.
    rep(auto,
        "import app.morphe.extension.youtube.settings.Settings;\n",
        "import app.morphe.extension.youtube.settings.Settings;\nimport app.spanishstudy.vot.SpanishStudyController;\n",
        "AutoCaptions study import")
    rep(auto,
        '''    public static boolean disableAutoCaptions(boolean original) {\n        // After the guard window (150ms), respect the user's manual CC button toggle.''',
        '''    public static boolean disableAutoCaptions(boolean original) {\n        if (SpanishStudyController.suppressNativeCaptions()) return true;\n        // After the guard window (150ms), respect the user's manual CC button toggle.''',
        "avoid duplicate automatic YouTube captions")

    # ------------------------------------------------------------------------------------------
    # OpenRouter: keep Morphe batching/ordering/seek machinery; fix only integrity + accounting.
    # ------------------------------------------------------------------------------------------
    rep(translator,
        "import app.morphe.extension.youtube.settings.Settings;\n",
        "import app.morphe.extension.youtube.settings.Settings;\n"
        "import app.spanishstudy.vot.DubTextSanitizer;\n"
        "import app.spanishstudy.vot.OpenRouterBudget;\n"
        "import app.spanishstudy.vot.OpenRouterOutputGuard;\n"
        "import app.spanishstudy.vot.OpenRouterTelemetry;\n"
        "import app.spanishstudy.vot.SpanishStudyDiagnostics;\n",
        "TranscriptTranslator integrity imports")

    # Final commit path: sanitize every provider result, while allowing legitimate identical text.
    rep_section(translator,
        "private static void applyBatch(",
        "\n    @Nullable\n    private static Consumer<List<String>> streamCallback",
        '''            TranscriptSegment orig = batch.get(j);\n            target.set(offset + j, new TranscriptSegment(\n                    orig.startMs, orig.endMs, translated.get(j), lang));''',
        '''            TranscriptSegment orig = batch.get(j);\n            String clean = DubTextSanitizer.cleanForSpeech(translated.get(j));\n            if (clean == null) {\n                SpanishStudyDiagnostics.record("TRANSLATION-SANITIZE", "drop final slot=" + (offset + j));\n                continue;\n            }\n            target.set(offset + j, new TranscriptSegment(\n                    orig.startMs, orig.endMs, clean, lang));''',
        "sanitize final provider text")

    # Stock stream callback receives a full result array whose unmatched slots still contain source
    # English. Publish only slots that actually changed, so subtitles never mistake placeholders for
    # completed Spanish while the same Morphe request is still streaming.
    text, start, end, body = section(
        translator,
        "private static Consumer<List<String>> streamCallback(",
        "\n    @Nullable\n    private static List<String> translateBatchSafe")
    old_stream = '''    @Nullable\n    private static Consumer<List<String>> streamCallback(\n            @Nullable Consumer<List<TranscriptSegment>> onUpdate,\n            Handler mainHandler,\n            List<TranscriptSegment> working,\n            List<TranscriptSegment> batch,\n            int offset,\n            String lang) {\n        if (onUpdate == null) return null;\n        return partial -> {\n            List<TranscriptSegment> snap = new ArrayList<>(working);\n            applyBatch(snap, batch, offset, partial, lang);\n            mainHandler.post(() -> onUpdate.accept(snap));\n        };\n    }\n\n'''
    new_stream = '''    @Nullable\n    private static Consumer<List<String>> streamCallback(\n            @Nullable Consumer<List<TranscriptSegment>> onUpdate,\n            Handler mainHandler,\n            List<TranscriptSegment> working,\n            List<TranscriptSegment> batch,\n            int offset,\n            String lang) {\n        if (onUpdate == null) return null;\n        return partial -> {\n            List<TranscriptSegment> snap = new ArrayList<>(working);\n            final int limit = Math.min(batch.size(), partial.size());\n            for (int j = 0; j < limit; j++) {\n                TranscriptSegment orig = batch.get(j);\n                String raw = partial.get(j);\n                if (raw == null || raw.equals(orig.text)) continue;\n                String clean = DubTextSanitizer.cleanForSpeech(raw);\n                if (clean == null) continue;\n                snap.set(offset + j, new TranscriptSegment(orig.startMs, orig.endMs, clean, lang));\n            }\n            mainHandler.post(() -> onUpdate.accept(snap));\n        };\n    }\n\n'''
    if body != old_stream:
        raise RuntimeError("stock streamCallback no longer matches v1.41.0 baseline")
    translator.write_text(text[:start] + new_stream + text[end:], encoding="utf-8")
    print("patched: stream only actually translated OpenRouter slots")

    # Retry a malformed/truncated OpenRouter response using Morphe's same batch, with bounded delay.
    rep_section(translator,
        "static List<TranscriptSegment> translate(",
        "\n    private static boolean[] toBoolArray",
        '''        int completed = 0;\n        // True while the next dispatched batch is the first one after a start or seek.''',
        '''        int completed = 0;\n        int consecutiveOpenRouterFailures = 0;\n        // True while the next dispatched batch is the first one after a start or seek.''',
        "track non-fatal OpenRouter parser failures")
    rep_section(translator,
        "static List<TranscriptSegment> translate(",
        "\n    private static boolean[] toBoolArray",
        '''                translatingBatchIndex = -1;\n\n                // A seek cut this request short''',
        '''                translatingBatchIndex = -1;\n\n                if (translated == null && isOpenRouter && !abortTranslation && !reprioritize) {\n                    consecutiveOpenRouterFailures++;\n                    long delayMs = Math.min(15_000L, 1_000L << Math.min(4, consecutiveOpenRouterFailures - 1));\n                    SpanishStudyDiagnostics.record("OPENROUTER-RECOVERY",\n                            "retry same native Morphe batch failures=" + consecutiveOpenRouterFailures\n                                    + " delayMs=" + delayMs);\n                    try {\n                        Thread.sleep(delayMs);\n                    } catch (InterruptedException ex) {\n                        Thread.currentThread().interrupt();\n                        return initial;\n                    }\n                    continue;\n                }\n                if (translated != null) consecutiveOpenRouterFailures = 0;\n\n                // A seek cut this request short''',
        "retry only non-fatal OpenRouter integrity failures")

    parser_start = "    private static boolean parseLine(String line, List<String> result, int segmentCount) {"
    parser_end = "    private static List<String> translateBatchGoogle("
    text = translator.read_text(encoding="utf-8")
    p0 = text.index(parser_start)
    p1 = text.index(parser_end, p0)
    parser_block = r'''    private static int parseLine(String line, List<String> result, int segmentCount) {
        OpenRouterOutputGuard.ParsedLine parsed = OpenRouterOutputGuard.parseNumberedLine(line, segmentCount);
        if (parsed == null) return -1;
        result.set(parsed.index, parsed.text);
        return parsed.index;
    }

    private static boolean applyStreamedLine(String line, List<String> result, int segmentCount,
                                             int[] matched, boolean[] matchedSlots) {
        int index = parseLine(line, result, segmentCount);
        if (index < 0) return false;
        if (!matchedSlots[index]) {
            matchedSlots[index] = true;
            matched[0]++;
        }
        return true;
    }

    @Nullable
    private static List<String> positionalFallback(String raw, int segmentCount) {
        return OpenRouterOutputGuard.positionalFallback(raw, segmentCount);
    }

'''
    translator.write_text(text[:p0] + parser_block + text[p1:], encoding="utf-8")
    print("patched: strict unique-slot OpenRouter parser")

    rep_section(translator,
        "private static List<String> translateBatchOpenRouter(",
        "\n    static void fetchOpenRouterModelCost",
        '''        final long start = System.currentTimeMillis();\n        Logger.printDebug(() -> "OpenRouter translation starting: " + videoId + " lang: " + targetLang + " model: " + model);''',
        '''        final long start = System.currentTimeMillis();\n        OpenRouterTelemetry.recordRequestStart();\n        Logger.printDebug(() -> "OpenRouter translation starting: " + videoId + " lang: " + targetLang + " model: " + model);''',
        "start OpenRouter usage telemetry")

    rep_section(translator,
        "private static List<String> translateBatchOpenRouter(",
        "\n    static void fetchOpenRouterModelCost",
        '''        JSONObject body = new JSONObject()\n                .put("model", model)\n                .put("temperature", 0)\n                .put("stream", true)\n                .put("max_tokens", segments.size() * 30)''',
        '''        final int maxOutputTokens = OpenRouterBudget.maxOutputTokens(joined.length(), segments.size());\n        JSONObject body = new JSONObject()\n                .put("model", model)\n                .put("temperature", 0)\n                .put("stream", true)\n                .put("usage", new JSONObject().put("include", true))\n                .put("max_tokens", maxOutputTokens)''',
        "raise only OpenRouter output allowance; keep Morphe batch shape")

    rep_section(translator,
        "private static List<String> translateBatchOpenRouter(",
        "\n    static void fetchOpenRouterModelCost",
        '''        conn.setRequestProperty("Accept-Encoding", "identity");''',
        '''        conn.setRequestProperty("Accept-Encoding", "identity");\n        conn.setRequestProperty("X-OpenRouter-Metadata", "enabled");''',
        "request OpenRouter routing metadata")

    rep_section(translator,
        "private static List<String> translateBatchOpenRouter(",
        "\n    static void fetchOpenRouterModelCost",
        '''        int[] matched = {0};\n        // Full raw model output''',
        '''        int[] matched = {0};\n        boolean[] matchedSlots = new boolean[segments.size()];\n        int httpCode = 0;\n        String generationId = "-";\n        String routedProvider = "-";\n        String finishReason = "-";\n        long promptTokens = -1, completionTokens = -1, totalTokens = -1, cachedTokens = -1;\n        double usageCostUsd = -1.0;\n        // Full raw model output''',
        "track unique slots and usage fields")

    rep_section(translator,
        "private static List<String> translateBatchOpenRouter(",
        "\n    static void fetchOpenRouterModelCost",
        '''            final int code = conn.getResponseCode();\n            if (code != 200) {''',
        '''            httpCode = conn.getResponseCode();\n            generationId = conn.getHeaderField("X-Generation-Id");\n            if (httpCode != 200) {''',
        "capture OpenRouter HTTP/generation telemetry")
    rep_section(translator,
        "private static List<String> translateBatchOpenRouter(",
        "\n    static void fetchOpenRouterModelCost",
        '''                VoiceOverTranslationPatch.notifyOpenRouterError(code, errorBody);\n                throw new Exception("OpenRouter HTTP status: " + code + " language: " + targetLang''',
        '''                VoiceOverTranslationPatch.notifyOpenRouterError(httpCode, errorBody);\n                throw new Exception("OpenRouter HTTP status: " + httpCode + " language: " + targetLang''',
        "use captured OpenRouter status")

    rep_section(translator,
        "private static List<String> translateBatchOpenRouter(",
        "\n    static void fetchOpenRouterModelCost",
        '''                    JSONArray choices = chunk.optJSONArray("choices");\n                    if (choices == null || choices.length() == 0) continue;\n                    JSONObject delta = choices.getJSONObject(0).optJSONObject("delta");\n                    if (delta == null) continue;\n\n                    String content = delta.optString("content", "");''',
        '''                    String providerName = chunk.optString("provider", "");\n                    if (!providerName.isEmpty()) routedProvider = providerName;\n                    JSONObject usage = chunk.optJSONObject("usage");\n                    if (usage != null) {\n                        promptTokens = usage.optLong("prompt_tokens", promptTokens);\n                        completionTokens = usage.optLong("completion_tokens", completionTokens);\n                        totalTokens = usage.optLong("total_tokens", totalTokens);\n                        usageCostUsd = usage.has("cost") ? usage.optDouble("cost", usageCostUsd) : usageCostUsd;\n                        JSONObject promptDetails = usage.optJSONObject("prompt_tokens_details");\n                        if (promptDetails != null) cachedTokens = promptDetails.optLong("cached_tokens", cachedTokens);\n                    }\n\n                    JSONArray choices = chunk.optJSONArray("choices");\n                    if (choices == null || choices.length() == 0) continue;\n                    JSONObject choice = choices.getJSONObject(0);\n                    String finish = choice.optString("finish_reason", "");\n                    if (!finish.isEmpty()) finishReason = finish;\n                    JSONObject delta = choice.optJSONObject("delta");\n                    if (delta == null) continue;\n\n                    String content = delta.optString("content", "");''',
        "parse OpenRouter streamed usage and finish reason")

    # Both complete-line call sites use the same signature in stock.
    rep_section(translator,
        "private static List<String> translateBatchOpenRouter(",
        "\n    static void fetchOpenRouterModelCost",
        "applyStreamedLine(line, result, segments.size(), matched)",
        "applyStreamedLine(line, result, segments.size(), matched, matchedSlots)",
        "use unique-slot tracking for streamed lines", count=2)

    rep_section(translator,
        "private static List<String> translateBatchOpenRouter(",
        "\n    static void fetchOpenRouterModelCost",
        '''                if (lineBuffer.length() > 0) {''',
        '''                if (lineBuffer.length() > 0 && !"length".equalsIgnoreCase(finishReason)) {''',
        "never publish an unterminated length-truncated tail")

    # Add failure telemetry to the native connection try/finally without changing disconnect semantics.
    rep_section(translator,
        "private static List<String> translateBatchOpenRouter(",
        "\n    static void fetchOpenRouterModelCost",
        '''            }\n        } finally {\n            if (activeConnection == conn) activeConnection = null;\n        }''',
        '''            }\n        } catch (Exception ex) {\n            OpenRouterTelemetry.recordFailure(httpCode, System.currentTimeMillis() - start, ex.getMessage());\n            throw ex;\n        } finally {\n            if (activeConnection == conn) activeConnection = null;\n        }''',
        "record OpenRouter transport failures")

    rep_section(translator,
        "private static List<String> translateBatchOpenRouter(",
        "\n    static void fetchOpenRouterModelCost",
        '''                matched[0] = segmentSize;\n                if (onLineStreamed != null) onLineStreamed.accept(new ArrayList<>(result));''',
        '''                matched[0] = segmentSize;\n                Arrays.fill(matchedSlots, true);\n                if (onLineStreamed != null) onLineStreamed.accept(new ArrayList<>(result));''',
        "mark positional recovery slots complete")

    rep_section(translator,
        "private static List<String> translateBatchOpenRouter(",
        "\n    static void fetchOpenRouterModelCost",
        '''        final int matchedFirst = matched[0];\n        Logger.printDebug(() -> "OpenRouter translation complete: " + targetLang''',
        '''        int contiguous = 0;\n        while (contiguous < segmentSize && matchedSlots[contiguous]) contiguous++;\n        final int matchedFirst = contiguous;\n\n        if ("length".equalsIgnoreCase(finishReason)) {\n            OpenRouterTelemetry.recordLengthFinish(httpCode, System.currentTimeMillis() - start,\n                    routedProvider, generationId, promptTokens, completionTokens, totalTokens, cachedTokens, usageCostUsd);\n            SpanishStudyDiagnostics.record("OPENROUTER-PARSE",\n                    "length-truncated native batch matched=" + matchedFirst + "/" + segmentSize\n                            + " maxTokens=" + maxOutputTokens);\n            throw new Exception("OpenRouter output truncated at max token budget");\n        }\n\n        OpenRouterTelemetry.recordSuccess(httpCode, System.currentTimeMillis() - start,\n                routedProvider, generationId, finishReason, promptTokens, completionTokens,\n                totalTokens, cachedTokens, usageCostUsd);\n        Logger.printDebug(() -> "OpenRouter translation complete: " + targetLang''',
        "use contiguous aligned prefix and record OpenRouter usage")

    rep_section(translator,
        "private static List<String> translateBatchOpenRouter(",
        "\n    static void fetchOpenRouterModelCost",
        '''        if (matchedFirst != segmentSize) {\n            Logger.printDebug(() -> "OpenRouter line mismatch - expected: " + segmentSize''',
        '''        if (matchedFirst != segmentSize) {\n            OpenRouterTelemetry.recordCardinalityMismatch(segmentSize, matched[0]);\n            Logger.printDebug(() -> "OpenRouter line mismatch - expected: " + segmentSize''',
        "count alignment mismatches")

    rep_section(translator,
        "private static List<String> translateBatchOpenRouter(",
        "\n    static void fetchOpenRouterModelCost",
        '''            if (matchedFirst > 0) {\n                // Return only the translated portion; the caller re-queues the tail for retry.\n                return new ArrayList<>(result.subList(0, matchedFirst));\n            }\n        }\n        return result;''',
        '''            if (matchedFirst > 0) {\n                // Return only the safely aligned prefix; Morphe re-queues the native tail.\n                return new ArrayList<>(result.subList(0, matchedFirst));\n            }\n            throw new Exception("OpenRouter output alignment mismatch");\n        }\n        return result;''',
        "fail closed when no OpenRouter slot can be aligned")

    print("v2.16.0 Morphe-core reconciliation complete")


if __name__ == "__main__":
    main()
