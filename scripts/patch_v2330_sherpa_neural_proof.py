#!/usr/bin/env python3
"""v2.33.0: isolated sherpa-onnx neural diarization proof on top of Stage J.

Adds a parallel, fail-soft neural backend. It collects one bounded 20 s block from the already
proven 48 kHz stereo PCM16 AudioTrack stream, downsamples to 16 kHz mono on the audio thread,
and performs exactly one sherpa-onnx offline diarization inference on a background thread.
Stage-J hand-built clustering and badges remain the live/control backend.

UNCHANGED: Morphe sentence segmentation, OpenRouter 1500/350 packetization/order, translation,
subtitle pagination/timing, Edge TTS, Stage-J badge routing and Spanish voice behavior.
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


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_v2330_sherpa_neural_proof.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    player = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/PlayerVolumePatch.java"
    controller = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SpanishStudyController.java"
    gradle = root / "extensions/youtube/build.gradle.kts"
    neural = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SherpaNeuralDiarizer.java"
    for path in (player, controller, gradle):
        if not path.is_file():
            raise RuntimeError(f"missing Stage-J source: {path}")

    rep(
        gradle,
        "    implementation(libs.protobuf.javalite)\n",
        "    implementation(libs.protobuf.javalite)\n"
        "    // Spanish Dub Study v2.33.0: official sherpa-onnx Android classes unpacked by CI.\n"
        "    implementation(files(\"libs/sherpa-onnx-1.13.7-classes.jar\"))\n"
        "    implementation(\"org.jetbrains.kotlin:kotlin-stdlib:1.7.20\")\n",
        "compile official sherpa Android API classes",
    )

    neural.parent.mkdir(parents=True, exist_ok=True)
    neural.write_text(r'''package app.spanishstudy.vot;

import android.content.Context;

import java.lang.reflect.Constructor;
import java.lang.reflect.Method;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.Locale;

import app.morphe.extension.shared.Utils;

/**
 * v2.33.0 neural diarization proof.
 *
 * This is intentionally not the live badge authority yet. It gathers one immutable 20-second
 * sample from the proven AudioTrack PCM16 stream and runs sherpa-onnx off the audio thread.
 * Every JNI/model/inference failure is latched into diagnostics and swallowed.
 */
public final class SherpaNeuralDiarizer {
    private static final Object LOCK = new Object();
    private static final int INPUT_RATE = 48_000;
    private static final int OUTPUT_RATE = 16_000;
    private static final int INPUT_CHANNELS = 2;
    private static final int INPUT_ENCODING_PCM16 = 2;
    private static final int PROOF_SECONDS = 20;
    private static final int PROOF_SAMPLES = OUTPUT_RATE * PROOF_SECONDS;
    private static final String SEGMENTATION_ASSET = "spanishstudy/sherpa/segmentation.onnx";
    private static final String EMBEDDING_ASSET = "spanishstudy/sherpa/embedding.onnx";

    private static volatile long epoch;
    private static volatile long resetCount;
    private static volatile long pcmCalls;
    private static volatile long formatSkips;
    private static volatile long samplesCollected;
    private static volatile long collectionErrors;
    private static volatile boolean proofScheduled;
    private static volatile boolean workerRunning;
    private static volatile long workerStarts;
    private static volatile long nativeLoadAttempts;
    private static volatile long nativeLoadSuccess;
    private static volatile long initAttempts;
    private static volatile long initSuccess;
    private static volatile long initErrors;
    private static volatile long inferenceAttempts;
    private static volatile long inferenceSuccess;
    private static volatile long inferenceErrors;
    private static volatile long lastInferenceMs;
    private static volatile int lastSegmentCount;
    private static volatile int lastSpeakerCount;
    private static volatile String lastResult = "none";
    private static volatile String lastError = "none";

    private static float[] proofBuffer;
    private static int proofFill;
    private static Object diarizer;
    private static Method processMethod;

    private SherpaNeuralDiarizer() {}

    public static void resetForNewVideo() {
        synchronized (LOCK) {
            epoch++;
            resetCount++;
            proofBuffer = null;
            proofFill = 0;
            proofScheduled = false;
            pcmCalls = 0;
            formatSkips = 0;
            samplesCollected = 0;
            collectionErrors = 0;
            inferenceAttempts = 0;
            inferenceSuccess = 0;
            inferenceErrors = 0;
            lastInferenceMs = 0;
            lastSegmentCount = 0;
            lastSpeakerCount = 0;
            lastResult = "none";
            lastError = "none";
        }
    }

    /** Called only from the already-proven AudioTrack ByteBuffer hook. */
    public static void observePcmBuffer(ByteBuffer buffer, int sampleRate, int channels, int encoding) {
        pcmCalls++;
        if (buffer == null || sampleRate != INPUT_RATE || channels != INPUT_CHANNELS || encoding != INPUT_ENCODING_PCM16) {
            formatSkips++;
            return;
        }
        if (proofScheduled) return;

        try {
            synchronized (LOCK) {
                if (proofScheduled) return;
                if (proofBuffer == null) proofBuffer = new float[PROOF_SAMPLES];

                ByteBuffer view = buffer.duplicate().order(ByteOrder.LITTLE_ENDIAN);
                int start = view.position();
                int end = view.limit();

                // 48 kHz stereo PCM16 -> 16 kHz mono. Each output sample consumes three stereo
                // frames (12 input bytes). 3840-byte YouTube buffers yield exactly 320 samples.
                for (int p = start; p + 11 < end && proofFill < PROOF_SAMPLES; p += 12) {
                    int left = view.getShort(p);
                    int right = view.getShort(p + 2);
                    proofBuffer[proofFill++] = ((left + right) * 0.5f) / 32768.0f;
                }
                samplesCollected = proofFill;

                if (proofFill >= PROOF_SAMPLES) {
                    proofScheduled = true;
                    final float[] frozen = proofBuffer;
                    proofBuffer = null;
                    final long runEpoch = epoch;
                    startWorker(frozen, runEpoch);
                }
            }
        } catch (Throwable t) {
            collectionErrors++;
            lastError = summarizeThrowable(t);
        }
    }

    private static void startWorker(final float[] samples, final long runEpoch) {
        if (workerRunning) {
            lastError = "worker-already-running";
            return;
        }
        workerRunning = true;
        workerStarts++;
        try {
            Thread worker = new Thread(() -> runProof(samples, runEpoch), "SpanishStudy-SherpaProof");
            worker.setDaemon(true);
            worker.start();
        } catch (Throwable t) {
            workerRunning = false;
            inferenceErrors++;
            lastError = summarizeThrowable(t);
        }
    }

    private static void runProof(float[] samples, long runEpoch) {
        long started = android.os.SystemClock.elapsedRealtime();
        inferenceAttempts++;
        try {
            Object sd = getOrCreateDiarizer();
            if (sd == null || processMethod == null) throw new IllegalStateException("sherpa diarizer unavailable");
            Object result = processMethod.invoke(sd, (Object) samples);
            Object[] segments = result instanceof Object[] ? (Object[]) result : new Object[0];

            int maxSpeaker = -1;
            StringBuilder summary = new StringBuilder();
            int shown = Math.min(segments.length, 16);
            for (int i = 0; i < segments.length; i++) {
                Object segment = segments[i];
                Class<?> cls = segment.getClass();
                float start = ((Number) cls.getMethod("getStart").invoke(segment)).floatValue();
                float end = ((Number) cls.getMethod("getEnd").invoke(segment)).floatValue();
                int speaker = ((Number) cls.getMethod("getSpeaker").invoke(segment)).intValue();
                if (speaker > maxSpeaker) maxSpeaker = speaker;
                if (i < shown) {
                    if (summary.length() > 0) summary.append(',');
                    summary.append(String.format(Locale.US, "%.2f-%.2f:S%d", start, end, speaker));
                }
            }

            if (runEpoch == epoch) {
                lastSegmentCount = segments.length;
                lastSpeakerCount = maxSpeaker + 1;
                lastResult = summary.length() == 0 ? "empty" : summary.toString();
                lastInferenceMs = android.os.SystemClock.elapsedRealtime() - started;
                inferenceSuccess++;
                lastError = "none";
            }
        } catch (Throwable t) {
            if (runEpoch == epoch) {
                lastInferenceMs = android.os.SystemClock.elapsedRealtime() - started;
                inferenceErrors++;
                lastError = summarizeThrowable(t);
            }
        } finally {
            workerRunning = false;
        }
    }

    private static Object getOrCreateDiarizer() throws Exception {
        if (diarizer != null) return diarizer;
        synchronized (LOCK) {
            if (diarizer != null) return diarizer;
            initAttempts++;
            try {
                nativeLoadAttempts++;
                System.loadLibrary("onnxruntime");
                System.loadLibrary("sherpa-onnx-jni");
                nativeLoadSuccess++;

                Class<?> pyCls = Class.forName("com.k2fsa.sherpa.onnx.OfflineSpeakerSegmentationPyannoteModelConfig");
                Object py = pyCls.getConstructor(String.class, float.class).newInstance(SEGMENTATION_ASSET, 0.1f);

                Class<?> segCls = Class.forName("com.k2fsa.sherpa.onnx.OfflineSpeakerSegmentationModelConfig");
                Object seg = segCls.getConstructor(pyCls, int.class, boolean.class, String.class)
                        .newInstance(py, 2, false, "cpu");

                Class<?> embCls = Class.forName("com.k2fsa.sherpa.onnx.SpeakerEmbeddingExtractorConfig");
                Object emb = embCls.getConstructor(String.class, int.class, boolean.class, String.class)
                        .newInstance(EMBEDDING_ASSET, 2, false, "cpu");

                Class<?> clusterCls = Class.forName("com.k2fsa.sherpa.onnx.FastClusteringConfig");
                Object cluster = clusterCls.getConstructor(int.class, float.class).newInstance(-1, 0.5f);

                Class<?> cfgCls = Class.forName("com.k2fsa.sherpa.onnx.OfflineSpeakerDiarizationConfig");
                Object cfg = cfgCls.getConstructor(segCls, embCls, clusterCls, float.class, float.class)
                        .newInstance(seg, emb, cluster, 0.2f, 0.5f);

                Class<?> diarizerCls = Class.forName("com.k2fsa.sherpa.onnx.OfflineSpeakerDiarization");
                Context context = Utils.getContext();
                Constructor<?> ctor = diarizerCls.getConstructor(android.content.res.AssetManager.class, cfgCls);
                diarizer = ctor.newInstance(context.getAssets(), cfg);
                processMethod = diarizerCls.getMethod("process", float[].class);
                initSuccess++;
                return diarizer;
            } catch (Throwable t) {
                initErrors++;
                lastError = summarizeThrowable(t);
                if (t instanceof Exception) throw (Exception) t;
                throw new RuntimeException(t);
            }
        }
    }

    private static String summarizeThrowable(Throwable t) {
        Throwable x = t;
        while (x.getCause() != null && x.getCause() != x) x = x.getCause();
        String msg = x.getMessage();
        if (msg == null) msg = "";
        msg = msg.replace('\n', ' ').replace('\r', ' ');
        if (msg.length() > 180) msg = msg.substring(0, 180);
        return x.getClass().getSimpleName() + (msg.isEmpty() ? "" : ":" + msg);
    }

    public static String getVersion() { return "sherpa-onnx-1.13.7-pyannote3-eres2net"; }
    public static long getEpoch() { return epoch; }
    public static long getResetCount() { return resetCount; }
    public static long getPcmCalls() { return pcmCalls; }
    public static long getFormatSkips() { return formatSkips; }
    public static long getSamplesCollected() { return samplesCollected; }
    public static long getCollectionErrors() { return collectionErrors; }
    public static int getProofSeconds() { return PROOF_SECONDS; }
    public static boolean isProofScheduled() { return proofScheduled; }
    public static boolean isWorkerRunning() { return workerRunning; }
    public static long getWorkerStarts() { return workerStarts; }
    public static long getNativeLoadAttempts() { return nativeLoadAttempts; }
    public static long getNativeLoadSuccess() { return nativeLoadSuccess; }
    public static long getInitAttempts() { return initAttempts; }
    public static long getInitSuccess() { return initSuccess; }
    public static long getInitErrors() { return initErrors; }
    public static long getInferenceAttempts() { return inferenceAttempts; }
    public static long getInferenceSuccess() { return inferenceSuccess; }
    public static long getInferenceErrors() { return inferenceErrors; }
    public static long getLastInferenceMs() { return lastInferenceMs; }
    public static int getLastSegmentCount() { return lastSegmentCount; }
    public static int getLastSpeakerCount() { return lastSpeakerCount; }
    public static String getLastResult() { return lastResult; }
    public static String getLastError() { return lastError; }
}
''', encoding="utf-8")
    print("created:", neural)

    rep(
        player,
        "        if (studySpeakerAnalysisResetInProgress) return;\n",
        "        if (studySpeakerAnalysisResetInProgress) return;\n"
        "        try {\n"
        "            app.spanishstudy.vot.SherpaNeuralDiarizer.observePcmBuffer(\n"
        "                    buffer, studyAudioTrackSampleRateHz, studyAudioTrackChannelCount, studyAudioTrackEncoding);\n"
        "        } catch (Throwable ignored) {\n"
        "            // Neural proof must never escape onto ExoPlayer's audio thread.\n"
        "        }\n",
        "feed bounded neural proof from proven PCM hook",
    )

    rep(
        player,
        "            studySpeakerAnalysisLastResetPcmHookCalls = studyPcmHookCalls;\n",
        "            app.spanishstudy.vot.SherpaNeuralDiarizer.resetForNewVideo();\n"
        "            studySpeakerAnalysisLastResetPcmHookCalls = studyPcmHookCalls;\n",
        "reset neural collector with Stage-J per-video reset",
    )

    rep(
        controller,
        'report.append("Spanish Dub Study v2.32.12 Stage-J per-video-speaker-reset diagnostics\\n");',
        'report.append("Spanish Dub Study v2.33.0 Sherpa neural diarization proof diagnostics\\n");',
        "update v2.33.0 diagnostics header",
    )

    anchor = '        report.append("speakerAnalysisResetInProgress=").append(PlayerVolumePatch.isSpeakerAnalysisResetInProgressForStudy()).append(\'\\n\');\n'
    insert = anchor + r'''        report.append("speakerNeuralBackend=sherpa-onnx-pyannote3+eres2net-one-shot-proof\n");
        report.append("speakerNeuralLiveBadgeAuthority=false-stage-j-remains-control\n");
        report.append("speakerNeuralVersion=").append(SherpaNeuralDiarizer.getVersion()).append('\n');
        report.append("speakerNeuralInput=48khz-stereo-pcm16-to-16khz-mono-decimate3\n");
        report.append("speakerNeuralProofSeconds=").append(SherpaNeuralDiarizer.getProofSeconds()).append('\n');
        report.append("speakerNeuralEpoch=").append(SherpaNeuralDiarizer.getEpoch()).append('\n');
        report.append("speakerNeuralResetCount=").append(SherpaNeuralDiarizer.getResetCount()).append('\n');
        report.append("speakerNeuralPcmCalls=").append(SherpaNeuralDiarizer.getPcmCalls()).append('\n');
        report.append("speakerNeuralFormatSkips=").append(SherpaNeuralDiarizer.getFormatSkips()).append('\n');
        report.append("speakerNeuralSamplesCollected=").append(SherpaNeuralDiarizer.getSamplesCollected()).append('\n');
        report.append("speakerNeuralCollectionErrors=").append(SherpaNeuralDiarizer.getCollectionErrors()).append('\n');
        report.append("speakerNeuralProofScheduled=").append(SherpaNeuralDiarizer.isProofScheduled()).append('\n');
        report.append("speakerNeuralWorkerRunning=").append(SherpaNeuralDiarizer.isWorkerRunning()).append('\n');
        report.append("speakerNeuralWorkerStarts=").append(SherpaNeuralDiarizer.getWorkerStarts()).append('\n');
        report.append("speakerNeuralNativeLoadAttempts=").append(SherpaNeuralDiarizer.getNativeLoadAttempts()).append('\n');
        report.append("speakerNeuralNativeLoadSuccess=").append(SherpaNeuralDiarizer.getNativeLoadSuccess()).append('\n');
        report.append("speakerNeuralInitAttempts=").append(SherpaNeuralDiarizer.getInitAttempts()).append('\n');
        report.append("speakerNeuralInitSuccess=").append(SherpaNeuralDiarizer.getInitSuccess()).append('\n');
        report.append("speakerNeuralInitErrors=").append(SherpaNeuralDiarizer.getInitErrors()).append('\n');
        report.append("speakerNeuralInferenceAttempts=").append(SherpaNeuralDiarizer.getInferenceAttempts()).append('\n');
        report.append("speakerNeuralInferenceSuccess=").append(SherpaNeuralDiarizer.getInferenceSuccess()).append('\n');
        report.append("speakerNeuralInferenceErrors=").append(SherpaNeuralDiarizer.getInferenceErrors()).append('\n');
        report.append("speakerNeuralLastInferenceMs=").append(SherpaNeuralDiarizer.getLastInferenceMs()).append('\n');
        report.append("speakerNeuralLastSegmentCount=").append(SherpaNeuralDiarizer.getLastSegmentCount()).append('\n');
        report.append("speakerNeuralLastSpeakerCount=").append(SherpaNeuralDiarizer.getLastSpeakerCount()).append('\n');
        report.append("speakerNeuralLastResult=").append(SherpaNeuralDiarizer.getLastResult()).append('\n');
        report.append("speakerNeuralLastError=").append(SherpaNeuralDiarizer.getLastError()).append('\n');
'''
    rep(controller, anchor, insert, "publish sherpa proof diagnostics")

    print("v2.33.0 sherpa neural proof patch complete")
    print("UNCHANGED: Stage-J live badge authority and legacy feature/clustering math")
    print("UNCHANGED: mergeIntoSentences, OpenRouter 1500/350 packets/order, subtitle timing/pagination, Edge TTS")
    print("ADDED: one 20 s PCM -> 16 kHz mono neural proof and fail-soft background sherpa inference")


if __name__ == "__main__":
    main()
