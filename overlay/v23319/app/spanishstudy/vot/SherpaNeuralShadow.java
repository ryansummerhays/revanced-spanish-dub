package app.spanishstudy.vot;

import com.k2fsa.sherpa.onnx.FastClusteringConfig;
import com.k2fsa.sherpa.onnx.OfflineSpeakerDiarization;
import com.k2fsa.sherpa.onnx.OfflineSpeakerDiarizationConfig;
import com.k2fsa.sherpa.onnx.OfflineSpeakerDiarizationSegment;
import com.k2fsa.sherpa.onnx.OfflineSpeakerSegmentationModelConfig;
import com.k2fsa.sherpa.onnx.OfflineSpeakerSegmentationPyannoteModelConfig;
import com.k2fsa.sherpa.onnx.SpeakerEmbeddingExtractorConfig;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.nio.ByteBuffer;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;

/**
 * Source reconstruction of the stable v2.33.19 bounded Sherpa shadow pipeline.
 *
 * Safety rules retained from the known-good runtime:
 * - no model work on the AudioTrack thread;
 * - initialize once after both PCM and an Android context have been observed;
 * - keep the native diarizer alive across video changes;
 * - video change invalidates results by epoch instead of interrupting native inference;
 * - one bounded 20 s / 16 kHz capture per video;
 * - Stage-J remains the live badge authority and no TTS voice routing occurs here.
 *
 * The temporary stride-4 gate is deliberately retained for source parity. It is containment,
 * not a content clock. VideoSessionClock/AudioVideoTimeBridge replace it in a later activation
 * gate after this source build has reproduced the stable v19 behavior.
 */
public final class SherpaNeuralShadow implements Runnable {
    private static final int TARGET_SAMPLE_RATE = 16_000;
    private static final int CAPTURE_SECONDS = 20;
    private static final int CAPTURE_TARGET_SAMPLES = TARGET_SAMPLE_RATE * CAPTURE_SECONDS;
    private static final Object LOCK = new Object();
    private static final float[] CAPTURE = new float[CAPTURE_TARGET_SAMPLES];

    private static final int STATE_IDLE = 0;
    private static final int STATE_STARTING = 1;
    private static final int STATE_READY = 2;
    private static final int STATE_FAILED = 3;

    private static volatile int state;
    private static volatile int attempts;
    private static volatile boolean pcmSeen;
    private static volatile Object providedContext;

    private static volatile String assetListing = "not-checked";
    private static volatile String extractionStep = "not-started";
    private static volatile boolean assetsExtracted;
    private static volatile boolean onnxLoaded;
    private static volatile boolean sherpaLoaded;
    private static volatile boolean modelCreated;
    private static volatile int sampleRateHz;
    private static volatile long initMs;
    private static volatile String lastError = "none";

    private static volatile int rawOnnxRuntimeId;
    private static volatile int rawSherpaJniId;
    private static volatile int rawSegmentationId;
    private static volatile int rawEmbeddingId;

    private static volatile OfflineSpeakerDiarization diarizer;

    private static volatile long captureEpoch = 1L;
    private static volatile long captureBuffers;
    private static volatile long captureInputFrames;
    private static volatile int captureSamples;
    private static volatile int captureSourceRateHz;
    private static volatile int captureChannels;
    private static volatile long resamplePhase;
    private static volatile boolean captureComplete;

    private static volatile boolean inferenceStarted;
    private static volatile boolean inferenceDone;
    private static volatile long inferenceMs;
    private static volatile int inferenceSegments;
    private static volatile int inferenceSpeakers;
    private static volatile String inferenceSummary = "none";
    private static volatile String inferenceError = "none";

    private final float[] inferenceInput;
    private final long workerEpoch;

    public SherpaNeuralShadow() {
        this.inferenceInput = null;
        this.workerEpoch = -1L;
    }

    private SherpaNeuralShadow(float[] input, long epoch) {
        this.inferenceInput = input;
        this.workerEpoch = epoch;
    }

    public static void provideContext(Object context) {
        if (context == null) return;
        providedContext = context;
        maybeStart();
    }

    public static void observePcmTrigger() {
        pcmSeen = true;
        maybeStart();
    }

    private static void maybeStart() {
        if (!pcmSeen || providedContext == null || state != STATE_IDLE) return;
        synchronized (LOCK) {
            if (!pcmSeen || providedContext == null || state != STATE_IDLE) return;
            state = STATE_STARTING;
            attempts++;
            try {
                Thread worker = new Thread(new SherpaNeuralShadow(), "SpanishStudy-SherpaInit");
                worker.setDaemon(true);
                worker.start();
            } catch (Throwable t) {
                fail(t, 0L);
            }
        }
    }

