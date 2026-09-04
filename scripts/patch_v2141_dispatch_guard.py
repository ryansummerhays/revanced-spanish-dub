#!/usr/bin/env python3
"""v2.14.1: reserve an in-flight speech index so one phrase cannot restart repeatedly."""
from pathlib import Path
import sys


def rep(path: Path, old: str, new: str, label: str):
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("patched:", label)


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_v2141_dispatch_guard.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()
    vot = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation/VoiceOverTranslationPatch.java"

    rep(vot,
'''    private static volatile int lastSpokenIndex = -1;''',
'''    private static volatile int lastSpokenIndex = -1;
    // Reserved while synthesis/playback preparation is in flight. Unlike lastSpokenIndex, this is
    // cleared on a failed attempt so retries remain possible, but duplicate concurrent attempts are not.
    private static volatile int pendingSpeechIndex = -1;''',
        "add pending speech reservation")

    rep(vot,
'''                        if (!ttsEngine.isSpeaking() || wasExplicitSeek) {
                            final int candidateIndex = i;
                            Logger.printDebug(() -> "Preparing segment: " + candidateIndex
                                    + " videoTime: " + timeMs + " "
                                    + SpanishStudyController.dubDiagnostic(seg));
                            speak(seg, i);
                        }''',
'''                        if (app.spanishstudy.vot.SpeechDispatchPolicy.mayDispatch(
                                i, lastSpokenIndex, pendingSpeechIndex,
                                ttsEngine.isSpeaking(), wasExplicitSeek)) {
                            final int candidateIndex = i;
                            pendingSpeechIndex = i;
                            Logger.printDebug(() -> "Preparing segment: " + candidateIndex
                                    + " videoTime: " + timeMs + " "
                                    + SpanishStudyController.dubDiagnostic(seg));
                            speak(seg, i);
                        }''',
        "gate duplicate in-flight speech dispatch")

    rep(vot,
'''        lastSpokenIndex = index;
        SpanishStudyController.onDubPlaybackStarted(seg, index, actualDurationMs, rate);''',
'''        pendingSpeechIndex = -1;
        lastSpokenIndex = index;
        SpanishStudyController.onDubPlaybackStarted(seg, index, actualDurationMs, rate);''',
        "release reservation when Edge playback starts")

    rep(vot,
'''        ttsEngine.clearBusy(playbackId);
        final int failures = SpanishStudyController.onDubPlaybackFailed(seg, index);''',
'''        ttsEngine.clearBusy(playbackId);
        if (pendingSpeechIndex == index) pendingSpeechIndex = -1;
        final int failures = SpanishStudyController.onDubPlaybackFailed(seg, index);''',
        "release reservation on failed Edge attempt")

    rep(vot,
'''            lastSpokenIndex = Math.max(lastSpokenIndex, index);
            SpanishStudyDiagnostics.record("TTS", "network-skip index=" + index''',
'''            pendingSpeechIndex = -1;
            lastSpokenIndex = Math.max(lastSpokenIndex, index);
            SpanishStudyDiagnostics.record("TTS", "network-skip index=" + index''',
        "release reservation on doomed network skip")

    rep(vot,
'''        lastSpokenIndex = index;
        SpanishStudyController.onDubPlaybackStarted(seg, index, estimatedMs, rate);
        SpanishStudyDiagnostics.record("TTS-FALLBACK", "playing offline index=" + index''',
'''        pendingSpeechIndex = -1;
        lastSpokenIndex = index;
        SpanishStudyController.onDubPlaybackStarted(seg, index, estimatedMs, rate);
        SpanishStudyDiagnostics.record("TTS-FALLBACK", "playing offline index=" + index''',
        "release reservation when offline fallback starts")

    rep(vot,
'''            if (speakResult == TextToSpeech.SUCCESS) {
                lastSpokenIndex = index;''',
'''            if (speakResult == TextToSpeech.SUCCESS) {
                pendingSpeechIndex = -1;
                lastSpokenIndex = index;''',
        "release reservation when system TTS starts")

    rep(vot,
'''        Logger.printDebug(() -> "stopTts");
        isTestSpeaking = false;''',
'''        Logger.printDebug(() -> "stopTts");
        pendingSpeechIndex = -1;
        isTestSpeaking = false;''',
        "clear pending speech reservation on any stop/seek/video change")

    print("v2.14.1 duplicate speech dispatch guard complete")


if __name__ == "__main__":
    main()
