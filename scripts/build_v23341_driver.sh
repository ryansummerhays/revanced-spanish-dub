#!/usr/bin/env bash
set -euo pipefail

python3 -m py_compile scripts/audit_v23341_clean_episode_statistics.py

# Rebuild and audit the exact v40 chain first.
bash scripts/build_v23340_driver.sh

LIVE=upstream/extensions/youtube/src/main/java/app/spanishstudy/vot/LiveSpeakerOnline.java
SHERPA=upstream/extensions/youtube/src/main/java/app/spanishstudy/vot/SherpaNeuralShadow.java
CONTROLLER=upstream/extensions/youtube/src/main/java/app/spanishstudy/vot/SpanishStudyController.java
printf '%s  %s\n' dd6042c2cef97f1ddc5fd07d2a9f91c2ac6c209bf48c3f47eb7b5af0421cb65c "$LIVE" | sha256sum -c -
printf '%s  %s\n' eb08583da4c2442e6d4e9040d34694eb7c5ba487a73008a00fd66d5140780167 "$SHERPA" | sha256sum -c -
printf '%s  %s\n' 688964730c41a9c82579da87bd15b47ff66d6737e31d65541d781f62d6718267 "$CONTROLLER" | sha256sum -c -

cat scripts/v23341_source.patch.gz.b64.* | tr -d '\r\n' | base64 -d > /tmp/v23341_source.patch.gz
echo '68d4fbb47c509bc531930af87fe8f6ab0e907b1d8055a58e4f71608bc138c0fe  /tmp/v23341_source.patch.gz' | sha256sum -c -
gzip -t /tmp/v23341_source.patch.gz
gzip -dc /tmp/v23341_source.patch.gz > /tmp/v23341_source.patch
echo 'a29fae092246a9bd149fc1934f0c9eadeb990d9f8a6b96dcca6a84077ee7b7ed  /tmp/v23341_source.patch' | sha256sum -c -
(
  cd upstream/extensions/youtube/src/main/java/app/spanishstudy/vot
  patch --batch --forward -p1 < /tmp/v23341_source.patch
)
printf '%s  %s\n' 390fe802672a109106d2650198ad66e740d3414b90128f16d3bc655904137f99 "$LIVE" | sha256sum -c -
printf '%s  %s\n' 2b4012c4e5353769b1d1d1927aeca3b6bcee482a3d12d2411693fbd539de5626 "$SHERPA" | sha256sum -c -
printf '%s  %s\n' 81364bfe7a86ccdcbd3840b880420945ac3fa76987341a4ac66b4bc91d759868 "$CONTROLLER" | sha256sum -c -

python3 scripts/audit_v23341_clean_episode_statistics.py upstream

(
  cd upstream
  chmod +x gradlew
  ./gradlew :patches:buildAndroid --no-daemon
)

python3 scripts/audit_v23312_caption_bootstrap_source.py upstream
python3 scripts/audit_v23327_neural_payload_source.py upstream
python3 scripts/audit_v23341_clean_episode_statistics.py upstream

rm -rf dist && mkdir -p dist
MPP="$(find upstream/patches/build/libs -maxdepth 1 -type f -name '*.mpp' | head -n1)"
test -n "$MPP"
unzip -p "$MPP" extensions/youtube.mpe > dist/youtube-v23341-source-compiled.mpe
unzip -p "$MPP" classes.dex > dist/patches-v23341-classes.dex
unzip -p "$MPP" app/morphe/patches/youtube/video/volume/PlayerVolumeHookPatchKt.class > dist/PlayerVolumeHookPatchKt.class

# Compiled-runtime gates.
strings dist/youtube-v23341-source-compiled.mpe | grep 'Spanish Dub Study v2.33.41 clean-episode statistical speaker identity diagnostics'
strings dist/youtube-v23341-source-compiled.mpe | grep 'speakerIdentityAuthority=clean-episode-statistical-v23341'
strings dist/youtube-v23341-source-compiled.mpe | grep 'speakerLiveMode=shadow-eres2net-v23340+clean-episode-statistical-authority-v23341'
strings dist/youtube-v23341-source-compiled.mpe | grep 'speakerStatConsensusPolicy=central+two-overlapping-context-probes-majority;not-independent-votes'
strings dist/youtube-v23341-source-compiled.mpe | grep 'speakerStatObservationPolicy=one-contiguous-clean-speaker-episode-one-independent-evidence-group'
strings dist/youtube-v23341-source-compiled.mpe | grep 'speakerStatResampler=stateful-biquad-antialias+rational-phase+accepted-slice-sample-provenance'
strings dist/youtube-v23341-source-compiled.mpe | grep 'speakerStatIndependentGroups='
strings dist/youtube-v23341-source-compiled.mpe | grep 'speakerStatModeMap='
strings dist/youtube-v23341-source-compiled.mpe | grep 'speakerNeuralAcceptedPcmAuthority=postwrite-return-value+threadlocal-prewrite-buffer-reference+advanced-position'
strings dist/youtube-v23341-source-compiled.mpe | grep 'pcmLifecycleReset=new-video+full-close-visible-reset;pause-keep;seek-continuity-invalidate'
strings -n 3 dist/patches-v23341-classes.dex | grep 'observeAudioTrackWriteResultForStudy'
strings -n 3 dist/PlayerVolumeHookPatchKt.class | grep 'observePcmBufferForStudy'
strings -n 3 dist/PlayerVolumeHookPatchKt.class | grep 'observeAudioTrackWriteResultForStudy'
if strings -n 3 dist/PlayerVolumeHookPatchKt.class | grep -q 'observeAcceptedPcmBufferForStudy'; then
  echo 'ERROR: verifier-unsafe post-write ByteBuffer callback remains in target hook class' >&2
  exit 1
fi
unzip -l "$MPP" | grep 'SpeakerNeuralPayloadPatchKt.class'

cp "$MPP" dist/spanish-dub-v23341-source-build-NOT-INSTALL.mpp
sha256sum dist/* > dist/SHA256SUMS.txt
ls -lh dist/
cat dist/SHA256SUMS.txt
