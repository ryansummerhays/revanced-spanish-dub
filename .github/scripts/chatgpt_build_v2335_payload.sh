#!/usr/bin/env bash
set -euxo pipefail

APK=/tmp/sherpa.apk
NAME='sherpa-onnx-1.13.7-arm64-v8a-speaker-diarization-revai_v1-3dspeaker.apk'
URLS=(
  "https://huggingface.co/csukuangfj/sherpa-onnx-apk/resolve/main/speaker-diarization/1.13.7/$NAME"
  "https://huggingface.co/csukuangfj2/sherpa-onnx-apk/resolve/main/speaker-diarization/1.13.7/$NAME"
  "https://hf-mirror.com/csukuangfj2/sherpa-onnx-apk/resolve/main/speaker-diarization/1.13.7/$NAME"
)
ok=0
for u in "${URLS[@]}"; do
  if curl -fL --retry 3 --connect-timeout 20 "$u" -o "$APK"; then ok=1; break; fi
done
test "$ok" = 1
test -s "$APK"
unzip -t "$APK" >/dev/null
sha256sum "$APK" | tee /tmp/SOURCE_APK_SHA256.txt
unzip -l "$APK" | tee /tmp/SOURCE_APK_CONTENTS.txt

rm -rf /tmp/sherpa-apk
mkdir -p /tmp/sherpa-apk
unzip -q "$APK" -d /tmp/sherpa-apk
RES='upstream/patches/src/main/resources/spanishstudy/sherpa'
mkdir -p "$RES"

find /tmp/sherpa-apk -type f \( -name '*.onnx' -o -path '*/lib/arm64-v8a/*.so' \) -print | sort | tee /tmp/PAYLOAD_SOURCE_FILES.txt
test -s /tmp/PAYLOAD_SOURCE_FILES.txt
test "$(grep -c '\.onnx$' /tmp/PAYLOAD_SOURCE_FILES.txt)" -ge 2
test "$(grep -c '\.so$' /tmp/PAYLOAD_SOURCE_FILES.txt)" -ge 1

while IFS= read -r f; do
  b="$(basename "$f")"
  if test -e "$RES/$b"; then echo "duplicate payload basename: $b" >&2; exit 2; fi
  cp "$f" "$RES/$b"
done < /tmp/PAYLOAD_SOURCE_FILES.txt

curl -fL --retry 3 'https://huggingface.co/Revai/reverb-diarization-v1/raw/main/LICENSE' -o "$RES/REV_REVERB_DIARIZATION_V1_LICENSE.txt"
curl -fL --retry 3 'https://raw.githubusercontent.com/alibaba-damo-academy/3D-Speaker/master/LICENSE' -o "$RES/THREEDSPEAKER_LICENSE.txt" || true
curl -fL --retry 3 'https://raw.githubusercontent.com/k2-fsa/sherpa-onnx/v1.13.7/LICENSE' -o "$RES/SHERPA_ONNX_LICENSE.txt" || true
cat > "$RES/NOTICE.txt" <<'EOF'
Spanish Dub Study neural diarization payload

Sherpa-ONNX 1.13.7: https://github.com/k2-fsa/sherpa-onnx
Speaker segmentation: Revai/reverb-diarization-v1, converted for sherpa-onnx.
Licensed by Rev under the Rev Model Non-Production License.
Speaker embedding: 3D-Speaker ERes2Net 16 kHz model, converted for sherpa-onnx.

This v2.33.5 checkpoint packages these files for startup/injection testing only.
Neural loading, model construction, PCM feed, inference, and voice routing remain disabled.
EOF
(cd "$RES" && sha256sum * | sort) | tee /tmp/PAYLOAD_SHA256SUMS.txt
du -ah "$RES" | sort -h | tail -30

python3 - <<'PY'
from pathlib import Path
res=Path('upstream/patches/src/main/resources/spanishstudy/sherpa')
names=sorted(p.name for p in res.iterdir() if p.is_file())
assert any(x.endswith('.onnx') for x in names)
assert any(x.endswith('.so') for x in names)
arr=',\n            '.join('"'+x.replace('\\','\\\\').replace('"','\\"')+'"' for x in names)
src=f'''package app.morphe.patches.youtube.video.voiceovertranslation

import app.morphe.patcher.patch.rawResourcePatch
import app.morphe.util.inputStreamFromBundledResource
import java.nio.file.Files

/**
 * v2.33.5 startup-safe neural payload injection.
 * Copies model/native files into APK assets only. Nothing is loaded or executed.
 */
internal val speakerNeuralPayloadPatch = rawResourcePatch {{
    execute {{
        val payloadFiles = arrayOf(
            {arr}
        )
        payloadFiles.forEach {{ sourceFileName ->
            val input = inputStreamFromBundledResource(
                "spanishstudy/sherpa",
                sourceFileName
            ) ?: error("Missing bundled neural payload: $sourceFileName")
            val target = get("assets/spanishstudy/sherpa/$sourceFileName", false).toPath()
            Files.createDirectories(target.parent)
            input.use {{ Files.copy(it, target) }}
        }}
    }}
}}
'''
out=Path('upstream/patches/src/main/kotlin/app/morphe/patches/youtube/video/voiceovertranslation/SpeakerNeuralPayloadPatch.kt')
out.write_text(src)

vot=Path('upstream/patches/src/main/kotlin/app/morphe/patches/youtube/video/voiceovertranslation/VoiceOverTranslationPatch.kt')
text=vot.read_text()
needle='''        voiceOverTranslationResourcePatch,\n        playerVolumeHookPatch'''
repl='''        voiceOverTranslationResourcePatch,\n        speakerNeuralPayloadPatch,\n        playerVolumeHookPatch'''
if needle not in text:
    raise SystemExit('VoiceOverTranslationPatch dependency anchor not found')
vot.write_text(text.replace(needle,repl,1))
print(out.read_text())
PY

pushd upstream
chmod +x gradlew
./gradlew :patches:buildAndroid --no-daemon
popd

mkdir -p dist
cp upstream/patches/build/libs/*.mpp dist/v2335-delta-build.mpp
cp /tmp/SOURCE_APK_SHA256.txt dist/
cp /tmp/SOURCE_APK_CONTENTS.txt dist/
cp /tmp/PAYLOAD_SOURCE_FILES.txt dist/
cp /tmp/PAYLOAD_SHA256SUMS.txt dist/
python3 - <<'PY'
import zipfile, hashlib, pathlib
p=pathlib.Path('dist/v2335-delta-build.mpp')
with zipfile.ZipFile(p) as z:
    names=z.namelist()
    wanted=[n for n in names if 'SpeakerNeuralPayloadPatch' in n or n.endswith('VoiceOverTranslationPatchKt.class') or n.startswith('spanishstudy/sherpa/')]
    pathlib.Path('dist/DELTA_ENTRIES.txt').write_text('\n'.join(wanted)+'\n')
    assert any('SpeakerNeuralPayloadPatch' in n for n in wanted)
    assert any(n.endswith('.onnx') for n in wanted)
    assert any(n.endswith('.so') for n in wanted)
    for n in wanted:
        d=z.read(n)
        print(hashlib.sha256(d).hexdigest(), len(d), n)
PY
sha256sum dist/v2335-delta-build.mpp > dist/DELTA_MPP_SHA256.txt
cat dist/DELTA_ENTRIES.txt
