package app.spanishstudy.vot;

import android.app.Activity;
import android.media.AudioTrack;
import android.media.audiofx.Visualizer;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

import app.morphe.extension.shared.Utils;
import app.morphe.extension.youtube.patches.voiceovertranslation.TranscriptSegment;

/**
 * Zero-API-cost speaker diarization experiment.
 *
 * It attaches Android's read-only Visualizer to YouTube's AudioTrack session, extracts a small
 * spectral/pitch feature vector during caption speech windows, and clusters caption segments into
 * anonymous A/B/C/D profiles. It does not use the microphone and does not identify real people.
 *
 * This deliberately does NOT route TTS voices yet: v2.28 is intended to prove capture and speaker
 * separation without changing stock Morphe speech output.
 */
public final class LocalSpeakerDiarizer {
    private static final Object LOCK = new Object();
    private static final int MIN_FRAMES = 5;
    private static final int PROVISIONAL_FRAMES = 7;
    private static final int MAX_SPEAKERS = 4;
    private static final double SECOND_SPEAKER_THRESHOLD = 0.86;
    private static final double EXTRA_SPEAKER_THRESHOLD = 0.76;

    // Log-frequency-ish speech bands in Hz. Visualizer FFT is low fidelity but useful as a probe.
    private static final double[] BAND_EDGES = {
            80, 150, 250, 400, 600, 900, 1300, 1800, 2500, 3400, 4500, 6000
    };
    private static final int SPECTRAL_DIMS = BAND_EDGES.length - 1;
    private static final int FEATURE_DIMS = SPECTRAL_DIMS + 4;

    private static Visualizer visualizer;
    private static int attachedSessionId = -1;
    private static int captureSize;
    private static int captureRate;
    private static volatile long playheadMs;
    private static volatile boolean enabled = true;

    private static List<TranscriptSegment> sourceSegments = new ArrayList<>();
    private static final Map<Integer, SegmentAccumulator> accumulators = new HashMap<>();
    private static final Map<Integer, Assignment> assignments = new HashMap<>();
    private static final List<SpeakerProfile> speakers = new ArrayList<>();

    private static double lastRms;
    private static double lastZcr;
    private static double lastPitchNorm;
    private static double lastPitchConfidence;

    private static long attachAttempts;
    private static long attachSucceeded;
    private static long attachFailed;
    private static long waveformCallbacks;
    private static long fftCallbacks;
    private static long voicedFftFrames;
    private static long finalizedSegments;
    private static long provisionalAssignments;
    private static long committedAssignments;
    private static long speakersCreated;
    private static String lastAttachError = "none";
    private static String lastDecision = "none";
    private static int lastSamplingRateHz;

    private LocalSpeakerDiarizer() {}

