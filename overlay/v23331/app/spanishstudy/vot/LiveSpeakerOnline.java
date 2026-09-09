package app.spanishstudy.vot;

import com.k2fsa.sherpa.onnx.OnlineStream;
import com.k2fsa.sherpa.onnx.SpeakerEmbeddingExtractor;
import com.k2fsa.sherpa.onnx.SpeakerEmbeddingExtractorConfig;

import java.nio.ByteBuffer;
import java.util.Arrays;

/**
 * v2.33.31 near-live speaker identity tracker.
 *
 * This intentionally does NOT replace the proven video-master/accepted-PCM clock. It consumes the
 * same exact Android-accepted PCM slice and uses AudioVideoSyncProbe only to project that slice to
 * YouTube video milliseconds.
 *
 * Identity policy is optimized for "which human is talking" rather than "does the voice sound
 * different right now":
 * - ERes2Net embeddings are computed on short rolling speech windows;
 * - persistent A/B/C identities are video-local;
 * - each identity can learn several vocal-style prototypes (normal voice, impression, register);
 * - a continuous speech run has strong identity inertia, so an impression does not instantly
 *   create a new person;
 * - a genuinely new identity requires repeated unmatched evidence after a speech boundary;
 * - latest-wins worker scheduling prevents inference backlog from turning into long latency.
 */
public final class LiveSpeakerOnline {
    private static final int TARGET_RATE = 16_000;
    private static final int WINDOW_SAMPLES = 32_000;          // 2.0 s
    private static final int HOP_SAMPLES = 12_000;             // 0.75 s
    private static final int RING_SAMPLES = 48_000;            // 3.0 s
    private static final int MAX_PROFILES = 8;
    private static final int MAX_PROTOTYPES = 3;
    private static final int MAX_TIMELINE = 512;
    private static final int QUIET_TO_BOUNDARY_MS = 240;
    private static final int LIVE_HOLD_MS = 2_800;
    private static final float ABS_MIN_RMS = 0.0065f;
    private static final float ABS_MIN_PEAK = 0.012f;
    private static final float STRONG_MATCH = 0.60f;
    private static final float NORMAL_MATCH = 0.53f;
    private static final float CONTINUITY_FLOOR = 0.36f;
    private static final float NEW_CANDIDATE_MATCH = 0.66f;
    private static final float STRONG_SWITCH = 0.68f;
    private static final float STRONG_SWITCH_MARGIN = 0.075f;

    private static final Object LOCK = new Object();
    private static final float[] RING = new float[RING_SAMPLES];
    private static final Profile[] PROFILES = new Profile[MAX_PROFILES];
    private static final long[] TL_START = new long[MAX_TIMELINE];
    private static final long[] TL_END = new long[MAX_TIMELINE];
    private static final int[] TL_SPEAKER = new int[MAX_TIMELINE];

    private static volatile SpeakerEmbeddingExtractor extractor;
    private static volatile int initState; // 0 idle, 1 starting, 2 ready, 3 failed
    private static volatile String initError = "none";
    private static volatile int embeddingDim;
    private static volatile long initMs;

    private static int ringWrite;
    private static int ringCount;
    private static long totalTargetSamples;
    private static long samplesSinceQueued;
    private static long ownerVideoEpoch = -1L;
    private static long ownerContinuityEpoch = -1L;
    private static int ownerTrackIdentity = -1;
    private static long lastSliceEndVideoMs = -1L;
    private static int lastScalePermille = 1000;

    private static float noiseFloor = 0.0035f;
    private static int quietRunMs;
    private static boolean inSpeech;
    private static long speechRunSerial;
    private static long lastQueuedSpeechRunSerial = -1L;
    private static int recentFrameCount;
    private static int recentVoicedFrames;
    private static final boolean[] VOICE_RING = new boolean[150]; // 3 s @ 20 ms-ish
    private static int voiceWrite;

    private static boolean workerBusy;
    private static Job pendingJob;
    private static long jobSequence;
    private static long jobsQueued;
    private static long jobsDroppedLatestWins;
    private static long jobsStarted;
    private static long jobsCompleted;
    private static long jobsNotReady;
    private static long jobsFailed;
    private static long lastInferenceMs;
    private static long maxInferenceMs;
    private static long analyzedThroughVideoMs = -1L;

