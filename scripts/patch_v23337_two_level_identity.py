#!/usr/bin/env python3
"""v2.33.37: decouple raw acoustic profiles from persistent human identities.

Applies after v2.33.36. The accepted-PCM/video-master clock, ERes2Net extractor, 2.0 s
window / 600 ms hop, change-point detector, translation, subtitles and TTS are unchanged.

v36 still let one stable acoustic state consume one visible person label. v37 makes the
speaker cache explicitly two-level:
- raw ERes2Net profiles remain independent acoustic/style states for matching;
- every raw profile maps to a compact persistent human identity;
- a new raw profile that originates as a continuation of an established person inside the
  same VAD speech run is linked to that person's human identity instead of minting a person;
- raw-profile inventory growth no longer makes later real humans pay the C+/D+ penalty;
  those gates are based on humanCount, not profileCount;
- timelines continue to store raw profile ids, so the visible label is resolved through the
  human map at display time;
- diagnostics expose raw->human ownership and raw-vs-human switching separately.

This targets the observed close-mic case (e.g. Shannon normal vs Shannon close-mic) without
collapsing their raw embedding states, so Peter can still become the next human identity.
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
        raise SystemExit("usage: patch_v23337_two_level_identity.py <morphe-root> [repo-root]")
    root = Path(sys.argv[1]).resolve()
    live = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/LiveSpeakerOnline.java"
    controller = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SpanishStudyController.java"
    for p in (live, controller):
        if not p.is_file():
            raise RuntimeError(f"missing v2.33.36 source: {p}")

    rep(live,
        '''    private static final Profile[] PROFILES = new Profile[MAX_PROFILES];\n    private static final long[] TL_START = new long[MAX_TIMELINE];\n''',
        '''    private static final Profile[] PROFILES = new Profile[MAX_PROFILES];\n    // v2.33.37: raw ERes2Net profiles are acoustic states, not automatically people.\n    // Timelines keep raw ids; labelFor() resolves raw -> human dynamically.\n    private static final int[] PROFILE_HUMAN = new int[MAX_PROFILES];\n    private static final boolean[] PROFILE_STYLE_LINK = new boolean[MAX_PROFILES];\n    private static final int[] PROFILE_STYLE_ORIGIN = new int[MAX_PROFILES];\n    private static final long[] PROFILE_FIRST_RUN = new long[MAX_PROFILES];\n    private static int humanCount;\n    private static int acousticProfilesCreated;\n    private static int acousticProfilesLinkedToExistingHuman;\n    private static int humansCreated;\n    private static int sameHumanRawTransitions;\n    private static int sameRunRawTransitions;\n    private static int acousticProfileSwitches;\n    private static final long[] TL_START = new long[MAX_TIMELINE];\n''',
        "add raw-profile to human mapping")

    rep(live,
        '''            for (int i = 0; i < MAX_PROFILES; i++) PROFILES[i] = null;\n            profileCount = 0;\n            lastCommittedSpeaker = -1;\n''',
        '''            for (int i = 0; i < MAX_PROFILES; i++) PROFILES[i] = null;\n            Arrays.fill(PROFILE_HUMAN, -1);\n            Arrays.fill(PROFILE_STYLE_LINK, false);\n            Arrays.fill(PROFILE_STYLE_ORIGIN, -1);\n            Arrays.fill(PROFILE_FIRST_RUN, -1L);\n            profileCount = 0;\n            humanCount = 0;\n            acousticProfilesCreated = 0;\n            acousticProfilesLinkedToExistingHuman = 0;\n            humansCreated = 0;\n            sameHumanRawTransitions = 0;\n            sameRunRawTransitions = 0;\n            acousticProfileSwitches = 0;\n            lastCommittedSpeaker = -1;\n''',
        "reset two-level inventory on new video")

    rep(live,
        '''        int parentSpeaker;\n        final long parentSpeechRunSerial;\n''',
        '''        int parentSpeaker;\n        final int originParentSpeaker;\n        final long parentSpeechRunSerial;\n        boolean startedAtVadBoundary;\n        boolean startedAtAcousticBoundary;\n        float startAdjacentSimilarity = -1f;\n''',
        "remember candidate acoustic-state origin")

    rep(live,
        '''            this.parentSpeaker = parentSpeaker;\n            this.parentSpeechRunSerial = speechRunSerial;\n''',
        '''            this.parentSpeaker = parentSpeaker;\n            this.originParentSpeaker = parentSpeaker;\n            this.parentSpeechRunSerial = speechRunSerial;\n''',
        "store persistent candidate origin parent")

    rep(live,
        '''        candidate = new Candidate(embedding.clone(), job.videoEpoch, job.speechRunSerial,\n                job.startVideoMs, job.endVideoMs, parent);\n        candidateStarts++;\n''',
        '''        candidate = new Candidate(embedding.clone(), job.videoEpoch, job.speechRunSerial,\n                job.startVideoMs, job.endVideoMs, parent);\n        candidate.startedAtVadBoundary = job.firstInSpeechRun;\n        candidate.startAdjacentSimilarity = lastAdjacentSimilarity;\n        candidate.startedAtAcousticBoundary = lastAdjacentSimilarity >= 0f\n                && lastAdjacentSimilarity < ADJACENT_CHANGE_POINT;\n        candidateStarts++;\n''',
        "capture boundary state when a raw candidate starts")

    rep(live,
        '''            int id = createProfileLocked(promoted.embedding);\n            PROFILES[id].supportCount = promoted.count;\n            if (promoted.count >= 3 && PROFILES[id].addPrototype(promoted.seedEmbedding)) {\n                stablePrototypeAdds++;\n            }\n            long retroStart = promoted.startVideoMs;\n            candidateConfirms++;\n            bootstrapConfirms++;\n''',
        '''            int id = createProfileLocked(promoted.embedding);\n            assignNewHumanLocked(id, promoted.speechRunSerial);\n            PROFILES[id].supportCount = promoted.count;\n            if (promoted.count >= 3 && PROFILES[id].addPrototype(promoted.seedEmbedding)) {\n                stablePrototypeAdds++;\n            }\n            long retroStart = promoted.startVideoMs;\n            candidateConfirms++;\n            bootstrapConfirms++;\n''',
        "bootstrap first raw profile as first human")

    rep(live,
        '''        int dynamicMinSupport = profileCount <= 1 ? NEW_PROFILE_MIN_SUPPORT\n                : (profileCount == 2 ? THIRD_SPEAKER_MIN_SUPPORT : LATER_SPEAKER_MIN_SUPPORT);\n        long dynamicMinSpanMs = profileCount <= 1 ? CANDIDATE_MIN_SPAN_MS\n                : (profileCount == 2 ? THIRD_SPEAKER_MIN_SPAN_MS : LATER_SPEAKER_MIN_SPAN_MS);\n''',
        '''        int dynamicMinSupport = humanCount <= 1 ? NEW_PROFILE_MIN_SUPPORT\n                : (humanCount == 2 ? THIRD_SPEAKER_MIN_SUPPORT : LATER_SPEAKER_MIN_SUPPORT);\n        long dynamicMinSpanMs = humanCount <= 1 ? CANDIDATE_MIN_SPAN_MS\n                : (humanCount == 2 ? THIRD_SPEAKER_MIN_SPAN_MS : LATER_SPEAKER_MIN_SPAN_MS);\n''',
        "base new-human complexity gates on humans, not acoustic profiles")

    rep(live,
        '''        boolean boundaryEvidence = profileCount <= 1\n                ? (vadBoundaryEvidence || recentAcousticBoundary)\n                : (vadBoundaryEvidence && recentAcousticBoundary);\n''',
        '''        boolean boundaryEvidence = humanCount <= 1\n                ? (vadBoundaryEvidence || recentAcousticBoundary)\n                : (vadBoundaryEvidence && recentAcousticBoundary);\n''',
        "base boundary strictness on human inventory")

    rep(live,
        '''                && candidateKnownBest < NEW_PROFILE_LONG_RUN_MAX_KNOWN\n                && profileCount <= 1;\n''',
        '''                && candidateKnownBest < NEW_PROFILE_LONG_RUN_MAX_KNOWN\n                && humanCount <= 1;\n''',
        "allow long-run escape hatch while only one human is known")

    rep(live,
        '''        if (!readyNew && profileCount >= 2 && candidate.count >= 4\n                && coherentEnough && (clearlyNovel || highCohesionOverride)) {\n''',
        '''        if (!readyNew && humanCount >= 2 && candidate.count >= 4\n                && coherentEnough && (clearlyNovel || highCohesionOverride)) {\n''',
        "count complexity blocks against human inventory")

    rep(live,
        '''        if (readyNew && profileCount < MAX_PROFILES) {\n            Candidate promoted = candidate;\n            int id = createProfileLocked(promoted.embedding);\n            PROFILES[id].supportCount = promoted.count;\n''',
        '''        if (readyNew && profileCount < MAX_PROFILES) {\n            Candidate promoted = candidate;\n            int id = createProfileLocked(promoted.embedding);\n            boolean linkedStyle = assignHumanForPromotedProfileLocked(id, promoted);\n            PROFILES[id].supportCount = promoted.count;\n''',
        "resolve raw acoustic profile to human at promotion")

    rep(live,
        '''            commitLocked(retro, id, "new-speaker-coherent-cluster", avgCohesion,\n                    Math.max(0f, CANDIDATE_RESCUE_MATCH - candidateKnownBest));\n''',
        '''            commitLocked(retro, id, linkedStyle\n                            ? "new-acoustic-style-cluster-linked-human"\n                            : "new-human-coherent-cluster", avgCohesion,\n                    Math.max(0f, CANDIDATE_RESCUE_MATCH - candidateKnownBest));\n''',
        "distinguish raw-style creation from human creation")

    rep(live,
        '''    private static int createProfileLocked(float[] embedding) {\n''',
        '''    private static int humanForProfileLocked(int profile) {\n        if (profile < 0 || profile >= profileCount) return -1;\n        return PROFILE_HUMAN[profile];\n    }\n\n    private static int assignNewHumanLocked(int profile, long speechRun) {\n        if (profile < 0 || profile >= MAX_PROFILES) return -1;\n        int human = humanCount++;\n        PROFILE_HUMAN[profile] = human;\n        PROFILE_STYLE_LINK[profile] = false;\n        PROFILE_STYLE_ORIGIN[profile] = -1;\n        PROFILE_FIRST_RUN[profile] = speechRun;\n        humansCreated++;\n        return human;\n    }\n\n    private static boolean linkRawProfileToExistingHumanLocked(int profile, int parentProfile,\n                                                                long speechRun) {\n        int human = humanForProfileLocked(parentProfile);\n        if (profile < 0 || profile >= MAX_PROFILES || human < 0) return false;\n        PROFILE_HUMAN[profile] = human;\n        PROFILE_STYLE_LINK[profile] = true;\n        PROFILE_STYLE_ORIGIN[profile] = parentProfile;\n        PROFILE_FIRST_RUN[profile] = speechRun;\n        acousticProfilesLinkedToExistingHuman++;\n        return true;\n    }\n\n    private static boolean assignHumanForPromotedProfileLocked(int profile, Candidate promoted) {\n        int origin = promoted == null ? -1 : promoted.originParentSpeaker;\n        if (promoted != null && origin >= 0 && origin < profileCount\n                && !promoted.startedAtVadBoundary\n                && humanForProfileLocked(origin) >= 0\n                && linkRawProfileToExistingHumanLocked(profile, origin, promoted.speechRunSerial)) {\n            return true;\n        }\n        assignNewHumanLocked(profile, promoted == null ? -1L : promoted.speechRunSerial);\n        return false;\n    }\n\n    private static int createProfileLocked(float[] embedding) {\n''',
        "add acoustic-profile/human ownership helpers")

    rep(live,
        '''        PROFILES[id] = p;\n        profileCount++;\n        return id;\n''',
        '''        PROFILES[id] = p;\n        PROFILE_HUMAN[id] = -1;\n        PROFILE_STYLE_LINK[id] = false;\n        PROFILE_STYLE_ORIGIN[id] = -1;\n        PROFILE_FIRST_RUN[id] = -1L;\n        profileCount++;\n        acousticProfilesCreated++;\n        return id;\n''',
        "initialize raw profile without assuming a new human")

    rep(live,
        '''        assignments++;\n        if (lastCommittedSpeaker >= 0 && speaker != lastCommittedSpeaker) switches++;\n        appendTimelineLocked(job.startVideoMs, job.endVideoMs, speaker);\n''',
        '''        assignments++;\n        if (lastCommittedSpeaker >= 0 && speaker != lastCommittedSpeaker) {\n            acousticProfileSwitches++;\n            int priorHuman = humanForProfileLocked(lastCommittedSpeaker);\n            int nextHuman = humanForProfileLocked(speaker);\n            if (priorHuman >= 0 && nextHuman >= 0 && priorHuman == nextHuman) {\n                sameHumanRawTransitions++;\n                if (job.speechRunSerial == lastCommittedSpeechRunSerial) sameRunRawTransitions++;\n            } else {\n                switches++;\n            }\n        }\n        appendTimelineLocked(job.startVideoMs, job.endVideoMs, speaker);\n''',
        "separate human switches from raw acoustic switches")

    rep(live,
        '''    private static String labelFor(int id) {\n        if (id >= 0 && id < 26) return String.valueOf((char) ('A' + id));\n        return "S" + id;\n    }\n''',
        '''    private static String rawLabelFor(int id) {\n        if (id >= 0 && id < 26) return String.valueOf((char) ('A' + id));\n        return "R" + id;\n    }\n\n    private static String humanLabelFor(int id) {\n        if (id >= 0 && id < 26) return String.valueOf((char) ('A' + id));\n        return "H" + id;\n    }\n\n    private static String labelFor(int profile) {\n        int human = humanForProfileLocked(profile);\n        return human >= 0 ? humanLabelFor(human) : "?";\n    }\n''',
        "resolve visible labels from human ownership")

    rep(live,
        '''                if (profile == null) p.append(labelFor(i)).append(":0/0");\n                else p.append(labelFor(i)).append(':').append(profile.prototypeCount)\n                        .append('/').append(profile.supportCount);\n''',
        '''                p.append(rawLabelFor(i)).append("->").append(labelFor(i));\n                if (PROFILE_STYLE_LINK[i]) p.append("~style");\n                if (profile == null) p.append(":0/0");\n                else p.append(':').append(profile.prototypeCount)\n                        .append('/').append(profile.supportCount);\n''',
        "publish raw acoustic profile to human ownership")

    rep(live,
        '''            return "speakerLiveMode=eres2net-contextual-streaming-human-identity-v23336\\n"\n                    + "speakerLiveWindowMs=2000\\n"\n                    + "speakerLiveHopMs=600\\n"\n                    + "speakerLiveArchitecture=sequential-change-point+multi-prototype-speaker-cache+provisional-retrofill\\n"\n                    + "speakerLiveBoundaryPolicy=vad-run+adjacent-embedding-change;Cplus-requires-both\\n"\n''',
        '''            return "speakerLiveMode=eres2net-two-level-acoustic-human-identity-v23337\\n"\n                    + "speakerLiveWindowMs=2000\\n"\n                    + "speakerLiveHopMs=600\\n"\n                    + "speakerLiveArchitecture=raw-acoustic-profile-cache->persistent-human-map+sequential-change-point+provisional-retrofill\\n"\n                    + "speakerLiveBoundaryPolicy=vad-run+adjacent-embedding-change;human-inventory-gates\\n"\n                    + "speakerLiveIdentityPolicy=raw-voice-state-is-not-a-person;same-run-origin-links-style-to-existing-human\\n"\n''',
        "publish v37 two-level architecture")

    rep(live,
        '''                    + "speakerLiveProfileFormat=label:prototypes/support\\n"\n''',
        '''                    + "speakerLiveProfileFormat=raw->human[~style]:prototypes/support\\n"\n''',
        "publish raw-to-human profile format")

    rep(live,
        '''                    + "speakerLiveProfiles=" + profileCount + "\\n"\n                    + "speakerLiveProfilePrototypes=" + (p.length() == 0 ? "none" : p.toString()) + "\\n"\n''',
        '''                    + "speakerLiveProfiles=" + profileCount + "\\n"\n                    + "speakerLiveHumans=" + humanCount + "\\n"\n                    + "speakerLiveAcousticProfilesCreated=" + acousticProfilesCreated + "\\n"\n                    + "speakerLiveAcousticProfilesLinkedToExistingHuman=" + acousticProfilesLinkedToExistingHuman + "\\n"\n                    + "speakerLiveHumansCreated=" + humansCreated + "\\n"\n                    + "speakerLiveAcousticProfileSwitches=" + acousticProfileSwitches + "\\n"\n                    + "speakerLiveSameHumanRawTransitions=" + sameHumanRawTransitions + "\\n"\n                    + "speakerLiveSameRunRawTransitions=" + sameRunRawTransitions + "\\n"\n                    + "speakerLiveProfilePrototypes=" + (p.length() == 0 ? "none" : p.toString()) + "\\n"\n''',
        "publish two-level inventory counters")

    rep(controller,
        'report.append("Spanish Dub Study v2.33.36 streaming speaker-cache + change-point diagnostics\\n");',
        'report.append("Spanish Dub Study v2.33.37 two-level acoustic-profile + human-identity diagnostics\\n");',
        "update diagnostics header")

    rep(controller,
        '        report.append("speakerLiveGoal=production-style-streaming-human-identity;sequence+boundary+speaker-cache\\n");\n',
        '        report.append("speakerLiveGoal=two-level-streaming-identity;acoustic-states-under-persistent-humans\\n");\n',
        "update live goal marker")

    req(live, "speakerLiveMode=eres2net-two-level-acoustic-human-identity-v23337", "v37 live marker")
    req(live, "raw-acoustic-profile-cache->persistent-human-map", "two-level architecture marker")
    req(live, "speakerLiveHumans=", "human inventory diagnostics")
    req(live, "speakerLiveAcousticProfilesLinkedToExistingHuman=", "style-link diagnostics")
    req(live, "PROFILE_HUMAN", "raw-to-human map")
    req(live, "int dynamicMinSupport = humanCount <= 1", "human-count complexity gate")
    req(live, "new-acoustic-style-cluster-linked-human", "style-profile promotion decision")
    req(controller, "v2.33.37 two-level acoustic-profile + human-identity", "v37 controller marker")

    print("v2.33.37 two-level acoustic-profile/human-identity revision complete")
    print("PRESERVED: exact accepted PCM, video-ms master clock, ERes2Net, 2s/600ms streaming, translation/TTS")
    print("CHANGED: raw acoustic profile ids are now mapped underneath compact human identities")
    print("EXPECTED: close-mic/normal Shannon can be raw A/B but visible Human A; Peter can become visible Human B")


if __name__ == "__main__":
    main()