    @Override
    public void run() {
        if (inferenceInput != null) runInference(inferenceInput, workerEpoch);
        else runInit();
    }

    private static void runInit() {
        final long startNs = System.nanoTime();
        final String provider = "cpu";
        try {
            Object context = providedContext;
            if (context == null) throw new IllegalStateException("provided-context-lost-before-worker");
            extractionStep = "context-ready";

            Class<?> contextClass = Class.forName("android.content.Context");
            try {
                Class<?> assetManagerClass = Class.forName("android.content.res.AssetManager");
                Method getAssets = contextClass.getMethod("getAssets");
                Object assets = getAssets.invoke(context);
                Method list = assetManagerClass.getMethod("list", String.class);
                Object result = list.invoke(assets, "spanishstudy/sherpa");
                if (result instanceof String[]) {
                    String[] names = (String[]) result;
                    if (names.length == 0) assetListing = "empty-expected-res-raw-transport";
                    else assetListing = String.join(",", names);
                } else {
                    assetListing = "unexpected-list-result";
                }
            } catch (Throwable t) {
                assetListing = "list-error:" + describe(rootCause(t));
            }

            Method getFilesDir = contextClass.getMethod("getFilesDir");
            File dir = new File((File) getFilesDir.invoke(context), "spanishstudy-sherpa-v23310");
            if (!dir.exists() && !dir.mkdirs()) {
                throw new IllegalStateException("cannot-create-neural-dir");
            }

            extractionStep = "resolve-onnxruntime-raw";
            rawOnnxRuntimeId = findRawResourceId(context, contextClass, "spanishstudy_sherpa_onnxruntime");
            if (rawOnnxRuntimeId == 0) throw new IllegalStateException("raw-resource-missing-spanishstudy_sherpa_onnxruntime");
            extractionStep = "copy-onnxruntime-raw";
            File onnx = copyRawResource(context, contextClass, dir, rawOnnxRuntimeId,
                    "libonnxruntime.so", 21_684_880L);
            extractionStep = "load-onnxruntime-extracted";
            System.load(onnx.getAbsolutePath());
            onnxLoaded = true;

            extractionStep = "resolve-sherpa-jni-raw";
            rawSherpaJniId = findRawResourceId(context, contextClass, "spanishstudy_sherpa_jni");
            if (rawSherpaJniId == 0) throw new IllegalStateException("raw-resource-missing-spanishstudy_sherpa_jni");
            extractionStep = "copy-sherpa-jni-raw";
            File sherpa = copyRawResource(context, contextClass, dir, rawSherpaJniId,
                    "libsherpa-onnx-jni.so", 3_519_720L);
            extractionStep = "load-sherpa-jni-extracted";
            System.load(sherpa.getAbsolutePath());
            sherpaLoaded = true;

            extractionStep = "resolve-segmentation-raw";
            rawSegmentationId = findRawResourceId(context, contextClass, "spanishstudy_sherpa_segmentation");
            if (rawSegmentationId == 0) throw new IllegalStateException("raw-resource-missing-spanishstudy_sherpa_segmentation");
            extractionStep = "copy-segmentation-raw";
            File segmentation = copyRawResource(context, contextClass, dir, rawSegmentationId,
                    "segmentation.onnx", 9_512_223L);

            extractionStep = "resolve-embedding-raw";
            rawEmbeddingId = findRawResourceId(context, contextClass, "spanishstudy_sherpa_embedding");
            if (rawEmbeddingId == 0) throw new IllegalStateException("raw-resource-missing-spanishstudy_sherpa_embedding");
            extractionStep = "copy-embedding-raw";
            File embedding = copyRawResource(context, contextClass, dir, rawEmbeddingId,
                    "embedding.onnx", 39_593_761L);
            assetsExtracted = true;
            extractionStep = "payload-ready";

            OfflineSpeakerSegmentationPyannoteModelConfig pyannote =
                    new OfflineSpeakerSegmentationPyannoteModelConfig();
            pyannote.model = segmentation.getAbsolutePath();
            pyannote.windowShiftRatio = 0.1f;

            OfflineSpeakerSegmentationModelConfig segmentationConfig =
                    new OfflineSpeakerSegmentationModelConfig();
            segmentationConfig.pyannote = pyannote;
            segmentationConfig.numThreads = 2;
            segmentationConfig.debug = false;
            segmentationConfig.provider = provider;

            SpeakerEmbeddingExtractorConfig embeddingConfig = new SpeakerEmbeddingExtractorConfig();
            embeddingConfig.model = embedding.getAbsolutePath();
            embeddingConfig.numThreads = 2;
            embeddingConfig.debug = false;
            embeddingConfig.provider = provider;

            FastClusteringConfig clustering = new FastClusteringConfig();
            clustering.numClusters = -1;
            clustering.threshold = 0.5f;

            OfflineSpeakerDiarizationConfig config = new OfflineSpeakerDiarizationConfig();
            config.segmentation = segmentationConfig;
            config.embedding = embeddingConfig;
            config.clustering = clustering;
            config.minDurationOn = 0.3f;
            config.minDurationOff = 0.5f;

            extractionStep = "model-create";
            OfflineSpeakerDiarization created = new OfflineSpeakerDiarization(config);
            int rate = created.getSampleRate();
            if (rate <= 0) throw new IllegalStateException("invalid-neural-sample-rate-" + rate);

            diarizer = created;
            sampleRateHz = rate;
            modelCreated = true;
            extractionStep = "ready";
            initMs = (System.nanoTime() - startNs) / 1_000_000L;
            lastError = "none";
            state = STATE_READY;
        } catch (Throwable t) {
            fail(t, startNs);
        }
    }

