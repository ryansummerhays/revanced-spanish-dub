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
        raise SystemExit("usage: audit_v23333_identity_stabilization.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()
    live = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/LiveSpeakerOnline.java"
    controller = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SpanishStudyController.java"
    hook = root / "patches/src/main/kotlin/app/morphe/patches/youtube/video/volume/PlayerVolumeHookPatch.kt"
    player = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/PlayerVolumePatch.java"
    lt = live.read_text(encoding="utf-8")
    ct = controller.read_text(encoding="utf-8")
    ht = hook.read_text(encoding="utf-8")
    pt = player.read_text(encoding="utf-8")

    # v32's proven near-live extraction path remains unchanged.
    need(lt, "WINDOW_SAMPLES = 24_000", "1.5 s embedding window retained")
    need(lt, "HOP_SAMPLES = 9_600", "0.6 s embedding hop retained")
    need(lt, "NEW_CANDIDATE_MATCH = 0.50f", "candidate observation floor retained")
    need(lt, "CONTINUITY_FLOOR = 0.47f", "bounded continuity retained")

    # v33 identity stabilization gates.
    need(lt, "CANDIDATE_RESCUE_MATCH = 0.50f", "candidate centroid known-person rescue")
    need(lt, "CANDIDATE_AMBIGUOUS_KNOWN = 0.40f", "ambiguous candidate remains unknown")
    need(lt, "CANDIDATE_MIN_AVG_COHESION = 0.55f", "candidate internal cohesion gate")
    need(lt, "NEW_PROFILE_MIN_SUPPORT = 3", "at least three observations for a new profile")
    need(lt, "NEW_PROFILE_CONTINUOUS_SUPPORT = 4", "long continuous speech support gate")
    need(lt, "bootstrap-speaker-confirmed", "first speaker bootstrapped from repeat evidence")
    need(lt, "candidate-rescued-known", "candidate cluster can resolve to known person")
    need(lt, "new-speaker-coherent-cluster", "new person requires coherent cluster")
    need(lt, "distinctSpeechRuns", "candidate recurrence is tracked")
    need(lt, "averageCohesion()", "candidate cohesion is tracked")
    need(lt, "if (candidate != null && videoMs >= candidate.startVideoMs", "unresolved candidate displays unknown")
    need(lt, "supportCount", "established profile evidence is tracked")
    need(lt, "speakerLiveMode=eres2net-short-window-online-human-identity-v23333", "v33 runtime marker")
    need(lt, "speakerLiveIdentityPolicy=coherent-candidate-cluster+known-profile-rescue+bounded-inertia", "v33 identity policy marker")
    need(lt, "speakerLiveUnknownPolicy=uncommitted-candidate-until-human-evidence-is-stable", "explicit unknown policy")
    need(lt, "speakerLiveCandidateRescues=", "candidate rescue diagnostics")
    need(lt, "speakerLiveCandidateCohesionPermille=", "candidate cohesion diagnostics")
    need(lt, "speakerLiveProfileFormat=label:prototypes/support", "profile evidence diagnostics")
    need(ct, "Spanish Dub Study v2.33.33 near-live ERes2Net identity-stabilization diagnostics", "controller v33 header")

    # The v32 two-window permanent-person failure mode must be gone.
    forbid(lt, "if (candidate.count >= 2 && profileCount < MAX_PROFILES)",
           "remove two-window permanent speaker promotion")
    forbid(lt, 'commitLocked(job, lastCommittedSpeaker, "continuous-run-identity-hold"',
           "do not restore v31 unconditional identity inertia")
    forbid(lt, "last.addPrototype(embedding)",
           "do not learn weak continuity as a style prototype")

    # Carry forward the verifier-safe exact-accepted-PCM path. These are hard release gates.
    need(ht, "observeAudioTrackWriteResultForStudy(I)V", "int-only postwrite callback retained")
    need(ht, "observePcmBufferForStudy(Ljava/nio/ByteBuffer;)V", "prewrite ByteBuffer callback retained")
    forbid(ht, "observeAcceptedPcmBufferForStudy", "no verifier-unsafe postwrite ByteBuffer callback")
    need(pt, "studyPcmWritePendingBuffer.set(buffer);", "ThreadLocal accepted-PCM bridge retained")
    need(pt, "LiveSpeakerOnline.observeAcceptedPcmBuffer", "live ERes2Net feed still consumes exact accepted PCM")

    print("v2.33.33 identity stabilization audit complete")


if __name__ == "__main__":
    main()
