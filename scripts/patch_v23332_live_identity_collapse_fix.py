#!/usr/bin/env python3
"""v2.33.32: stop near-live ERes2Net identity collapse into Speaker A.

Keeps v2.33.31's proven accepted-PCM/video clock and Android embedding extractor. The fix is
entirely inside the online human-identity policy:
- shorter 1.5 s windows / 0.6 s hop reduce mixed-speaker embeddings;
- continuity is allowed only with meaningful similarity to the current person;
- a competing known speaker is never swallowed by continuity inertia;
- low-similarity evidence falls through to new-speaker confirmation instead of being committed;
- weak windows never become alternate prototypes of the current person;
- new-speaker candidates can confirm across a VAD boundary and use a practical similarity gate.
"""
from pathlib import Path
import sys


def rep(path: Path, old: str, new: str, label: str, count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    found = text.count(old)
    if found != count:
        raise RuntimeError(f"{label}: expected {count} anchor(s), found {found} in {path}")
    path.write_text(text.replace(old, new, count), encoding="utf-8")
    print("patched:", label)


def req(path: Path, needle: str, label: str) -> None:
    if needle not in path.read_text(encoding="utf-8"):
        raise RuntimeError(f"{label}: missing {needle!r}")


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: patch_v23332_live_identity_collapse_fix.py <morphe-root> [repo-root]")
    root = Path(sys.argv[1]).resolve()
    live = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/LiveSpeakerOnline.java"
    controller = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SpanishStudyController.java"
    if not live.is_file() or not controller.is_file():
        raise RuntimeError("v2.33.32 requires v2.33.31 source to be applied first")

    rep(live,
        '''    private static final int WINDOW_SAMPLES = 32_000;          // 2.0 s\n    private static final int HOP_SAMPLES = 12_000;             // 0.75 s\n    private static final int RING_SAMPLES = 48_000;            // 3.0 s\n''',
        '''    private static final int WINDOW_SAMPLES = 24_000;          // 1.5 s\n    private static final int HOP_SAMPLES = 9_600;              // 0.60 s\n    private static final int RING_SAMPLES = 40_000;            // 2.5 s\n''',
        "shorten live embedding window and hop")

    rep(live,
        '''    private static final int QUIET_TO_BOUNDARY_MS = 240;\n    private static final int LIVE_HOLD_MS = 2_800;\n''',
        '''    private static final int QUIET_TO_BOUNDARY_MS = 180;\n    private static final int LIVE_HOLD_MS = 1_800;\n''',
        "tighten boundary and visible hold")

    rep(live,
        '''    private static final float STRONG_MATCH = 0.60f;\n    private static final float NORMAL_MATCH = 0.53f;\n    private static final float CONTINUITY_FLOOR = 0.36f;\n    private static final float NEW_CANDIDATE_MATCH = 0.66f;\n    private static final float STRONG_SWITCH = 0.68f;\n    private static final float STRONG_SWITCH_MARGIN = 0.075f;\n''',
        '''    private static final float STRONG_MATCH = 0.60f;\n    private static final float NORMAL_MATCH = 0.53f;\n    private static final float CONTINUITY_FLOOR = 0.47f;\n    private static final float NEW_CANDIDATE_MATCH = 0.50f;\n    private static final float STRONG_SWITCH = 0.64f;\n    private static final float STRONG_SWITCH_MARGIN = 0.055f;\n    private static final float COMPETING_KNOWN_MARGIN = 0.040f;\n    private static final long CANDIDATE_MAX_GAP_MS = 1_200L;\n''',
        "replace over-sticky identity thresholds")

    rep(live,
        '''    private static int candidateRejects;\n    private static Candidate candidate;\n''',
        '''    private static int candidateRejects;\n    private static int lowSimilarityBreakouts;\n    private static int profilePoisonBlocks;\n    private static Candidate candidate;\n''',
        "add collapse diagnostics")

    rep(live,
        '''            candidateRejects = 0;\n            candidate = null;\n''',
        '''            candidateRejects = 0;\n            lowSimilarityBreakouts = 0;\n            profilePoisonBlocks = 0;\n            candidate = null;\n''',
        "reset collapse diagnostics")

    old_continuity = '''        // Human-identity inertia: a vocal-style change inside the same uninterrupted speech run\n        // stays with the person unless another already-known speaker matches very strongly.\n        if (!job.firstInSpeechRun && lastCommittedSpeaker >= 0 && lastCommittedSpeaker < profileCount) {\n            Profile last = PROFILES[lastCommittedSpeaker];\n            float lastScore = last.score(embedding);\n            if (best < 0 || best == lastCommittedSpeaker || bestScore < STRONG_SWITCH) {\n                continuityHolds++;\n                if (lastScore < NORMAL_MATCH && lastScore >= CONTINUITY_FLOOR) {\n                    if (last.addPrototype(embedding)) impressionPrototypeAdds++;\n                    else last.update(embedding, 0.035f);\n                } else if (lastScore >= CONTINUITY_FLOOR) {\n                    last.update(embedding, 0.055f);\n                }\n                cancelCandidateLocked();\n                commitLocked(job, lastCommittedSpeaker, "continuous-run-identity-hold",\n                        lastScore, Math.max(0f, lastScore - second));\n                return;\n            }\n        }\n'''
    new_continuity = '''        // v2.33.32: continuity is a tie-breaker, never an unconditional assignment. v31\n        // committed the current person even at cosine 0.08-0.15 and then learned those windows as\n        // that person's alternate voice. Dense YouTube audio rarely produced a VAD boundary, so\n        // this collapsed an entire video into A. Require real evidence for the current person.\n        if (!job.firstInSpeechRun && lastCommittedSpeaker >= 0 && lastCommittedSpeaker < profileCount) {\n            Profile last = PROFILES[lastCommittedSpeaker];\n            float lastScore = last.score(embedding);\n            boolean competingKnown = best >= 0 && best != lastCommittedSpeaker\n                    && bestScore >= NORMAL_MATCH\n                    && bestScore - lastScore >= COMPETING_KNOWN_MARGIN;\n            if (lastScore >= CONTINUITY_FLOOR && !competingKnown) {\n                continuityHolds++;\n                // Do not create style prototypes from merely tolerated continuity. Only a\n                // reasonably matching window may gently update the existing profile.\n                if (lastScore >= NORMAL_MATCH) last.update(embedding, 0.025f);\n                else profilePoisonBlocks++;\n                cancelCandidateLocked();\n                commitLocked(job, lastCommittedSpeaker, "bounded-continuity-hold",\n                        lastScore, Math.max(0f, lastScore - second));\n                return;\n            }\n            if (lastScore < CONTINUITY_FLOOR) lowSimilarityBreakouts++;\n        }\n'''
    rep(live, old_continuity, new_continuity, "bound continuous identity inertia")

    old_recent = '''        // Weak continuity shortly after the same person's prior segment can teach a second vocal\n        // style (e.g. impression/register) to that person's profile.\n        if (lastCommittedSpeaker >= 0 && lastCommittedSpeaker < profileCount\n                && job.startVideoMs - lastCommittedEndVideoMs <= 1600L) {\n            Profile last = PROFILES[lastCommittedSpeaker];\n            float lastScore = last.score(embedding);\n            if (lastScore >= CONTINUITY_FLOOR && bestScore < STRONG_SWITCH) {\n                continuityHolds++;\n                if (lastScore < NORMAL_MATCH && last.addPrototype(embedding)) impressionPrototypeAdds++;\n                else last.update(embedding, 0.035f);\n                cancelCandidateLocked();\n                commitLocked(job, lastCommittedSpeaker, "recent-speaker-style-hold",\n                        lastScore, Math.max(0f, lastScore - second));\n                return;\n            }\n        }\n'''
    new_recent = '''        // Short-gap continuity is deliberately conservative in v2.33.32. Correctly separating\n        // actual humans is more important than keeping impressions attached to the same person.\n        if (lastCommittedSpeaker >= 0 && lastCommittedSpeaker < profileCount\n                && job.startVideoMs - lastCommittedEndVideoMs <= 900L) {\n            Profile last = PROFILES[lastCommittedSpeaker];\n            float lastScore = last.score(embedding);\n            if (lastScore >= NORMAL_MATCH && (best == lastCommittedSpeaker || bestScore < STRONG_SWITCH)) {\n                continuityHolds++;\n                last.update(embedding, 0.025f);\n                cancelCandidateLocked();\n                commitLocked(job, lastCommittedSpeaker, "recent-known-hold",\n                        lastScore, Math.max(0f, lastScore - second));\n                return;\n            }\n        }\n'''
    rep(live, old_recent, new_recent, "make short-gap style hold conservative")

    rep(live,
        '''        if (candidate == null || candidate.videoEpoch != job.videoEpoch\n                || candidate.speechRunSerial != job.speechRunSerial\n                || cosine(candidate.embedding, embedding) < NEW_CANDIDATE_MATCH) {\n''',
        '''        if (candidate == null || candidate.videoEpoch != job.videoEpoch\n                || job.startVideoMs > candidate.endVideoMs + CANDIDATE_MAX_GAP_MS\n                || cosine(candidate.embedding, embedding) < NEW_CANDIDATE_MATCH) {\n''',
        "allow new-speaker confirmation across VAD boundaries")

    rep(live,
        '''            return "speakerLiveMode=eres2net-short-window-online-human-identity-v23331\\n"\n                    + "speakerLiveWindowMs=2000\\n"\n                    + "speakerLiveHopMs=750\\n"\n                    + "speakerLiveLatestWins=true\\n"\n                    + "speakerLiveIdentityPolicy=multi-prototype+continuous-run-inertia+two-window-new-person-confirm\\n"\n                    + "speakerLiveImpressionPolicy=continuous-style-change-stays-human-and-may-add-prototype\\n"\n''',
        '''            return "speakerLiveMode=eres2net-short-window-online-human-identity-v23332\\n"\n                    + "speakerLiveWindowMs=1500\\n"\n                    + "speakerLiveHopMs=600\\n"\n                    + "speakerLiveLatestWins=true\\n"\n                    + "speakerLiveIdentityPolicy=bounded-inertia+low-sim-breakout+two-window-new-person-confirm\\n"\n                    + "speakerLiveImpressionPolicy=conservative-until-real-human-separation-is-stable\\n"\n''',
        "update live architecture diagnostics")

    rep(live,
        '''                    + "speakerLiveCandidateRejects=" + candidateRejects + "\\n"\n                    + "speakerLiveLastBestSimilarityPermille=" + permille(lastBestSimilarity) + "\\n"\n''',
        '''                    + "speakerLiveCandidateRejects=" + candidateRejects + "\\n"\n                    + "speakerLiveLowSimilarityBreakouts=" + lowSimilarityBreakouts + "\\n"\n                    + "speakerLiveProfilePoisonBlocks=" + profilePoisonBlocks + "\\n"\n                    + "speakerLiveLastBestSimilarityPermille=" + permille(lastBestSimilarity) + "\\n"\n''',
        "publish collapse counters")

    rep(controller,
        'report.append("Spanish Dub Study v2.33.31 near-live ERes2Net human-speaker diagnostics\\n");',
        'report.append("Spanish Dub Study v2.33.32 near-live ERes2Net speaker-separation diagnostics\\n");',
        "update diagnostics header")
    rep(controller,
        '        report.append("speakerLiveGoal=human-identity-not-voice-style;multi-prototype-impression-tolerance\\n");\n',
        '        report.append("speakerLiveGoal=human-identity-first;bounded-inertia-prevents-single-speaker-collapse\\n");\n',
        "update live goal marker")

    req(live, 'speakerLiveMode=eres2net-short-window-online-human-identity-v23332', 'v32 runtime marker')
    req(live, 'speakerLiveLowSimilarityBreakouts=', 'collapse diagnostics')
    req(live, 'bounded-continuity-hold', 'bounded continuity decision')
    req(live, 'NEW_CANDIDATE_MATCH = 0.50f', 'candidate threshold')
    req(controller, 'v2.33.32 near-live ERes2Net', 'controller version')
    print("v2.33.32 live identity collapse fix complete")
    print("PRESERVED: exact accepted PCM, videoMs master projection, ThreadLocal verifier-safe write bridge")
    print("FIXED: v31 could commit A at arbitrarily low similarity and poison A with weak prototypes")
    print("PRIORITY: reliable real-human A/B/C separation before aggressive impression tolerance")


if __name__ == "__main__":
    main()
