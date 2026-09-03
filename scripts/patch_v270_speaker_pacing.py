#!/usr/bin/env python3
"""v2.7: lightweight speaker profiles, lower-quota video grounding, and adaptive dub pacing."""
from pathlib import Path
import sys


def rep(path: Path, old: str, new: str, label: str):
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count} in {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("patched:", label)


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_v270_speaker_pacing.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    votpkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    prefs = study / "SpanishStudyPrefs.java"
    ctl = study / "SpanishStudyController.java"
    sheet = study / "SpanishStudySheet.java"
    gemini = study / "GeminiTranslator.java"
    ground_sidecar = study / "GeminiVideoGroundingSidecar.java"
    grounding = study / "GeminiVideoGrounding.java"
    vot = votpkg / "VoiceOverTranslationPatch.java"

    # ---------- Preferences -----------------------------------------------------------------
    rep(prefs,
'''            SPEAKER_VOICES="speaker_voices_enabled",
            SPEAKER_LABELS="speaker_labels_enabled";''',
'''            SPEAKER_VOICES="speaker_voices_enabled",
            SPEAKER_LABELS="speaker_labels_enabled",
            MATCH_SOURCE_PACE="match_source_pace_enabled";''',
        "add match-source-pace preference")

    rep(prefs,
'''    static boolean speakerLabelsEnabled(Context c){return prefs(c).getBoolean(SPEAKER_LABELS,true);}
    static void setSpeakerLabelsEnabled(Context c,boolean v){putBoolean(c,SPEAKER_LABELS,v);}
}''',
'''    static boolean speakerLabelsEnabled(Context c){return prefs(c).getBoolean(SPEAKER_LABELS,true);}
    static void setSpeakerLabelsEnabled(Context c,boolean v){putBoolean(c,SPEAKER_LABELS,v);}

    /**
     * When enabled, the normal max-speech-rate slider is a preferred ceiling rather than a hard
     * wall. Dense translated phrases may temporarily accelerate only enough to preserve sync.
     */
    static boolean matchSourcePace(Context c){return prefs(c).getBoolean(MATCH_SOURCE_PACE,true);}
    static void setMatchSourcePace(Context c,boolean v){putBoolean(c,MATCH_SOURCE_PACE,v);}
}''',
        "add adaptive pacing preference API")

    # ---------- Controller: schedule digital-video speaker profiling in parallel --------------
    rep(ctl,
'''    private static WeakReference<View> playerControlsRef=new WeakReference<>(null);''',
'''    private static WeakReference<View> playerControlsRef=new WeakReference<>(null);
    // Immutable YouTube source-caption snapshot used only to align background speaker windows.
    private static List<TranscriptSegment> speakerSourceSegments=new ArrayList<>();''',
        "store source captions for rolling speaker windows")

    rep(ctl,
'''        SpanishStudyDiagnostics.record("CAPTIONS", "source fetched events=" + snapshot.size());
        if(Looper.myLooper()==Looper.getMainLooper())SpanishSubtitleOverlay.setSourceSegments(snapshot);''',
'''        SpanishStudyDiagnostics.record("CAPTIONS", "source fetched events=" + snapshot.size());
        speakerSourceSegments=new ArrayList<>(snapshot);
        if(Looper.myLooper()==Looper.getMainLooper())SpanishSubtitleOverlay.setSourceSegments(snapshot);''',
        "retain source captions for speaker profiling")

    rep(ctl,
'''    public static void onVideoTimeChanged(long timeMs){
        SpanishStudyDiagnostics.samplePlayhead(timeMs);
        Activity activity=Utils.getActivity();''',
'''    public static void onVideoTimeChanged(long timeMs){
        SpanishStudyDiagnostics.samplePlayhead(timeMs);
        // Runs independently from translation/TTS and never touches microphone or speaker output.
        GeminiSpeakerDiarizationSidecar.maybeSchedule(
                VoiceOverTranslationPatch.getCurrentVideoIdForStudy(),speakerSourceSegments,timeMs);
        Activity activity=Utils.getActivity();''',
        "schedule lightweight speaker clustering from the source-video clock")

    rep(ctl,
'''        SpeakerAssignmentStore.clear();
        DubEventStateStore.clear();''',
'''        SpeakerAssignmentStore.clear();
        GeminiSpeakerDiarizationSidecar.clear();
        speakerSourceSegments=new ArrayList<>();
        DubEventStateStore.clear();''',
        "clear speaker profiler per video")

    rep(ctl,
'''    public static boolean speakerVoicesEnabled(){
        android.content.Context context=Utils.getContext();
        return context!=null&&SpanishStudyPrefs.speakerVoicesEnabled(context);
    }
''',
'''    public static boolean speakerVoicesEnabled(){
        android.content.Context context=Utils.getContext();
        return context!=null&&SpanishStudyPrefs.speakerVoicesEnabled(context);
    }

    public static String speakerProfileStatus(){return GeminiSpeakerDiarizationSidecar.status();}

    /** Trivial timing arithmetic only; no acoustic analysis runs on-device. */
    public static boolean matchSourcePaceEnabled(){
        android.content.Context context=Utils.getContext();
        return context!=null&&SpanishStudyPrefs.matchSourcePace(context);
    }

    /** Emergency ceiling used only when a Spanish phrase would otherwise block later subtitles. */
    public static float adaptiveCatchupCeiling(){return 1.60f;}
''',
        "expose speaker profile and adaptive pacing state")

    # ---------- UI: make speaker clustering visible and pacing user-controllable ----------------
    rep(sheet,
'''        content.addView(section(activity,"Playback & study",secondary));''',
'''        LinearLayout speakerProfiles=valueRow(activity,fg,"Speaker profiles",
                SpanishStudyController.speakerProfileStatus());
        speakerProfiles.setOnClickListener(v->Toast.makeText(activity,
                SpanishStudyController.speakerProfileStatus(),Toast.LENGTH_SHORT).show());
        content.addView(speakerProfiles);

        content.addView(section(activity,"Playback & study",secondary));
        content.addView(switchRow(activity,fg,"Match source pace",
                "Treat the normal max-rate slider as preferred. If Spanish would overrun the next subtitle, temporarily speed only as much as needed (up to 1.6×) instead of skipping a later phrase.",
                SpanishStudyPrefs.matchSourcePace(activity),
                checked->SpanishStudyPrefs.setMatchSourcePace(activity,checked)));''',
        "show speaker profiles and source-pace control")

    # ---------- Translation: ask for duration-aware concise Spanish without extra API calls ------
    rep(gemini,
'''                .append("ISOCHRONY RULE: prefer concise natural wording that preserves complete meaning so speech can fit its source time slot. ")''',
'''                .append("ISOCHRONY RULE: preserve complete meaning, but prefer the shortest natural conversational wording that can actually be spoken inside that ID's source time slot. Remove needless filler/repetition when Spanish has a shorter equivalent; never omit factual content merely to save time. The event list includes each slot duration so dense speech can be translated more compactly without an extra model call. ")''',
        "make translation explicitly duration-aware")

    rep(gemini,
'''            prompt.append('[').append(i).append(" @ ")
                    .append(s.startMs).append('-').append(s.endMs).append("ms] ")
                    .append(s.text).append('\\n');''',
'''            prompt.append('[').append(i).append(" @ ")
                    .append(s.startMs).append('-').append(s.endMs).append("ms, slot=")
                    .append(String.format(Locale.ROOT,"%.2fs",Math.max(1L,s.endMs-s.startMs)/1000.0))
                    .append("] ").append(s.text).append('\\n');''',
        "include source speech-slot duration in Gemini context")

    # ---------- Pacing: use measured TTS duration / source slot, with optional catch-up headroom --
    rep(vot,
'''    private static float calculateSpeechRate(long speechDurationMs, long availableMs) {
        final float maxRate = Settings.VOT_MAX_SPEECH_RATE.get() / 10.0f;
        if (availableMs <= 0) return maxRate;
        return Math.max(MIN_SPEECH_RATE, Math.min(maxRate, speechDurationMs / (float) availableMs));
    }''',
'''    private static float calculateSpeechRate(long speechDurationMs, long availableMs) {
        final float preferredMax = Math.max(MIN_SPEECH_RATE,
                Settings.VOT_MAX_SPEECH_RATE.get() / 10.0f);
        final float effectiveMax = SpanishStudyController.matchSourcePaceEnabled()
                ? Math.max(preferredMax, SpanishStudyController.adaptiveCatchupCeiling())
                : preferredMax;
        if (availableMs <= 0) return effectiveMax;
        final float needed = speechDurationMs / (float) availableMs;
        return Math.max(MIN_SPEECH_RATE, Math.min(effectiveMax, needed));
    }''',
        "adapt measured TTS rate to source pace without hard-skipping")

    # If a prior Spanish phrase is still speaking when the next source subtitle begins, do not just
    # let it consume the entire next event. Accelerate the existing MP3 in place to the emergency
    # ceiling; this preserves its words and releases the next phrase sooner without a hard cut.
    rep(vot,
'''                        if (!ttsEngine.isSpeaking() || wasExplicitSeek) {
                            final int candidateIndex = i;
                            Logger.printDebug(() -> "Preparing segment: " + candidateIndex
                                    + " videoTime: " + timeMs + " "
                                    + SpanishStudyController.dubDiagnostic(seg));
                            speak(seg, i);
                        }''',
'''                        if (ttsEngine.isSpeaking() && !wasExplicitSeek
                                && SpanishStudyController.matchSourcePaceEnabled()) {
                            final float catchup = SpanishStudyController.adaptiveCatchupCeiling();
                            if (currentTtsBaseRate + 0.01f < catchup) {
                                currentTtsBaseRate = catchup;
                                lastAppliedPlaybackSpeed = VideoInformation.getPlaybackSpeed();
                                ttsEngine.setPlaybackRate(currentTtsBaseRate
                                        * Math.max(0.1f,lastAppliedPlaybackSpeed));
                                SpanishStudyDiagnostics.record("PACE", "prior phrase overlapping index="
                                        + i + "; accelerated active dub to " + catchup + "x");
                            }
                        }
                        if (!ttsEngine.isSpeaking() || wasExplicitSeek) {
                            final int candidateIndex = i;
                            Logger.printDebug(() -> "Preparing segment: " + candidateIndex
                                    + " videoTime: " + timeMs + " "
                                    + SpanishStudyController.dubDiagnostic(seg));
                            speak(seg, i);
                        }''',
        "accelerate an overlapping prior phrase instead of silently losing the next subtitle")

    # The max-rate slider remains non-destructive. With source-pacing on, lowering it changes the
    # preferred speed but should not forcibly slow an already-emergency-catching-up phrase.
    rep(vot,
'''            final float newMaxRate = Math.max(1.0f,
                    Settings.VOT_MAX_SPEECH_RATE.get() / 10.0f);''',
'''            final float preferredMaxRate = Math.max(1.0f,
                    Settings.VOT_MAX_SPEECH_RATE.get() / 10.0f);
            final float newMaxRate = SpanishStudyController.matchSourcePaceEnabled()
                    ? Math.max(preferredMaxRate,SpanishStudyController.adaptiveCatchupCeiling())
                    : preferredMaxRate;''',
        "keep live speed slider compatible with adaptive catch-up")

    # Record only exceptional acceleration decisions; normal 1.0x lines stay quiet in diagnostics.
    rep(vot,
'''        final float rate = calculateSpeechRate(remainingSpeechMs, availableMs);
        final float playbackRate = rate * VideoInformation.getPlaybackSpeed();''',
'''        final float rate = calculateSpeechRate(remainingSpeechMs, availableMs);
        final float preferredRate = Math.max(1.0f,Settings.VOT_MAX_SPEECH_RATE.get()/10.0f);
        if (rate > preferredRate + 0.01f) {
            SpanishStudyDiagnostics.record("PACE", "adaptive rate=" + rate + " preferred="
                    + preferredRate + " speech=" + remainingSpeechMs + "ms slot=" + availableMs + "ms");
        }
        final float playbackRate = rate * VideoInformation.getPlaybackSpeed();''',
        "diagnose adaptive catch-up only when it is actually needed")

    # ---------- Grounding quota hygiene ---------------------------------------------------------
    # Caption/video grounding remains optional side-data, but do not let a successful response cause
    # another expensive YouTube-video request on every six-second translation batch.
    rep(ground_sidecar,
'''    private static final long FAILURE_BACKOFF_MS = 5 * 60 * 1000L;
    private static final Set<String> IN_FLIGHT = new HashSet<>();
    private static final Map<String, Long> BACKOFF_UNTIL = new HashMap<>();''',
'''    private static final long FAILURE_BACKOFF_MS = 5 * 60 * 1000L;
    private static final long SUCCESS_COOLDOWN_MS = 60_000L;
    private static final Set<String> IN_FLIGHT = new HashSet<>();
    private static final Map<String, Long> BACKOFF_UNTIL = new HashMap<>();
    private static final Map<String, Long> NEXT_ALLOWED = new HashMap<>();''',
        "add successful video-grounding cooldown")

    rep(ground_sidecar,
'''            Long until = BACKOFF_UNTIL.get(videoId);
            if (until != null && now < until) return;
            if (IN_FLIGHT.contains(videoId)) return;''',
'''            Long until = BACKOFF_UNTIL.get(videoId);
            if (until != null && now < until) return;
            Long next = NEXT_ALLOWED.get(videoId);
            if (next != null && now < next) return;
            if (IN_FLIGHT.contains(videoId)) return;''',
        "throttle successful grounding sidecar calls")

    rep(ground_sidecar,
'''                    if (!success) BACKOFF_UNTIL.put(videoId,
                            System.currentTimeMillis() + FAILURE_BACKOFF_MS);
                    else BACKOFF_UNTIL.remove(videoId);''',
'''                    if (!success) BACKOFF_UNTIL.put(videoId,
                            System.currentTimeMillis() + FAILURE_BACKOFF_MS);
                    else {
                        BACKOFF_UNTIL.remove(videoId);
                        NEXT_ALLOWED.put(videoId,System.currentTimeMillis()+SUCCESS_COOLDOWN_MS);
                    }''',
        "cool down after successful video grounding")

    rep(ground_sidecar,
'''        IN_FLIGHT.remove(videoId);
        BACKOFF_UNTIL.remove(videoId);''',
'''        IN_FLIGHT.remove(videoId);
        BACKOFF_UNTIL.remove(videoId);
        NEXT_ALLOWED.remove(videoId);''',
        "clear grounding cooldown per video")

    # Use a model explicitly documented for YouTube/audio understanding, independently of the text
    # translation model. This also prevents speaker/video work from consuming the primary model's RPM.
    rep(grounding,
'''            String model=SpanishStudyPrefs.geminiModel(context).trim().replaceAll("[^A-Za-z0-9._-]","");
            if(model.isEmpty())model=SpanishStudyPrefs.DEFAULT_GEMINI_MODEL;''',
'''            String model="gemini-3.7-flash";''',
        "use documented 3.7 Flash for public-YouTube grounding")

    rep(grounding,
'''        video.put("type","video");
        video.put("uri","https://www.youtube.com/watch?v="+videoId);''',
'''        video.put("type","video");
        video.put("uri","https://www.youtube.com/watch?v="+videoId);
        video.put("mime_type","video/mp4");''',
        "declare YouTube video MIME type for grounding")

    # ---------- Diagnostics -------------------------------------------------------------------
    rep(ctl,
'''        report.append("speakerVoices=").append(SpanishStudyPrefs.speakerVoicesEnabled(activity)).append('\\n');
        report.append("--- events ---\\n").append(SpanishStudyDiagnostics.dump());''',
'''        report.append("speakerVoices=").append(SpanishStudyPrefs.speakerVoicesEnabled(activity)).append('\\n');
        report.append("speakerProfiles=").append(GeminiSpeakerDiarizationSidecar.status()).append('\\n');
        report.append("matchSourcePace=").append(SpanishStudyPrefs.matchSourcePace(activity)).append('\\n');
        report.append("--- events ---\\n").append(SpanishStudyDiagnostics.dump());''',
        "include speaker/pacing state in copied diagnostics")

    print("v2.7 speaker-profile/adaptive-pacing integration complete")


if __name__ == "__main__":
    main()
