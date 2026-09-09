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
        raise SystemExit("usage: audit_v23334_style_context_recovery.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()
    live = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/LiveSpeakerOnline.java"
    controller = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SpanishStudyController.java"
    translator = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation/TranscriptTranslator.java"
    hook = root / "patches/src/main/kotlin/app/morphe/patches/youtube/video/volume/PlayerVolumeHookPatch.kt"
    player = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/PlayerVolumePatch.java"
    for p in (live, controller, translator, hook, player):
        if not p.is_file():
            raise RuntimeError(f"missing audit input: {p}")
    lt = live.read_text(encoding="utf-8")
    ct = controller.read_text(encoding="utf-8")
    tt = translator.read_text(encoding="utf-8")
    ht = hook.read_text(encoding="utf-8")
    pt = player.read_text(encoding="utf-8")

    # Proven live extraction/timing remains exactly on the v32/v33 path.
    need(lt, "WINDOW_SAMPLES = 24_000", "1.5 s embedding window retained")
    need(lt, "HOP_SAMPLES = 9_600", "0.6 s embedding hop retained")
    need(lt, "CONTINUITY_FLOOR = 0.47f", "bounded continuity retained")
    need(lt, "NEW_CANDIDATE_MATCH = 0.50f", "candidate similarity floor retained")

    # v34 human-vs-style separation.
    need(lt, "NEW_PROFILE_LONG_RUN_SUPPORT = 12", "one short continuous style run cannot create human")
    need(lt, "STYLE_PENDING_CONFIRMATIONS = 3", "three bridge confirmations required for style learning")
    need(lt, "STYLE_PENDING_MATCH = 0.60f", "style recurrence similarity gate")
    need(lt, "STYLE_PENDING", "quarantined style proposals exist")
    need(lt, "resolveStyleCandidateOnKnownReturnLocked", "same-run bridge-back resolver exists")
    need(lt, "job.speechRunSerial == lastCommittedSpeechRunSerial", "style parent requires same VAD run")
    need(lt, "parentSpeaker = -1;", "VAD boundary releases style-parent hypothesis")
    need(lt, "candidate.distinctSpeechRuns >= 2", "normal new human needs boundary evidence")
    need(lt, "exceptionalLongRun", "long coherent monologue escape hatch exists")
    need(lt, "profilePoisonBlocks++", "weak evidence has anti-poison path")
    need(lt, "speakerLiveStyleExcursionsStarted=", "style excursion diagnostics")
    need(lt, "speakerLiveStylePrototypeConfirms=", "confirmed style prototype diagnostics")
    need(lt, "speakerLiveNewProfileBoundaryPromotions=", "new-human boundary diagnostics")
    need(lt, "speakerLiveMode=eres2net-short-window-online-human-identity-v23334", "v34 live mode marker")
    need(lt, "human-vs-style-hypothesis+vad-boundary-evidence+known-rescue", "v34 identity policy marker")
    need(lt, "same-run-style-excursion+three-bridge-quarantine-before-prototype", "v34 impression policy marker")
    need(ct, "Spanish Dub Study v2.33.34 context-aware human/style identity diagnostics", "controller v34 header")

    # v33's eager continuous-run permanent human gate must be gone.
    forbid(lt, "NEW_PROFILE_CONTINUOUS_SUPPORT = 4", "remove four-window continuous human promotion")
    forbid(lt, "candidate.count >= NEW_PROFILE_CONTINUOUS_SUPPORT", "continuous support alone cannot mint human")
    forbid(lt, "if (candidate.count >= 2 && profileCount < MAX_PROFILES)", "old two-window permanent speaker promotion absent")
    forbid(lt, 'commitLocked(job, lastCommittedSpeaker, "continuous-run-identity-hold"',
           "v31 unconditional identity inertia remains absent")

    # Translation: a null OpenRouter result must get bounded recovery before stock done=true.
    need(tt, "List<String> translated = translateBatchSafe", "batch result is mutable for recovery")
    need(tt, "OpenRouter recovery action=retry-once", "one OpenRouter retry exists")
    need(tt, "OpenRouter recovery action=google-batch-fallback", "same-batch Google fallback exists")
    need(tt, "OpenRouter recovery action=google-batch-fallback-success", "fallback success is observable")
    need(tt, "translated == null && isOpenRouter && !abortTranslation && !reprioritize",
         "recovery is gated away from auth/quota abort and seek cuts")
    need(tt, "translateBatchGoogle(videoId, batch, targetLang)", "fallback uses existing Google batch path")
    forbid(tt, "retry same native Morphe batch failures=", "old unbounded retry machinery absent")

    # Hard release gates from the v30 verifier-safe accepted-PCM path.
    need(ht, "observeAudioTrackWriteResultForStudy(I)V", "int-only postwrite callback retained")
    need(ht, "observePcmBufferForStudy(Ljava/nio/ByteBuffer;)V", "prewrite ByteBuffer callback retained")
    forbid(ht, "observeAcceptedPcmBufferForStudy", "no verifier-unsafe postwrite ByteBuffer callback")
    need(pt, "studyPcmWritePendingBuffer.set(buffer);", "ThreadLocal accepted-PCM bridge retained")
    need(pt, "LiveSpeakerOnline.observeAcceptedPcmBuffer", "live ERes2Net still consumes exact accepted PCM")

    print("v2.33.34 style-context + translation-recovery audit complete")


if __name__ == "__main__":
    main()
