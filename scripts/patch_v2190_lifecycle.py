#!/usr/bin/env python3
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


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: patch_v2190_lifecycle.py <morphe-root> <repo-root>")

    root = Path(sys.argv[1]).resolve()
    repo = Path(sys.argv[2]).resolve()
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    vot = pkg / "VoiceOverTranslationPatch.java"
    controller = study / "SpanishStudyController.java"
    telemetry = study / "SpanishStudyRuntimeTelemetry.java"
    for path in (vot, controller, telemetry):
        if not path.is_file():
            raise RuntimeError(f"missing v2.18 source: {path}")

    for name in ("WorkerLifecyclePolicy.java", "TtsStartPolicy.java"):
        shutil.copy2(repo / "overlay/v219/app/spanishstudy/vot" / name, study / name)
        print("copied:", name)

    rep(telemetry,
        '''    private static final AtomicLong subtitleTtsOverrunMaxMs = new AtomicLong();''',
        '''    private static final AtomicLong subtitleTtsOverrunMaxMs = new AtomicLong();
    private static final AtomicInteger translationWorkerStarts = new AtomicInteger();
    private static final AtomicInteger translationWorkerStops = new AtomicInteger();
    private static final AtomicInteger translationWorkerRestartRequests = new AtomicInteger();
    private static final AtomicInteger translationWorkerStaleDrops = new AtomicInteger();
    private static final AtomicInteger ttsStartAttempts = new AtomicInteger();
    private static final AtomicInteger ttsRepeatedStartAttempts = new AtomicInteger();
    private static final AtomicInteger ttsLateSkips = new AtomicInteger();
    private static final AtomicLong ttsMaxLateStartMs = new AtomicLong();
    private static volatile long translationWorkerEpoch = -1L;
    private static volatile String translationWorkerState = "idle";
    private static volatile String translationWorkerLastStartReason = "-";
    private static volatile String translationWorkerLastStopReason = "-";
    private static volatile String translationWorkerLastRestartReason = "-";''',
        "add worker and TTS telemetry fields")

    rep(telemetry,
        '''    public static String diagnostics() {''',
        '''    public static void recordWorkerStart(long workerEpoch, String reason) {
        translationWorkerEpoch = workerEpoch;
        translationWorkerState = "running";
        translationWorkerLastStartReason = clean(reason);
        translationWorkerStarts.incrementAndGet();
    }

    public static void recordWorkerStop(long workerEpoch, String reason) {
        translationWorkerEpoch = workerEpoch;
        translationWorkerState = "idle";
        translationWorkerLastStopReason = clean(reason);
        translationWorkerStops.incrementAndGet();
    }

    public static void recordWorkerRestartRequest(String reason) {
        translationWorkerState = "restart-pending";
        translationWorkerLastRestartReason = clean(reason);
        translationWorkerRestartRequests.incrementAndGet();
    }

    public static void recordWorkerStaleDrop() {
        translationWorkerStaleDrops.incrementAndGet();
    }

    public static void recordTtsStartAttempt(boolean repeated, long lateStartMs) {
        ttsStartAttempts.incrementAndGet();
        if (repeated) ttsRepeatedStartAttempts.incrementAndGet();
        ttsMaxLateStartMs.accumulateAndGet(Math.max(0L, lateStartMs), Math::max);
    }

    public static void recordTtsLateSkip(long lateStartMs) {
        ttsLateSkips.incrementAndGet();
        ttsMaxLateStartMs.accumulateAndGet(Math.max(0L, lateStartMs), Math::max);
    }

    private static String clean(String value) {
        if (value == null || value.isBlank()) return "-";
        return value.replace('\n', ' ').replace('\r', ' ');
    }

    public static String diagnostics() {''',
        "add worker and TTS telemetry methods")

    rep(telemetry,
        '''                + "subtitleMaxTtsOverrunMs=" + subtitleTtsOverrunMaxMs.get() + '\n';''',
        '''                + "subtitleMaxTtsOverrunMs=" + subtitleTtsOverrunMaxMs.get() + '\n'
                + "translationWorkerEpoch=" + translationWorkerEpoch + '\n'
                + "translationWorkerState=" + translationWorkerState + '\n'
                + "translationWorkerStarts=" + translationWorkerStarts.get() + '\n'
                + "translationWorkerStops=" + translationWorkerStops.get() + '\n'
                + "translationWorkerRestartRequests=" + translationWorkerRestartRequests.get() + '\n'
                + "translationWorkerStaleDrops=" + translationWorkerStaleDrops.get() + '\n'
                + "translationWorkerLastStartReason=" + translationWorkerLastStartReason + '\n'
                + "translationWorkerLastStopReason=" + translationWorkerLastStopReason + '\n'
                + "translationWorkerLastRestartReason=" + translationWorkerLastRestartReason + '\n'
                + "ttsStartAttempts=" + ttsStartAttempts.get() + '\n'
                + "ttsRepeatedStartAttempts=" + ttsRepeatedStartAttempts.get() + '\n'
                + "ttsLateSkips=" + ttsLateSkips.get() + '\n'
                + "ttsMaxLateStartMs=" + ttsMaxLateStartMs.get() + '\n';''',
        "publish worker and TTS telemetry")

    rep(telemetry,
        '''        subtitleTtsOverrunMaxMs.set(0);
    }
}''',
        '''        subtitleTtsOverrunMaxMs.set(0);
        translationWorkerStarts.set(0);
        translationWorkerStops.set(0);
        translationWorkerRestartRequests.set(0);
        translationWorkerStaleDrops.set(0);
        ttsStartAttempts.set(0);
        ttsRepeatedStartAttempts.set(0);
        ttsLateSkips.set(0);
        ttsMaxLateStartMs.set(0);
        translationWorkerEpoch = -1L;
        translationWorkerState = "idle";
        translationWorkerLastStartReason = "-";
        translationWorkerLastStopReason = "-";
        translationWorkerLastRestartReason = "-";
    }
}''',
        "reset v2.19 telemetry per video")

    rep(controller,
        '''    private static boolean cleared = true;''',
        '''    private static boolean cleared = true;
    private static final java.util.Map<Integer,Integer> ttsAttempts = new java.util.HashMap<>();''',
        "track per-segment TTS attempts")

    rep(controller,
        '''            translatedSnapshotVersion = 0;
            cleared = false;''',
        '''            translatedSnapshotVersion = 0;
            ttsAttempts.clear();
            cleared = false;''',
        "reset TTS attempts on new video")

    rep(controller,
        '''            cleared = false;
            lastTranslatedFingerprint = Long.MIN_VALUE;
        }
        SpanishStudyDiagnostics.record("SESSION", "epoch=" + epoch + " enabled");''',
        '''            cleared = false;
            lastTranslatedFingerprint = Long.MIN_VALUE;
            ttsAttempts.clear();
        }
        SpanishStudyDiagnostics.record("SESSION", "epoch=" + epoch + " enabled");''',
        "reset TTS attempts on session enable")

    old_tts = '''    public static void onTtsWindow(int index, String text, long showAtMs, long hideAtMs,
                                   long speechDurationMs, float rate) {
        if (index < 0 || hideAtMs <= showAtMs) return;
        Utils.runOnMainThreadNowOrLater(() -> SpanishSubtitleOverlay.setTtsWindow(index, showAtMs, hideAtMs));

        List<TranscriptSegment> sources = sourceSegments;
        if (index >= 0 && index < sources.size()) {
            TranscriptSegment source = sources.get(index);
            long overrunMs = Math.max(0L, hideAtMs - source.endMs);
            SpanishStudyRuntimeTelemetry.recordSubtitleOverrun(overrunMs);
            if (overrunMs >= 500L) {
                SpanishStudyDiagnostics.record("SUBTITLE-TIMING", "epoch="
                        + SpanishStudyRuntimeTelemetry.currentEpoch() + " index=" + index
                        + " sourceEnd=" + source.endMs + " ttsEnd=" + hideAtMs
                        + " overrunMs=" + overrunMs + " speechMs=" + speechDurationMs
                        + " rate=" + String.format(java.util.Locale.US, "%.2f", rate));
            }
        }
    }
'''
    new_tts = '''    public static void onTtsWindow(int index, String text, long showAtMs, long hideAtMs,
                                   long remainingSpeechMs, float rate, boolean explicitSeek) {
        if (index < 0 || hideAtMs <= showAtMs) return;
        Utils.runOnMainThreadNowOrLater(() -> SpanishSubtitleOverlay.setTtsWindow(index, showAtMs, hideAtMs));

        List<TranscriptSegment> sources = sourceSegments;
        if (index >= 0 && index < sources.size()) {
            TranscriptSegment source = sources.get(index);
            final int attempt;
            synchronized (SpanishStudyController.class) {
                attempt = ttsAttempts.getOrDefault(index, 0) + 1;
                ttsAttempts.put(index, attempt);
            }
            long lateStartMs = TtsStartPolicy.lateFromSourceStartMs(showAtMs, source.startMs);
            long sourceRemainingMs = TtsStartPolicy.sourceRemainingMs(showAtMs, source.endMs);
            float requiredRate = TtsStartPolicy.requiredRate(remainingSpeechMs, showAtMs, source.endMs);
            long overrunMs = Math.max(0L, hideAtMs - source.endMs);
            SpanishStudyRuntimeTelemetry.recordSubtitleOverrun(overrunMs);
            SpanishStudyRuntimeTelemetry.recordTtsStartAttempt(attempt > 1, lateStartMs);
            if (overrunMs >= 500L || attempt > 1 || requiredRate > rate + 0.05f) {
                String required = Float.isFinite(requiredRate)
                        ? String.format(java.util.Locale.US, "%.2f", requiredRate) : "inf";
                SpanishStudyDiagnostics.record("TTS-TIMING", "epoch="
                        + SpanishStudyRuntimeTelemetry.currentEpoch() + " index=" + index
                        + " attempt=" + attempt + " explicitSeek=" + explicitSeek
                        + " sourceStart=" + source.startMs + " sourceEnd=" + source.endMs
                        + " speakFrom=" + showAtMs + " lateStartMs=" + lateStartMs
                        + " sourceRemainingMs=" + sourceRemainingMs
                        + " speechRemainingMs=" + remainingSpeechMs
                        + " requiredRate=" + required
                        + " appliedRate=" + String.format(java.util.Locale.US, "%.2f", rate)
                        + " ttsEnd=" + hideAtMs + " overrunMs=" + overrunMs);
            }
        }
    }

    public static boolean allowTtsStart(int index, long speakFromMs, boolean explicitSeek) {
        List<TranscriptSegment> sources = sourceSegments;
        if (index < 0 || index >= sources.size()) return true;
        TranscriptSegment source = sources.get(index);
        if (TtsStartPolicy.allowStart(speakFromMs, source.startMs, source.endMs, explicitSeek)) return true;
        long latePastEndMs = Math.max(0L, speakFromMs - source.endMs);
        SpanishStudyRuntimeTelemetry.recordTtsLateSkip(latePastEndMs);
        SpanishStudyDiagnostics.record("TTS-LATE-SKIP", "epoch="
                + SpanishStudyRuntimeTelemetry.currentEpoch() + " index=" + index
                + " sourceEnd=" + source.endMs + " speakFrom=" + speakFromMs
                + " latePastEndMs=" + latePastEndMs);
        return false;
    }
'''
    rep(controller, old_tts, new_tts, "decompose TTS timing and block stale fresh starts")

    rep(controller,
        '''    public static void onSessionDisabled() {
        Utils.runOnMainThreadNowOrLater(SpanishSubtitleOverlay::hide);
        SpanishStudyDiagnostics.record("SESSION", "epoch=" + SpanishStudyRuntimeTelemetry.currentEpoch() + " disabled");
    }
''',
        '''    public static void onSessionDisabled() {
        long epoch = SpanishStudyRuntimeTelemetry.bumpEpoch();
        Utils.runOnMainThreadNowOrLater(SpanishSubtitleOverlay::hide);
        SpanishStudyDiagnostics.record("SESSION", "epoch=" + epoch + " disabled");
    }

    public static long onTranslationWorkerStarted(String reason) {
        long workerEpoch = SpanishStudyRuntimeTelemetry.currentEpoch();
        SpanishStudyRuntimeTelemetry.recordWorkerStart(workerEpoch, reason);
        SpanishStudyDiagnostics.record("TRANSLATION-WORKER", "epoch=" + workerEpoch
                + " action=start reason=" + reason);
        return workerEpoch;
    }

    public static boolean acceptTranslationWorkerCallback(long workerEpoch, String callbackKind) {
        boolean current = WorkerLifecyclePolicy.shouldPublish(
                true, VoiceOverTranslationPatch.isSessionEnabled(),
                workerEpoch, SpanishStudyRuntimeTelemetry.currentEpoch());
        if (!current) {
            SpanishStudyRuntimeTelemetry.recordWorkerStaleDrop();
            SpanishStudyDiagnostics.record("TRANSLATION-WORKER", "workerEpoch=" + workerEpoch
                    + " currentEpoch=" + SpanishStudyRuntimeTelemetry.currentEpoch()
                    + " action=stale-drop callback=" + callbackKind);
        }
        return current;
    }

    public static void onTranslationWorkerRestartRequested(String reason) {
        SpanishStudyRuntimeTelemetry.recordWorkerRestartRequest(reason);
        SpanishStudyDiagnostics.record("TRANSLATION-WORKER", "epoch="
                + SpanishStudyRuntimeTelemetry.currentEpoch()
                + " action=restart-request reason=" + reason);
    }

    public static void onTranslationWorkerStopped(long workerEpoch, String reason) {
        SpanishStudyRuntimeTelemetry.recordWorkerStop(workerEpoch, reason);
        SpanishStudyDiagnostics.record("TRANSLATION-WORKER", "workerEpoch=" + workerEpoch
                + " currentEpoch=" + SpanishStudyRuntimeTelemetry.currentEpoch()
                + " action=stop reason=" + reason);
    }
''',
        "invalidate session epoch and add worker lifecycle logs")

    rep(vot,
        '''import app.spanishstudy.vot.SpanishStudyRuntimeTelemetry;''',
        '''import app.spanishstudy.vot.SpanishStudyRuntimeTelemetry;
import app.spanishstudy.vot.WorkerLifecyclePolicy;''',
        "import worker lifecycle policy")

    rep(vot,
        '''    private static boolean isLoading;''',
        '''    private static boolean isLoading;
    private static volatile boolean restartTranscriptAfterLoad;''',
        "add worker re-arm latch")

    rep(vot,
        '''        currentVideoId = videoId;
        segments = new ArrayList<>();
        SpanishStudyController.onNewVideo(videoId);''',
        '''        currentVideoId = videoId;
        segments = new ArrayList<>();
        restartTranscriptAfterLoad = false;
        SpanishStudyController.onNewVideo(videoId);''',
        "reset re-arm latch per video")

    rep(vot,
        '''        sessionEnabled = true;
        Settings.VOT_SESSION_ENABLED.save(true);
        SpanishStudyController.onSessionEnabled();
        TtsPrefetcher.triggerRescan();
        if (!currentVideoId.isEmpty() && segments.isEmpty() && !isLoading) {
            loadTranscript(currentVideoId);
        }''',
        '''        sessionEnabled = true;
        Settings.VOT_SESSION_ENABLED.save(true);
        SpanishStudyController.onSessionEnabled();
        if (!currentVideoId.isEmpty()) {
            if (isLoading) {
                restartTranscriptAfterLoad = true;
                SpanishStudyController.onTranslationWorkerRestartRequested("session-enable-while-loading");
                TranscriptTranslator.requestAbort();
            } else {
                restartTranscriptAfterLoad = false;
                segments = new ArrayList<>();
                TtsPrefetcher.clear();
                SpanishStudyController.onTranslationWorkerRestartRequested("session-enable-immediate");
                loadTranscript(currentVideoId);
            }
        }
        TtsPrefetcher.triggerRescan();''',
        "deterministically re-arm translation on enable")

    rep(vot,
        '''        sessionEnabled = false;
        Settings.VOT_SESSION_ENABLED.save(false);
        TranscriptTranslator.requestAbort();''',
        '''        sessionEnabled = false;
        Settings.VOT_SESSION_ENABLED.save(false);
        restartTranscriptAfterLoad = false;
        TranscriptTranslator.requestAbort();''',
        "cancel pending re-arm on disable")

    rep_section(vot, "private static void loadTranscript(String videoId)",
                "\n    /** Current video id exposed only to the local diagnostics UI.",
        '''        if (isLoading) return;
        isLoading = true;
        final String loadLang = resolveTargetLang();''',
        '''        if (isLoading) return;
        isLoading = true;
        final long loadEpoch = SpanishStudyController.onTranslationWorkerStarted("loadTranscript");
        final String loadLang = resolveTargetLang();''',
        "tag native translation worker with session epoch")

    rep_section(vot, "private static void loadTranscript(String videoId)",
                "\n    /** Current video id exposed only to the local diagnostics UI.",
        '''                            if (Settings.VOT_ENABLED.get() && sessionEnabled
                                    && videoId.equals(currentVideoId) && loadLang.equals(resolveTargetLang())) {''',
        '''                            if (Settings.VOT_ENABLED.get() && sessionEnabled
                                    && SpanishStudyController.acceptTranslationWorkerCallback(loadEpoch, "progress")
                                    && videoId.equals(currentVideoId) && loadLang.equals(resolveTargetLang())) {''',
        "drop stale progressive worker callback")

    rep_section(vot, "private static void loadTranscript(String videoId)",
                "\n    /** Current video id exposed only to the local diagnostics UI.",
        '''                    if (Settings.VOT_ENABLED.get() && sessionEnabled
                            && videoId.equals(currentVideoId) && loadLang.equals(resolveTargetLang())) {''',
        '''                    if (Settings.VOT_ENABLED.get() && sessionEnabled
                            && SpanishStudyController.acceptTranslationWorkerCallback(loadEpoch, "final")
                            && videoId.equals(currentVideoId) && loadLang.equals(resolveTargetLang())) {''',
        "drop stale final worker callback")

    old_finally = '''                    isLoading = false;
                    // Restart if the video, language, or translation provider changed while this fetch was in flight.
                    if (!currentVideoId.isEmpty() && Settings.VOT_ENABLED.get() && sessionEnabled
                            && (!currentVideoId.equals(videoId)
                            || !loadLang.equals(resolveTargetLang())
                            || !loadService.equals(Settings.VOT_TRANSLATION_SERVICE.get()))) {
                        loadTranscript(currentVideoId);
                    }'''
    new_finally = '''                    isLoading = false;
                    final boolean videoPresent = !currentVideoId.isEmpty();
                    final boolean videoChanged = !currentVideoId.equals(videoId);
                    final boolean languageChanged = !loadLang.equals(resolveTargetLang());
                    final boolean providerChanged = !loadService.equals(Settings.VOT_TRANSLATION_SERVICE.get());
                    final boolean restartRequested = restartTranscriptAfterLoad;
                    final long currentEpoch = SpanishStudyRuntimeTelemetry.currentEpoch();
                    final boolean shouldRestart = WorkerLifecyclePolicy.shouldRestartAfterFinish(
                            Settings.VOT_ENABLED.get(), sessionEnabled, videoPresent, restartRequested,
                            loadEpoch, currentEpoch, videoChanged, languageChanged, providerChanged);
                    String stopReason = !sessionEnabled ? "session-disabled"
                            : loadEpoch != currentEpoch ? "stale-epoch"
                            : restartRequested ? "restart-requested"
                            : videoChanged ? "video-changed"
                            : languageChanged ? "language-changed"
                            : providerChanged ? "provider-changed"
                            : "completed";
                    SpanishStudyController.onTranslationWorkerStopped(loadEpoch, stopReason);
                    if (shouldRestart) {
                        restartTranscriptAfterLoad = false;
                        segments = new ArrayList<>();
                        TtsPrefetcher.clear();
                        SpanishStudyController.onTranslationWorkerRestartRequested(
                                "worker-finished-" + stopReason);
                        loadTranscript(currentVideoId);
                    }'''
    rep_section(vot, "private static void loadTranscript(String videoId)",
                "\n    /** Current video id exposed only to the local diagnostics UI.",
                old_finally, new_finally,
                "restart stale/aborted worker exactly once after finish")

    rep_section(vot, "private static void speak(TranscriptSegment seg, int index)",
                "\n    private static void triggerNextSegmentCheck()",
        '''        final long speakFromMs = Math.max(lastVideoTimeMs, seg.playbackStartMs);
        final long availableMs = seg.playbackEndMs - speakFromMs;''',
        '''        final long speakFromMs = Math.max(lastVideoTimeMs, seg.playbackStartMs);
        final boolean explicitSeekAttempt = wasExplicitSeek;
        if (!SpanishStudyController.allowTtsStart(index, speakFromMs, explicitSeekAttempt)) {
            triggerNextSegmentCheck();
            return;
        }
        final long availableMs = seg.playbackEndMs - speakFromMs;''',
        "block stale TTS fresh start")

    rep_section(vot, "private static void speak(TranscriptSegment seg, int index)",
                "\n    private static void triggerNextSegmentCheck()",
        '''        SpanishStudyController.onTtsWindow(index, seg.text, speakFromMs, ttsEndVideoTimeMs,
                speechDurationMs, rate);''',
        '''        SpanishStudyController.onTtsWindow(index, seg.text, speakFromMs, ttsEndVideoTimeMs,
                remainingSpeechMs, rate, explicitSeekAttempt);''',
        "expand TTS timing diagnostics")

    print("v2.19 lifecycle and TTS integration complete")


if __name__ == "__main__":
    main()