    private static int profileCount;
    private static int lastCommittedSpeaker = -1;
    private static long lastCommittedEndVideoMs = -1L;
    private static int assignments;
    private static int switches;
    private static int continuityHolds;
    private static int impressionPrototypeAdds;
    private static int candidateStarts;
    private static int candidateConfirms;
    private static int candidateRejects;
    private static Candidate candidate;
    private static float lastBestSimilarity;
    private static float lastSecondSimilarity;
    private static float lastMargin;
    private static String lastDecision = "none";

    private static int timelineCount;
    private static long generation = 1L;

    private LiveSpeakerOnline() {}

    public static void initialize(String embeddingModelPath) {
        if (embeddingModelPath == null || embeddingModelPath.isEmpty() || initState != 0) return;
        synchronized (LOCK) {
            if (initState != 0) return;
            initState = 1;
        }
        final long startNs = System.nanoTime();
        try {
            SpeakerEmbeddingExtractorConfig config = SpeakerEmbeddingExtractorConfig.builder()
                    .setModel(embeddingModelPath)
                    .setNumThreads(1)
                    .setDebug(false)
                    .build();
            SpeakerEmbeddingExtractor created = new SpeakerEmbeddingExtractor(config);
            int dim = created.getDim();
            if (dim <= 0) throw new IllegalStateException("invalid-embedding-dim-" + dim);
            extractor = created;
            embeddingDim = dim;
            initMs = (System.nanoTime() - startNs) / 1_000_000L;
            initError = "none";
            initState = 2;
        } catch (Throwable t) {
            initMs = (System.nanoTime() - startNs) / 1_000_000L;
            initError = describe(t);
            initState = 3;
        }
    }

    public static boolean isReady() { return initState == 2 && extractor != null; }

    /** Full identity reset for a genuinely new video. The neural model remains loaded. */
    public static void resetForVideo() {
        synchronized (LOCK) {
            generation++;
            clearTransientLocked(true);
            for (int i = 0; i < MAX_PROFILES; i++) PROFILES[i] = null;
            profileCount = 0;
            lastCommittedSpeaker = -1;
            lastCommittedEndVideoMs = -1L;
            assignments = 0;
            switches = 0;
            continuityHolds = 0;
            impressionPrototypeAdds = 0;
            candidateStarts = 0;
            candidateConfirms = 0;
            candidateRejects = 0;
            candidate = null;
            lastBestSimilarity = 0f;
            lastSecondSimilarity = 0f;
            lastMargin = 0f;
            lastDecision = "new-video-reset";
            timelineCount = 0;
            analyzedThroughVideoMs = -1L;
        }
    }

    /** Seek/discontinuity reset: drop mixed audio/timeline continuity, preserve learned people. */
    private static void resetContinuityLocked(long videoEpoch, long continuityEpoch, int trackIdentity) {
        generation++;
        clearTransientLocked(false);
        ownerVideoEpoch = videoEpoch;
        ownerContinuityEpoch = continuityEpoch;
        ownerTrackIdentity = trackIdentity;
        candidate = null;
        lastCommittedEndVideoMs = -1L;
        lastDecision = "continuity-reset-profiles-kept";
    }

    private static void clearTransientLocked(boolean clearOwner) {
        ringWrite = 0;
        ringCount = 0;
        totalTargetSamples = 0L;
        samplesSinceQueued = 0L;
        Arrays.fill(RING, 0f);
        Arrays.fill(VOICE_RING, false);
        voiceWrite = 0;
        recentFrameCount = 0;
        recentVoicedFrames = 0;
        noiseFloor = 0.0035f;
        quietRunMs = 0;
        inSpeech = false;
        speechRunSerial = 0L;
        lastQueuedSpeechRunSerial = -1L;
        pendingJob = null;
        if (clearOwner) {
            ownerVideoEpoch = -1L;
            ownerContinuityEpoch = -1L;
            ownerTrackIdentity = -1;
            lastSliceEndVideoMs = -1L;
            lastScalePermille = 1000;
        }
    }

