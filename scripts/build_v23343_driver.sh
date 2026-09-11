#!/usr/bin/env bash
set -euo pipefail
python3 -m py_compile scripts/audit_v23343_empirical_calibration.py
bash scripts/build_v23342_r2_driver.sh
LIVE=upstream/extensions/youtube/src/main/java/app/spanishstudy/vot/LiveSpeakerOnline.java
SHERPA=upstream/extensions/youtube/src/main/java/app/spanishstudy/vot/SherpaNeuralShadow.java
CONTROLLER=upstream/extensions/youtube/src/main/java/app/spanishstudy/vot/SpanishStudyController.java
printf '%s  %s\n' a436664f71f6f65825bd5782f1e3a262842bc1d0c9cfc601f606e8d6b6aecacf "$LIVE" | sha256sum -c -
printf '%s  %s\n' 2b4012c4e5353769b1d1d1927aeca3b6bcee482a3d12d2411693fbd539de5626 "$SHERPA" | sha256sum -c -
printf '%s  %s\n' 25a06af074c20880887da3395f45c47a9fef58b095a29027e96e8ab730a9d532 "$CONTROLLER" | sha256sum -c -
cat scripts/v23343r2_source.patch.gz.b64.* | tr -d '\r\n' | base64 -d > /tmp/v23343_source.patch.gz
echo '09b497e650e14458b6605b3e668d3a9dfef397def9a3258042ba793525545378  /tmp/v23343_source.patch.gz' | sha256sum -c -
gzip -t /tmp/v23343_source.patch.gz
gzip -dc /tmp/v23343_source.patch.gz > /tmp/v23343_source.patch
echo '31f7a0f3968d70c48fba882762e41b8567d4ee1fcacc4e4ca69f2afd62fe52f5  /tmp/v23343_source.patch' | sha256sum -c -
(
 cd upstream/extensions/youtube/src/main/java/app/spanishstudy/vot
 patch --batch --forward -p1 < /tmp/v23343_source.patch
)
printf '%s  %s\n' 0a4731c74d7fd69f02057e14d736acc24111ef50cd1d53d2f66b7d9e554d12fe "$LIVE" | sha256sum -c -
printf '%s  %s\n' 2b4012c4e5353769b1d1d1927aeca3b6bcee482a3d12d2411693fbd539de5626 "$SHERPA" | sha256sum -c -
printf '%s  %s\n' b6101b1d093c776d76127d49a84a4e91e833c3170aea201bff8133228cde8697 "$CONTROLLER" | sha256sum -c -
python3 scripts/audit_v23343_empirical_calibration.py upstream
(
 cd upstream
 chmod +x gradlew
 ./gradlew :patches:buildAndroid --no-daemon
)
python3 scripts/audit_v23312_caption_bootstrap_source.py upstream
python3 scripts/audit_v23327_neural_payload_source.py upstream
python3 scripts/audit_v23343_empirical_calibration.py upstream
rm -rf dist && mkdir -p dist
MPP="$(find upstream/patches/build/libs -maxdepth 1 -type f -name '*.mpp' | head -n1)"
test -n "$MPP"
unzip -p "$MPP" extensions/youtube.mpe > dist/youtube-v23343-source-compiled.mpe
unzip -p "$MPP" classes.dex > dist/patches-v23343-classes.dex
unzip -p "$MPP" app/morphe/patches/youtube/video/volume/PlayerVolumeHookPatchKt.class > dist/PlayerVolumeHookPatchKt.class
strings dist/youtube-v23343-source-compiled.mpe | grep 'Spanish Dub Study v2.33.43 empirically calibrated cross-episode statistical speaker identity diagnostics'
strings dist/youtube-v23343-source-compiled.mpe | grep 'speakerIdentityAuthority=empirically-calibrated-cross-episode-statistical-v23343'
strings dist/youtube-v23343-source-compiled.mpe | grep 'speakerStatObservationPolicy=one-natural-clean-speaker-episode-one-independent-evidence-group;chunked-continuation-reuses-group'
strings dist/youtube-v23343-source-compiled.mpe | grep 'speakerStatCalibrationPolicy=clean-same-episode-positive+turn-separated-negative;bounded-session-adaptive-floor'
strings dist/youtube-v23343-source-compiled.mpe | grep 'speakerStatLivePolicy=read-only-latent-human-nearest-with-adaptive-floor+margin;always-provisional'
strings dist/youtube-v23343-source-compiled.mpe | grep 'speakerStatAdaptiveSeedFloorPermille='
strings dist/youtube-v23343-source-compiled.mpe | grep 'speakerStatTurnBoundariesCarried='
strings dist/youtube-v23343-source-compiled.mpe | grep 'speakerNeuralAcceptedPcmAuthority=postwrite-return-value+threadlocal-prewrite-buffer-reference+advanced-position'
strings dist/youtube-v23343-source-compiled.mpe | grep 'pcmLifecycleReset=new-video+full-close-visible-reset;pause-keep;seek-continuity-invalidate'
strings -n 3 dist/patches-v23343-classes.dex | grep 'observeAudioTrackWriteResultForStudy'
strings -n 3 dist/PlayerVolumeHookPatchKt.class | grep 'observePcmBufferForStudy'
strings -n 3 dist/PlayerVolumeHookPatchKt.class | grep 'observeAudioTrackWriteResultForStudy'
if strings -n 3 dist/PlayerVolumeHookPatchKt.class | grep -q 'observeAcceptedPcmBufferForStudy'; then
 echo 'ERROR: verifier-unsafe post-write ByteBuffer callback remains in target hook class' >&2; exit 1
fi
unzip -l "$MPP" | grep 'SpeakerNeuralPayloadPatchKt.class'
cp "$MPP" dist/spanish-dub-v23343-source-build-NOT-INSTALL.mpp
sha256sum dist/* > dist/SHA256SUMS.txt
ls -lh dist/
cat dist/SHA256SUMS.txt
