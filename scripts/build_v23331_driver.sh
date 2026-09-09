#!/usr/bin/env bash
set -euo pipefail

gzip -dc scripts/patch_v23329_accepted_pcm_video_master.py.gz > /tmp/patch_v23329.py
gzip -dc scripts/audit_v23329_accepted_pcm_video_master.py.gz > /tmp/audit_v23329.py
python3 -m py_compile /tmp/patch_v23329.py /tmp/audit_v23329.py

rm -rf /tmp/video-master-tests && mkdir -p /tmp/video-master-tests
javac -d /tmp/video-master-tests \
  overlay/v2331/app/spanishstudy/vot/VideoSessionClock.java \
  overlay/v2331/app/spanishstudy/vot/AudioVideoTimeBridge.java \
  overlay/v2331/app/spanishstudy/vot/SpeakerTimeline.java \
  tests/VideoMasterClockFoundationTest.java
java -cp /tmp/video-master-tests app.spanishstudy.vot.VideoMasterClockFoundationTest

python3 scripts/patch_v2280_deep_diagnostics_local_diarization.py upstream .
python3 scripts/tune_v2280_local_speaker.py upstream
python3 scripts/audit_v2280_deep_diagnostics_local_diarization.py upstream
python3 scripts/patch_v2290_stability.py upstream .
python3 scripts/audit_v2290_stability.py upstream
python3 scripts/patch_v2300_runtime_stability.py upstream .
python3 scripts/audit_v2300_runtime_stability.py upstream
python3 scripts/patch_v2310_conversational_subtitles.py upstream .
python3 scripts/audit_v2310_conversational_subtitles.py upstream
for s in \
  2322_label_only \
  2323_pcm_counter_english_source \
  2324_pcm_metadata_stage_b \
  2325_pcm_sample_read_stage_c \
  2326_audiotrack_format_stage_d \
  2327_pcm16_vad_stage_e \
  2328_speaker_features_stage_f \
  2329_online_clustering_stage_g \
  23210_live_cluster_label_stage_h \
  23211_spanish_voice_toggle_stage_i \
  23212_per_video_speaker_reset_stage_j; do
  python3 "scripts/patch_v${s}.py" upstream
  python3 "scripts/audit_v${s}.py" upstream
done

AAR=/tmp/sherpa-onnx-1.13.7.aar
curl -L --fail --retry 4 -o "$AAR" https://github.com/k2-fsa/sherpa-onnx/releases/download/v1.13.7/sherpa-onnx-1.13.7.aar
echo "c4ef49e309f24fcee5c106b8a279481aaecaabb078cd37b2cd6e9a62cc8a73c8  $AAR" | sha256sum -c -
rm -rf /tmp/sherpa-aar && mkdir -p /tmp/sherpa-aar upstream/extensions/youtube/libs
unzip -q "$AAR" -d /tmp/sherpa-aar
cp /tmp/sherpa-aar/classes.jar upstream/extensions/youtube/libs/sherpa-onnx-1.13.7-classes.jar
jar tf upstream/extensions/youtube/libs/sherpa-onnx-1.13.7-classes.jar | grep 'com/k2fsa/sherpa/onnx/OfflineSpeakerDiarization.class'
jar tf upstream/extensions/youtube/libs/sherpa-onnx-1.13.7-classes.jar | grep 'com/k2fsa/sherpa/onnx/SpeakerEmbeddingExtractor.class'
jar tf upstream/extensions/youtube/libs/sherpa-onnx-1.13.7-classes.jar | grep 'com/k2fsa/sherpa/onnx/OnlineStream.class'
test ! -e upstream/extensions/youtube/src/main/jniLibs/arm64-v8a/libsherpa-onnx-jni.so

