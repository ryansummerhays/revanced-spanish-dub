#!/usr/bin/env python3
"""Apply v2.14 with compatibility for the post-runtime-diagnostics newVideoLoaded gate."""
from pathlib import Path
import importlib.util
import sys

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "v214_base", HERE / "patch_v214_tts_failover_marker_confidence.py")
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MOD)
ORIG_REP = MOD.rep


def compat_rep(path: Path, old: str, new: str, label: str):
    if label != "warm native TTS for persisted active sessions":
        return ORIG_REP(path, old, new, label)

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
    text = path.read_text(encoding="utf-8")
    count = text.count(actual_old)
    if count != 1:
        raise RuntimeError(f"{label}: expected final diagnostic gate once, found {count} in {path}")
    path.write_text(text.replace(actual_old, actual_new, 1), encoding="utf-8")
    print("patched:", label)


MOD.rep = compat_rep

if __name__ == "__main__":
    MOD.main()