    /** Called from Morphe's existing AudioTrack wrapper hook. Safe from any thread. */
    public static void onAudioTrack(AudioTrack track) {
        if (track == null) return;
        final int sessionId;
        final int sampleRate;
        try {
            sessionId = track.getAudioSessionId();
            sampleRate = track.getSampleRate();
        } catch (Exception ex) {
            SpanishStudyDiagnostics.error(SpanishStudyDiagnostics.AUDIO,
                    "AudioTrack metadata failed", ex);
            return;
        }
        SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.AUDIO,
                "AudioTrack observed session=" + sessionId + " sampleRate=" + sampleRate);
        Utils.runOnMainThread(() -> attach(sessionId, sampleRate));
    }

    static void setEnabled(Activity activity, boolean value) {
        enabled = value;
        if (!value) {
            Utils.runOnMainThread(LocalSpeakerDiarizer::releaseVisualizer);
            SpanishStudyDiagnostics.recordAlways(SpanishStudyDiagnostics.SPEAKER,
                    "local speaker experiment disabled");
        } else {
            SpanishStudyDiagnostics.recordAlways(SpanishStudyDiagnostics.SPEAKER,
                    "local speaker experiment enabled; waiting for AudioTrack observation");
        }
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
        // Finalize any accumulator whose source segment is safely behind the playhead.
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
            lastRms = lastZcr = lastPitchNorm = lastPitchConfidence = 0;
        }
        SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.SPEAKER,
                "speaker timeline reset");
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
            return String.format(Locale.US, "%c similarity=%.3f confidence=%.3f frames=%d committed=%s",
                    (char) ('A' + a.speaker), a.similarity, a.confidence, a.frames, a.committed);
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
            StringBuilder out = new StringBuilder();
            out.append("speakerBackend=android-visualizer-local-spectral-clustering-experiment\n");
            out.append("speakerApiCostUsd=0.000000\n");
            out.append("speakerMicrophoneAccess=none-audiotrack-session-only\n");
            out.append("speakerVoiceRouting=disabled-diagnostic-labels-only\n");
            out.append("speakerExperimentEnabled=").append(enabled).append('\n');
            out.append("speakerAudioSession=").append(attachedSessionId).append('\n');
            out.append("speakerCaptureSize=").append(captureSize).append('\n');
            out.append("speakerCaptureRateMilliHz=").append(captureRate).append('\n');
            out.append("speakerSamplingRateHz=").append(lastSamplingRateHz).append('\n');
            out.append("speakerAttachAttempts=").append(attachAttempts).append('\n');
            out.append("speakerAttachSucceeded=").append(attachSucceeded).append('\n');
            out.append("speakerAttachFailed=").append(attachFailed).append('\n');
            out.append("speakerWaveformCallbacks=").append(waveformCallbacks).append('\n');
            out.append("speakerFftCallbacks=").append(fftCallbacks).append('\n');
            out.append("speakerVoicedFftFrames=").append(voicedFftFrames).append('\n');
            out.append("speakerFinalizedSegments=").append(finalizedSegments).append('\n');
            out.append("speakerProvisionalAssignments=").append(provisionalAssignments).append('\n');
            out.append("speakerCommittedAssignments=").append(committedAssignments).append('\n');
            out.append("speakerClustersCreated=").append(speakersCreated).append('\n');
            out.append("speakerProfiles=").append(profilesSummary()).append('\n');
            out.append("speakerLastDecision=").append(lastDecision).append('\n');
            out.append("speakerLastAttachError=").append(lastAttachError).append('\n');
            return out.toString();
        }
    }

    private static void attach(int sessionId, int trackSampleRate) {
        if (!enabled) return;
        Activity activity = Utils.getActivity();
        if (activity == null || activity.isFinishing()) {
            SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.AUDIO,
                    "Visualizer attach deferred: no activity");
            return;
        }
        if (!SpanishStudyPrefs.speakerExperiment(activity)) return;
        if (sessionId <= 0) {
            SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.AUDIO,
                    "Visualizer attach skipped invalid session=" + sessionId);
            return;
        }
        synchronized (LOCK) {
            if (visualizer != null && attachedSessionId == sessionId) return;
            attachAttempts++;
        }
        releaseVisualizer();
        try {
            Visualizer v = new Visualizer(sessionId);
            int[] range = Visualizer.getCaptureSizeRange();
            int wanted = range != null && range.length >= 2 ? Math.min(1024, range[1]) : 1024;
            if (range != null && range.length >= 2) wanted = Math.max(range[0], wanted);
            v.setCaptureSize(wanted);
            int rate = Math.max(1000, Visualizer.getMaxCaptureRate() / 2);
            int listenerStatus = v.setDataCaptureListener(new Visualizer.OnDataCaptureListener() {
                @Override
                public void onWaveFormDataCapture(Visualizer visualizer, byte[] waveform, int samplingRate) {
                    processWaveform(waveform, samplingRate);
                }

                @Override
                public void onFftDataCapture(Visualizer visualizer, byte[] fft, int samplingRate) {
                    processFft(fft, samplingRate);
                }
            }, rate, true, true);
            if (listenerStatus != Visualizer.SUCCESS) {
                throw new IllegalStateException("setDataCaptureListener status=" + listenerStatus);
            }
            int enableStatus = v.setEnabled(true);
            if (enableStatus != Visualizer.SUCCESS) {
                throw new IllegalStateException("setEnabled status=" + enableStatus);
            }
            synchronized (LOCK) {
                visualizer = v;
                attachedSessionId = sessionId;
                captureSize = wanted;
                captureRate = rate;
                lastSamplingRateHz = trackSampleRate;
                attachSucceeded++;
                lastAttachError = "none";
            }
            SpanishStudyDiagnostics.recordAlways(SpanishStudyDiagnostics.AUDIO,
                    "Visualizer attached session=" + sessionId + " captureSize=" + wanted
                            + " rateMilliHz=" + rate + " trackSampleRate=" + trackSampleRate);
        } catch (Throwable ex) {
            synchronized (LOCK) {
                attachFailed++;
                lastAttachError = ex.getClass().getSimpleName() + ": " + String.valueOf(ex.getMessage());
            }
            SpanishStudyDiagnostics.error(SpanishStudyDiagnostics.AUDIO,
                    "Visualizer attach failed session=" + sessionId
                            + " (RECORD_AUDIO permission/effect availability are common causes)", ex);
        }
    }

    private static void releaseVisualizer() {
        Visualizer old;
        synchronized (LOCK) {
            old = visualizer;
            visualizer = null;
            attachedSessionId = -1;
        }
        if (old != null) {
            try { old.setEnabled(false); } catch (Throwable ignored) {}
            try { old.release(); } catch (Throwable ignored) {}
            SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.AUDIO,
                    "Visualizer released");
        }
    }

    private static void processWaveform(byte[] waveform, int samplingRateRaw) {
        if (!enabled || waveform == null || waveform.length < 64) return;
        waveformCallbacks++;
        double sr = normalizeSampleRate(samplingRateRaw);
        if (sr > 1000) lastSamplingRateHz = (int) Math.round(sr);

        double mean = 0;
        for (byte b : waveform) mean += ((b & 0xff) - 128) / 128.0;
        mean /= waveform.length;
        double sum = 0;
        int zeroCross = 0;
        double prev = ((waveform[0] & 0xff) - 128) / 128.0 - mean;
        double[] x = new double[waveform.length];
        for (int i = 0; i < waveform.length; i++) {
            double value = ((waveform[i] & 0xff) - 128) / 128.0 - mean;
            x[i] = value;
            sum += value * value;
            if (i > 0 && ((value >= 0) != (prev >= 0))) zeroCross++;
            prev = value;
        }
        lastRms = Math.sqrt(sum / waveform.length);
        lastZcr = zeroCross / (double) Math.max(1, waveform.length - 1);

        // Very small autocorrelation pitch cue. It is intentionally only one feature, not identity.
        lastPitchNorm = 0;
        lastPitchConfidence = 0;
        if (sr >= 8000 && lastRms > 0.02) {
            int minLag = Math.max(2, (int) (sr / 350.0));
            int maxLag = Math.min(waveform.length / 2, (int) (sr / 70.0));
            double best = 0;
            int bestLag = 0;
            for (int lag = minLag; lag <= maxLag; lag += 2) {
                double num = 0, a = 0, b = 0;
                for (int i = 0; i + lag < x.length; i++) {
                    double p = x[i], q = x[i + lag];
                    num += p * q;
                    a += p * p;
                    b += q * q;
                }
                double corr = num / Math.sqrt(Math.max(1e-12, a * b));
                if (corr > best) { best = corr; bestLag = lag; }
            }
            if (bestLag > 0) {
                double pitch = sr / bestLag;
                double low = Math.log(70), high = Math.log(350);
                lastPitchNorm = Math.max(-1, Math.min(1,
                        2.0 * ((Math.log(Math.max(70, Math.min(350, pitch))) - low) / (high - low)) - 1.0));
                lastPitchConfidence = Math.max(0, Math.min(1, best));
            }
        }
    }

    private static void processFft(byte[] fft, int samplingRateRaw) {
        if (!enabled || fft == null || fft.length < 32) return;
        fftCallbacks++;
        // Skip silence/near-silence and do not invent speaker evidence from it.
        if (lastRms < 0.018) return;

        final long timeMs = playheadMs;
        int segmentIndex;
        synchronized (LOCK) {
            segmentIndex = findSourceSegment(timeMs);
        }
        if (segmentIndex < 0) return;

        double sr = normalizeSampleRate(samplingRateRaw);
        if (sr < 1000) sr = lastSamplingRateHz > 1000 ? lastSamplingRateHz : 48000;
        lastSamplingRateHz = (int) Math.round(sr);
        double[] feature = fftFeature(fft, sr);
        if (feature == null) return;

        synchronized (LOCK) {
            voicedFftFrames++;
            SegmentAccumulator acc = accumulators.computeIfAbsent(segmentIndex,
                    key -> new SegmentAccumulator());
            acc.add(feature);
            if (!acc.finalized && acc.frames == PROVISIONAL_FRAMES) {
                Assignment a = classify(acc.mean(), acc.frames, false);
                assignments.put(segmentIndex, a);
                provisionalAssignments++;
                SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.SPEAKER,
                        "provisional segment=" + segmentIndex + " -> " + formatAssignment(a));
            }
        }
    }

    private static double[] fftFeature(byte[] fft, double sampleRateHz) {
        int n = fft.length;
        int bins = n / 2;
        if (bins < 8) return null;
        double hzPerBin = sampleRateHz / n;
        double[] out = new double[FEATURE_DIMS];
        double spectralSum = 0;
        double weighted = 0;

        for (int band = 0; band < SPECTRAL_DIMS; band++) {
            int first = Math.max(1, (int) Math.floor(BAND_EDGES[band] / hzPerBin));
            int last = Math.min(bins - 1, (int) Math.ceil(BAND_EDGES[band + 1] / hzPerBin));
            double energy = 0;
            int count = 0;
            for (int k = first; k <= last; k++) {
                int p = 2 * k;
                if (p + 1 >= n) break;
                double re = fft[p];
                double im = fft[p + 1];
                double mag2 = re * re + im * im;
                energy += mag2;
                spectralSum += mag2;
                weighted += mag2 * k;
                count++;
            }
            out[band] = Math.log1p(energy / Math.max(1, count));
        }

        double mean = 0;
        for (int i = 0; i < SPECTRAL_DIMS; i++) mean += out[i];
        mean /= SPECTRAL_DIMS;
        double norm = 0;
        for (int i = 0; i < SPECTRAL_DIMS; i++) {
            out[i] -= mean;
            norm += out[i] * out[i];
        }
        norm = Math.sqrt(Math.max(1e-9, norm));
        for (int i = 0; i < SPECTRAL_DIMS; i++) out[i] /= norm;

        out[SPECTRAL_DIMS] = lastPitchNorm;
        out[SPECTRAL_DIMS + 1] = lastPitchConfidence;
        out[SPECTRAL_DIMS + 2] = Math.max(-1, Math.min(1, (lastZcr - 0.10) / 0.10));
        double centroidBin = spectralSum > 0 ? weighted / spectralSum : 0;
        out[SPECTRAL_DIMS + 3] = Math.max(0, Math.min(1, centroidBin / Math.max(1, bins / 4.0)));
        return out;
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
                    "segment=" + index + " insufficient voiced frames=" + acc.frames);
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
            if (create) {
                createSpeaker(feature);
            } else {
                speakers.get(chosen).update(feature);
            }
        }

        lastDecision = String.format(Locale.US,
                "speaker=%c bestExisting=%c similarity=%.3f threshold=%.3f create=%s frames=%d",
                (char) ('A' + chosen), (char) ('A' + bestSpeaker), best, threshold, create, frames);
        return new Assignment(chosen, best, confidence, frames, commit);
    }

    private static void createSpeaker(double[] feature) {
        SpeakerProfile p = new SpeakerProfile(feature);
        speakers.add(p);
        speakersCreated++;
        SpanishStudyDiagnostics.recordAlways(SpanishStudyDiagnostics.SPEAKER,
                "created cluster=" + (char) ('A' + speakers.size() - 1)
                        + " totalClusters=" + speakers.size());
    }

    private static double similarity(double[] a, double[] b) {
        double dot = 0, na = 0, nb = 0;
        for (int i = 0; i < SPECTRAL_DIMS; i++) {
            dot += a[i] * b[i];
            na += a[i] * a[i];
            nb += b[i] * b[i];
        }
        double spectral = dot / Math.sqrt(Math.max(1e-9, na * nb));
        spectral = (spectral + 1.0) / 2.0;

        double pitchWeight = Math.min(a[SPECTRAL_DIMS + 1], b[SPECTRAL_DIMS + 1]);
        double pitchSimilarity = Math.exp(-2.5 * Math.abs(a[SPECTRAL_DIMS] - b[SPECTRAL_DIMS]));
        double zcrSimilarity = Math.exp(-1.5 * Math.abs(a[SPECTRAL_DIMS + 2] - b[SPECTRAL_DIMS + 2]));
        double centroidSimilarity = Math.exp(-2.0 * Math.abs(a[SPECTRAL_DIMS + 3] - b[SPECTRAL_DIMS + 3]));

        double pitchPart = pitchWeight * pitchSimilarity + (1.0 - pitchWeight) * 0.5;
        return 0.70 * spectral + 0.17 * pitchPart + 0.07 * zcrSimilarity + 0.06 * centroidSimilarity;
    }

    private static double normalizeSampleRate(int raw) {
        // Visualizer commonly reports milliHertz (e.g. 48,000,000); some implementations report Hz.
        return raw > 200_000 ? raw / 1000.0 : raw;
    }

    private static String formatAssignment(Assignment a) {
        return String.format(Locale.US, "%c similarity=%.3f confidence=%.3f frames=%d committed=%s",
                (char) ('A' + a.speaker), a.similarity, a.confidence, a.frames, a.committed);
    }

    private static final class SegmentAccumulator {
        final double[] sum = new double[FEATURE_DIMS];
        int frames;
        boolean finalized;
        void add(double[] f) {
            for (int i = 0; i < FEATURE_DIMS; i++) sum[i] += f[i];
            frames++;
        }
        double[] mean() {
            double[] out = new double[FEATURE_DIMS];
            for (int i = 0; i < FEATURE_DIMS; i++) out[i] = sum[i] / Math.max(1, frames);
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