    /** Stable v19 PCM capture path. Intentionally retains the temporary stride-4 gate. */
    public static void observePcmBuffer(ByteBuffer buffer, int sourceRateHz, int channels, int encoding) {
        pcmSeen = true;
        maybeStart();
        if (state != STATE_READY || diarizer == null || buffer == null || encoding != 2
                || sourceRateHz < 8_000 || channels < 1 || channels > 8) return;

        try {
            ByteBuffer src = buffer.duplicate();
            int position = src.position();
            int remaining = src.remaining();
            int frameBytes = channels * 2;
            int frames = remaining / frameBytes;
            if (frames <= 0) return;

            float[] inference = null;
            long epoch = -1L;
            synchronized (LOCK) {
                if (captureComplete || inferenceStarted || inferenceDone) return;

                // v2.33.19 containment only: every fourth eligible callback feeds capture.
                captureBuffers++;
                if ((((int) captureBuffers) & 3) != 0) return;

                if (captureSourceRateHz != sourceRateHz || captureChannels != channels) {
                    captureSourceRateHz = sourceRateHz;
                    captureChannels = channels;
                    resamplePhase = 0L;
                }

                for (int frame = 0; frame < frames && captureSamples < CAPTURE_TARGET_SAMPLES; frame++) {
                    int base = position + frame * frameBytes;
                    long sum = 0L;
                    for (int ch = 0; ch < channels; ch++) {
                        int p = base + ch * 2;
                        int lo = src.get(p) & 0xff;
                        int hi = src.get(p + 1) << 8;
                        short s = (short) (hi | lo);
                        sum += s;
                    }
                    float mono = (float) (sum / channels) / 32768.0f;
                    resamplePhase += TARGET_SAMPLE_RATE;
                    while (resamplePhase >= sourceRateHz && captureSamples < CAPTURE_TARGET_SAMPLES) {
                        resamplePhase -= sourceRateHz;
                        CAPTURE[captureSamples++] = mono;
                    }
                }

                if (captureSamples >= CAPTURE_TARGET_SAMPLES) {
                    captureComplete = true;
                    inferenceStarted = true;
                    inference = Arrays.copyOf(CAPTURE, CAPTURE_TARGET_SAMPLES);
                    epoch = captureEpoch;
                }
            }

            if (inference != null) {
                Thread worker = new Thread(new SherpaNeuralShadow(inference, epoch),
                        "SpanishStudy-SherpaInfer");
                worker.setDaemon(true);
                worker.setPriority(Thread.MIN_PRIORITY);
                worker.start();
            }
        } catch (Throwable t) {
            synchronized (LOCK) {
                inferenceError = "capture:" + describe(rootCause(t));
                if (captureComplete && inferenceStarted) inferenceDone = true;
            }
        }
    }

