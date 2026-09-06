package app.spanishstudy.vot;

import android.app.Activity;
import android.media.AudioTrack;

import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

import app.morphe.extension.youtube.patches.voiceovertranslation.TranscriptSegment;

/**
 * Zero-API-cost local speaker diarization probe using YouTube's decoded PCM directly.
 *
 * v2.32 deliberately abandons Android Visualizer. A bytecode hook copies a small slice of the
 * ByteBuffer immediately before ExoPlayer writes it to AudioTrack. The playback buffer itself is
 * never modified. Feature extraction runs on one bounded background worker so the audio thread is
 * not blocked. Assignments remain anonymous A/B/C/D labels and do not identify real people.
 */
public final class LocalSpeakerDiarizer {
    private static final Object LOCK = new Object();
    private static final int MIN_FRAMES = 5;
    private static final int PROVISIONAL_FRAMES = 7;
    private static final int MAX_SPEAKERS = 4;
    private static final double SECOND_SPEAKER_THRESHOLD = 0.86;
    private static final double EXTRA_SPEAKER_THRESHOLD = 0.76;
    private static final int MAX_COPY_BYTES = 8192;
    private static final long CAPTURE_INTERVAL_NS = 45_000_000L;

    private static final ThreadPoolExecutor PCM_EXECUTOR = new ThreadPoolExecutor(
            1, 1, 0L, TimeUnit.MILLISECONDS,
            new ArrayBlockingQueue<>(4),
            r -> {
                Thread t = new Thread(r, "SpanishStudyPcmSpeaker");
                t.setDaemon(true);
                return t;
            },
            new ThreadPoolExecutor.DiscardOldestPolicy());

    private static volatile boolean enabled = true;
    private static volatile long playheadMs;
    private static volatile long lastCaptureNs;
    private static volatile int audioSessionId = -1;
    private static volatile int sampleRateHz;
    private static volatile int channelCount;
    private static volatile int pcmEncoding;
    private static volatile boolean supportedPcm;

    private static List<TranscriptSegment> sourceSegments = new ArrayList<>();
    private static final Map<Integer, SegmentAccumulator> accumulators = new HashMap<>();
    private static final Map<Integer, Assignment> assignments = new HashMap<>();
    private static final List<SpeakerProfile> speakers = new ArrayList<>();

    private static long audioTrackObservations;
    private static long pcmHookCalls;
    private static long pcmBytesCopied;
    private static long pcmChunksQueued;
    private static long pcmChunksAnalyzed;
    private static long pcmVoicedFrames;
    private static long pcmUnsupportedBuffers;
    private static long finalizedSegments;
    private static long provisionalAssignments;
    private static long committedAssignments;
    private static long speakersCreated;
    private static String lastCaptureDecision = "none";
    private static String lastDecision = "none";
    private static double lastRms;
    private static double lastPitchHz;
    private static double lastPitchConfidence;

    private LocalSpeakerDiarizer() {}