    /**
     * Exact post-write PCM observer. This is called from the AudioTrack callback and therefore must
     * remain bounded: PCM conversion/ring bookkeeping only. Neural inference is always off-thread.
     */
    public static void observeAcceptedPcmBuffer(ByteBuffer buffer, int sourceRateHz, int channels,
                                                int encoding, int acceptedBytes,
                                                long trackEndFrame, int trackIdentity) {
        if (initState != 2 || extractor == null || buffer == null || encoding != 2
                || sourceRateHz < 8_000 || channels < 1 || channels > 8 || acceptedBytes <= 0) return;
        try {
            final int frameBytes = channels * 2;
            int accepted = acceptedBytes - (acceptedBytes % frameBytes);
            ByteBuffer src = buffer.duplicate();
            int end = src.position();
            if (accepted <= 0 || end < accepted) return;
            int position = end - accepted;
            int frames = accepted / frameBytes;
            if (frames <= 0) return;

            AudioVideoSyncProbe.RenderAnchor render = AudioVideoSyncProbe.latestRenderAnchor();
            if (render == null || !render.valid || render.trackIdentity != trackIdentity
                    || render.sampleRateHz <= 0) return;
            long trackStartFrame = trackEndFrame - frames;
            long sliceStartVideoMs = AudioVideoSyncProbe.projectTrackFrameToVideoMs(
                    trackIdentity, sourceRateHz, trackStartFrame);
            long sliceEndVideoMs = AudioVideoSyncProbe.projectTrackFrameToVideoMs(
                    trackIdentity, sourceRateHz, trackEndFrame);
            if (sliceStartVideoMs < 0L || sliceEndVideoMs < sliceStartVideoMs) return;

            synchronized (LOCK) {
                if (ownerVideoEpoch >= 0L && (render.videoEpoch != ownerVideoEpoch
                        || render.continuityEpoch != ownerContinuityEpoch
                        || ownerTrackIdentity != trackIdentity)) {
                    // A continuity change within the same video keeps learned identities; a new
                    // video is already fully reset by PlayerVolumePatch's Stage-J lifecycle reset.
                    resetContinuityLocked(render.videoEpoch, render.continuityEpoch, trackIdentity);
                }
                if (ownerVideoEpoch < 0L) {
                    ownerVideoEpoch = render.videoEpoch;
                    ownerContinuityEpoch = render.continuityEpoch;
                    ownerTrackIdentity = trackIdentity;
                }
                lastSliceEndVideoMs = sliceEndVideoMs;
                lastScalePermille = render.videoPerAudioPermille > 0
                        ? render.videoPerAudioPermille : 1000;

                // One resampling phase per accepted slice is sufficient here because AudioTrack
                // writes are normally 20 ms. No allocation is performed on the audio thread.
                long phase = 0L;
                double sumSq = 0.0;
                float peak = 0f;
                int out = 0;
                for (int frame = 0; frame < frames; frame++) {
                    int base = position + frame * frameBytes;
                    long sum = 0L;
                    for (int ch = 0; ch < channels; ch++) {
                        int p = base + ch * 2;
                        int lo = src.get(p) & 0xff;
                        int hi = src.get(p + 1) << 8;
                        sum += (short) (hi | lo);
                    }
                    float mono = (float) (sum / channels) / 32768.0f;
                    phase += TARGET_RATE;
                    while (phase >= sourceRateHz) {
                        phase -= sourceRateHz;
                        RING[ringWrite] = mono;
                        ringWrite = (ringWrite + 1) % RING_SAMPLES;
                        if (ringCount < RING_SAMPLES) ringCount++;
                        totalTargetSamples++;
                        samplesSinceQueued++;
                        sumSq += mono * mono;
                        float abs = Math.abs(mono);
                        if (abs > peak) peak = abs;
                        out++;
                    }
                }
                if (out <= 0) return;

                float rms = (float) Math.sqrt(sumSq / out);
                float threshold = Math.max(ABS_MIN_RMS, noiseFloor * 2.6f);
                boolean voiced = rms >= threshold && peak >= ABS_MIN_PEAK && peak >= rms * 1.45f;
                if (!voiced) {
                    noiseFloor = noiseFloor * 0.985f + Math.min(rms, 0.02f) * 0.015f;
                    quietRunMs += Math.max(1, (int) (1000L * frames / sourceRateHz));
                    if (quietRunMs >= QUIET_TO_BOUNDARY_MS) inSpeech = false;
                } else {
                    if (!inSpeech) {
                        speechRunSerial++;
                        inSpeech = true;
                    }
                    quietRunMs = 0;
                }
                updateVoiceFrameLocked(voiced);

                if (inSpeech && ringCount >= WINDOW_SAMPLES && samplesSinceQueued >= HOP_SAMPLES
                        && recentFrameCount >= 50 && recentVoicedFrames * 100 >= recentFrameCount * 48) {
                    float[] samples = copyLatestLocked(WINDOW_SAMPLES);
                    long windowDurationMs = (WINDOW_SAMPLES * 1000L * lastScalePermille)
                            / (TARGET_RATE * 1000L);
                    long windowEnd = sliceEndVideoMs;
                    long windowStart = Math.max(0L, windowEnd - windowDurationMs);
                    boolean firstInRun = speechRunSerial != lastQueuedSpeechRunSerial;
                    lastQueuedSpeechRunSerial = speechRunSerial;
                    samplesSinceQueued = 0L;
                    queueLatestLocked(new Job(samples, windowStart, windowEnd, render.videoEpoch,
                            render.continuityEpoch, speechRunSerial, firstInRun, generation));
                }
            }
        } catch (Throwable ignored) {
            // Never escape onto ExoPlayer's audio thread.
        }
    }

