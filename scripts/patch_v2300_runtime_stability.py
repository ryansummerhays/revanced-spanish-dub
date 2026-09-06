#!/usr/bin/env python3
"""v2.30: fix runtime races/integrity failures demonstrated by the v2.29 device trace."""
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


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: patch_v2300_runtime_stability.py <morphe-root> <repo-root>")

    root = Path(sys.argv[1]).resolve()
    repo = Path(sys.argv[2]).resolve()
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"

    vot = pkg / "VoiceOverTranslationPatch.java"
    translator = pkg / "TranscriptTranslator.java"
    prefetch = pkg / "TtsPrefetcher.java"
    cache = pkg / "TtsCache.java"
    subtitle = study / "SpanishSubtitleOverlay.java"
    controller = study / "SpanishStudyController.java"
    speaker = study / "LocalSpeakerDiarizer.java"
    for path in (vot, translator, prefetch, cache, subtitle, controller, speaker):
        if not path.is_file():
            raise RuntimeError(f"missing source: {path}")

    # Reuse the previously tested strict output parser/sanitizer and install the stronger v2.30
    # source-aware mixed-English guard.
    helper_sources = {
        "DubTextSanitizer.java": repo / "overlay/src/app/spanishstudy/vot/DubTextSanitizer.java",
        "OpenRouterOutputGuard.java": repo / "overlay/src/app/spanishstudy/vot/OpenRouterOutputGuard.java",
        "DubLanguageGuard.java": repo / "overlay/v230/app/spanishstudy/vot/DubLanguageGuard.java",
    }
    for name, src in helper_sources.items():
        if not src.is_file():
            raise RuntimeError(f"missing helper: {src}")
        shutil.copy2(src, study / name)
        print("copied:", name)

    # --------------------------------------------------------------------------------------
    # OpenRouter integrity: unique numbered slots, contiguous-prefix requeue, and mixed-English
    # guard. Stock v1.41 counts duplicate/noncontiguous numbers as if they were an aligned prefix.
    # --------------------------------------------------------------------------------------
    rep(
        translator,
        "import app.spanishstudy.vot.OpenRouterBudget;\n"
        "import app.spanishstudy.vot.SpanishStudyDiagnostics;\n",
        "import app.spanishstudy.vot.DubLanguageGuard;\n"
        "import app.spanishstudy.vot.OpenRouterBudget;\n"
        "import app.spanishstudy.vot.OpenRouterOutputGuard;\n"
        "import app.spanishstudy.vot.SpanishStudyDiagnostics;\n",
        "OpenRouter integrity imports",
    )

    text, start, end, _ = section(
        translator,
        "    private static boolean parseLine(String line, List<String> result, int segmentCount) {",
        "    private static List<String> translateBatchGoogle(",
    )
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
    translator.write_text(text[:start] + parser_block + text[end:], encoding="utf-8")
    print("patched: strict unique-slot OpenRouter parser")

    rep(
        translator,
        "        int[] matched = {0};\n"
        "        // Full raw model output, kept so a positional fallback can run if numbered parsing fails.\n",
        "        int[] matched = {0};\n"
        "        boolean[] matchedSlots = new boolean[segments.size()];\n"
        "        // Full raw model output, kept so a positional fallback can run if numbered parsing fails.\n",
        "track unique OpenRouter slots",
    )
    rep(
        translator,
        "applyStreamedLine(line, result, segments.size(), matched)",
        "applyStreamedLine(line, result, segments.size(), matched, matchedSlots)",
        "use unique slot tracking for streamed lines",
        count=2,
    )
    rep(
        translator,
        "                matched[0] = segmentSize;\n"
        "                if (onLineStreamed != null) onLineStreamed.accept(new ArrayList<>(result));\n",
        "                matched[0] = segmentSize;\n"
        "                Arrays.fill(matchedSlots, true);\n"
        "                if (onLineStreamed != null) onLineStreamed.accept(new ArrayList<>(result));\n",
        "mark positional fallback slots complete",
    )

    # Progressive snapshots must not prefetch an English-leaking line before final batch validation.
    rep(
        translator,
        "                if (streamed != null && !streamed.equals(orig.text)) {\n"
        "                    snap.set(offset + j, new TranscriptSegment(\n"
        "                            orig.startMs, orig.endMs, streamed, lang));\n"
        "                }\n",
        "                if (streamed != null && !streamed.equals(orig.text)) {\n"
        "                    String guardReason = DubLanguageGuard.reason(orig.text, streamed, lang);\n"
        "                    if (guardReason == null) {\n"
        "                        snap.set(offset + j, new TranscriptSegment(\n"
        "                                orig.startMs, orig.endMs, streamed, lang));\n"
        "                    } else {\n"
        "                        SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.TRANSLATION,\n"
        "                                \"stream guard withheld slot=\" + (offset + j)\n"
        "                                        + \" reason=\" + guardReason);\n"
        "                    }\n"
        "                }\n",
        "guard progressive OpenRouter text before publication",
    )

    rep(
        translator,
        "        final int matchedFirst = matched[0];\n"
        "        SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.TRANSLATION,\n"
        "                \"OpenRouter stream complete expected=\" + segmentSize + \" matched=\" + matchedFirst\n",
        "        int contiguous = 0;\n"
        "        while (contiguous < segmentSize && matchedSlots[contiguous]) contiguous++;\n\n"
        "        // If an aligned OpenRouter slot still contains a suspicious source-English run,\n"
        "        // repair that slot through Morphe's existing Google translator before publication.\n"
        "        for (int i = 0; i < contiguous; i++) {\n"
        "            String guardReason = DubLanguageGuard.reason(segments.get(i).text, result.get(i), targetLang);\n"
        "            if (guardReason == null) continue;\n"
        "            SpanishStudyDiagnostics.recordAlways(SpanishStudyDiagnostics.TRANSLATION,\n"
        "                    \"language guard slot=\" + i + \" reason=\" + guardReason\n"
        "                            + \" action=google-singleton-fallback\");\n"
        "            List<String> fallback = translateBatchGoogle(videoId,\n"
        "                    Collections.singletonList(segments.get(i)), targetLang);\n"
        "            if (fallback == null || fallback.size() != 1\n"
        "                    || DubLanguageGuard.reason(segments.get(i).text, fallback.get(0), targetLang) != null) {\n"
        "                throw new Exception(\"Language guard fallback failed at slot \" + i);\n"
        "            }\n"
        "            result.set(i, fallback.get(0));\n"
        "        }\n\n"
        "        final int matchedFirst = contiguous;\n"
        "        SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.TRANSLATION,\n"
        "                \"OpenRouter stream complete expected=\" + segmentSize\n"
        "                        + \" matchedUnique=\" + matched[0] + \" contiguous=\" + matchedFirst\n",
        "use contiguous prefix and repair mixed-English slots",
    )

    # --------------------------------------------------------------------------------------
    # TTS: if progressive prefetch is already synthesizing the exact segment, join that work
    # rather than queueing the same Edge synthesis behind it a second time.
    # --------------------------------------------------------------------------------------
    rep(
        prefetch,
        "    @GuardedBy(\"lock\")\n"
        "    private static volatile CountDownLatch loadingLatch;\n",
        "    @GuardedBy(\"lock\")\n"
        "    private static volatile CountDownLatch loadingLatch;\n"
        "    @GuardedBy(\"lock\") private static String inFlightVideoId = \"\";\n"
        "    @GuardedBy(\"lock\") private static int inFlightIndex = -1;\n"
        "    @GuardedBy(\"lock\") private static String inFlightVoice = \"\";\n"
        "    @GuardedBy(\"lock\") private static String inFlightLang = \"\";\n"
        "    @GuardedBy(\"lock\") private static String inFlightText = \"\";\n",
        "track exact in-flight prefetch segment",
    )

    prefetch_helpers = r'''
    /** Waits only when the prefetcher is already synthesizing this exact clip. */
    static boolean awaitMatchingFetch(String videoId, int index, String voice, String lang,
                                      String text, long timeoutMs) {
        synchronized (lock) {
            if (!matchesInFlight(videoId, index, voice, lang, text)) return false;
            final long deadline = System.currentTimeMillis() + Math.max(0, timeoutMs);
            while (matchesInFlight(videoId, index, voice, lang, text)) {
                long remaining = deadline - System.currentTimeMillis();
                if (remaining <= 0) break;
                try {
                    lock.wait(remaining);
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    break;
                }
            }
            return true;
        }
    }

    private static boolean matchesInFlight(String videoId, int index, String voice, String lang, String text) {
        return inFlightIndex == index && videoId.equals(inFlightVideoId)
                && voice.equals(inFlightVoice) && lang.equals(inFlightLang) && text.equals(inFlightText);
    }

    private static void beginInFlight(String videoId, int index, String voice, String lang, String text) {
        synchronized (lock) {
            inFlightVideoId = videoId;
            inFlightIndex = index;
            inFlightVoice = voice;
            inFlightLang = lang;
            inFlightText = text;
        }
    }

    private static void endInFlight(String videoId, int index, String voice, String lang, String text) {
        synchronized (lock) {
            if (matchesInFlight(videoId, index, voice, lang, text)) {
                inFlightVideoId = "";
                inFlightIndex = -1;
                inFlightVoice = inFlightLang = inFlightText = "";
                lock.notifyAll();
            }
        }
    }

'''
    rep(
        prefetch,
        "    @GuardedBy(\"lock\")\n"
        "    private static void startBackgroundThread() {\n",
        prefetch_helpers + "    @GuardedBy(\"lock\")\n    private static void startBackgroundThread() {\n",
        "add prefetch join helpers",
    )

    rep(
        prefetch,
        "            final byte[] data = engine.prefetch(seg.text, voice, lang);\n"
        "            if (data.length > 0) {\n",
        "            beginInFlight(videoId, index, voice, lang, seg.text);\n"
        "            final byte[] data;\n"
        "            try {\n"
        "                data = engine.prefetch(seg.text, voice, lang);\n"
        "            } finally {\n"
        "                endInFlight(videoId, index, voice, lang, seg.text);\n"
        "            }\n"
        "            if (data.length > 0) {\n",
        "publish exact prefetch in-flight lifetime",
    )

    rep(
        vot,
        "            try {\n"
        "                data = ttsEngine.prefetch(seg.text, voice, lang);\n",
        "            try {\n"
        "                data = TtsCache.get(videoIdSnapshot, index, voice, lang, seg.text);\n"
        "                boolean joinedPrefetch = false;\n"
        "                if (data == null) {\n"
        "                    joinedPrefetch = TtsPrefetcher.awaitMatchingFetch(\n"
        "                            videoIdSnapshot, index, voice, lang, seg.text, 20_000);\n"
        "                    if (joinedPrefetch) {\n"
        "                        data = TtsCache.get(videoIdSnapshot, index, voice, lang, seg.text);\n"
        "                    }\n"
        "                }\n"
        "                if (data == null) data = ttsEngine.prefetch(seg.text, voice, lang);\n"
        "                final boolean reusedPrefetch = joinedPrefetch && data != null;\n"
        "                if (reusedPrefetch) {\n"
        "                    SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.TTS,\n"
        "                            \"on-demand joined prefetch index=\" + index + \" bytes=\" + data.length);\n"
        "                }\n",
        "join identical progressive prefetch before on-demand synthesis",
    )

    # --------------------------------------------------------------------------------------
    # Subtitle clock handoff: retain the last actual-audio progress when MediaPlayer completes,
    # so falling back to the video clock cannot move from a later page to an earlier page.
    # --------------------------------------------------------------------------------------
    rep(
        subtitle,
        "    private static String lastSpeaker = \"\";\n",
        "    private static String lastSpeaker = \"\";\n"
        "    private static int lastAudioProgressSegment = -1;\n"
        "    private static double lastAudioProgress;\n"
        "    private static long lastObservedVideoMs = -1;\n",
        "track subtitle audio-clock handoff",
    )

    rep(
        subtitle,
        "        String shownEs = \"\";\n",
        "        boolean backwardSeek = lastObservedVideoMs >= 0 && timeMs + 750 < lastObservedVideoMs;\n"
        "        if (backwardSeek) {\n"
        "            lastAudioProgressSegment = -1;\n"
        "            lastAudioProgress = 0;\n"
        "        }\n"
        "        if (clockSource.startsWith(\"tts-\")) {\n"
        "            if (lastAudioProgressSegment != index) {\n"
        "                lastAudioProgressSegment = index;\n"
        "                lastAudioProgress = 0;\n"
        "            }\n"
        "            lastAudioProgress = Math.max(lastAudioProgress, progress);\n"
        "        } else if (lastAudioProgressSegment == index && progress < lastAudioProgress) {\n"
        "            progress = lastAudioProgress;\n"
        "            clockSource = \"video+audio-hold\";\n"
        "        }\n"
        "        lastObservedVideoMs = timeMs;\n\n"
        "        String shownEs = \"\";\n",
        "prevent subtitle page rollback after TTS completion",
    )

    rep(
        subtitle,
        "        lastSpeaker = \"\";\n"
        "    }\n",
        "        lastSpeaker = \"\";\n"
        "        lastAudioProgressSegment = -1;\n"
        "        lastAudioProgress = 0;\n"
        "        lastObservedVideoMs = -1;\n"
        "    }\n",
        "reset subtitle handoff telemetry",
    )

    # --------------------------------------------------------------------------------------
    # Visualizer failure is deterministic on this device/API configuration. Stop retrying the same
    # unsupported attach on every AudioTrack observation; keep the experiment diagnostic-only.
    # --------------------------------------------------------------------------------------
    rep(
        speaker,
        "    private static volatile boolean enabled = true;\n",
        "    private static volatile boolean enabled = true;\n"
        "    private static volatile boolean captureUnavailable;\n",
        "latch deterministic Visualizer unavailability",
    )
    rep(
        speaker,
        "            out.append(\"speakerExperimentEnabled=\").append(enabled).append('\\n');\n",
        "            out.append(\"speakerExperimentEnabled=\").append(enabled).append('\\n');\n"
        "            out.append(\"speakerCaptureAvailable=\").append(!captureUnavailable).append('\\n');\n",
        "report speaker capture availability",
    )
    rep(
        speaker,
        "        if (!enabled) return;\n"
        "        Activity activity = Utils.getActivity();\n",
        "        if (!enabled || captureUnavailable) return;\n"
        "        Activity activity = Utils.getActivity();\n",
        "skip repeated unsupported Visualizer attaches",
    )
    rep(
        speaker,
        "                lastAttachError = ex.getClass().getSimpleName() + \": \" + String.valueOf(ex.getMessage());\n"
        "            }\n"
        "            SpanishStudyDiagnostics.error(SpanishStudyDiagnostics.AUDIO,\n",
        "                lastAttachError = ex.getClass().getSimpleName() + \": \" + String.valueOf(ex.getMessage());\n"
        "                if (lastAttachError.contains(\"error: -3\")) captureUnavailable = true;\n"
        "            }\n"
        "            if (captureUnavailable) {\n"
        "                SpanishStudyDiagnostics.recordAlways(SpanishStudyDiagnostics.SPEAKER,\n"
        "                        \"Visualizer unavailable for this process; further attach attempts suppressed\");\n"
        "            }\n"
        "            SpanishStudyDiagnostics.error(SpanishStudyDiagnostics.AUDIO,\n",
        "latch Visualizer error -3",
    )

    # Test-voice cache samples use segment index -1. They are harmless but flooded the v2.29 trace.
    rep(
        cache,
        "        SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.TTS,\n"
        "                \"cache get index=\" + segmentIndex + \" hit=\" + (data != null)\n"
        "                        + \" bytes=\" + (data == null ? 0 : data.length));\n",
        "        if (segmentIndex >= 0) {\n"
        "            SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.TTS,\n"
        "                    \"cache get index=\" + segmentIndex + \" hit=\" + (data != null)\n"
        "                            + \" bytes=\" + (data == null ? 0 : data.length));\n"
        "        }\n",
        "suppress test-sample cache read spam",
    )
    rep(
        cache,
        "        SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.TTS,\n"
        "                \"cache put index=\" + segmentIndex + \" bytes=\" + (data == null ? 0 : data.length));\n",
        "        if (segmentIndex >= 0) {\n"
        "            SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.TTS,\n"
        "                    \"cache put index=\" + segmentIndex + \" bytes=\" + (data == null ? 0 : data.length));\n"
        "        }\n",
        "suppress test-sample cache write spam",
    )

    # Keep the report self-describing; v2.29 was running but still identified itself as v2.28.
    rep(controller, 'report.append("Spanish Dub Study v2.28.0 diagnostics\\n");',
        'report.append("Spanish Dub Study v2.30.0 diagnostics\\n");', "update diagnostics version")
    rep(controller,
        'report.append("translationPipeline=stock-morphe-openrouter-mistral\\n");',
        'report.append("translationPipeline=morphe-openrouter+char-budget+unique-slot-parser+mixed-language-guard\\n");',
        "update translation architecture diagnostic")
    rep(controller,
        'report.append("translationCustomRecovery=none\\n");',
        'report.append("translationCustomRecovery=stock-tail-requeue+google-singleton-language-repair\\n");',
        "update translation recovery diagnostic")
    rep(controller,
        'report.append("ttsArchitecture=stock-morphe+diagnostic-hooks-only\\n");',
        'report.append("ttsArchitecture=stock-morphe+progressive-prefetch+inflight-deduplication\\n");',
        "update TTS architecture diagnostic")
    rep(controller,
        'report.append("subtitleClock=stock-playback-window+active-spoken-index\\n");',
        'report.append("subtitleClock=edge-mediaplayer+video-fallback+monotonic-audio-handoff\\n");',
        "update subtitle clock diagnostic")

    print("v2.30 runtime stability patch complete")


if __name__ == "__main__":
    main()
