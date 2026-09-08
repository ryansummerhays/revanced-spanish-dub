#!/usr/bin/env python3
"""Make the v2.33.19 source-parity Sherpa wrapper compatible with the Android 1.13.7 AAR.

The proven runtime used the Android API shape, while the first source reconstruction accidentally
compiled against direct config fields from a different Java API shape. Keep all capture/lifecycle
logic unchanged and switch only model construction + result access to reflection. This also keeps
Sherpa implementation details off the AudioTrack path.
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
        raise SystemExit("usage: patch_v23319_sherpa_reflection_compat.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()
    path = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SherpaNeuralShadow.java"
    if not path.is_file():
        raise RuntimeError(f"missing Sherpa source: {path}")

    rep(
        path,
        "import com.k2fsa.sherpa.onnx.FastClusteringConfig;\n"
        "import com.k2fsa.sherpa.onnx.OfflineSpeakerDiarization;\n"
        "import com.k2fsa.sherpa.onnx.OfflineSpeakerDiarizationConfig;\n"
        "import com.k2fsa.sherpa.onnx.OfflineSpeakerDiarizationSegment;\n"
        "import com.k2fsa.sherpa.onnx.OfflineSpeakerSegmentationModelConfig;\n"
        "import com.k2fsa.sherpa.onnx.OfflineSpeakerSegmentationPyannoteModelConfig;\n"
        "import com.k2fsa.sherpa.onnx.SpeakerEmbeddingExtractorConfig;\n\n",
        "",
        "remove incompatible direct Sherpa imports",
    )
    rep(
        path,
        "import java.lang.reflect.InvocationTargetException;\nimport java.lang.reflect.Method;\n",
        "import java.lang.reflect.Constructor;\nimport java.lang.reflect.InvocationTargetException;\nimport java.lang.reflect.Method;\n",
        "add reflection constructor import",
    )
    rep(
        path,
        "    private static volatile OfflineSpeakerDiarization diarizer;\n",
        "    private static volatile Object diarizer;\n"
        "    private static volatile Method processMethod;\n",
        "make retained diarizer API-neutral",
    )

    old_model = '''            OfflineSpeakerSegmentationPyannoteModelConfig pyannote =
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
'''
    new_model = '''            // Android sherpa-onnx 1.13.7 has a different public Java surface from the generic
            // java-api source tree. Use the same constructor signatures as the proven Android
            // runtime so private config fields never become a source-compatibility dependency.
            Class<?> pyCls = Class.forName(
                    "com.k2fsa.sherpa.onnx.OfflineSpeakerSegmentationPyannoteModelConfig");
            Object pyannote = pyCls.getConstructor(String.class, Float.TYPE)
                    .newInstance(segmentation.getAbsolutePath(), 0.1f);

            Class<?> segCls = Class.forName(
                    "com.k2fsa.sherpa.onnx.OfflineSpeakerSegmentationModelConfig");
            Object segmentationConfig = segCls
                    .getConstructor(pyCls, Integer.TYPE, Boolean.TYPE, String.class)
                    .newInstance(pyannote, 2, false, provider);

            Class<?> embCls = Class.forName(
                    "com.k2fsa.sherpa.onnx.SpeakerEmbeddingExtractorConfig");
            Object embeddingConfig = embCls
                    .getConstructor(String.class, Integer.TYPE, Boolean.TYPE, String.class)
                    .newInstance(embedding.getAbsolutePath(), 2, false, provider);

            Class<?> clusterCls = Class.forName("com.k2fsa.sherpa.onnx.FastClusteringConfig");
            Object clustering = clusterCls.getConstructor(Integer.TYPE, Float.TYPE)
                    .newInstance(-1, 0.5f);

            Class<?> cfgCls = Class.forName("com.k2fsa.sherpa.onnx.OfflineSpeakerDiarizationConfig");
            Object config = cfgCls
                    .getConstructor(segCls, embCls, clusterCls, Float.TYPE, Float.TYPE)
                    .newInstance(segmentationConfig, embeddingConfig, clustering, 0.3f, 0.5f);

            extractionStep = "model-create";
            Class<?> diarizerCls = Class.forName("com.k2fsa.sherpa.onnx.OfflineSpeakerDiarization");
            Class<?> assetManagerClass = Class.forName("android.content.res.AssetManager");
            Object assets = contextClass.getMethod("getAssets").invoke(context);
            Constructor<?> diarizerCtor = diarizerCls.getConstructor(assetManagerClass, cfgCls);
            Object created = diarizerCtor.newInstance(assets, config);
            Method getSampleRate = diarizerCls.getMethod("getSampleRate");
            Method process = diarizerCls.getMethod("process", float[].class);
            int rate = ((Number) getSampleRate.invoke(created)).intValue();
            if (rate <= 0) throw new IllegalStateException("invalid-neural-sample-rate-" + rate);

            diarizer = created;
            processMethod = process;
'''
    rep(path, old_model, new_model, "use Android-AAR reflection for model creation")

    old_infer = '''            OfflineSpeakerDiarization local = diarizer;
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
'''
    new_infer = '''            Object local = diarizer;
            Method process = processMethod;
            if (local == null || process == null || state != STATE_READY) {
                throw new IllegalStateException("diarizer-not-ready-at-inference");
            }
            Object rawResult = process.invoke(local, (Object) input);
            Object[] result = rawResult instanceof Object[] ? (Object[]) rawResult : null;
            long elapsed = (System.nanoTime() - startNs) / 1_000_000L;
            int segmentCount = result == null ? 0 : result.length;
            Set<Integer> speakers = new HashSet<>();
            StringBuilder summary = new StringBuilder();
            if (result != null) {
                int summaryLimit = Math.min(result.length, 12);
                for (int i = 0; i < result.length; i++) {
                    Object s = result[i];
                    if (s == null) continue;
                    Class<?> segmentClass = s.getClass();
                    int speaker = ((Number) segmentClass.getMethod("getSpeaker").invoke(s)).intValue();
                    float start = ((Number) segmentClass.getMethod("getStart").invoke(s)).floatValue();
                    float end = ((Number) segmentClass.getMethod("getEnd").invoke(s)).floatValue();
                    speakers.add(speaker);
                    if (i < summaryLimit) {
                        if (summary.length() > 0) summary.append(',');
                        summary.append(speaker).append('@')
                                .append(Math.round(start * 1000.0f)).append('-')
                                .append(Math.round(end * 1000.0f));
                    }
                }
            }
'''
    rep(path, old_infer, new_infer, "use reflected process/result getters")

    print("v2.33.19 Android-AAR reflection compatibility patch complete")
    print("UNCHANGED: capture stride, sample target, worker lifecycle, state gate, epoch invalidation")


if __name__ == "__main__":
    main()
