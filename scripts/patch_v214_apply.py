#!/usr/bin/env python3
"""Apply v2.14 against the fully patched v2.13 generated-source shapes."""
from pathlib import Path
import importlib.util

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "v214_base", HERE / "patch_v214_tts_failover_marker_confidence.py")
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MOD)
ORIG_REP = MOD.rep


def replace_exact(path: Path, old: str, new: str, label: str):
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected final generated-source anchor once, found {count} in {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("patched:", label)


def compat_rep(path: Path, old: str, new: str, label: str):
    if label == "warm native TTS for persisted active sessions":
        actual_old = '''        if (!Settings.VOT_ENABLED.get() || !sessionEnabled) {
            SpanishStudyDiagnostics.record("VIDEO", "load skipped: VoT/session disabled");
            return;
        }
        if (PlayerType.getCurrent() == PlayerType.INLINE_MINIMAL) {
            SpanishStudyDiagnostics.record("VIDEO", "load deferred: INLINE_MINIMAL");
            return;
        }
        TtsPrefetcher.updateVideo(videoId, segments);
        SpanishStudyDiagnostics.record("CAPTIONS", "requesting transcript at hint=" + videoPositionHint);
        loadTranscript(videoId);'''
        actual_new = '''        if (!Settings.VOT_ENABLED.get() || !sessionEnabled) {
            SpanishStudyDiagnostics.record("VIDEO", "load skipped: VoT/session disabled");
            return;
        }
        if (PlayerType.getCurrent() == PlayerType.INLINE_MINIMAL) {
            SpanishStudyDiagnostics.record("VIDEO", "load deferred: INLINE_MINIMAL");
            return;
        }
        ensureTts(); // warm the local/native reliability floor in parallel with transcript work
        TtsPrefetcher.updateVideo(videoId, segments);
        SpanishStudyDiagnostics.record("CAPTIONS", "requesting transcript at hint=" + videoPositionHint);
        loadTranscript(videoId);'''
        return replace_exact(path, actual_old, actual_new, label)

    if label == "clear failure counters on explicit reset":
        actual_old = '''            currentVideoId = "";
            currentSegments = Collections.emptyList();
            failedUntilByIndex.clear();
            currentVideoTimeMs = 0;
            lock.notifyAll();'''
        actual_new = '''            currentVideoId = "";
            currentSegments = Collections.emptyList();
            failedUntilByIndex.clear();
            failedAttemptsByIndex.clear();
            currentVideoTimeMs = 0;
            lock.notifyAll();'''
        return replace_exact(path, actual_old, actual_new, label)

    if label == "cap first Google batch near playhead":
        actual_old = '''                if ((isOpenRouter || isGemini) && firstBatchAfterReposition) {
                    capFirstBatch(batches, batchDone, index);
                }
                firstBatchAfterReposition = false;'''
        actual_new = '''                // First audible slice is deliberately small for Google as well as OpenRouter.
                if (firstBatchAfterReposition && !isMyMemory) {
                    capFirstBatch(batches, batchDone, index,
                            isOpenRouter ? OPENROUTER_FIRST_BATCH_CHARS : GOOGLE_FIRST_BATCH_CHARS);
                }
                firstBatchAfterReposition = false;'''
        return replace_exact(path, actual_old, actual_new, label)

    return ORIG_REP(path, old, new, label)


MOD.rep = compat_rep

if __name__ == "__main__":
    MOD.main()
