#!/usr/bin/env bash
set -euo pipefail

python3 -m py_compile scripts/audit_v23342_cross_episode_statistics.py

# Rebuild and audit exact v41 first. This leaves upstream source at the trusted v41 state.
bash scripts/build_v23341_driver.sh

LIVE=upstream/extensions/youtube/src/main/java/app/spanishstudy/vot/LiveSpeakerOnline.java
SHERPA=upstream/extensions/youtube/src/main/java/app/spanishstudy/vot/SherpaNeuralShadow.java
CONTROLLER=upstream/extensions/youtube/src/main/java/app/spanishstudy/vot/SpanishStudyController.java
printf '%s  %s\n' 390fe802672a109106d2650198ad66e740d3414b90128f16d3bc655904137f99 "$LIVE" | sha256sum -c -
printf '%s  %s\n' 2b4012c4e5353769b1d1d1927aeca3b6bcee482a3d12d2411693fbd539de5626 "$SHERPA" | sha256sum -c -
printf '%s  %s\n' 81364bfe7a86ccdcbd3840b880420945ac3fa76987341a4ac66b4bc91d759868 "$CONTROLLER" | sha256sum -c -

cat scripts/v23342_source.patch.gz.b64.* | tr -d '\r\n' | base64 -d > /tmp/v23342_source.patch.gz
echo 'be2f5f4942940c2702165f4909eb43579b8036c404e0fa390b523421dcf86fa1  /tmp/v23342_source.patch.gz' | sha256sum -c -
gzip -t /tmp/v23342_source.patch.gz
gzip -dc /tmp/v23342_source.patch.gz > /tmp/v23342_source.patch
echo '4efc7cd4e5ebcb5d84253c1c7505818402f40f978347346865e68d556ddf005f  /tmp/v23342_source.patch' | sha256sum -c -
(
  cd upstream/extensions/youtube/src/main/java/app/spanishstudy/vot
  patch --batch --forward -p1 < /tmp/v23342_source.patch
)
printf '%s  %s\n' 0cd7704f09acf2769b46831a79af98f03b926022a2ecb6ecff97b63b61ae8c91 "$LIVE" | sha256sum -c -
printf '%s  %s\n' 2b4012c4e5353769b1d1d1927aeca3b6bcee482a3d12d2411693fbd539de5626 "$SHERPA" | sha256sum -c -
printf '%s  %s\n' 25a06af074c20880887da3395f45c47a9fef58b095a29027e96e8ab730a9d532 "$CONTROLLER" | sha256sum -c -
python3 scripts/audit_v23342_cross_episode_statistics.py upstream

(
  cd upstream
  chmod +x gradlew
  ./gradlew :patches:buildAndroid --no-daemon
)

python3 scripts/audit_v23312_caption_bootstrap_source.py upstream
python3 scripts/audit_v23327_neural_payload_source.py upstream
python3 scripts/audit_v23342_cross_episode_statistics.py upstream

rm -rf dist && mkdir -p dist
MPP="$(find upstream/patches/build/libs -maxdepth 1 -type f -name '*.mpp' | head -n1)"
test -n "$MPP"
unzip -p "$MPP" extensions/youtube.mpe > dist/youtube-v23342-source-compiled.mpe
unzip -p "$MPP" classes.dex > dist/patches-v23342-classes.dex
unzip -p "$MPP" app/morphe/patches/youtube/video/volume/PlayerVolumeHookPatchKt.class > dist/PlayerVolumeHookPatchKt.class

# Compiled-runtime gates.
strings dist/youtube-v23342-source-compiled.mpe | grep 'Spanish Dub Study v2.33.42 independent cross-episode statistical speaker identity diagnostics'
strings dist/youtube-v23342-source-compiled.mpe | grep 'speakerIdentityAuthority=independent-cross-episode-statistical-v23342'
strings dist/youtube-v23342-source-compiled.mpe | grep 'speakerStatCrossEpisodePolicy=greedy-disjoint-independence-group-matching;each-group-at-most-once-per-mode-pair'
strings dist/youtube-v23342-source-compiled.mpe | grep 'speakerStatSeedPolicy=very-strong-or-reciprocal-nearest-with-margin;recomputed-and-reversible'
strings dist/youtube-v23342-source-compiled.mpe | grep 'speakerStatConfirmationPolicy=minimum-three-independent-groups+jackknife-corroboration-or-majority-seeds'
strings dist/youtube-v23342-source-compiled.mpe | grep 'speakerStatBiometricIndependentMatches='
strings dist/youtube-v23342-source-compiled.mpe | grep 'speakerStatJackknifePass='
strings dist/youtube-v23342-source-compiled.mpe | grep 'speakerNeuralAcceptedPcmAuthority=postwrite-return-value+threadlocal-prewrite-buffer-reference+advanced-position'
strings dist/youtube-v23342-source-compiled.mpe | grep 'pcmLifecycleReset=new-video+full-close-visible-reset;pause-keep;seek-continuity-invalidate'
strings -n 3 dist/patches-v23342-classes.dex | grep 'observeAudioTrackWriteResultForStudy'
strings -n 3 dist/PlayerVolumeHookPatchKt.class | grep 'observePcmBufferForStudy'
strings -n 3 dist/PlayerVolumeHookPatchKt.class | grep 'observeAudioTrackWriteResultForStudy'
if strings -n 3 dist/PlayerVolumeHookPatchKt.class | grep -q 'observeAcceptedPcmBufferForStudy'; then
  echo 'ERROR: verifier-unsafe post-write ByteBuffer callback remains in target hook class' >&2
  exit 1
fi
unzip -l "$MPP" | grep 'SpeakerNeuralPayloadPatchKt.class'

cp "$MPP" dist/spanish-dub-v23342-source-build-NOT-INSTALL.mpp
sha256sum dist/* > dist/SHA256SUMS.txt
ls -lh dist/
cat dist/SHA256SUMS.txt
