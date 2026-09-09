#!/usr/bin/env python3
"""v2.33.33: stabilize near-live ERes2Net human identities without touching audio/clock.

Applies after v2.33.32. The v32 runtime proved that the 1.5 s / 0.6 s ERes2Net path is
fast enough (~0.1-0.2 s inference) but its two-window promotion rule can turn short-window
embedding variance into A/B/C/D/E/F/G/H. v33 changes only identity management:

- the very first person is bootstrapped from repeated coherent evidence instead of one window;
- unknown windows remain an uncommitted candidate cluster, not a permanent person;
- new people require >=3 coherent observations plus temporal/recurrent support;
- candidate centroids are re-checked against established people before promotion;
- moderately similar candidates stay unknown instead of forcing either a false merge or split;
- established people gain bounded, high-confidence extra prototypes;
- unresolved candidate spans deliberately display unknown rather than extending the prior label;
- diagnostics expose candidate support/cohesion/rescues and profile evidence.

PRESERVED: exact accepted post-write PCM, ThreadLocal verifier-safe handoff, videoMs master clock,
AudioVideoSyncProbe projection, native ERes2Net extraction, latest-wins worker, translation/TTS.
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
        raise SystemExit("usage: patch_v23333_identity_stabilization.py <morphe-root> [repo-root]")
    root = Path(sys.argv[1]).resolve()
    live = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/LiveSpeakerOnline.java"
    controller = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SpanishStudyController.java"
    if not live.is_file() or not controller.is_file():
        raise RuntimeError("v2.33.33 requires v2.33.32 source to be applied first")

    rep(live,
        '''    private static final float COMPETING_KNOWN_MARGIN = 0.040f;\n    private static final long CANDIDATE_MAX_GAP_MS = 1_200L;\n''',
        '''    private static final float COMPETING_KNOWN_MARGIN = 0.040f;\n    private static final long CANDIDATE_MAX_GAP_MS = 1_200L;\n    // v2.33.33 candidate-cluster policy. A low similarity is uncertainty, not a new human.\n    private static final float CANDIDATE_RESCUE_MATCH = 0.50f;\n    private static final float CANDIDATE_AMBIGUOUS_KNOWN = 0.40f;\n    private static final float CANDIDATE_MIN_AVG_COHESION = 0.55f;\n    private static final float CANDIDATE_HIGH_COHESION = 0.62f;\n    private static final float BOOTSTRAP_TWO_WINDOW_COHESION = 0.65f;\n    private static final float BOOTSTRAP_THREE_WINDOW_COHESION = 0.54f;\n    private static final long CANDIDATE_MIN_SPAN_MS = 1_200L;\n    private static final int NEW_PROFILE_MIN_SUPPORT = 3;\n    private static final int NEW_PROFILE_CONTINUOUS_SUPPORT = 4;\n''',
        "add conservative candidate cluster thresholds")

    rep(live,
        '''    private static int candidateRejects;\n    private static int lowSimilarityBreakouts;\n    private static int profilePoisonBlocks;\n    private static Candidate candidate;\n''',
        '''    private static int candidateRejects;\n    private static int lowSimilarityBreakouts;\n    private static int profilePoisonBlocks;\n    private static int unresolvedWindows;\n    private static int candidateRescues;\n    private static int bootstrapConfirms;\n    private static int stablePrototypeAdds;\n    private static int ambiguousKnownHolds;\n    private static int lastCandidateSupport;\n    private static int lastCandidateDistinctRuns;\n    private static float lastCandidateCohesion;\n    private static float lastCandidateKnownBest;\n    private static Candidate candidate;\n''',
        "add identity stabilization diagnostics")

    rep(live,
        '''            candidateRejects = 0;\n            lowSimilarityBreakouts = 0;\n            profilePoisonBlocks = 0;\n            candidate = null;\n''',
        '''            candidateRejects = 0;\n            lowSimilarityBreakouts = 0;\n            profilePoisonBlocks = 0;\n            unresolvedWindows = 0;\n            candidateRescues = 0;\n            bootstrapConfirms = 0;\n            stablePrototypeAdds = 0;\n            ambiguousKnownHolds = 0;\n            lastCandidateSupport = 0;\n            lastCandidateDistinctRuns = 0;\n            lastCandidateCohesion = 0f;\n            lastCandidateKnownBest = -1f;\n            candidate = null;\n''',
        "reset identity stabilization diagnostics")

    rep(live,
        '''        if (profileCount == 0) {\n            int id = createProfileLocked(embedding);\n            commitLocked(job, id, "seed-first-speaker", 1f, 1f);\n            return;\n        }\n''',
        '''        if (profileCount == 0) {\n            // v2.33.33: do not let one possibly mixed/noisy 1.5 s window define Speaker A.\n            // Two very coherent windows may bootstrap A quickly; otherwise require a third.\n            if (candidate == null || candidate.videoEpoch != job.videoEpoch\n                    || job.startVideoMs > candidate.endVideoMs + CANDIDATE_MAX_GAP_MS) {\n                startCandidateLocked(job, embedding, "bootstrap-candidate-start");\n                return;\n            }\n            float cohesion = cosine(candidate.embedding, embedding);\n            if (cohesion < NEW_CANDIDATE_MATCH) {\n                startCandidateLocked(job, embedding, "bootstrap-candidate-reset-low-cohesion");\n                return;\n            }\n            observeCandidateLocked(job, embedding, cohesion);\n            float avg = candidate.averageCohesion();\n            boolean ready = (candidate.count >= 2 && avg >= BOOTSTRAP_TWO_WINDOW_COHESION)\n                    || (candidate.count >= 3 && avg >= BOOTSTRAP_THREE_WINDOW_COHESION);\n            if (!ready) {\n                lastDecision = "bootstrap-candidate-repeat support=" + candidate.count\n                        + " cohesion=" + permille(avg);\n                return;\n            }\n            Candidate promoted = candidate;\n            int id = createProfileLocked(promoted.embedding);\n            PROFILES[id].supportCount = promoted.count;\n            if (promoted.count >= 3 && PROFILES[id].addPrototype(promoted.seedEmbedding)) {\n                stablePrototypeAdds++;\n            }\n            long retroStart = promoted.startVideoMs;\n            candidateConfirms++;\n            bootstrapConfirms++;\n            candidate = null;\n            Job retro = new Job(job.samples, retroStart, job.endVideoMs, job.videoEpoch,\n                    job.continuityEpoch, job.speechRunSerial, true, job.generation);\n            commitLocked(retro, id, "bootstrap-speaker-confirmed", avg, avg);\n            return;\n        }\n''',
        "bootstrap first identity from coherent evidence")

    rep(live,
        '''            cancelCandidateLocked();\n            PROFILES[best].update(embedding, 0.10f);\n            commitLocked(job, best, best == lastCommittedSpeaker ? "strong-stay" : "strong-known-switch",\n                    bestScore, margin);\n''',
        '''            cancelCandidateLocked();\n            Profile matched = PROFILES[best];\n            matched.supportCount++;\n            if (matched.supportCount >= 3 && bestScore >= STRONG_MATCH && bestScore < 0.72f\n                    && matched.prototypeCount < MAX_PROTOTYPES && matched.addPrototype(embedding)) {\n                stablePrototypeAdds++;\n            } else {\n                matched.update(embedding, 0.08f);\n            }\n            commitLocked(job, best, best == lastCommittedSpeaker ? "strong-stay" : "strong-known-switch",\n                    bestScore, margin);\n''',
        "learn bounded prototypes only from strong known matches")

    rep(live,
        '''                if (lastScore >= NORMAL_MATCH) last.update(embedding, 0.025f);\n                else profilePoisonBlocks++;\n''',
        '''                if (lastScore >= NORMAL_MATCH) {\n                    last.supportCount++;\n                    last.update(embedding, 0.020f);\n                } else profilePoisonBlocks++;\n''',
        "count only evidenced continuity support")

    rep(live,
        '''            cancelCandidateLocked();\n            PROFILES[best].update(embedding, 0.07f);\n            commitLocked(job, best, "normal-known-match", bestScore, margin);\n''',
        '''            cancelCandidateLocked();\n            PROFILES[best].supportCount++;\n            PROFILES[best].update(embedding, 0.045f);\n            commitLocked(job, best, "normal-known-match", bestScore, margin);\n''',
        "make moderate known-profile learning conservative")

    rep(live,
        '''                continuityHolds++;\n                last.update(embedding, 0.025f);\n                cancelCandidateLocked();\n''',
        '''                continuityHolds++;\n                last.supportCount++;\n                last.update(embedding, 0.020f);\n                cancelCandidateLocked();\n''',
        "count recent known support")

    old_candidate = '''        // Unknown identity: require repeated mutually-similar evidence before creating a new human.\n        if (candidate == null || candidate.videoEpoch != job.videoEpoch\n                || job.startVideoMs > candidate.endVideoMs + CANDIDATE_MAX_GAP_MS\n                || cosine(candidate.embedding, embedding) < NEW_CANDIDATE_MATCH) {\n            if (candidate != null) candidateRejects++;\n            candidate = new Candidate(embedding.clone(), job.videoEpoch, job.speechRunSerial,\n                    job.startVideoMs, job.endVideoMs);\n            candidateStarts++;\n            lastDecision = "new-speaker-candidate";\n            return;\n        }\n\n        candidate.count++;\n        candidate.endVideoMs = job.endVideoMs;\n        blendNormalized(candidate.embedding, embedding, 0.35f);\n        if (candidate.count >= 2 && profileCount < MAX_PROFILES) {\n            int id = createProfileLocked(candidate.embedding);\n            long retroStart = candidate.startVideoMs;\n            candidateConfirms++;\n            candidate = null;\n            Job retro = new Job(job.samples, retroStart, job.endVideoMs, job.videoEpoch,\n                    job.continuityEpoch, job.speechRunSerial, true, job.generation);\n            commitLocked(retro, id, "new-speaker-confirmed", bestScore, margin);\n        } else {\n            lastDecision = "new-speaker-candidate-repeat";\n        }\n'''
    new_candidate = '''        // v2.33.33 unknown identity: accumulate a temporary coherent cluster. Low similarity\n        // means "unknown"; it does not create a permanent human after only two windows.\n        float candidateSimilarity = candidate == null ? -1f : cosine(candidate.embedding, embedding);\n        if (candidate == null || candidate.videoEpoch != job.videoEpoch\n                || job.startVideoMs > candidate.endVideoMs + CANDIDATE_MAX_GAP_MS\n                || candidateSimilarity < NEW_CANDIDATE_MATCH) {\n            startCandidateLocked(job, embedding, "unresolved-speaker-candidate-start");\n            return;\n        }\n\n        observeCandidateLocked(job, embedding, candidateSimilarity);\n        int candidateKnown = -1;\n        float candidateKnownBest = -1f;\n        for (int i = 0; i < profileCount; i++) {\n            Profile p = PROFILES[i];\n            if (p == null) continue;\n            float score = p.score(candidate.embedding);\n            if (score > candidateKnownBest) {\n                candidateKnownBest = score;\n                candidateKnown = i;\n            }\n        }\n        lastCandidateKnownBest = candidateKnownBest;\n        float avgCohesion = candidate.averageCohesion();\n        lastCandidateCohesion = avgCohesion;\n        lastCandidateSupport = candidate.count;\n        lastCandidateDistinctRuns = candidate.distinctSpeechRuns;\n\n        // Averaging several short windows often recovers the established human even when each\n        // individual phonetic window was weak. Rescue that cluster instead of minting C/D/E....\n        if (candidate.count >= NEW_PROFILE_MIN_SUPPORT && candidateKnown >= 0\n                && candidateKnownBest >= CANDIDATE_RESCUE_MATCH) {\n            Candidate rescued = candidate;\n            Profile p = PROFILES[candidateKnown];\n            p.supportCount += rescued.count;\n            if (candidateKnownBest >= NORMAL_MATCH && candidateKnownBest < 0.72f\n                    && p.prototypeCount < MAX_PROTOTYPES && p.addPrototype(rescued.embedding)) {\n                stablePrototypeAdds++;\n            } else {\n                p.update(rescued.embedding, 0.035f);\n            }\n            candidateRescues++;\n            candidate = null;\n            Job retro = new Job(job.samples, rescued.startVideoMs, job.endVideoMs, job.videoEpoch,\n                    job.continuityEpoch, job.speechRunSerial, true, job.generation);\n            commitLocked(retro, candidateKnown, "candidate-rescued-known", candidateKnownBest,\n                    Math.max(0f, candidateKnownBest - second));\n            return;\n        }\n\n        long candidateSpanMs = candidate.endVideoMs - candidate.startVideoMs;\n        boolean recurrentEnough = candidate.distinctSpeechRuns >= 2\n                || candidate.count >= NEW_PROFILE_CONTINUOUS_SUPPORT;\n        boolean coherentEnough = avgCohesion >= CANDIDATE_MIN_AVG_COHESION;\n        boolean clearlyNovel = candidateKnownBest < CANDIDATE_AMBIGUOUS_KNOWN;\n        boolean highCohesionOverride = candidate.count >= 5\n                && avgCohesion >= CANDIDATE_HIGH_COHESION\n                && candidateKnownBest < CANDIDATE_RESCUE_MATCH;\n        boolean readyNew = candidate.count >= NEW_PROFILE_MIN_SUPPORT\n                && candidateSpanMs >= CANDIDATE_MIN_SPAN_MS\n                && recurrentEnough && coherentEnough\n                && (clearlyNovel || highCohesionOverride);\n\n        if (readyNew && profileCount < MAX_PROFILES) {\n            Candidate promoted = candidate;\n            int id = createProfileLocked(promoted.embedding);\n            PROFILES[id].supportCount = promoted.count;\n            if (PROFILES[id].addPrototype(promoted.seedEmbedding)) stablePrototypeAdds++;\n            long retroStart = promoted.startVideoMs;\n            candidateConfirms++;\n            candidate = null;\n            Job retro = new Job(job.samples, retroStart, job.endVideoMs, job.videoEpoch,\n                    job.continuityEpoch, job.speechRunSerial, true, job.generation);\n            commitLocked(retro, id, "new-speaker-coherent-cluster", avgCohesion,\n                    Math.max(0f, CANDIDATE_RESCUE_MATCH - candidateKnownBest));\n            return;\n        }\n\n        if (candidateKnownBest >= CANDIDATE_AMBIGUOUS_KNOWN) ambiguousKnownHolds++;\n        lastDecision = "unresolved-speaker-candidate support=" + candidate.count\n                + " runs=" + candidate.distinctSpeechRuns\n                + " cohesion=" + permille(avgCohesion)\n                + " knownBest=" + permille(candidateKnownBest);\n'''
    rep(live, old_candidate, new_candidate, "replace two-window promotion with coherent candidate cluster")

    rep(live,
        '''    private static int createProfileLocked(float[] embedding) {\n''',
        '''    private static void startCandidateLocked(Job job, float[] embedding, String reason) {\n        if (candidate != null) candidateRejects++;\n        candidate = new Candidate(embedding.clone(), job.videoEpoch, job.speechRunSerial,\n                job.startVideoMs, job.endVideoMs);\n        candidateStarts++;\n        unresolvedWindows++;\n        lastCandidateSupport = 1;\n        lastCandidateDistinctRuns = 1;\n        lastCandidateCohesion = 0f;\n        lastCandidateKnownBest = -1f;\n        lastDecision = reason;\n    }\n\n    private static void observeCandidateLocked(Job job, float[] embedding, float cohesion) {\n        candidate.observe(job, embedding, cohesion);\n        unresolvedWindows++;\n        lastCandidateSupport = candidate.count;\n        lastCandidateDistinctRuns = candidate.distinctSpeechRuns;\n        lastCandidateCohesion = candidate.averageCohesion();\n    }\n\n    private static int createProfileLocked(float[] embedding) {\n''',
        "add candidate helper methods")

    rep(live,
        '''        p.addPrototype(embedding);\n        PROFILES[id] = p;\n''',
        '''        p.addPrototype(embedding);\n        p.supportCount = 1;\n        PROFILES[id] = p;\n''',
        "seed profile evidence count")

    rep(live,
        '''    public static String labelAtVideoMs(long videoMs) {\n        synchronized (LOCK) {\n            if (videoMs < 0L) return "";\n            for (int i = timelineCount - 1; i >= 0; i--) {\n''',
        '''    public static String labelAtVideoMs(long videoMs) {\n        synchronized (LOCK) {\n            if (videoMs < 0L) return "";\n            // During an unresolved candidate span, showing the previous speaker would turn\n            // uncertainty into a false label. Prefer ? until the cluster resolves; promotion\n            // retroactively fills the candidate interval in the video-time timeline.\n            if (candidate != null && videoMs >= candidate.startVideoMs\n                    && videoMs <= candidate.endVideoMs + 400L) return "";\n            for (int i = timelineCount - 1; i >= 0; i--) {\n''',
        "show unknown during unresolved candidate spans")

    rep(live,
        '''                p.append(labelFor(i)).append(':').append(profile == null ? 0 : profile.prototypeCount);\n''',
        '''                if (profile == null) p.append(labelFor(i)).append(":0/0");\n                else p.append(labelFor(i)).append(':').append(profile.prototypeCount)\n                        .append('/').append(profile.supportCount);\n''',
        "publish prototypes and support per profile")

    rep(live,
        '''            return "speakerLiveMode=eres2net-short-window-online-human-identity-v23332\\n"\n                    + "speakerLiveWindowMs=1500\\n"\n                    + "speakerLiveHopMs=600\\n"\n                    + "speakerLiveLatestWins=true\\n"\n                    + "speakerLiveIdentityPolicy=bounded-inertia+low-sim-breakout+two-window-new-person-confirm\\n"\n                    + "speakerLiveImpressionPolicy=conservative-until-real-human-separation-is-stable\\n"\n''',
        '''            return "speakerLiveMode=eres2net-short-window-online-human-identity-v23333\\n"\n                    + "speakerLiveWindowMs=1500\\n"\n                    + "speakerLiveHopMs=600\\n"\n                    + "speakerLiveLatestWins=true\\n"\n                    + "speakerLiveIdentityPolicy=coherent-candidate-cluster+known-profile-rescue+bounded-inertia\\n"\n                    + "speakerLiveUnknownPolicy=uncommitted-candidate-until-human-evidence-is-stable\\n"\n                    + "speakerLiveImpressionPolicy=high-confidence-multi-prototype-only\\n"\n                    + "speakerLiveProfileFormat=label:prototypes/support\\n"\n''',
        "update v33 identity architecture markers")

    rep(live,
        '''                    + "speakerLiveCandidateRejects=" + candidateRejects + "\\n"\n                    + "speakerLiveLowSimilarityBreakouts=" + lowSimilarityBreakouts + "\\n"\n                    + "speakerLiveProfilePoisonBlocks=" + profilePoisonBlocks + "\\n"\n                    + "speakerLiveLastBestSimilarityPermille=" + permille(lastBestSimilarity) + "\\n"\n''',
        '''                    + "speakerLiveCandidateRejects=" + candidateRejects + "\\n"\n                    + "speakerLiveLowSimilarityBreakouts=" + lowSimilarityBreakouts + "\\n"\n                    + "speakerLiveProfilePoisonBlocks=" + profilePoisonBlocks + "\\n"\n                    + "speakerLiveUnresolvedWindows=" + unresolvedWindows + "\\n"\n                    + "speakerLiveCandidateRescues=" + candidateRescues + "\\n"\n                    + "speakerLiveBootstrapConfirms=" + bootstrapConfirms + "\\n"\n                    + "speakerLiveStablePrototypeAdds=" + stablePrototypeAdds + "\\n"\n                    + "speakerLiveAmbiguousKnownHolds=" + ambiguousKnownHolds + "\\n"\n                    + "speakerLiveCandidateActive=" + (candidate != null) + "\\n"\n                    + "speakerLiveCandidateSupport=" + (candidate != null ? candidate.count : lastCandidateSupport) + "\\n"\n                    + "speakerLiveCandidateDistinctRuns=" + (candidate != null ? candidate.distinctSpeechRuns : lastCandidateDistinctRuns) + "\\n"\n                    + "speakerLiveCandidateCohesionPermille=" + permille(candidate != null ? candidate.averageCohesion() : lastCandidateCohesion) + "\\n"\n                    + "speakerLiveCandidateKnownBestPermille=" + permille(lastCandidateKnownBest) + "\\n"\n                    + "speakerLiveLastBestSimilarityPermille=" + permille(lastBestSimilarity) + "\\n"\n''',
        "publish candidate stabilization counters")

    old_candidate_class = '''    private static final class Candidate {\n        final float[] embedding;\n        final long videoEpoch;\n        final long speechRunSerial;\n        final long startVideoMs;\n        long endVideoMs;\n        int count = 1;\n\n        Candidate(float[] embedding, long videoEpoch, long speechRunSerial,\n                  long startVideoMs, long endVideoMs) {\n            this.embedding = embedding;\n            this.videoEpoch = videoEpoch;\n            this.speechRunSerial = speechRunSerial;\n            this.startVideoMs = startVideoMs;\n            this.endVideoMs = endVideoMs;\n        }\n    }\n'''
    new_candidate_class = '''    private static final class Candidate {\n        final float[] embedding;\n        final float[] seedEmbedding;\n        final long videoEpoch;\n        final long speechRunSerial;\n        final long startVideoMs;\n        long endVideoMs;\n        long lastSpeechRunSerial;\n        int distinctSpeechRuns = 1;\n        int count = 1;\n        float cohesionSum;\n        float minCohesion = 1f;\n\n        Candidate(float[] embedding, long videoEpoch, long speechRunSerial,\n                  long startVideoMs, long endVideoMs) {\n            this.embedding = embedding;\n            this.seedEmbedding = embedding.clone();\n            this.videoEpoch = videoEpoch;\n            this.speechRunSerial = speechRunSerial;\n            this.startVideoMs = startVideoMs;\n            this.endVideoMs = endVideoMs;\n            this.lastSpeechRunSerial = speechRunSerial;\n        }\n\n        void observe(Job job, float[] next, float cohesion) {\n            count++;\n            endVideoMs = job.endVideoMs;\n            if (job.speechRunSerial != lastSpeechRunSerial) {\n                distinctSpeechRuns++;\n                lastSpeechRunSerial = job.speechRunSerial;\n            }\n            cohesionSum += cohesion;\n            if (cohesion < minCohesion) minCohesion = cohesion;\n            blendNormalized(embedding, next, 1f / Math.min(5f, (float) count));\n        }\n\n        float averageCohesion() {\n            return count <= 1 ? 0f : cohesionSum / (count - 1);\n        }\n    }\n'''
    rep(live, old_candidate_class, new_candidate_class, "track candidate cohesion and recurring speech runs")

    rep(live,
        '''    private static final class Profile {\n        final float[][] prototypes;\n        int prototypeCount;\n''',
        '''    private static final class Profile {\n        final float[][] prototypes;\n        int prototypeCount;\n        int supportCount;\n''',
        "track profile evidence support")

    rep(controller,
        'report.append("Spanish Dub Study v2.33.32 near-live ERes2Net speaker-separation diagnostics\\n");',
        'report.append("Spanish Dub Study v2.33.33 near-live ERes2Net identity-stabilization diagnostics\\n");',
        "update diagnostics header")
    rep(controller,
        '        report.append("speakerLiveGoal=human-identity-first;bounded-inertia-prevents-single-speaker-collapse\\n");\n',
        '        report.append("speakerLiveGoal=human-identity-first;unknown-before-false-split;coherent-candidate-promotion\\n");\n',
        "update live goal marker")

    req(live, 'speakerLiveMode=eres2net-short-window-online-human-identity-v23333', 'v33 runtime marker')
    req(live, 'coherent-candidate-cluster+known-profile-rescue+bounded-inertia', 'v33 identity policy')
    req(live, 'speakerLiveCandidateRescues=', 'candidate rescue diagnostics')
    req(live, 'speakerLiveCandidateCohesionPermille=', 'candidate cohesion diagnostics')
    req(live, 'bootstrap-speaker-confirmed', 'bootstrap evidence gate')
    req(live, 'new-speaker-coherent-cluster', 'coherent new-person gate')
    req(live, 'candidate-rescued-known', 'known profile rescue')
    req(live, 'uncommitted-candidate-until-human-evidence-is-stable', 'unknown policy')
    req(controller, 'v2.33.33 near-live ERes2Net identity-stabilization', 'controller version')
    print("v2.33.33 identity stabilization complete")
    print("PRESERVED: v32 live ERes2Net latency path, exact accepted PCM, videoMs master projection")
    print("CHANGED: permanent speakers now require coherent evidence; uncertain windows stay unknown")
    print("EXPECTED: profile count should stop exploding A->H during two-person conversation")


if __name__ == "__main__":
    main()
