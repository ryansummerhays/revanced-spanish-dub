#!/usr/bin/env python3
from pathlib import Path
import sys


def need(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise RuntimeError(f"FAIL {label}: missing {needle!r}")
    print("PASS", label)


def forbid(text: str, needle: str, label: str) -> None:
    if needle in text:
        raise RuntimeError(f"FAIL {label}: forbidden {needle!r}")
    print("PASS", label)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: audit_v23332_live_identity_collapse_fix.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()
    live = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/LiveSpeakerOnline.java"
    controller = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SpanishStudyController.java"
    hook = root / "patches/src/main/kotlin/app/morphe/patches/youtube/video/volume/PlayerVolumeHookPatch.kt"
    player = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/PlayerVolumePatch.java"
    lt = live.read_text(encoding="utf-8")
    ct = controller.read_text(encoding="utf-8")
    ht = hook.read_text(encoding="utf-8")
    pt = player.read_text(encoding="utf-8")

    need(lt, "WINDOW_SAMPLES = 24_000", "1.5 s embedding window")
    need(lt, "HOP_SAMPLES = 9_600", "0.6 s embedding hop")
    need(lt, "CONTINUITY_FLOOR = 0.47f", "bounded continuity floor")
    need(lt, "NEW_CANDIDATE_MATCH = 0.50f", "practical candidate repeat gate")
    need(lt, "COMPETING_KNOWN_MARGIN = 0.040f", "known-speaker competition gate")
    need(lt, "lastScore >= CONTINUITY_FLOOR && !competingKnown", "continuity cannot swallow low similarity")
    need(lt, "if (lastScore < CONTINUITY_FLOOR) lowSimilarityBreakouts++", "low similarity escapes current speaker")
    need(lt, "profilePoisonBlocks++", "weak continuity profile-poison protection")
    need(lt, "job.startVideoMs > candidate.endVideoMs + CANDIDATE_MAX_GAP_MS", "candidate can survive VAD boundary")
    need(lt, "speakerLiveMode=eres2net-short-window-online-human-identity-v23332", "v32 runtime marker")
    need(lt, "speakerLiveLowSimilarityBreakouts=", "collapse diagnostic")
    need(ct, "Spanish Dub Study v2.33.32 near-live ERes2Net speaker-separation diagnostics", "controller v32 header")

    # Carry forward the old verifier-crash guard exactly.
    need(ht, "observeAudioTrackWriteResultForStudy(I)V", "int-only postwrite callback retained")
    need(ht, "observePcmBufferForStudy(Ljava/nio/ByteBuffer;)V", "prewrite ByteBuffer callback retained")
    forbid(ht, "observeAcceptedPcmBufferForStudy", "no verifier-unsafe postwrite ByteBuffer callback")
    need(pt, "studyPcmWritePendingBuffer.set(buffer);", "ThreadLocal accepted-PCM bridge retained")
    need(pt, "LiveSpeakerOnline.observeAcceptedPcmBuffer", "live feed still uses exact accepted PCM")

    # The v31 failure mode must be structurally gone.
    forbid(lt, 'commitLocked(job, lastCommittedSpeaker, "continuous-run-identity-hold"',
           "remove unconditional v31 continuous-run commit")
    forbid(lt, "last.addPrototype(embedding)",
           "do not learn weak impression/style prototypes during separation stabilization")

    print("v2.33.32 audit complete")


if __name__ == "__main__":
    main()