    private static void runInference(float[] input, long epoch) {
        final long startNs = System.nanoTime();
        try {
            OfflineSpeakerDiarization local = diarizer;
            if (local == null || state != STATE_READY) {
                throw new IllegalStateException("diarizer-not-ready-at-inference");
            }
            OfflineSpeakerDiarizationSegment[] result = local.process(input);
            long elapsed = (System.nanoTime() - startNs) / 1_000_000L;
            int segmentCount = result == null ? 0 : result.length;
            Set<Integer> speakers = new HashSet<>();
            StringBuilder summary = new StringBuilder();
            if (result != null) {
                int summaryLimit = Math.min(result.length, 12);
                for (int i = 0; i < result.length; i++) {
                    OfflineSpeakerDiarizationSegment s = result[i];
                    if (s == null) continue;
                    speakers.add(s.speaker);
                    if (i < summaryLimit) {
                        if (summary.length() > 0) summary.append(',');
                        summary.append(s.speaker).append('@')
                                .append(Math.round(s.start * 1000.0f)).append('-')
                                .append(Math.round(s.end * 1000.0f));
                    }
                }
            }
            synchronized (LOCK) {
                if (epoch != captureEpoch) return;
                inferenceMs = elapsed;
                inferenceSegments = segmentCount;
                inferenceSpeakers = speakers.size();
                inferenceSummary = summary.length() == 0 ? "none" : summary.toString();
                inferenceError = "none";
                inferenceDone = true;
            }
        } catch (Throwable t) {
            synchronized (LOCK) {
                if (epoch != captureEpoch) return;
                inferenceMs = (System.nanoTime() - startNs) / 1_000_000L;
                inferenceError = describe(rootCause(t));
                inferenceDone = true;
            }
        }
    }

    /** Invalidates partial and in-flight results but never destroys/interrupts native inference. */
    public static void resetCaptureForVideo() {
        synchronized (LOCK) {
            captureEpoch++;
            captureSamples = 0;
            captureInputFrames = 0L;
            captureBuffers = 0L;
            captureSourceRateHz = 0;
            captureChannels = 0;
            resamplePhase = 0L;
            captureComplete = false;
            inferenceStarted = false;
            inferenceDone = false;
            inferenceMs = 0L;
            inferenceSegments = 0;
            inferenceSpeakers = 0;
            inferenceSummary = "none";
            inferenceError = "none";
        }
    }

    private static int findRawResourceId(Object context, Class<?> contextClass, String name) throws Exception {
        Class<?> resourcesClass = Class.forName("android.content.res.Resources");
        Method getIdentifier = resourcesClass.getMethod("getIdentifier", String.class, String.class, String.class);
        Object resources = contextClass.getMethod("getResources").invoke(context);
        String packageName = (String) contextClass.getMethod("getPackageName").invoke(context);
        return ((Integer) getIdentifier.invoke(resources, name, "raw", packageName)).intValue();
    }

    private static File copyRawResource(Object context, Class<?> contextClass, File dir, int resourceId,
                                        String fileName, long expectedSize) throws Exception {
        File out = new File(dir, fileName);
        if (out.isFile() && out.length() == expectedSize) return out;

        Class<?> resourcesClass = Class.forName("android.content.res.Resources");
        Object resources = contextClass.getMethod("getResources").invoke(context);
        Method openRawResource = resourcesClass.getMethod("openRawResource", Integer.TYPE);
        File temp = new File(dir, fileName + ".tmp");

        try (InputStream in = (InputStream) openRawResource.invoke(resources, resourceId);
             FileOutputStream fos = new FileOutputStream(temp, false)) {
            byte[] copyBuffer = new byte[65_536];
            int n;
            while ((n = in.read(copyBuffer)) >= 0) {
                if (n > 0) fos.write(copyBuffer, 0, n);
            }
            fos.getFD().sync();
        }

        if (temp.length() != expectedSize) {
            throw new IllegalStateException("raw-size-" + fileName + "-" + temp.length());
        }
        if (out.exists() && !out.delete()) {
            throw new IllegalStateException("cannot-replace-" + fileName);
        }
        if (!temp.renameTo(out)) {
            throw new IllegalStateException("cannot-rename-" + fileName);
        }
        return out;
    }

    private static void fail(Throwable t, long startNs) {
        try {
            if (startNs != 0L) initMs = (System.nanoTime() - startNs) / 1_000_000L;
            lastError = describe(rootCause(t));
            state = STATE_FAILED;
        } catch (Throwable ignored) {
            lastError = "unknown-init-error";
            state = STATE_FAILED;
        }
    }

    private static Throwable rootCause(Throwable t) {
        Throwable current = t;
        for (int i = 0; i < 8 && current != null; i++) {
            Throwable next = current instanceof InvocationTargetException
                    ? ((InvocationTargetException) current).getCause() : null;
            if (next == null) next = current.getCause();
            if (next == null || next == current) break;
            current = next;
        }
        return current == null ? t : current;
    }

