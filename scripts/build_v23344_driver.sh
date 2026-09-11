#!/usr/bin/env bash
set -euo pipefail
python3 -m py_compile scripts/audit_v23344_structural_episode_family.py

# Rebuild and audit exact v43 first. This leaves upstream source at the trusted v43 state.
bash scripts/build_v23343_driver.sh

LIVE=upstream/extensions/youtube/src/main/java/app/spanishstudy/vot/LiveSpeakerOnline.java
SHERPA=upstream/extensions/youtube/src/main/java/app/spanishstudy/vot/SherpaNeuralShadow.java
CONTROLLER=upstream/extensions/youtube/src/main/java/app/spanishstudy/vot/SpanishStudyController.java
printf '%s  %s\n' 0a4731c74d7fd69f02057e14d736acc24111ef50cd1d53d2f66b7d9e554d12fe "$LIVE" | sha256sum -c -
printf '%s  %s\n' 2b4012c4e5353769b1d1d1927aeca3b6bcee482a3d12d2411693fbd539de5626 "$SHERPA" | sha256sum -c -
printf '%s  %s\n' b6101b1d093c776d76127d49a84a4e91e833c3170aea201bff8133228cde8697 "$CONTROLLER" | sha256sum -c -

cat scripts/v23344_source.patch.gz.b64.* | tr -d '\r\n' | base64 -d > /tmp/v23344_source.patch.gz
echo 'c56c2e34eabbfb8179acbf529013ae17e24b3a035ed67498fcc478dbbaf057cb  /tmp/v23344_source.patch.gz' | sha256sum -c -
gzip -t /tmp/v23344_source.patch.gz
gzip -dc /tmp/v23344_source.patch.gz > /tmp/v23344_source.patch
echo '5a24455d7ab80cca2002c0c7e8b93a28438bd467770e9194d32808797b706c9c  /tmp/v23344_source.patch' | sha256sum -c -
(
  cd upstream/extensions/youtube/src/main/java/app/spanishstudy/vot
  patch --batch --forward -p1 < /tmp/v23344_source.patch
)
printf '%s  %s\n' 431a30811c3eeee604d342a15192eef5f2d77eaa2cfbdcff84e21fca1f61be6c "$LIVE" | sha256sum -c -
printf '%s  %s\n' 2b4012c4e5353769b1d1d1927aeca3b6bcee482a3d12d2411693fbd539de5626 "$SHERPA" | sha256sum -c -
printf '%s  %s\n' 4ef47fbaa9ad81ffacb6fcdef817931f5c6c096cade953b11a965ae3f7b1f6d5 "$CONTROLLER" | sha256sum -c -
python3 scripts/audit_v23344_structural_episode_family.py upstream

(
  cd upstream
  chmod +x gradlew
  ./gradlew :patches:buildAndroid --no-daemon
)

python3 scripts/audit_v23312_caption_bootstrap_source.py upstream
python3 scripts/audit_v23327_neural_payload_source.py upstream
python3 scripts/audit_v23344_structural_episode_family.py upstream

rm -rf dist && mkdir -p dist
MPP="$(find upstream/patches/build/libs -maxdepth 1 -type f -name '*.mpp' | head -n1)"
test -n "$MPP"
unzip -p "$MPP" extensions/youtube.mpe > dist/youtube-v23344-source-compiled.mpe
unzip -p "$MPP" classes.dex > dist/patches-v23344-classes.dex
unzip -p "$MPP" app/morphe/patches/youtube/video/volume/PlayerVolumeHookPatchKt.class > dist/PlayerVolumeHookPatchKt.class

strings dist/youtube-v23344-source-compiled.mpe | grep 'Spanish Dub Study v2.33.44 structural episode-family statistical speaker identity diagnostics'
strings dist/youtube-v23344-source-compiled.mpe | grep 'speakerIdentityAuthority=structural-episode-family-statistical-v23344'
strings dist/youtube-v23344-source-compiled.mpe | grep 'speakerStatObservationPolicy=one-natural-clean-speaker-episode-one-independent-evidence-group;chunked-continuation-reuses-group-and-is-structural-must-link'
strings dist/youtube-v23344-source-compiled.mpe | grep 'speakerStatCalibrationPolicy=raw-within-clean-episode-measurement-positive+turn-separated-negative;no-selected-mode-split-bias;bounded-session-adaptive-floor'
strings dist/youtube-v23344-source-compiled.mpe | grep 'speakerStatStructuralGroupUnions='
strings dist/youtube-v23344-source-compiled.mpe | grep 'speakerStatHumanLabelPolicy=stable-earliest-mode-anchor;unrelated-merges-do-not-renumber'
strings dist/youtube-v23344-source-compiled.mpe | grep 'speakerStatCalibrationPositiveSource=raw-within-clean-episode-measurement-pairs'
strings dist/youtube-v23344-source-compiled.mpe | grep 'speakerNeuralAcceptedPcmAuthority=postwrite-return-value+threadlocal-prewrite-buffer-reference+advanced-position'
strings dist/youtube-v23344-source-compiled.mpe | grep 'pcmLifecycleReset=new-video+full-close-visible-reset;pause-keep;seek-continuity-invalidate'
strings -n 3 dist/patches-v23344-classes.dex | grep 'observeAudioTrackWriteResultForStudy'
strings -n 3 dist/PlayerVolumeHookPatchKt.class | grep 'observePcmBufferForStudy'
strings -n 3 dist/PlayerVolumeHookPatchKt.class | grep 'observeAudioTrackWriteResultForStudy'
if strings -n 3 dist/PlayerVolumeHookPatchKt.class | grep -q 'observeAcceptedPcmBufferForStudy'; then
  echo 'ERROR: verifier-unsafe post-write ByteBuffer callback remains in target hook class' >&2
  exit 1
fi
unzip -l "$MPP" | grep 'SpeakerNeuralPayloadPatchKt.class'

cp "$MPP" dist/spanish-dub-v23344-source-build-NOT-INSTALL.mpp
sha256sum dist/* > dist/SHA256SUMS.txt
ls -lh dist/
cat dist/SHA256SUMS.txt
