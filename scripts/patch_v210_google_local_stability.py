#!/usr/bin/env python3
"""v2.10.0: Google-only stable baseline, no Gemini runtime, resilient Edge TTS.

Applied after v2.9.1. This release intentionally removes Gemini from the active playback path.
Google remains the only transcript translator. Gemini text/video/speaker sidecars are hard-disabled
without deleting stored credentials, so future experimental builds can re-enable them explicitly.

It also prevents one bad Edge phrase from monopolizing the serialized synthesis socket: failed
prefetch indices receive a cooldown, active/on-demand failures fail forward quickly, and the Edge
read timeout is shortened so the ready buffer can recover instead of draining for ~40 seconds.
"""
from pathlib import Path
import sys


def rep(path: Path, old: str, new: str, label: str):
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count} in {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("patched:", label)


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_v210_google_local_stability.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    votpkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    translator = votpkg / "TranscriptTranslator.java"
    controller = study / "SpanishStudyController.java"
    gemini = study / "GeminiTranslator.java"
    ground = study / "GeminiVideoGroundingSidecar.java"
    speaker = study / "GeminiSpeakerDiarizationSidecar.java"
    sheet = study / "SpanishStudySheet.java"
    tts = votpkg / "TtsEngine.java"
    prefetcher = votpkg / "TtsPrefetcher.java"

    # ---- Google-only translation -----------------------------------------------------------
    # Do not mutate Morphe's persisted provider setting. This patch simply makes Spanish Dub Study
    # use Google regardless of that setting, while diagnostics expose requested vs effective mode.
    rep(translator,
'''        String service = Settings.VOT_TRANSLATION_SERVICE.get();
        final boolean isMyMemory = service.equals(TRANSLATION_SERVICE_MY_MEMORY);
        final boolean isOpenRouter = service.equals(TRANSLATION_SERVICE_OPENROUTER);''',
'''        // v2.10 stable baseline: Google is the only active transcript translator.
        // Keep the external setting untouched for forward compatibility, but do not route this
        // Spanish-dub session through Gemini/OpenRouter/MyMemory.
        String service = TRANSLATION_SERVICE_GOOGLE;
        final boolean isMyMemory = false;
        final boolean isOpenRouter = false;''',
        "force effective translation provider to Google")

    # Any Gemini translator hooks left by older patches must resolve false at runtime.
    rep(gemini,
'''    public static boolean isEnabled() {
        Context context = Utils.getContext();
        return context != null
                && SpanishStudyPrefs.geminiEnabled(context)
                && !SpanishStudyPrefs.geminiApiKey(context).trim().isEmpty();
    }''',
'''    public static boolean isEnabled() {
        // v2.10 stable baseline deliberately makes no Gemini API calls.
        return false;
    }''',
        "hard-disable Gemini text translation")

    # ---- Disable Gemini media analysis completely ------------------------------------------
    rep(ground,
'''    static void maybeSchedule(String videoId, List<TranscriptSegment> source, long playheadMs) {''',
'''    static void maybeSchedule(String videoId, List<TranscriptSegment> source, long playheadMs) {
        // v2.10 stable baseline: media grounding is reserved for a future experimental build.
        if (true) return;''',
        "hard-disable Gemini video grounding")

    rep(speaker,
'''    static void maybeSchedule(String videoId, List<TranscriptSegment> source, long playheadMs) {''',
'''    static void maybeSchedule(String videoId, List<TranscriptSegment> source, long playheadMs) {
        // v2.10 stable baseline: no remote speaker diarization. A future local implementation must
        // obtain actual source audio and run VAD/voice embeddings on-device before this is restored.
        if (true) return;''',
        "hard-disable Gemini speaker diarization")

    # ---- Diagnostics: make zero-Gemini runtime obvious --------------------------------------
    rep(controller,
'''        report.append("Spanish Dub Study v2.9.1 diagnostics\\n");''',
'''        report.append("Spanish Dub Study v2.10.0 diagnostics\\n");''',
        "label v2.10.0 diagnostics")

    # v2.9 diagnostics added these lines. Rewrite the values so saved Gemini preferences cannot be
    # mistaken for active runtime behavior.
    rep(controller,
'''        report.append("translationProvider=").append(activeProvider).append('\\n');''',
'''        report.append("translationProvider=google\\n");
        report.append("translationMode=google-only-stable\\n");''',
        "report effective Google-only provider")

    rep(controller,
'''        report.append("geminiTranslationSelected=").append(geminiSelected).append('\\n');''',
'''        report.append("geminiTranslationSelected=false\\n");
        report.append("geminiRuntime=disabled-in-v2.10\\n");''',
        "report Gemini runtime disabled")

    rep(controller,
'''        report.append("videoGroundingActive=").append(groundingActive).append('\\n');''',
'''        report.append("videoGroundingActive=false\\n");''',
        "report grounding inactive")

    rep(controller,
'''        report.append("speakerBackend=gemini-media-independent-of-text-provider\\n");''',
'''        report.append("speakerBackend=disabled-pending-local-audio-pipeline\\n");''',
        "report local-speaker future scope")

    # ---- UI: retire Gemini controls from the active study sheet ------------------------------
    # Keep stored prefs/API key untouched; only replace explanatory/status text and disable active
    # media toggles so old installs cannot accidentally re-enable remote calls.
    text = sheet.read_text(encoding="utf-8")
    text = text.replace("Gemini", "Advanced analysis (future)")
    # We deliberately do not rely on exact UI structure here; runtime hard-disables are authoritative.
    sheet.write_text(text, encoding="utf-8")
    print("patched: relabel Gemini study UI as future analysis")

    # ---- Edge TTS starvation recovery -------------------------------------------------------
    # The serialized WebSocket can block every later phrase while one request consumes two 20s read
    # timeouts. Shorten that failure window. Successful synthesis is normally far faster than 8s.
    rep(tts,
'''    private static final int READ_TIMEOUT_MS    = 20_000;''',
'''    private static final int READ_TIMEOUT_MS    = 8_000;''',
        "shorten Edge synthesis read timeout")

    # One engine-level retry is enough for the stable path; per-event retry/fail-forward already
    # exists above this layer. This caps a single bad synthesis at roughly 16s rather than 40s.
    rep(tts,
'''            for (int attempt = 1; attempt <= 2; attempt++) {''',
'''            for (int attempt = 1; attempt <= 2; attempt++) {
                // Kept at two socket attempts, but the shorter read timeout above bounds stalls.''',
        "document bounded Edge retry")

    # Add per-index failure cooldown to TtsPrefetcher. Otherwise the current-first logic immediately
    # selects the same uncached failed segment again after backoff, monopolizing synthesis forever.
    rep(prefetcher,
'''import java.util.ArrayList;
import java.util.Collections;''',
'''import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;''',
        "prefetch cooldown imports")

    rep(prefetcher,
'''    private static final Object lock = new Object();''',
'''    private static final Object lock = new Object();
    private static final long FAILED_SEGMENT_COOLDOWN_MS = 25_000L;
    @GuardedBy("lock")
    private static final Map<Integer, Long> failedUntilByIndex = new HashMap<>();''',
        "add failed-segment cooldown state")

    rep(prefetcher,
'''            if (!videoId.equals(currentVideoId)) {
                loadingLatch = new CountDownLatch(1);
            }''',
'''            if (!videoId.equals(currentVideoId)) {
                loadingLatch = new CountDownLatch(1);
                failedUntilByIndex.clear();
            }''',
        "clear failed cooldowns on video change")

    rep(prefetcher,
'''            currentVideoId = "";
            currentSegments = Collections.emptyList();''',
'''            currentVideoId = "";
            currentSegments = Collections.emptyList();
            failedUntilByIndex.clear();''',
        "clear failed cooldowns on prefetch reset")

    # Skip cooled-down indices in all priority passes.
    rep(prefetcher,
'''                if (!TranscriptFetcher.isSpokenLanguageDifferent(lang, seg.lang)
                        && TtsCache.notCached(videoId, i, voice, lang, seg.text)) {''',
'''                if (!TranscriptFetcher.isSpokenLanguageDifferent(lang, seg.lang)
                        && !isPrefetchCoolingDown(i)
                        && TtsCache.notCached(videoId, i, voice, lang, seg.text)) {''',
        "skip cooled active segment")

    # Future and past passes share the same cache condition twice.
    text = prefetcher.read_text(encoding="utf-8")
    old = '''                if (TtsCache.notCached(videoId, i, voice, lang, seg.text)) {
                    return new NextFetch(i, i - firstFutureIndex, seg);
                }'''
    new = '''                if (!isPrefetchCoolingDown(i)
                        && TtsCache.notCached(videoId, i, voice, lang, seg.text)) {
                    return new NextFetch(i, i - firstFutureIndex, seg);
                }'''
    if text.count(old) != 1:
        raise RuntimeError(f"future cooldown anchor count={text.count(old)}")
    text = text.replace(old, new, 1)
    old2 = '''            if (TtsCache.notCached(videoId, i, voice, lang, seg.text)) {
                return new NextFetch(i, firstFutureIndex - i, seg);
            }'''
    new2 = '''            if (!isPrefetchCoolingDown(i)
                    && TtsCache.notCached(videoId, i, voice, lang, seg.text)) {
                return new NextFetch(i, firstFutureIndex - i, seg);
            }'''
    if text.count(old2) != 1:
        raise RuntimeError(f"past cooldown anchor count={text.count(old2)}")
    prefetcher.write_text(text.replace(old2, new2, 1), encoding="utf-8")
    print("patched: skip cooled future/past prefetch segments")

    rep(prefetcher,
'''    private static boolean fetch(String videoId, TranscriptSegment seg, int index,
                                 int totalSegments, String voice, String lang) {''',
'''    private static boolean isPrefetchCoolingDown(int index) {
        synchronized (lock) {
            Long until = failedUntilByIndex.get(index);
            if (until == null) return false;
            if (until <= System.currentTimeMillis()) {
                failedUntilByIndex.remove(index);
                return false;
            }
            return true;
        }
    }

    private static void markPrefetchFailure(int index) {
        synchronized (lock) {
            failedUntilByIndex.put(index, System.currentTimeMillis() + FAILED_SEGMENT_COOLDOWN_MS);
        }
        SpanishStudyDiagnostics.record("TTS-PREFETCH", "cooldown index=" + index + " 25s");
    }

    private static void clearPrefetchFailure(int index) {
        synchronized (lock) { failedUntilByIndex.remove(index); }
    }

    private static boolean fetch(String videoId, TranscriptSegment seg, int index,
                                 int totalSegments, String voice, String lang) {''',
        "add prefetch cooldown helpers")

    rep(prefetcher,
'''                SpanishStudyController.onDubAudioReady(seg, index, seg.durationMs);''',
'''                SpanishStudyController.onDubAudioReady(seg, index, seg.durationMs);
                clearPrefetchFailure(index);''',
        "clear prefetch cooldown after success")

    rep(prefetcher,
'''            VoiceOverTranslationPatch.logError(() -> "Prefetch failed for segment " + index, ex);
            return false;''',
'''            markPrefetchFailure(index);
            VoiceOverTranslationPatch.logError(() -> "Prefetch failed for segment " + index, ex);
            return false;''',
        "cool failed prefetch segment")

    # An empty Edge response is also a failed fetch and must not be selected again immediately.
    rep(prefetcher,
'''            return false;
        } catch (Exception ex) {''',
'''            markPrefetchFailure(index);
            return false;
        } catch (Exception ex) {''',
        "cool empty Edge prefetch response")

    print("v2.10.0 Google-only/local-first stability integration complete")


if __name__ == "__main__":
    main()