python3 scripts/patch_v23319_sherpa_source_parity.py upstream .
python3 scripts/audit_v23319_sherpa_source_parity.py upstream
python3 scripts/patch_v23312_caption_bootstrap_source.py upstream
python3 scripts/audit_v23312_caption_bootstrap_source.py upstream
python3 scripts/patch_v23324_video_master_clock_foundation.py upstream .
python3 scripts/audit_v23324_video_master_clock_foundation.py upstream
python3 scripts/prepare_v23326_driver.py upstream .
python3 scripts/patch_v23326_neural_absolute_timeline.py upstream .
python3 scripts/audit_v23326_neural_absolute_timeline.py upstream
python3 scripts/patch_v23327_neural_payload_source.py upstream
python3 scripts/audit_v23327_neural_payload_source.py upstream
python3 scripts/patch_v23327_accepted_write_accounting.py upstream .
python3 scripts/audit_v23327_accepted_write_accounting.py upstream
set +e
python3 scripts/patch_v23328_render_clock_admission.py upstream > /tmp/v23328-stage1.log 2>&1
rc=$?
set -e
cat /tmp/v23328-stage1.log
if [ "$rc" -ne 0 ]; then
  grep -q 'RuntimeError: update neural gate diagnostic: expected 1 anchor(s), found 0' /tmp/v23328-stage1.log || exit "$rc"
fi
python3 scripts/finish_v23328_render_clock_admission.py upstream
python3 scripts/audit_v23328_render_clock_admission.py upstream

python3 /tmp/patch_v23329.py upstream
python3 /tmp/audit_v23329.py upstream
python3 scripts/patch_v23330_postwrite_register_fix.py upstream
python3 scripts/audit_v23330_postwrite_register_fix.py upstream
python3 scripts/patch_v23331_live_speaker.py upstream .
python3 scripts/audit_v23331_live_speaker.py upstream

(
  cd upstream
  chmod +x gradlew
  ./gradlew :patches:buildAndroid --no-daemon
)

python3 scripts/audit_v23312_caption_bootstrap_source.py upstream
python3 scripts/audit_v23327_neural_payload_source.py upstream
python3 scripts/audit_v23330_postwrite_register_fix.py upstream
python3 scripts/audit_v23331_live_speaker.py upstream

rm -rf dist && mkdir -p dist
MPP="$(find upstream/patches/build/libs -maxdepth 1 -type f -name '*.mpp' | head -n1)"
test -n "$MPP"
unzip -p "$MPP" extensions/youtube.mpe > dist/youtube-v23331-source-compiled.mpe
unzip -p "$MPP" classes.dex > dist/patches-v23331-classes.dex
unzip -p "$MPP" app/morphe/patches/youtube/video/volume/PlayerVolumeHookPatchKt.class > dist/PlayerVolumeHookPatchKt.class
strings dist/youtube-v23331-source-compiled.mpe | grep 'Spanish Dub Study v2.33.31 near-live ERes2Net human-speaker diagnostics'
strings dist/youtube-v23331-source-compiled.mpe | grep 'speakerNeuralGate=v2.33.31-live-embedding-primary+20s-diarization-fallback'
strings dist/youtube-v23331-source-compiled.mpe | grep 'speakerNeuralAcceptedPcmAuthority=postwrite-return-value+threadlocal-prewrite-buffer-reference+advanced-position'
strings dist/youtube-v23331-source-compiled.mpe | grep 'speakerLiveMode=eres2net-short-window-online-human-identity-v23331'
strings dist/youtube-v23331-source-compiled.mpe | grep 'speakerLiveImpressionPolicy=continuous-style-change-stays-human-and-may-add-prototype'
strings dist/youtube-v23331-source-compiled.mpe | grep 'pcmLifecycleReset=new-video+full-close-visible-reset;pause-keep;seek-continuity-invalidate'
strings -n 3 dist/patches-v23331-classes.dex | grep 'observeAudioTrackWriteResultForStudy'
strings -n 3 dist/PlayerVolumeHookPatchKt.class | grep 'observePcmBufferForStudy'
strings -n 3 dist/PlayerVolumeHookPatchKt.class | grep 'observeAudioTrackWriteResultForStudy'
if strings -n 3 dist/PlayerVolumeHookPatchKt.class | grep -q 'observeAcceptedPcmBufferForStudy'; then
  echo 'ERROR: verifier-unsafe post-write ByteBuffer callback remains in target hook class' >&2
  exit 1
fi
strings dist/youtube-v23331-source-compiled.mpe | grep 'pcmWriteAcceptedBufferHandoffs='
unzip -l "$MPP" | grep 'SpeakerNeuralPayloadPatchKt.class'
cp "$MPP" dist/spanish-dub-v23331-source-build-NOT-INSTALL.mpp
sha256sum dist/* > dist/SHA256SUMS.txt
ls -lh dist/
cat dist/SHA256SUMS.txt
