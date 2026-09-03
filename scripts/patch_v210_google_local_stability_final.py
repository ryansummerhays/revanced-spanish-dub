#!/usr/bin/env python3
"""v2.10.0 final: Google-only/local-first stable runtime + Edge TTS starvation recovery."""
from pathlib import Path
import sys


def rep(path: Path, old: str, new: str, label: str):
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count} in {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("patched:", label)


def replace_method(path: Path, signature: str, replacement: str, label: str):
    text = path.read_text(encoding="utf-8")
    start = text.find(signature)
    if start < 0:
        raise RuntimeError(f"{label}: signature not found in {path}")
    # All target methods here are followed by a Javadoc block. Replacing to that boundary avoids
    # depending on the exact post-v2.9 method body.
    end = text.find("\n    /**", start)
    if end < 0:
        raise RuntimeError(f"{label}: following Javadoc boundary not found in {path}")
    path.write_text(text[:start] + replacement + text[end:], encoding="utf-8")
    print("patched:", label)


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_v210_google_local_stability_final.py <morphe-root>")

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

    # Google is the effective translator regardless of the legacy/global provider selector. We do
    # not mutate the saved setting; future experimental builds can restore provider choice cleanly.
    rep(translator,
'''        String service = Settings.VOT_TRANSLATION_SERVICE.get();
        final boolean isMyMemory = service.equals(TRANSLATION_SERVICE_MY_MEMORY);
        final boolean isOpenRouter = service.equals(TRANSLATION_SERVICE_OPENROUTER);''',
'''        // v2.10 stable baseline: only Google translates Spanish Dub Study transcripts.
        String service = TRANSLATION_SERVICE_GOOGLE;
        final boolean isMyMemory = false;
        final boolean isOpenRouter = false;''',
        "force effective translation provider to Google")

    # Hard-disable every Gemini entry point that can produce a network request. Stored credentials
    # remain untouched so later experimental builds do not require re-entry.
    replace_method(gemini,
        "    public static boolean isEnabled() {",
'''    public static boolean isEnabled() {
        // v2.10 stable baseline deliberately makes no Gemini API calls.
        return false;
    }
''', "hard-disable Gemini text translation")

    rep(ground,
'''    static void maybeSchedule(String videoId, List<TranscriptSegment> source, long playheadMs) {''',
'''    static void maybeSchedule(String videoId, List<TranscriptSegment> source, long playheadMs) {
        // v2.10: remote audiovisual grounding is reserved for a future experimental build.
        if (true) return;''',
        "hard-disable Gemini video grounding")

    rep(speaker,
'''    static void maybeSchedule(String videoId, List<TranscriptSegment> source, long playheadMs) {''',
'''    static void maybeSchedule(String videoId, List<TranscriptSegment> source, long playheadMs) {
        // v2.10: no remote diarization. A future local implementation must first expose source audio
        // and then run lightweight VAD/voice embeddings on-device.
        if (true) return;''',
        "hard-disable Gemini speaker diarization")

    # Diagnostics: add authoritative mode lines and relabel the version. Existing historical fields
    # may remain for migration/debugging, but these lines state the effective runtime unambiguously.
    rep(controller,
'''        report.append("Spanish Dub Study v2.9.1 diagnostics\\n");''',
'''        report.append("Spanish Dub Study v2.10.0 diagnostics\\n");
        report.append("translationMode=google-only-stable\\n");
        report.append("geminiRuntime=disabled-in-v2.10\\n");
        report.append("analysisMode=local-lightweight-only\\n");''',
        "label v2.10 stable diagnostics")

    text = controller.read_text(encoding="utf-8")
    text = text.replace('report.append("speakerBackend=gemini-media-independent-of-text-provider\\n");',
                        'report.append("speakerBackend=disabled-pending-local-audio-pipeline\\n");')
    text = text.replace('report.append("videoGroundingActive=").append(groundingActive).append(\'\\n\');',
                        'report.append("videoGroundingActive=false\\n");')
    controller.write_text(text, encoding="utf-8")
    print("patched: clarify disabled remote analysis in diagnostics")

    # Make the study UI stop presenting quota-consuming features as active. Preferences are retained
    # but the runtime no-ops them, and the labels clearly mark them as future work.
    text = sheet.read_text(encoding="utf-8")
    text = text.replace("Gemini", "Advanced analysis (future)")
    text = text.replace("Use video/audio context", "Video/audio context (future)")
    text = text.replace("Recognize different speakers", "Speaker recognition (future)")
    text = text.replace("Different Spanish voice per speaker", "Per-speaker Spanish voices (future)")
    text = text.replace("Gemini may inspect the public YouTube video around the current phrase to correct unclear auto-captions and jargon",
                        "Disabled in the stable build; future local/experimental analysis")
    text = text.replace("Conservative voice identity; uncertain changes keep the established speaker",
                        "Disabled until a lightweight local source-audio pipeline is ready")
    text = text.replace("Uses stable alternate Spanish voices for confirmed speakers",
                        "Disabled until local speaker recognition is available")
    sheet.write_text(text, encoding="utf-8")
    print("patched: mark remote-analysis UI as future")

    # Edge TTS starvation: one failed synthesis previously held the single serialized WebSocket for
    # up to two 20-second read timeouts, draining the ready buffer. Eight seconds still gives normal
    # Edge synthesis ample room while bounding a bad request to ~16s across two socket attempts.
    rep(tts,
'''    private static final int READ_TIMEOUT_MS    = 20_000;''',
'''    private static final int READ_TIMEOUT_MS    = 8_000;''',
        "shorten Edge synthesis read timeout")

    # A failed current/future phrase must not immediately win current-first prefetch again forever.
    rep(prefetcher,
'''import java.util.ArrayList;
import java.util.Collections;''',
'''import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;''',
        "prefetch cooldown collection imports")

    rep(prefetcher,
'''import app.spanishstudy.vot.SpanishStudyController;''',
'''import app.spanishstudy.vot.SpanishStudyController;
import app.spanishstudy.vot.SpanishStudyDiagnostics;''',
        "prefetch diagnostics import")

    rep(prefetcher,
'''    private static final Object lock = new Object();''',
'''    private static final Object lock = new Object();
    private static final long FAILED_SEGMENT_COOLDOWN_MS = 25_000L;
    @GuardedBy("lock")
    private static final Map<Integer, Long> failedUntilByIndex = new HashMap<>();''',
        "add failed-segment cooldown state")

    rep(prefetcher,
'''            if (videoChanged) {
                loadingLatch = new CountDownLatch(1);
                currentVideoTimeMs = 0;
                currentBackoffMs = 0;
            }''',
'''            if (videoChanged) {
                loadingLatch = new CountDownLatch(1);
                currentVideoTimeMs = 0;
                currentBackoffMs = 0;
                failedUntilByIndex.clear();
            }''',
        "clear failed cooldowns on video change")

    rep(prefetcher,
'''            currentVideoId = "";
            currentSegments = Collections.emptyList();''',
'''            currentVideoId = "";
            currentSegments = Collections.emptyList();
            failedUntilByIndex.clear();''',
        "clear failed cooldowns on reset")

    # Current segment pass.
    rep(prefetcher,
'''                if (!TranscriptFetcher.isSpokenLanguageDifferent(lang, seg.lang)
                        && TtsCache.notCached(videoId, i, voice, lang, seg.text)) {''',
'''                if (!TranscriptFetcher.isSpokenLanguageDifferent(lang, seg.lang)
                        && !isPrefetchCoolingDown(i)
                        && TtsCache.notCached(videoId, i, voice, lang, seg.text)) {''',
        "skip cooled current phrase")

    # Speaker-aware future and past passes are the final post-v2.7 shape.
    rep(prefetcher,
'''                String candidateVoice = VoiceOverTranslationPatch.resolveVoiceForSegment(seg, lang);
                if (candidateVoice != null && TtsCache.notCached(videoId, i, candidateVoice, lang, seg.text)) {
                    return new NextFetch(i, i - firstFutureIndex, seg);
                }''',
'''                String candidateVoice = VoiceOverTranslationPatch.resolveVoiceForSegment(seg, lang);
                if (candidateVoice != null && !isPrefetchCoolingDown(i)
                        && TtsCache.notCached(videoId, i, candidateVoice, lang, seg.text)) {
                    return new NextFetch(i, i - firstFutureIndex, seg);
                }''',
        "skip cooled future phrase")

    rep(prefetcher,
'''            String candidateVoice = VoiceOverTranslationPatch.resolveVoiceForSegment(seg, lang);
            if (candidateVoice != null && TtsCache.notCached(videoId, i, candidateVoice, lang, seg.text)) {
                return new NextFetch(i, firstFutureIndex - i, seg);
            }''',
'''            String candidateVoice = VoiceOverTranslationPatch.resolveVoiceForSegment(seg, lang);
            if (candidateVoice != null && !isPrefetchCoolingDown(i)
                    && TtsCache.notCached(videoId, i, candidateVoice, lang, seg.text)) {
                return new NextFetch(i, firstFutureIndex - i, seg);
            }''',
        "skip cooled past phrase")

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
        "add TTS prefetch cooldown helpers")

    rep(prefetcher,
'''                SpanishStudyController.onDubAudioReady(seg, index, seg.durationMs);''',
'''                SpanishStudyController.onDubAudioReady(seg, index, seg.durationMs);
                clearPrefetchFailure(index);''',
        "clear cooldown after successful synthesis")

    rep(prefetcher,
'''            return false;
        } catch (Exception ex) {
            VoiceOverTranslationPatch.logError(() -> "Prefetch failed for segment " + index, ex);''',
'''            markPrefetchFailure(index);
            return false;
        } catch (Exception ex) {
            markPrefetchFailure(index);
            VoiceOverTranslationPatch.logError(() -> "Prefetch failed for segment " + index, ex);''',
        "cool empty/error Edge synthesis")

    print("v2.10.0 Google-only/local-first stability integration complete")


if __name__ == "__main__":
    main()