    private static void updateVoiceFrameLocked(boolean voiced) {
        if (recentFrameCount < VOICE_RING.length) {
            recentFrameCount++;
        } else if (VOICE_RING[voiceWrite]) {
            recentVoicedFrames--;
        }
        VOICE_RING[voiceWrite] = voiced;
        if (voiced) recentVoicedFrames++;
        voiceWrite = (voiceWrite + 1) % VOICE_RING.length;
    }

    private static float[] copyLatestLocked(int count) {
        float[] out = new float[count];
        int start = ringWrite - count;
        if (start < 0) start += RING_SAMPLES;
        int first = Math.min(count, RING_SAMPLES - start);
        System.arraycopy(RING, start, out, 0, first);
        if (first < count) System.arraycopy(RING, 0, out, first, count - first);
        return out;
    }

    private static void queueLatestLocked(Job job) {
        jobsQueued++;
        if (workerBusy) {
            if (pendingJob != null) jobsDroppedLatestWins++;
            pendingJob = job;
            return;
        }
        workerBusy = true;
        startWorker(job);
    }

    private static void startWorker(Job first) {
        try {
            Thread t = new Thread(() -> workerLoop(first), "SpanishStudy-LiveSpeaker");
            t.setDaemon(true);
            t.setPriority(Thread.NORM_PRIORITY - 1);
            t.start();
        } catch (Throwable t) {
            synchronized (LOCK) {
                workerBusy = false;
                jobsFailed++;
                lastDecision = "worker-start-failed:" + describe(t);
            }
        }
    }

    private static void workerLoop(Job first) {
        Job job = first;
        while (job != null) {
            processJob(job);
            synchronized (LOCK) {
                job = pendingJob;
                pendingJob = null;
                if (job == null) workerBusy = false;
            }
        }
    }

    private static void processJob(Job job) {
        final long startNs = System.nanoTime();
        jobsStarted++;
        OnlineStream stream = null;
        try {
            SpeakerEmbeddingExtractor local = extractor;
            if (local == null || initState != 2) return;
            stream = local.createStream();
            stream.acceptWaveform(job.samples, TARGET_RATE);
            stream.inputFinished();
            if (!local.isReady(stream)) {
                synchronized (LOCK) {
                    jobsNotReady++;
                    analyzedThroughVideoMs = Math.max(analyzedThroughVideoMs, job.endVideoMs);
                    lastDecision = "embedding-not-ready";
                }
                return;
            }
            float[] embedding = local.compute(stream);
            normalize(embedding);
            long elapsed = (System.nanoTime() - startNs) / 1_000_000L;
            synchronized (LOCK) {
                if (job.generation != generation || job.videoEpoch != ownerVideoEpoch
                        || job.continuityEpoch != ownerContinuityEpoch) return;
                lastInferenceMs = elapsed;
                if (elapsed > maxInferenceMs) maxInferenceMs = elapsed;
                jobsCompleted++;
                analyzedThroughVideoMs = Math.max(analyzedThroughVideoMs, job.endVideoMs);
                assignLocked(job, embedding);
            }
        } catch (Throwable t) {
            synchronized (LOCK) {
                jobsFailed++;
                lastDecision = "embedding-failed:" + describe(t);
            }
        } finally {
            if (stream != null) {
                try { stream.release(); } catch (Throwable ignored) {}
            }
        }
    }

