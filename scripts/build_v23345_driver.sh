#!/usr/bin/env bash
set -euo pipefail
python3 -m py_compile scripts/audit_v23345_calibrated_neighborhood.py
bash scripts/build_v23344_driver.sh
LIVE=upstream/extensions/youtube/src/main/java/app/spanishstudy/vot/LiveSpeakerOnline.java
SHERPA=upstream/extensions/youtube/src/main/java/app/spanishstudy/vot/SherpaNeuralShadow.java
CONTROLLER=upstream/extensions/youtube/src/main/java/app/spanishstudy/vot/SpanishStudyController.java
printf '%s  %s\n' 431a30811c3eeee604d342a15192eef5f2d77eaa2cfbdcff84e21fca1f61be6c "$LIVE" | sha256sum -c -
printf '%s  %s\n' 2b4012c4e5353769b1d1d1927aeca3b6bcee482a3d12d2411693fbd539de5626 "$SHERPA" | sha256sum -c -
printf '%s  %s\n' 4ef47fbaa9ad81ffacb6fcdef817931f5c6c096cade953b11a965ae3f7b1f6d5 "$CONTROLLER" | sha256sum -c -
cat scripts/v23345_source.patch.gz.b64.* | tr -d '\r\n' | base64 -d > /tmp/v23345_source.patch.gz
echo '9b4c03a03aa778b02c34fce45624170e3fa57d96a669233cb6d5acd7b2bf9000  /tmp/v23345_source.patch.gz' | sha256sum -c -
gzip -t /tmp/v23345_source.patch.gz
gzip -dc /tmp/v23345_source.patch.gz > /tmp/v23345_source.patch
echo 'ace55045d49b6da399234ffe235d8638b4312ba7d9e9772c00fc6815b59051be  /tmp/v23345_source.patch' | sha256sum -c -
(cd upstream/extensions/youtube/src/main/java/app/spanishstudy/vot && patch --batch --forward -p1 < /tmp/v23345_source.patch)
printf '%s  %s\n' 314a7ca6ab50154329ae0bc5b6b56b7b8e066f62fd4598cecc5fc771288539ee "$LIVE" | sha256sum -c -
printf '%s  %s\n' 2b4012c4e5353769b1d1d1927aeca3b6bcee482a3d12d2411693fbd539de5626 "$SHERPA" | sha256sum -c -
printf '%s  %s\n' a3787e30cfa768004e5043216049708e621c050139c973fa590adb2ca2570e12 "$CONTROLLER" | sha256sum -c -
python3 scripts/audit_v23345_calibrated_neighborhood.py upstream
(cd upstream && chmod +x gradlew && ./gradlew :patches:buildAndroid --no-daemon)
python3 scripts/audit_v23312_caption_bootstrap_source.py upstream
python3 scripts/audit_v23327_neural_payload_source.py upstream
python3 scripts/audit_v23345_calibrated_neighborhood.py upstream
rm -rf dist && mkdir -p dist
MPP="$(find upstream/patches/build/libs -maxdepth 1 -type f -name '*.mpp' | head -n1)"
test -n "$MPP"
unzip -p "$MPP" extensions/youtube.mpe > dist/youtube-v23345-source-compiled.mpe
unzip -p "$MPP" classes.dex > dist/patches-v23345-classes.dex
unzip -p "$MPP" app/morphe/patches/youtube/video/volume/PlayerVolumeHookPatchKt.class > dist/PlayerVolumeHookPatchKt.class
strings dist/youtube-v23345-source-compiled.mpe | grep 'Spanish Dub Study v2.33.45 calibrated neighborhood statistical speaker identity diagnostics'
strings dist/youtube-v23345-source-compiled.mpe | grep 'speakerIdentityAuthority=calibrated-neighborhood-statistical-v23345'
strings dist/youtube-v23345-source-compiled.mpe | grep 'speakerStatSeedPolicy=empirical-gap-neighborhood-edge;singleton-bootstrap-stricter;established-cluster-needs-multiple-member-support;recomputed-and-reversible'
strings dist/youtube-v23345-source-compiled.mpe | grep 'speakerStatAdaptiveModeReuseFloorPermille='
strings dist/youtube-v23345-source-compiled.mpe | grep 'speakerStatCalibratedNeighborhoodEdges='
strings -n 3 dist/patches-v23345-classes.dex | grep 'observeAudioTrackWriteResultForStudy'
strings -n 3 dist/PlayerVolumeHookPatchKt.class | grep 'observePcmBufferForStudy'
strings -n 3 dist/PlayerVolumeHookPatchKt.class | grep 'observeAudioTrackWriteResultForStudy'
if strings -n 3 dist/PlayerVolumeHookPatchKt.class | grep -q 'observeAcceptedPcmBufferForStudy'; then exit 1; fi
unzip -l "$MPP" | grep 'SpeakerNeuralPayloadPatchKt.class'
cp "$MPP" dist/spanish-dub-v23345-source-build-NOT-INSTALL.mpp
sha256sum dist/* > dist/SHA256SUMS.txt