    private static String describe(Throwable t) {
        if (t == null) return "unknown";
        String msg = t.getMessage();
        return t.getClass().getSimpleName() + (msg == null ? "" : ":" + sanitize(msg));
    }

    private static String sanitize(String text) {
        if (text == null) return "";
        String cleaned = text.replace('\n', ' ').replace('\r', ' ');
        return cleaned.length() > 180 ? cleaned.substring(0, 180) : cleaned;
    }

    private static String stateName() {
        if (state == STATE_STARTING) return "starting";
        if (state == STATE_READY) return "ready";
        if (state == STATE_FAILED) return "failed";
        return "idle-waiting-first-pcm";
    }

    private static String yesNo(boolean value) {
        return value ? "success" : "not-started";
    }

    public static String diagnostics() {
        int progress = (int) Math.min(1000L,
                ((long) captureSamples * 1000L) / CAPTURE_TARGET_SAMPLES);
        return new StringBuilder()
                .append("\nspeakerNeuralGate=v2.33.19-source-parity+stride4-only")
                .append("\nspeakerNeuralBackend=sherpa-onnx-1.13.7+pyannote3+3dspeaker-eres2net")
                .append("\nspeakerNeuralJavaApi=pure-java-minimal-process-wrapper-no-kotlin")
                .append("\nspeakerNeuralPayloadTransport=explicit-resource-patch+res-raw-all+absolute-system-load")
                .append("\nspeakerNeuralInitState=").append(stateName())
                .append("\nspeakerNeuralInitAttempts=").append(attempts)
                .append("\nspeakerNeuralPcmSeen=").append(pcmSeen)
                .append("\nspeakerNeuralContextProvided=").append(providedContext != null)
                .append("\nspeakerNeuralExtractionStep=").append(extractionStep)
                .append("\nspeakerNeuralAssetListing=").append(assetListing)
                .append("\nspeakerNeuralRawOnnxRuntimeId=").append(rawOnnxRuntimeId)
                .append("\nspeakerNeuralRawSherpaJniId=").append(rawSherpaJniId)
                .append("\nspeakerNeuralRawSegmentationId=").append(rawSegmentationId)
                .append("\nspeakerNeuralRawEmbeddingId=").append(rawEmbeddingId)
                .append("\nspeakerNeuralAssetsExtracted=").append(assetsExtracted)
                .append("\nspeakerNeuralOnnxRuntimeLoad=").append(yesNo(onnxLoaded))
                .append("\nspeakerNeuralSherpaLoad=").append(yesNo(sherpaLoaded))
                .append("\nspeakerNeuralModelCreate=").append(yesNo(modelCreated))
                .append("\nspeakerNeuralSampleRateHz=").append(sampleRateHz)
                .append("\nspeakerNeuralInitMs=").append(initMs)
                .append("\nspeakerNeuralLastError=").append(lastError)
                .append("\nspeakerNeuralPcmFeed=direct-pcm16-fullwindow-stride4-16k-20s")
                .append("\nspeakerNeuralCaptureEpoch=").append(captureEpoch)
                .append("\nspeakerNeuralCaptureSourceRateHz=").append(captureSourceRateHz)
                .append("\nspeakerNeuralCaptureChannels=").append(captureChannels)
                .append("\nspeakerNeuralCallCount=").append(captureBuffers)
                .append("\nspeakerNeuralInputFramesLegacy=").append(captureInputFrames)
                .append("\nspeakerNeuralCaptureSamples=").append(captureSamples)
                .append("\nspeakerNeuralCaptureTargetSamples=").append(CAPTURE_TARGET_SAMPLES)
                .append("\nspeakerNeuralCaptureProgressPermille=").append(progress)
                .append("\nspeakerNeuralCaptureComplete=").append(captureComplete)
                .append("\nspeakerNeuralInference=bounded-once-per-video-shadow")
                .append("\nspeakerNeuralInferenceStarted=").append(inferenceStarted)
                .append("\nspeakerNeuralInferenceDone=").append(inferenceDone)
                .append("\nspeakerNeuralInferenceMs=").append(inferenceMs)
                .append("\nspeakerNeuralInferenceSegments=").append(inferenceSegments)
                .append("\nspeakerNeuralInferenceSpeakers=").append(inferenceSpeakers)
                .append("\nspeakerNeuralInferenceSummary=").append(inferenceSummary)
                .append("\nspeakerNeuralInferenceLastError=").append(inferenceError)
                .append("\nspeakerNeuralLiveBadgeAuthority=false-stage-j-remains-control")
                .toString();
    }
}