    private static void assignLocked(Job job, float[] embedding) {
        if (embedding == null || embedding.length == 0) return;
        if (profileCount == 0) {
            int id = createProfileLocked(embedding);
            commitLocked(job, id, "seed-first-speaker", 1f, 1f);
            return;
        }

        int best = -1;
        float bestScore = -1f;
        float second = -1f;
        for (int i = 0; i < profileCount; i++) {
            Profile p = PROFILES[i];
            if (p == null) continue;
            float score = p.score(embedding);
            if (score > bestScore) {
                second = bestScore;
                bestScore = score;
                best = i;
            } else if (score > second) {
                second = score;
            }
        }
        if (second < -0.5f) second = 0f;
        float margin = bestScore - second;
        lastBestSimilarity = bestScore;
        lastSecondSimilarity = second;
        lastMargin = margin;

        // Strong known-identity evidence always wins, including fast turn-taking without a pause.
        if (best >= 0 && (bestScore >= STRONG_MATCH
                || (best != lastCommittedSpeaker && bestScore >= STRONG_SWITCH
                    && margin >= STRONG_SWITCH_MARGIN))) {
            cancelCandidateLocked();
            PROFILES[best].update(embedding, 0.10f);
            commitLocked(job, best, best == lastCommittedSpeaker ? "strong-stay" : "strong-known-switch",
                    bestScore, margin);
            return;
        }

        // Human-identity inertia: a vocal-style change inside the same uninterrupted speech run
        // stays with the person unless another already-known speaker matches very strongly.
        if (!job.firstInSpeechRun && lastCommittedSpeaker >= 0 && lastCommittedSpeaker < profileCount) {
            Profile last = PROFILES[lastCommittedSpeaker];
            float lastScore = last.score(embedding);
            if (best < 0 || best == lastCommittedSpeaker || bestScore < STRONG_SWITCH) {
                continuityHolds++;
                if (lastScore < NORMAL_MATCH && lastScore >= CONTINUITY_FLOOR) {
                    if (last.addPrototype(embedding)) impressionPrototypeAdds++;
                    else last.update(embedding, 0.035f);
                } else if (lastScore >= CONTINUITY_FLOOR) {
                    last.update(embedding, 0.055f);
                }
                cancelCandidateLocked();
                commitLocked(job, lastCommittedSpeaker, "continuous-run-identity-hold",
                        lastScore, Math.max(0f, lastScore - second));
                return;
            }
        }

        // A moderate match after a pause is still safer than spawning another person immediately.
        if (best >= 0 && bestScore >= NORMAL_MATCH) {
            cancelCandidateLocked();
            PROFILES[best].update(embedding, 0.07f);
            commitLocked(job, best, "normal-known-match", bestScore, margin);
            return;
        }

        // Weak continuity shortly after the same person's prior segment can teach a second vocal
        // style (e.g. impression/register) to that person's profile.
        if (lastCommittedSpeaker >= 0 && lastCommittedSpeaker < profileCount
                && job.startVideoMs - lastCommittedEndVideoMs <= 1600L) {
            Profile last = PROFILES[lastCommittedSpeaker];
            float lastScore = last.score(embedding);
            if (lastScore >= CONTINUITY_FLOOR && bestScore < STRONG_SWITCH) {
                continuityHolds++;
                if (lastScore < NORMAL_MATCH && last.addPrototype(embedding)) impressionPrototypeAdds++;
                else last.update(embedding, 0.035f);
                cancelCandidateLocked();
                commitLocked(job, lastCommittedSpeaker, "recent-speaker-style-hold",
                        lastScore, Math.max(0f, lastScore - second));
                return;
            }
        }

        // Unknown identity: require repeated mutually-similar evidence before creating a new human.
        if (candidate == null || candidate.videoEpoch != job.videoEpoch
                || candidate.speechRunSerial != job.speechRunSerial
                || cosine(candidate.embedding, embedding) < NEW_CANDIDATE_MATCH) {
            if (candidate != null) candidateRejects++;
            candidate = new Candidate(embedding.clone(), job.videoEpoch, job.speechRunSerial,
                    job.startVideoMs, job.endVideoMs);
            candidateStarts++;
            lastDecision = "new-speaker-candidate";
            return;
        }

        candidate.count++;
        candidate.endVideoMs = job.endVideoMs;
        blendNormalized(candidate.embedding, embedding, 0.35f);
        if (candidate.count >= 2 && profileCount < MAX_PROFILES) {
            int id = createProfileLocked(candidate.embedding);
            long retroStart = candidate.startVideoMs;
            candidateConfirms++;
            candidate = null;
            Job retro = new Job(job.samples, retroStart, job.endVideoMs, job.videoEpoch,
                    job.continuityEpoch, job.speechRunSerial, true, job.generation);
            commitLocked(retro, id, "new-speaker-confirmed", bestScore, margin);
        } else {
            lastDecision = "new-speaker-candidate-repeat";
        }
    }

