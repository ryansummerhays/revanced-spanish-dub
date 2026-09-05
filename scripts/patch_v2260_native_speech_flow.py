#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


def rep(path: Path, old: str, new: str, label: str, count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    found = text.count(old)
    if found != count:
        raise RuntimeError(f"{label}: expected {count} anchor(s), found {found} in {path}")
    path.write_text(text.replace(old, new, count), encoding="utf-8")
    print("patched:", label)


def replace_between(path: Path, start_marker: str, end_marker: str,
                    replacement: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    start = text.find(start_marker)
    if start < 0:
        raise RuntimeError(f"{label}: start marker not found in {path}")
    end = text.find(end_marker, start + len(start_marker))
    if end < 0:
        raise RuntimeError(f"{label}: end marker not found in {path}")
    path.write_text(text[:start] + replacement + text[end:], encoding="utf-8")
    print("patched:", label)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_v2260_native_speech_flow.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    vot = pkg / "VoiceOverTranslationPatch.java"
    translator = pkg / "TranscriptTranslator.java"
    controller = study / "SpanishStudyController.java"
    sidecar = study / "GeminiSpeakerDiarizationSidecar.java"

    for path in (vot, translator, controller, sidecar):
        if not path.is_file():
            raise RuntimeError(f"missing v2.25 generated source: {path}")

    # -------------------------------------------------------------------------
    # Speech must remain Morphe-native. Remove the custom late-start gate from
    # the actual speak() path. Subtitle timing remains an observer of the audio
    # start callback; it is not allowed to decide whether or how speech plays.
    # -------------------------------------------------------------------------
    rep(vot,
'''        final long speakFromMs = Math.max(lastVideoTimeMs, seg.playbackStartMs);
        final boolean explicitSeekAttempt = wasExplicitSeek;
        if (!SpanishStudyController.allowTtsStart(index, speakFromMs, explicitSeekAttempt)) {
            triggerNextSegmentCheck();
            return;
        }
        final long availableMs = seg.playbackEndMs - speakFromMs;''',
'''        final long speakFromMs = Math.max(lastVideoTimeMs, seg.playbackStartMs);
        // Observer-only snapshot for subtitle diagnostics. This must never gate or alter Morphe speech.
        final boolean explicitSeekAttempt = wasExplicitSeek;
        final long availableMs = seg.playbackEndMs - speakFromMs;''',
        "restore Morphe-native TTS start authority")

    # -------------------------------------------------------------------------
    # Flow-priority OpenRouter recovery. A deterministic integrity failure is
    # not a network outage and resplitting it causes extra serial requests just
    # when the playhead is catching the translator. Keep OpenRouter primary,
    # but fail the entire *native Morphe batch* forward through the existing
    # Google fallback once. Transport failures still get one retry as before.
    # -------------------------------------------------------------------------
    start = '''                    if (lastOpenRouterFailureWasIntegrity) {
'''
    end = '''                    } else {
                        consecutiveOpenRouterTransportFailures++;'''
    replacement = '''                    if (lastOpenRouterFailureWasIntegrity) {
                        consecutiveOpenRouterTransportFailures = 0;

                        // Preserve Morphe's native batch as one scheduling unit. Deterministic
                        // malformed/English/truncated model output is immediately replaced by
                        // the existing Google translator instead of split/retry serial work.
                        translated = fallbackGoogleAfterOpenRouter(
                                videoId, batch, targetLang, "integrity-whole-native-batch");
'''
    replace_between(translator, start, end, replacement, "use flow-priority whole-batch integrity fallback")

    # -------------------------------------------------------------------------
    # OpenRouter's video endpoint currently returns HTTP 402 before inference
    # when the account balance is below its minimum for video. Treat that as a
    # terminal condition for this video: one diagnostic call, then stop. The
    # user can reload the video after funding the account.
    # -------------------------------------------------------------------------
    rep(sidecar,
'''    private static boolean analysisComplete;
    private static long requestGeneration;''',
'''    private static boolean analysisComplete;
    private static boolean terminalBlocked;
    private static String terminalBlockReason = "none";
    private static long requestGeneration;''',
        "add terminal speaker block state")

    rep(sidecar,
'''        analysisComplete = false;
        requestGeneration++;
        backoffUntilWallMs = 0L;''',
'''        analysisComplete = false;
        terminalBlocked = false;
        terminalBlockReason = "none";
        requestGeneration++;
        backoffUntilWallMs = 0L;''',
        "reset terminal speaker block on clear")

    rep(sidecar,
'''                analysisComplete = false;
                requestGeneration++;
                backoffUntilWallMs = 0L;''',
'''                analysisComplete = false;
                terminalBlocked = false;
                terminalBlockReason = "none";
                requestGeneration++;
                backoffUntilWallMs = 0L;''',
        "reset terminal speaker block for new video")

    rep(sidecar,
'''            if (analysisComplete || inFlight || now < backoffUntilWallMs) return;''',
'''            if (analysisComplete || terminalBlocked || inFlight || now < backoffUntilWallMs) return;''',
        "stop rescheduling terminal speaker failures")

    rep(sidecar,
'''                synchronized (GeminiSpeakerDiarizationSidecar.class) {
                    failed++;
                    lastError = safe(ex.getMessage());
                    long delay = lastHttpStatus == 429 ? QUOTA_BACKOFF_MS : FAILURE_BACKOFF_MS;
                    backoffUntilWallMs = Math.max(backoffUntilWallMs, System.currentTimeMillis() + delay);
                }''',
'''                synchronized (GeminiSpeakerDiarizationSidecar.class) {
                    failed++;
                    lastError = safe(ex.getMessage());
                    if (lastHttpStatus == 402) {
                        terminalBlocked = true;
                        terminalBlockReason = lastError;
                        backoffUntilWallMs = Long.MAX_VALUE;
                    } else {
                        long delay = lastHttpStatus == 429 ? QUOTA_BACKOFF_MS : FAILURE_BACKOFF_MS;
                        backoffUntilWallMs = Math.max(backoffUntilWallMs, System.currentTimeMillis() + delay);
                    }
                }''',
        "make HTTP 402 terminal for current video")

    rep(sidecar,
'''        if (inFlight) return base + " · mapping full video";
        if (analysisComplete) return base + " · mapped";''',
'''        if (inFlight) return base + " · mapping full video";
        if (analysisComplete) return base + " · mapped";
        if (terminalBlocked) return base + " · OpenRouter video blocked: $1 balance required";''',
        "show terminal OpenRouter video balance block")

    rep(sidecar,
'''                + "Last error: " + lastError + "\\n\\n"
                + "Speaker letters come from digital-audio diarization.''',
'''                + "Last error: " + lastError + "\\n"
                + "Terminal for this video: " + terminalBlocked + "\\n"
                + "Terminal reason: " + terminalBlockReason + "\\n\\n"
                + "Speaker letters come from digital-audio diarization.''',
        "expose terminal speaker failure in selectable details")

    rep(sidecar,
'''                + "speakerLastError=" + safe(lastError) + '\\n';''',
'''                + "speakerLastError=" + safe(lastError) + '\\n'
                + "speakerTerminalBlocked=" + terminalBlocked + '\\n'
                + "speakerTerminalReason=" + safe(terminalBlockReason) + '\\n';''',
        "publish terminal speaker failure diagnostics")

    # -------------------------------------------------------------------------
    # Make the runtime report unambiguous about which systems are authoritative.
    # -------------------------------------------------------------------------
    rep(controller,
        'report.append("Spanish Dub Study v2.25.0 diagnostics\\n");',
        'report.append("Spanish Dub Study v2.26.0 diagnostics\\n");',
        "bump diagnostics to v2.26")
    rep(controller,
        'report.append("subtitleTiming=morphe-tts-effective-end+source-fallback\\n");',
        'report.append("subtitleTiming=observer-only-actual-audio-start+source-fallback\\n");\n'
        '        report.append("speechFlowAuthority=morphe-v1.41.0-native-speak+rate+seek+edge-cache-prefetch\\n");',
        "publish native speech authority")
    rep(controller,
        'report.append("cardinalityRecovery=aligned-prefix+split-first+singleton-google+transport-retry-once\\n");',
        'report.append("cardinalityRecovery=aligned-prefix+whole-native-batch-google-on-integrity+transport-retry-once\\n");',
        "publish flow-priority recovery")
    rep(controller,
        'report.append("ttsLateStartPolicy=source-end+500ms-fresh-start-deadline\\n");',
        'report.append("ttsLateStartPolicy=diagnostic-only-no-custom-start-gate\\n");',
        "publish observer-only late-start telemetry")
    rep(controller,
        'report.append("speakerAnalysisMode=one-shot-full-video-caption-map\\n");',
        'report.append("speakerAnalysisMode=one-shot-full-video-caption-map+terminal-402-per-video\\n");',
        "publish terminal speaker 402 policy")

    print("v2.26 native speech flow + flow-priority translation recovery + terminal speaker 402 complete")


if __name__ == "__main__":
    main()
