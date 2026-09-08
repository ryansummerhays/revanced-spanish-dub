#!/usr/bin/env python3
"""Keep the small public Sherpa runtime surface as direct typed calls.

Configuration construction stays reflected for Android-AAR compatibility, but sampleRate(),
process(), and segment getters are referenced directly. This prevents R8 from deleting the native
process bridge or OfflineSpeakerDiarizationSegment class while still avoiding private config fields.
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
        raise SystemExit("usage: patch_v23319_sherpa_direct_runtime_api.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()
    path = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SherpaNeuralShadow.java"
    if not path.is_file():
        raise RuntimeError(f"missing Sherpa source: {path}")

    rep(
        path,
        "package app.spanishstudy.vot;\n\n",
        "package app.spanishstudy.vot;\n\n"
        "import com.k2fsa.sherpa.onnx.OfflineSpeakerDiarization;\n"
        "import com.k2fsa.sherpa.onnx.OfflineSpeakerDiarizationSegment;\n\n",
        "retain public Sherpa runtime types",
    )
    rep(
        path,
        "    private static volatile Object diarizer;\n"
        "    private static volatile Method processMethod;\n",
        "    private static volatile OfflineSpeakerDiarization diarizer;\n",
        "retain typed diarizer",
    )

    old_create = '''            Object created = diarizerCtor.newInstance(assets, config);
            Method getSampleRate = diarizerCls.getMethod("getSampleRate");
            Method process = diarizerCls.getMethod("process", float[].class);
            int rate = ((Number) getSampleRate.invoke(created)).intValue();
            if (rate <= 0) throw new IllegalStateException("invalid-neural-sample-rate-" + rate);

            diarizer = created;
            processMethod = process;
'''
    new_create = '''            OfflineSpeakerDiarization created =
                    (OfflineSpeakerDiarization) diarizerCtor.newInstance(assets, config);
            int rate = created.sampleRate();
            if (rate <= 0) throw new IllegalStateException("invalid-neural-sample-rate-" + rate);

            diarizer = created;
'''
    rep(path, old_create, new_create, "retain direct sampleRate bridge")

    old_infer = '''            Object local = diarizer;
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
    new_infer = '''            OfflineSpeakerDiarization local = diarizer;
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
                    int speaker = s.getSpeaker();
                    float start = s.getStart();
                    float end = s.getEnd();
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
    rep(path, old_infer, new_infer, "retain direct process and segment getters")

    print("v2.33.19 Sherpa direct runtime API retention patch complete")
    print("REFLECTED: config construction and Android AssetManager constructor")
    print("DIRECT: sampleRate, process, segment getters so R8 cannot prune JNI result surface")


if __name__ == "__main__":
    main()