    /** Existing Morphe AudioTrack constructor hook. Records the format used by direct PCM analysis. */
    public static void onAudioTrack(AudioTrack track) {
        if (track == null) return;
        int session = -1, rate = 0, channels = 0, encoding = 0;
        try {
            session = track.getAudioSessionId();
            rate = track.getSampleRate();
            channels = track.getChannelCount();
            encoding = track.getAudioFormat();
        } catch (Throwable ex) {
            SpanishStudyDiagnostics.error(SpanishStudyDiagnostics.AUDIO,
                    "AudioTrack PCM metadata failed", ex);
        }
        audioTrackObservations++;
        audioSessionId = session;
        if (rate > 0) sampleRateHz = rate;
        if (channels > 0) channelCount = channels;
        if (encoding > 0) pcmEncoding = encoding;
        supportedPcm = isSupportedEncoding(pcmEncoding) && sampleRateHz >= 8000 && channelCount > 0;
        SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.AUDIO,
                "AudioTrack observed session=" + session + " sampleRate=" + rate
                        + " channels=" + channels + " encoding=" + encoding
                        + " directPcmSupported=" + supportedPcm);
    }

    /**
     * Injection point immediately before AudioTrack.write(ByteBuffer,int,int).
     * Copies at most 8 KiB from a duplicate buffer; the original ByteBuffer position/data are intact.
     */
    public static void onPcmBuffer(ByteBuffer buffer, int requestedBytes) {
        pcmHookCalls++;
        if (!enabled || buffer == null || requestedBytes <= 0) return;
        if (!supportedPcm) {
            pcmUnsupportedBuffers++;
            return;
        }
        long now = System.nanoTime();
        if (now - lastCaptureNs < CAPTURE_INTERVAL_NS) return;
        lastCaptureNs = now;

        final byte[] copy;
        try {
            ByteBuffer dup = buffer.duplicate();
            int bytes = Math.min(Math.min(requestedBytes, dup.remaining()), MAX_COPY_BYTES);
            int frameBytes = bytesPerSample(pcmEncoding) * Math.max(1, channelCount);
            if (frameBytes <= 0) return;
            bytes -= bytes % frameBytes;
            if (bytes < frameBytes * 256) return;
            copy = new byte[bytes];
            dup.get(copy);
        } catch (Throwable ex) {
            pcmUnsupportedBuffers++;
            lastCaptureDecision = "copy-error:" + ex.getClass().getSimpleName();
            return;
        }

        final int sr = sampleRateHz;
        final int channels = channelCount;
        final int encoding = pcmEncoding;
        final long capturedVideoMs = playheadMs;
        pcmBytesCopied += copy.length;
        pcmChunksQueued++;
        try {
            PCM_EXECUTOR.execute(() -> processPcm(copy, sr, channels, encoding, capturedVideoMs));
        } catch (Throwable ignored) {
            // Never let diagnostics interfere with the playback thread.
        }
    }

    static void setEnabled(Activity activity, boolean value) {
        enabled = value;
        SpanishStudyDiagnostics.recordAlways(SpanishStudyDiagnostics.SPEAKER,
                value ? "direct PCM speaker experiment enabled" : "direct PCM speaker experiment disabled");
    }

    static void setSourceSegments(List<TranscriptSegment> segments) {
        synchronized (LOCK) {
            sourceSegments = segments == null ? new ArrayList<>() : new ArrayList<>(segments);
            accumulators.clear();
            assignments.clear();
            speakers.clear();
            finalizedSegments = 0;
            provisionalAssignments = 0;
            committedAssignments = 0;
            speakersCreated = 0;
            lastDecision = "none";
        }
        SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.SPEAKER,
                "source timeline installed segments=" + sourceSegments.size());
    }

    static void updatePlayhead(long timeMs) {
        playheadMs = timeMs;
        synchronized (LOCK) {
            for (Map.Entry<Integer, SegmentAccumulator> e : new ArrayList<>(accumulators.entrySet())) {
                int index = e.getKey();
                if (index < 0 || index >= sourceSegments.size()) continue;
                TranscriptSegment seg = sourceSegments.get(index);
                if (!e.getValue().finalized && timeMs > seg.endMs + 250) {
                    finalizeAccumulator(index, e.getValue());
                }
            }
        }
    }

    static void resetForVideo() {
        synchronized (LOCK) {
            sourceSegments = new ArrayList<>();
            accumulators.clear();
            assignments.clear();
            speakers.clear();
            playheadMs = 0;
            lastDecision = "none";
            lastCaptureDecision = "none";
            lastRms = lastPitchHz = lastPitchConfidence = 0;
        }
        SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.SPEAKER, "speaker timeline reset");
    }

    static String labelForSegment(int index) {
        synchronized (LOCK) {
            Assignment a = assignments.get(index);
            return a == null ? "" : String.valueOf((char) ('A' + a.speaker));
        }
    }

    static String assignmentDetails(int index) {
        synchronized (LOCK) {
            Assignment a = assignments.get(index);
            if (a == null) return "none";
            return formatAssignment(a);
        }
    }

    static String profilesSummary() {
        synchronized (LOCK) {
            if (speakers.isEmpty()) return "none yet";
            int[] counts = new int[speakers.size()];
            for (Assignment a : assignments.values()) {
                if (a.committed && a.speaker >= 0 && a.speaker < counts.length) counts[a.speaker]++;
            }
            StringBuilder out = new StringBuilder();
            for (int i = 0; i < speakers.size(); i++) {
                if (i > 0) out.append(", ");
                out.append((char) ('A' + i)).append(" (").append(counts[i]).append(')');
            }
            return out.toString();
        }
    }

    static String diagnostics() {
        synchronized (LOCK) {
            boolean captureAvailable = supportedPcm && pcmHookCalls > 0;
            StringBuilder out = new StringBuilder();
            out.append("speakerBackend=direct-exoplayer-pcm-local-spectral-clustering-experiment\n");
            out.append("speakerApiCostUsd=0.000000\n");
            out.append("speakerMicrophoneAccess=none-direct-decoded-playback-pcm\n");
            out.append("speakerVoiceRouting=disabled-diagnostic-labels-only\n");
            out.append("speakerExperimentEnabled=").append(enabled).append('\n');
            out.append("speakerCaptureAvailable=").append(captureAvailable).append('\n');
            out.append("speakerAudioSession=").append(audioSessionId).append('\n');
            out.append("speakerSamplingRateHz=").append(sampleRateHz).append('\n');
            out.append("speakerChannelCount=").append(channelCount).append('\n');
            out.append("speakerPcmEncoding=").append(pcmEncoding).append('\n');
            out.append("speakerAudioTrackObservations=").append(audioTrackObservations).append('\n');
            out.append("speakerPcmHookCalls=").append(pcmHookCalls).append('\n');
            out.append("speakerPcmBytesCopied=").append(pcmBytesCopied).append('\n');
            out.append("speakerPcmChunksQueued=").append(pcmChunksQueued).append('\n');
            out.append("speakerPcmChunksAnalyzed=").append(pcmChunksAnalyzed).append('\n');
            out.append("speakerPcmVoicedFrames=").append(pcmVoicedFrames).append('\n');
            out.append("speakerPcmUnsupportedBuffers=").append(pcmUnsupportedBuffers).append('\n');
            out.append("speakerFinalizedSegments=").append(finalizedSegments).append('\n');
            out.append("speakerProvisionalAssignments=").append(provisionalAssignments).append('\n');
            out.append("speakerCommittedAssignments=").append(committedAssignments).append('\n');
            out.append("speakerClustersCreated=").append(speakersCreated).append('\n');
            out.append("speakerProfiles=").append(profilesSummary()).append('\n');
            out.append("speakerLastRms=").append(String.format(Locale.US, "%.4f", lastRms)).append('\n');
            out.append("speakerLastPitchHz=").append(String.format(Locale.US, "%.1f", lastPitchHz)).append('\n');
            out.append("speakerLastPitchConfidence=").append(String.format(Locale.US, "%.3f", lastPitchConfidence)).append('\n');
            out.append("speakerLastCaptureDecision=").append(lastCaptureDecision).append('\n');
            out.append("speakerLastDecision=").append(lastDecision).append('\n');
            return out.toString();
        }
    }

    private static void processPcm(byte[] pcm, int sr, int channels, int encoding, long timeMs) {
        PcmSpeakerFeature.Result result = PcmSpeakerFeature.analyze(pcm, sr, channels, encoding);
        pcmChunksAnalyzed++;
        if (result == null) {
            lastCaptureDecision = "silence-or-unsupported-feature-frame";
            return;
        }
        lastRms = result.rms;
        lastPitchHz = result.pitchHz;
        lastPitchConfidence = result.pitchConfidence;

        int segmentIndex;
        synchronized (LOCK) {
            segmentIndex = findSourceSegment(timeMs);
            if (segmentIndex < 0) {
                lastCaptureDecision = "no-source-segment@" + timeMs;
                return;
            }
            pcmVoicedFrames++;
            SegmentAccumulator acc = accumulators.computeIfAbsent(segmentIndex,
                    key -> new SegmentAccumulator());
            acc.add(result.feature);
            lastCaptureDecision = "segment=" + segmentIndex + " frames=" + acc.frames;
            if (!acc.finalized && acc.frames == PROVISIONAL_FRAMES) {
                Assignment a = classify(acc.mean(), acc.frames, false);
                assignments.put(segmentIndex, a);
                provisionalAssignments++;
                SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.SPEAKER,
                        "provisional segment=" + segmentIndex + " -> " + formatAssignment(a));
            }
        }
    }

    private static int findSourceSegment(long timeMs) {
        for (int i = 0; i < sourceSegments.size(); i++) {
            TranscriptSegment s = sourceSegments.get(i);
            if (timeMs >= s.startMs && timeMs < s.endMs) return i;
            if (s.startMs > timeMs) break;
        }
        return -1;
    }

    private static void finalizeAccumulator(int index, SegmentAccumulator acc) {
        if (acc.finalized) return;
        acc.finalized = true;
        finalizedSegments++;
        if (acc.frames < MIN_FRAMES) {
            assignments.remove(index);
            SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.SPEAKER,
                    "segment=" + index + " insufficient PCM frames=" + acc.frames);
            return;
        }
        Assignment a = classify(acc.mean(), acc.frames, true);
        assignments.put(index, a);
        committedAssignments++;
        SpanishStudyDiagnostics.recordAlways(SpanishStudyDiagnostics.SPEAKER,
                "commit segment=" + index + " -> " + formatAssignment(a));
    }

    private static Assignment classify(double[] feature, int frames, boolean commit) {
        if (speakers.isEmpty()) {
            if (commit) createSpeaker(feature);
            return new Assignment(0, 1.0, 1.0, frames, commit);
        }

        int bestSpeaker = 0;
        double best = -1;
        for (int i = 0; i < speakers.size(); i++) {
            double similarity = similarity(feature, speakers.get(i).centroid);
            if (similarity > best) {
                best = similarity;
                bestSpeaker = i;
            }
        }

        double threshold = speakers.size() == 1 ? SECOND_SPEAKER_THRESHOLD : EXTRA_SPEAKER_THRESHOLD;
        boolean create = best < threshold && speakers.size() < MAX_SPEAKERS;
        int chosen = create ? speakers.size() : bestSpeaker;
        double confidence = create ? Math.max(0.55, 1.0 - best) : Math.max(0, Math.min(1, best));

        if (commit) {
            if (create) createSpeaker(feature);
            else speakers.get(chosen).update(feature);
        }

        lastDecision = String.format(Locale.US,
                "speaker=%c bestExisting=%c similarity=%.3f threshold=%.3f create=%s frames=%d",
                (char) ('A' + chosen), (char) ('A' + bestSpeaker), best, threshold, create, frames);
        return new Assignment(chosen, best, confidence, frames, commit);
    }

    private static void createSpeaker(double[] feature) {
        speakers.add(new SpeakerProfile(feature));
        speakersCreated++;
        SpanishStudyDiagnostics.recordAlways(SpanishStudyDiagnostics.SPEAKER,
                "created cluster=" + (char) ('A' + speakers.size() - 1)
                        + " totalClusters=" + speakers.size());
    }

    private static double similarity(double[] a, double[] b) {
        int spectralDims = PcmSpeakerFeature.SPECTRAL_DIMS;
        double dot = 0, na = 0, nb = 0;
        for (int i = 0; i < spectralDims; i++) {
            dot += a[i] * b[i];
            na += a[i] * a[i];
            nb += b[i] * b[i];
        }
        double spectral = dot / Math.sqrt(Math.max(1e-9, na * nb));
        spectral = (spectral + 1.0) / 2.0;

        double pitchWeight = Math.min(a[spectralDims + 1], b[spectralDims + 1]);
        double pitchSimilarity = Math.exp(-2.5 * Math.abs(a[spectralDims] - b[spectralDims]));
        double zcrSimilarity = Math.exp(-1.5 * Math.abs(a[spectralDims + 2] - b[spectralDims + 2]));
        double centroidSimilarity = Math.exp(-2.0 * Math.abs(a[spectralDims + 3] - b[spectralDims + 3]));
        double pitchPart = pitchWeight * pitchSimilarity + (1.0 - pitchWeight) * 0.5;
        return 0.70 * spectral + 0.17 * pitchPart + 0.07 * zcrSimilarity + 0.06 * centroidSimilarity;
    }

    private static boolean isSupportedEncoding(int encoding) {
        return encoding == PcmSpeakerFeature.ENCODING_PCM_16BIT
                || encoding == PcmSpeakerFeature.ENCODING_PCM_8BIT
                || encoding == PcmSpeakerFeature.ENCODING_PCM_FLOAT;
    }

    private static int bytesPerSample(int encoding) {
        if (encoding == PcmSpeakerFeature.ENCODING_PCM_16BIT) return 2;
        if (encoding == PcmSpeakerFeature.ENCODING_PCM_8BIT) return 1;
        if (encoding == PcmSpeakerFeature.ENCODING_PCM_FLOAT) return 4;
        return 0;
    }

    private static String formatAssignment(Assignment a) {
        return String.format(Locale.US, "%c similarity=%.3f confidence=%.3f frames=%d committed=%s",
                (char) ('A' + a.speaker), a.similarity, a.confidence, a.frames, a.committed);
    }

    private static final class SegmentAccumulator {
        final double[] sum = new double[PcmSpeakerFeature.FEATURE_DIMS];
        int frames;
        boolean finalized;
        void add(double[] f) {
            for (int i = 0; i < sum.length; i++) sum[i] += f[i];
            frames++;
        }
        double[] mean() {
            double[] out = new double[sum.length];
            for (int i = 0; i < out.length; i++) out[i] = sum[i] / Math.max(1, frames);
            return out;
        }
    }

    private static final class SpeakerProfile {
        double[] centroid;
        int observations = 1;
        SpeakerProfile(double[] feature) { centroid = feature.clone(); }
        void update(double[] feature) {
            observations++;
            double alpha = 1.0 / Math.min(10, observations);
            for (int i = 0; i < centroid.length; i++) {
                centroid[i] = centroid[i] * (1.0 - alpha) + feature[i] * alpha;
            }
        }
    }

    private static final class Assignment {
        final int speaker;
        final double similarity;
        final double confidence;
        final int frames;
        final boolean committed;
        Assignment(int speaker, double similarity, double confidence, int frames, boolean committed) {
            this.speaker = speaker;
            this.similarity = similarity;
            this.confidence = confidence;
            this.frames = frames;
            this.committed = committed;
        }
    }
}