    private static int createProfileLocked(float[] embedding) {
        int id = profileCount;
        Profile p = new Profile(embeddingDim > 0 ? embeddingDim : embedding.length);
        p.addPrototype(embedding);
        PROFILES[id] = p;
        profileCount++;
        return id;
    }

    private static void cancelCandidateLocked() {
        if (candidate != null) candidateRejects++;
        candidate = null;
    }

    private static void commitLocked(Job job, int speaker, String reason, float similarity, float margin) {
        if (speaker < 0) return;
        assignments++;
        if (lastCommittedSpeaker >= 0 && speaker != lastCommittedSpeaker) switches++;
        appendTimelineLocked(job.startVideoMs, job.endVideoMs, speaker);
        lastCommittedSpeaker = speaker;
        lastCommittedEndVideoMs = job.endVideoMs;
        lastDecision = reason + " speaker=" + labelFor(speaker)
                + " sim=" + permille(similarity) + " margin=" + permille(margin);
        try {
            SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.SPEAKER,
                    "live speaker " + labelFor(speaker)
                            + " " + job.startVideoMs + "-" + job.endVideoMs
                            + " decision=" + reason
                            + " simPermille=" + permille(similarity)
                            + " marginPermille=" + permille(margin)
                            + " profiles=" + profileCount
                            + " prototypes=" + PROFILES[speaker].prototypeCount);
        } catch (Throwable ignored) {}
    }

    private static void appendTimelineLocked(long start, long end, int speaker) {
        if (end < start) return;
        if (timelineCount > 0) {
            int last = timelineCount - 1;
            if (TL_SPEAKER[last] == speaker && start <= TL_END[last] + 900L) {
                TL_END[last] = Math.max(TL_END[last], end);
                return;
            }
        }
        if (timelineCount >= MAX_TIMELINE) {
            System.arraycopy(TL_START, 1, TL_START, 0, MAX_TIMELINE - 1);
            System.arraycopy(TL_END, 1, TL_END, 0, MAX_TIMELINE - 1);
            System.arraycopy(TL_SPEAKER, 1, TL_SPEAKER, 0, MAX_TIMELINE - 1);
            timelineCount = MAX_TIMELINE - 1;
        }
        TL_START[timelineCount] = start;
        TL_END[timelineCount] = end;
        TL_SPEAKER[timelineCount] = speaker;
        timelineCount++;
    }

    public static String labelAtVideoMs(long videoMs) {
        synchronized (LOCK) {
            if (videoMs < 0L) return "";
            for (int i = timelineCount - 1; i >= 0; i--) {
                if (videoMs >= TL_START[i] && videoMs <= TL_END[i]) return labelFor(TL_SPEAKER[i]);
                if (videoMs > TL_END[i] && videoMs - TL_END[i] <= LIVE_HOLD_MS
                        && videoMs <= Math.max(lastSliceEndVideoMs, analyzedThroughVideoMs) + 500L) {
                    return labelFor(TL_SPEAKER[i]);
                }
                if (videoMs > TL_END[i] + LIVE_HOLD_MS) break;
            }
            return "";
        }
    }

    public static String labelDetailsAtVideoMs(long videoMs) {
        synchronized (LOCK) {
            return "live-embedding videoMs=" + videoMs
                    + " label=" + labelAtVideoMs(videoMs)
                    + " analyzedThrough=" + analyzedThroughVideoMs
                    + " inputThrough=" + lastSliceEndVideoMs
                    + " profiles=" + profileCount
                    + " decision=" + lastDecision;
        }
    }

    public static String diagnostics() {
        synchronized (LOCK) {
            StringBuilder p = new StringBuilder();
            for (int i = 0; i < profileCount; i++) {
                if (i > 0) p.append(',');
                Profile profile = PROFILES[i];
                p.append(labelFor(i)).append(':').append(profile == null ? 0 : profile.prototypeCount);
            }
            return "speakerLiveMode=eres2net-short-window-online-human-identity-v23331\n"
                    + "speakerLiveWindowMs=2000\n"
                    + "speakerLiveHopMs=750\n"
                    + "speakerLiveLatestWins=true\n"
                    + "speakerLiveIdentityPolicy=multi-prototype+continuous-run-inertia+two-window-new-person-confirm\n"
                    + "speakerLiveImpressionPolicy=continuous-style-change-stays-human-and-may-add-prototype\n"
                    + "speakerLiveInitState=" + stateName(initState) + "\n"
                    + "speakerLiveInitMs=" + initMs + "\n"
                    + "speakerLiveInitError=" + initError + "\n"
                    + "speakerLiveEmbeddingDim=" + embeddingDim + "\n"
                    + "speakerLiveOwnerVideoEpoch=" + ownerVideoEpoch + "\n"
                    + "speakerLiveOwnerContinuityEpoch=" + ownerContinuityEpoch + "\n"
                    + "speakerLiveProfiles=" + profileCount + "\n"
                    + "speakerLiveProfilePrototypes=" + (p.length() == 0 ? "none" : p.toString()) + "\n"
                    + "speakerLiveJobsQueued=" + jobsQueued + "\n"
                    + "speakerLiveJobsDroppedLatestWins=" + jobsDroppedLatestWins + "\n"
                    + "speakerLiveJobsStarted=" + jobsStarted + "\n"
                    + "speakerLiveJobsCompleted=" + jobsCompleted + "\n"
                    + "speakerLiveJobsNotReady=" + jobsNotReady + "\n"
                    + "speakerLiveJobsFailed=" + jobsFailed + "\n"
                    + "speakerLiveWorkerBusy=" + workerBusy + "\n"
                    + "speakerLiveLastInferenceMs=" + lastInferenceMs + "\n"
                    + "speakerLiveMaxInferenceMs=" + maxInferenceMs + "\n"
                    + "speakerLiveInputThroughVideoMs=" + lastSliceEndVideoMs + "\n"
                    + "speakerLiveAnalyzedThroughVideoMs=" + analyzedThroughVideoMs + "\n"
                    + "speakerLiveLagMs=" + (lastSliceEndVideoMs >= 0 && analyzedThroughVideoMs >= 0
                        ? Math.max(0L, lastSliceEndVideoMs - analyzedThroughVideoMs) : -1L) + "\n"
                    + "speakerLiveAssignments=" + assignments + "\n"
                    + "speakerLiveSwitches=" + switches + "\n"
                    + "speakerLiveContinuityHolds=" + continuityHolds + "\n"
                    + "speakerLiveImpressionPrototypeAdds=" + impressionPrototypeAdds + "\n"
                    + "speakerLiveCandidateStarts=" + candidateStarts + "\n"
                    + "speakerLiveCandidateConfirms=" + candidateConfirms + "\n"
                    + "speakerLiveCandidateRejects=" + candidateRejects + "\n"
                    + "speakerLiveLastBestSimilarityPermille=" + permille(lastBestSimilarity) + "\n"
                    + "speakerLiveLastSecondSimilarityPermille=" + permille(lastSecondSimilarity) + "\n"
                    + "speakerLiveLastMarginPermille=" + permille(lastMargin) + "\n"
                    + "speakerLiveLastDecision=" + lastDecision + "\n"
                    + "speakerLiveTimelineSegments=" + timelineCount + "\n"
                    + "speakerLiveCurrent=" + (lastCommittedSpeaker >= 0 ? labelFor(lastCommittedSpeaker) : "none");
        }
    }

    private static void normalize(float[] v) {
        if (v == null) return;
        double sum = 0.0;
        for (float x : v) sum += x * x;
        double n = Math.sqrt(sum);
        if (n <= 1e-9) return;
        for (int i = 0; i < v.length; i++) v[i] = (float) (v[i] / n);
    }

    private static float cosine(float[] a, float[] b) {
        if (a == null || b == null) return -1f;
        int n = Math.min(a.length, b.length);
        double dot = 0.0;
        for (int i = 0; i < n; i++) dot += a[i] * b[i];
        return (float) dot; // both normalized
    }

    private static void blendNormalized(float[] dst, float[] src, float alpha) {
        int n = Math.min(dst.length, src.length);
        float keep = 1f - alpha;
        for (int i = 0; i < n; i++) dst[i] = keep * dst[i] + alpha * src[i];
        normalize(dst);
    }

    private static int permille(float v) {
        return Math.round(v * 1000f);
    }

    private static String labelFor(int id) {
        if (id >= 0 && id < 26) return String.valueOf((char) ('A' + id));
        return "S" + id;
    }

    private static String stateName(int s) {
        switch (s) {
            case 0: return "idle";
            case 1: return "starting";
            case 2: return "ready";
            case 3: return "failed";
            default: return "unknown-" + s;
        }
    }

    private static String describe(Throwable t) {
        if (t == null) return "unknown";
        Throwable root = t;
        while (root.getCause() != null && root.getCause() != root) root = root.getCause();
        String msg = root.getMessage();
        return root.getClass().getSimpleName() + (msg == null || msg.isEmpty() ? "" : ": " + msg);
    }

    private static final class Job {
        final float[] samples;
        final long startVideoMs;
        final long endVideoMs;
        final long videoEpoch;
        final long continuityEpoch;
        final long speechRunSerial;
        final boolean firstInSpeechRun;
        final long generation;

        Job(float[] samples, long startVideoMs, long endVideoMs, long videoEpoch,
            long continuityEpoch, long speechRunSerial, boolean firstInSpeechRun, long generation) {
            this.samples = samples;
            this.startVideoMs = startVideoMs;
            this.endVideoMs = endVideoMs;
            this.videoEpoch = videoEpoch;
            this.continuityEpoch = continuityEpoch;
            this.speechRunSerial = speechRunSerial;
            this.firstInSpeechRun = firstInSpeechRun;
            this.generation = generation;
        }
    }

    private static final class Candidate {
        final float[] embedding;
        final long videoEpoch;
        final long speechRunSerial;
        final long startVideoMs;
        long endVideoMs;
        int count = 1;

        Candidate(float[] embedding, long videoEpoch, long speechRunSerial,
                  long startVideoMs, long endVideoMs) {
            this.embedding = embedding;
            this.videoEpoch = videoEpoch;
            this.speechRunSerial = speechRunSerial;
            this.startVideoMs = startVideoMs;
            this.endVideoMs = endVideoMs;
        }
    }

    private static final class Profile {
        final float[][] prototypes;
        int prototypeCount;

        Profile(int dim) {
            prototypes = new float[MAX_PROTOTYPES][dim];
        }

        float score(float[] embedding) {
            float best = -1f;
            for (int i = 0; i < prototypeCount; i++) {
                float s = cosine(prototypes[i], embedding);
                if (s > best) best = s;
            }
            return best;
        }

        boolean addPrototype(float[] embedding) {
            if (prototypeCount >= MAX_PROTOTYPES) return false;
            int n = Math.min(prototypes[prototypeCount].length, embedding.length);
            System.arraycopy(embedding, 0, prototypes[prototypeCount], 0, n);
            normalize(prototypes[prototypeCount]);
            prototypeCount++;
            return true;
        }

        void update(float[] embedding, float alpha) {
            if (prototypeCount == 0) {
                addPrototype(embedding);
                return;
            }
            int best = 0;
            float score = -1f;
            for (int i = 0; i < prototypeCount; i++) {
                float s = cosine(prototypes[i], embedding);
                if (s > score) { score = s; best = i; }
            }
            blendNormalized(prototypes[best], embedding, alpha);
        }
    }
}
