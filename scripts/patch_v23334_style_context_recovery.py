#!/usr/bin/env python3
"""v2.33.34: distinguish temporary voice style from a new human and recover null OpenRouter batches.

Applies after v2.33.33. The accepted-PCM/video-master clock, AudioTrack hook, ERes2Net model,
1.5 s window, 0.6 s hop, and latest-wins worker are intentionally untouched.
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
        raise SystemExit("usage: patch_v23334_style_context_recovery.py <morphe-root> [repo-root]")
    root = Path(sys.argv[1]).resolve()
    live = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/LiveSpeakerOnline.java"
    controller = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SpanishStudyController.java"
    translator = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation/TranscriptTranslator.java"
    for p in (live, controller, translator):
        if not p.is_file():
            raise RuntimeError(f"missing v2.33.33 source: {p}")

    # ------------------------------------------------------------------
    # Human identity vs temporary voice style.
    # ------------------------------------------------------------------
    rep(live,
        '''    private static final int NEW_PROFILE_MIN_SUPPORT = 3;\n    private static final int NEW_PROFILE_CONTINUOUS_SUPPORT = 4;\n''',
        '''    private static final int NEW_PROFILE_MIN_SUPPORT = 3;\n    // v2.33.34: one short uninterrupted voice-style run is not evidence of another human.\n    private static final int NEW_PROFILE_LONG_RUN_SUPPORT = 12;\n    private static final long NEW_PROFILE_LONG_RUN_MS = 7_000L;\n    private static final float NEW_PROFILE_LONG_RUN_COHESION = 0.64f;\n    private static final float NEW_PROFILE_LONG_RUN_MAX_KNOWN = 0.34f;\n    private static final long STYLE_BRIDGE_MAX_MS = 4_500L;\n    private static final long STYLE_PENDING_TTL_MS = 120_000L;\n    private static final int STYLE_PENDING_CONFIRMATIONS = 3;\n    private static final float STYLE_PENDING_MATCH = 0.60f;\n    private static final float STYLE_MIN_COHESION = 0.54f;\n''',
        "replace eager continuous-run promotion gate")

    rep(live,
        '''    private static Candidate candidate;\n    private static float lastBestSimilarity;\n''',
        '''    private static Candidate candidate;\n    private static final float[][] STYLE_PENDING = new float[MAX_PROFILES][];\n    private static final int[] STYLE_PENDING_SUPPORT = new int[MAX_PROFILES];\n    private static final long[] STYLE_PENDING_END_MS = new long[MAX_PROFILES];\n    private static long lastCommittedSpeechRunSerial = -1L;\n    private static int styleExcursionsStarted;\n    private static int styleBridgeBacks;\n    private static int stylePendingStarts;\n    private static int stylePendingMatches;\n    private static int stylePrototypeConfirms;\n    private static int newProfileBoundaryPromotions;\n    private static int newProfileLongRunPromotions;\n    private static int lastCandidateParent = -1;\n    private static float lastBestSimilarity;\n''',
        "add style hypothesis state")

    rep(live,
        '''            candidate = null;\n            lastBestSimilarity = 0f;\n''',
        '''            candidate = null;\n            clearStylePendingLocked();\n            lastCommittedSpeechRunSerial = -1L;\n            styleExcursionsStarted = 0;\n            styleBridgeBacks = 0;\n            stylePendingStarts = 0;\n            stylePendingMatches = 0;\n            stylePrototypeConfirms = 0;\n            newProfileBoundaryPromotions = 0;\n            newProfileLongRunPromotions = 0;\n            lastCandidateParent = -1;\n            lastBestSimilarity = 0f;\n''',
        "reset style state on new video")

    rep(live,
        '''        candidate = null;\n        lastCommittedEndVideoMs = -1L;\n        lastDecision = "continuity-reset-profiles-kept";\n''',
        '''        candidate = null;\n        clearStylePendingLocked();\n        lastCommittedSpeechRunSerial = -1L;\n        lastCommittedEndVideoMs = -1L;\n        lastDecision = "continuity-reset-profiles-kept";\n''',
        "invalidate temporal style evidence on seek")

    # Resolve a same-run excursion if the embedding returns to its parent human.
    rep(live,
        '''            cancelCandidateLocked();\n            Profile matched = PROFILES[best];\n''',
        '''            resolveStyleCandidateOnKnownReturnLocked(best, job);\n            cancelCandidateLocked();\n            Profile matched = PROFILES[best];\n''',
        "resolve style bridge before strong known assignment")

    rep(live,
        '''            cancelCandidateLocked();\n            PROFILES[best].supportCount++;\n            PROFILES[best].update(embedding, 0.045f);\n''',
        '''            resolveStyleCandidateOnKnownReturnLocked(best, job);\n            cancelCandidateLocked();\n            PROFILES[best].supportCount++;\n            PROFILES[best].update(embedding, 0.045f);\n''',
        "resolve style bridge before normal known assignment")

    rep(live,
        '''                cancelCandidateLocked();\n                commitLocked(job, lastCommittedSpeaker, "bounded-continuity-hold",\n''',
        '''                resolveStyleCandidateOnKnownReturnLocked(lastCommittedSpeaker, job);\n                cancelCandidateLocked();\n                commitLocked(job, lastCommittedSpeaker, "bounded-continuity-hold",\n''',
        "resolve style bridge before bounded continuity")

    rep(live,
        '''                cancelCandidateLocked();\n                commitLocked(job, lastCommittedSpeaker, "recent-known-hold",\n''',
        '''                resolveStyleCandidateOnKnownReturnLocked(lastCommittedSpeaker, job);\n                cancelCandidateLocked();\n                commitLocked(job, lastCommittedSpeaker, "recent-known-hold",\n''',
        "resolve style bridge before recent known hold")

    # A new candidate is parented to the current human only inside the same VAD speech run.
    rep(live,
        '''        candidate = new Candidate(embedding.clone(), job.videoEpoch, job.speechRunSerial,\n                job.startVideoMs, job.endVideoMs);\n        candidateStarts++;\n        unresolvedWindows++;\n''',
        '''        int parent = -1;\n        if (!job.firstInSpeechRun && lastCommittedSpeaker >= 0 && lastCommittedSpeaker < profileCount\n                && job.speechRunSerial == lastCommittedSpeechRunSerial\n                && lastCommittedEndVideoMs >= 0L\n                && job.startVideoMs <= lastCommittedEndVideoMs + 900L) {\n            parent = lastCommittedSpeaker;\n            styleExcursionsStarted++;\n        }\n        candidate = new Candidate(embedding.clone(), job.videoEpoch, job.speechRunSerial,\n                job.startVideoMs, job.endVideoMs, parent);\n        candidateStarts++;\n        unresolvedWindows++;\n        lastCandidateParent = parent;\n''',
        "anchor same-run candidate to current human")

    # New permanent people normally require evidence across speech runs. A long coherent monologue
    # remains an escape hatch so a real speaker change without a VAD gap is not unknown forever.
    rep(live,
        '''        boolean recurrentEnough = candidate.distinctSpeechRuns >= 2\n                || candidate.count >= NEW_PROFILE_CONTINUOUS_SUPPORT;\n        boolean coherentEnough = avgCohesion >= CANDIDATE_MIN_AVG_COHESION;\n        boolean clearlyNovel = candidateKnownBest < CANDIDATE_AMBIGUOUS_KNOWN;\n        boolean highCohesionOverride = candidate.count >= 5\n                && avgCohesion >= CANDIDATE_HIGH_COHESION\n                && candidateKnownBest < CANDIDATE_RESCUE_MATCH;\n        boolean readyNew = candidate.count >= NEW_PROFILE_MIN_SUPPORT\n                && candidateSpanMs >= CANDIDATE_MIN_SPAN_MS\n                && recurrentEnough && coherentEnough\n                && (clearlyNovel || highCohesionOverride);\n''',
        '''        int dynamicMinSupport = profileCount <= 1 ? NEW_PROFILE_MIN_SUPPORT\n                : (profileCount == 2 ? 4 : 5);\n        boolean boundaryEvidence = candidate.distinctSpeechRuns >= 2\n                && candidate.count >= dynamicMinSupport;\n        boolean exceptionalLongRun = candidate.parentSpeaker < 0\n                && candidate.distinctSpeechRuns == 1\n                && candidate.count >= NEW_PROFILE_LONG_RUN_SUPPORT\n                && candidateSpanMs >= NEW_PROFILE_LONG_RUN_MS\n                && avgCohesion >= NEW_PROFILE_LONG_RUN_COHESION\n                && candidateKnownBest < NEW_PROFILE_LONG_RUN_MAX_KNOWN;\n        boolean coherentEnough = avgCohesion >= CANDIDATE_MIN_AVG_COHESION;\n        boolean clearlyNovel = candidateKnownBest < CANDIDATE_AMBIGUOUS_KNOWN;\n        boolean highCohesionOverride = candidate.count >= 6\n                && avgCohesion >= CANDIDATE_HIGH_COHESION\n                && candidateKnownBest < CANDIDATE_RESCUE_MATCH;\n        boolean readyNew = candidate.count >= dynamicMinSupport\n                && candidateSpanMs >= CANDIDATE_MIN_SPAN_MS\n                && coherentEnough\n                && (boundaryEvidence || exceptionalLongRun)\n                && (clearlyNovel || highCohesionOverride);\n''',
        "require boundary evidence or exceptional long-run evidence")

    rep(live,
        '''            candidateConfirms++;\n            candidate = null;\n            Job retro = new Job(job.samples, retroStart, job.endVideoMs, job.videoEpoch,\n''',
        '''            candidateConfirms++;\n            if (promoted.distinctSpeechRuns >= 2) newProfileBoundaryPromotions++;\n            else newProfileLongRunPromotions++;\n            candidate = null;\n            Job retro = new Job(job.samples, retroStart, job.endVideoMs, job.videoEpoch,\n''',
        "classify permanent-human promotion evidence",
        count=1)

    # Helper block before profile creation.
    rep(live,
        '''    private static int createProfileLocked(float[] embedding) {\n''',
        '''    private static void clearStylePendingLocked() {\n        for (int i = 0; i < MAX_PROFILES; i++) {\n            STYLE_PENDING[i] = null;\n            STYLE_PENDING_SUPPORT[i] = 0;\n            STYLE_PENDING_END_MS[i] = -1L;\n        }\n    }\n\n    private static void resolveStyleCandidateOnKnownReturnLocked(int knownSpeaker, Job returnJob) {\n        Candidate c = candidate;\n        if (c == null || knownSpeaker < 0 || knownSpeaker >= profileCount) return;\n        if (c.parentSpeaker != knownSpeaker || c.distinctSpeechRuns != 1\n                || c.parentSpeechRunSerial != returnJob.speechRunSerial || c.count < 3) return;\n        long span = c.endVideoMs - c.startVideoMs;\n        if (span < 0L || span > STYLE_BRIDGE_MAX_MS || c.averageCohesion() < STYLE_MIN_COHESION) return;\n\n        // Same human -> coherent altered voice -> same human, all inside one VAD run. Label the\n        // excursion as that human, but quarantine its embedding until the pattern repeats.\n        appendTimelineLocked(c.startVideoMs, c.endVideoMs, knownSpeaker);\n        styleBridgeBacks++;\n        float[] pending = STYLE_PENDING[knownSpeaker];\n        long age = pending == null ? Long.MAX_VALUE\n                : Math.max(0L, c.startVideoMs - STYLE_PENDING_END_MS[knownSpeaker]);\n        if (pending != null && age <= STYLE_PENDING_TTL_MS\n                && cosine(pending, c.embedding) >= STYLE_PENDING_MATCH) {\n            blendNormalized(pending, c.embedding, 0.35f);\n            STYLE_PENDING_SUPPORT[knownSpeaker]++;\n            stylePendingMatches++;\n        } else {\n            STYLE_PENDING[knownSpeaker] = c.embedding.clone();\n            STYLE_PENDING_SUPPORT[knownSpeaker] = 1;\n            stylePendingStarts++;\n        }\n        STYLE_PENDING_END_MS[knownSpeaker] = c.endVideoMs;\n        if (STYLE_PENDING_SUPPORT[knownSpeaker] >= STYLE_PENDING_CONFIRMATIONS) {\n            Profile p = PROFILES[knownSpeaker];\n            if (p != null && p.prototypeCount < MAX_PROTOTYPES\n                    && p.addPrototype(STYLE_PENDING[knownSpeaker])) {\n                stablePrototypeAdds++;\n                stylePrototypeConfirms++;\n            }\n            STYLE_PENDING[knownSpeaker] = null;\n            STYLE_PENDING_SUPPORT[knownSpeaker] = 0;\n            STYLE_PENDING_END_MS[knownSpeaker] = -1L;\n        }\n    }\n\n    private static int createProfileLocked(float[] embedding) {\n''',
        "add quarantined style bridge resolver")

    # Remember the VAD run that produced the current human assignment.
    rep(live,
        '''        lastCommittedSpeaker = speaker;\n        lastCommittedEndVideoMs = job.endVideoMs;\n''',
        '''        lastCommittedSpeaker = speaker;\n        lastCommittedSpeechRunSerial = job.speechRunSerial;\n        lastCommittedEndVideoMs = job.endVideoMs;\n''',
        "remember committed speech run")

    # Candidate carries a temporary parent only while the same speech run is plausible.
    rep(live,
        '''        final long speechRunSerial;\n        final long startVideoMs;\n        long endVideoMs;\n        long lastSpeechRunSerial;\n''',
        '''        final long speechRunSerial;\n        final long startVideoMs;\n        long endVideoMs;\n        long lastSpeechRunSerial;\n        int parentSpeaker;\n        final long parentSpeechRunSerial;\n''',
        "track candidate parent human")

    rep(live,
        '''        Candidate(float[] embedding, long videoEpoch, long speechRunSerial,\n                  long startVideoMs, long endVideoMs) {\n''',
        '''        Candidate(float[] embedding, long videoEpoch, long speechRunSerial,\n                  long startVideoMs, long endVideoMs, int parentSpeaker) {\n''',
        "extend candidate constructor")

    rep(live,
        '''            this.startVideoMs = startVideoMs;\n            this.endVideoMs = endVideoMs;\n            this.lastSpeechRunSerial = speechRunSerial;\n''',
        '''            this.startVideoMs = startVideoMs;\n            this.endVideoMs = endVideoMs;\n            this.lastSpeechRunSerial = speechRunSerial;\n            this.parentSpeaker = parentSpeaker;\n            this.parentSpeechRunSerial = speechRunSerial;\n''',
        "store candidate parent")

    rep(live,
        '''            if (job.speechRunSerial != lastSpeechRunSerial) {\n                distinctSpeechRuns++;\n                lastSpeechRunSerial = job.speechRunSerial;\n            }\n''',
        '''            if (job.speechRunSerial != lastSpeechRunSerial) {\n                distinctSpeechRuns++;\n                lastSpeechRunSerial = job.speechRunSerial;\n                parentSpeaker = -1;\n            }\n            if (parentSpeaker >= 0 && endVideoMs - startVideoMs > STYLE_BRIDGE_MAX_MS) {\n                parentSpeaker = -1;\n            }\n''',
        "release style parent after boundary or long excursion")

    # Bootstrap Candidate construction still needs the new constructor shape only through the
    # common startCandidateLocked helper, so there should be no remaining five-argument call.

    rep(live,
        '''            return "speakerLiveMode=eres2net-short-window-online-human-identity-v23333\\n"\n''',
        '''            return "speakerLiveMode=eres2net-short-window-online-human-identity-v23334\\n"\n''',
        "update live mode marker")
    rep(live,
        '''                    + "speakerLiveIdentityPolicy=coherent-candidate-cluster+known-profile-rescue+bounded-inertia\\n"\n                    + "speakerLiveUnknownPolicy=uncommitted-candidate-until-human-evidence-is-stable\\n"\n                    + "speakerLiveImpressionPolicy=high-confidence-multi-prototype-only\\n"\n''',
        '''                    + "speakerLiveIdentityPolicy=human-vs-style-hypothesis+vad-boundary-evidence+known-rescue\\n"\n                    + "speakerLiveUnknownPolicy=unknown-before-false-human-split\\n"\n                    + "speakerLiveImpressionPolicy=same-run-style-excursion+three-bridge-quarantine-before-prototype\\n"\n''',
        "publish v34 identity policy")

    rep(live,
        '''                    + "speakerLiveAmbiguousKnownHolds=" + ambiguousKnownHolds + "\\n"\n''',
        '''                    + "speakerLiveAmbiguousKnownHolds=" + ambiguousKnownHolds + "\\n"\n                    + "speakerLiveStyleExcursionsStarted=" + styleExcursionsStarted + "\\n"\n                    + "speakerLiveStyleBridgeBacks=" + styleBridgeBacks + "\\n"\n                    + "speakerLiveStylePendingStarts=" + stylePendingStarts + "\\n"\n                    + "speakerLiveStylePendingMatches=" + stylePendingMatches + "\\n"\n                    + "speakerLiveStylePrototypeConfirms=" + stylePrototypeConfirms + "\\n"\n                    + "speakerLiveNewProfileBoundaryPromotions=" + newProfileBoundaryPromotions + "\\n"\n                    + "speakerLiveNewProfileLongRunPromotions=" + newProfileLongRunPromotions + "\\n"\n                    + "speakerLiveCandidateParent=" + (candidate != null ? candidate.parentSpeaker : lastCandidateParent) + "\\n"\n''',
        "publish style/new-human diagnostics")

    rep(controller,
        'report.append("Spanish Dub Study v2.33.33 near-live ERes2Net identity-stabilization diagnostics\\n");',
        'report.append("Spanish Dub Study v2.33.34 context-aware human/style identity diagnostics\\n");',
        "update controller header")
    rep(controller,
        '        report.append("speakerLiveGoal=human-identity-first;unknown-before-false-split;coherent-candidate-promotion\\n");\n',
        '        report.append("speakerLiveGoal=human-identity-first;voice-style-is-not-a-new-human-without-boundary-evidence\\n");\n',
        "update speaker goal")

    # ------------------------------------------------------------------
    # Translation: do not permanently mark a transient null OpenRouter batch as done.
    # ------------------------------------------------------------------
    rep(translator,
        '''                final List<String> translated = translateBatchSafe(videoId, batch, targetLang,\n                        streamCallback(onUpdate, mainHandler, working, batch, offset, targetLang));\n                translatingBatchIndex = -1;\n''',
        '''                List<String> translated = translateBatchSafe(videoId, batch, targetLang,\n                        streamCallback(onUpdate, mainHandler, working, batch, offset, targetLang));\n                translatingBatchIndex = -1;\n''',
        "make batch result recoverable")

    recovery_anchor = '''                SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.TRANSLATION,\n                        "batch result=" + index + " expected=" + batch.size()\n                                + " got=" + (translated == null ? -1 : translated.size())\n                                + " latencyMs=" + (System.currentTimeMillis() - diagBatchStart)\n                                + " reprioritize=" + reprioritize + " abort=" + abortTranslation);\n'''
    recovery = recovery_anchor + '''\n                if (translated == null && isOpenRouter && !abortTranslation && !reprioritize) {\n                    SpanishStudyDiagnostics.recordAlways(SpanishStudyDiagnostics.TRANSLATION,\n                            "OpenRouter recovery action=retry-once batch=" + index\n                                    + " size=" + batch.size());\n                    translatingBatchIndex = index;\n                    translated = translateBatchSafe(videoId, batch, targetLang,\n                            streamCallback(onUpdate, mainHandler, working, batch, offset, targetLang));\n                    translatingBatchIndex = -1;\n                    if (translated == null && !abortTranslation && !reprioritize) {\n                        SpanishStudyDiagnostics.recordAlways(SpanishStudyDiagnostics.TRANSLATION,\n                                "OpenRouter recovery action=google-batch-fallback batch=" + index\n                                        + " size=" + batch.size());\n                        try {\n                            translated = translateBatchGoogle(videoId, batch, targetLang);\n                            SpanishStudyDiagnostics.recordAlways(SpanishStudyDiagnostics.TRANSLATION,\n                                    "OpenRouter recovery action=google-batch-fallback-success batch="\n                                            + index + " got=" + (translated == null ? -1 : translated.size()));\n                        } catch (Exception fallbackEx) {\n                            SpanishStudyDiagnostics.error(SpanishStudyDiagnostics.TRANSLATION,\n                                    "OpenRouter recovery Google fallback failed batch=" + index, fallbackEx);\n                        }\n                    }\n                }\n'''
    rep(translator, recovery_anchor, recovery, "recover transient null OpenRouter batch")

    # Final source-level release invariants.
    req(live, "speakerLiveMode=eres2net-short-window-online-human-identity-v23334", "v34 live marker")
    req(live, "STYLE_PENDING_CONFIRMATIONS = 3", "style quarantine confirmation gate")
    req(live, "candidate.distinctSpeechRuns >= 2", "boundary evidence gate")
    req(live, "NEW_PROFILE_LONG_RUN_SUPPORT = 12", "long-run escape hatch")
    req(live, "resolveStyleCandidateOnKnownReturnLocked", "style bridge resolver")
    req(translator, "OpenRouter recovery action=retry-once", "OpenRouter retry marker")
    req(translator, "OpenRouter recovery action=google-batch-fallback-success", "Google batch fallback marker")
    req(controller, "v2.33.34 context-aware human/style identity", "v34 controller marker")
    print("v2.33.34 compact style-context + timeout recovery patch complete")
    print("PRESERVED: exact accepted PCM, verifier-safe int-only postwrite hook, videoMs master clock, ERes2Net extraction")


if __name__ == "__main__":
    main()
