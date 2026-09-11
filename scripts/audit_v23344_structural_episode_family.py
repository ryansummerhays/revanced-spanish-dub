#!/usr/bin/env python3
from pathlib import Path
import hashlib, sys
EXPECTED={
 'LiveSpeakerOnline.java':'431a30811c3eeee604d342a15192eef5f2d77eaa2cfbdcff84e21fca1f61be6c',
 'SherpaNeuralShadow.java':'2b4012c4e5353769b1d1d1927aeca3b6bcee482a3d12d2411693fbd539de5626',
 'SpanishStudyController.java':'4ef47fbaa9ad81ffacb6fcdef817931f5c6c096cade953b11a965ae3f7b1f6d5',
}
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def must(t,n,l):
    if n not in t: raise RuntimeError(f'{l}: missing {n!r}')
def main():
    root=Path(sys.argv[1]).resolve(); d=root/'extensions/youtube/src/main/java/app/spanishstudy/vot'
    ps={n:d/n for n in EXPECTED}
    for n,p in ps.items():
        g=sha(p)
        if g!=EXPECTED[n]: raise RuntimeError(f'hash mismatch {n}: {g}')
    live=ps['LiveSpeakerOnline.java'].read_text(); sherpa=ps['SherpaNeuralShadow.java'].read_text(); ctl=ps['SpanishStudyController.java'].read_text()
    for needle,label in [
      ('AudioVideoSyncProbe.projectTrackFrameToVideoMs','video master'),('STAT_CONTEXT_HOP_SAMPLES = 16_000','1s cadence'),
      ('STAT_CORE_START_SAMPLE = 72_000','centered core'),('slot.cleanVotes < 2','consensus'),
      ('configureAnalysisResamplerLocked','resampler'),('recordSampleSpanLocked','provenance'),
      ('cleanSingleSpeakerSpanAroundCore','clean span')]: must(live if needle!='cleanSingleSpeakerSpanAroundCore' else sherpa,needle,label)
    must(live,'speakerIdentityAuthority=structural-episode-family-statistical-v23344','authority')
    must(live,'statModesShareIndependenceGroupLocked','shared-group structural relation')
    must(live,'Artificial chunks that share one independence-group id','structural union comment')
    must(live,'statStructuralGroupUnions++','structural union telemetry')
    must(live,'Structural continuity never counts as independent confirmation','policy comment')
    must(live,'if (statModesShareIndependenceGroupLocked(a, b)) continue; // structural continuity is not independent confirmation','no structural confirmation inflation')
    must(live,'recordStatWithinEpisodeCalibrationLocked(b);','raw positive calibration call')
    must(live,'j = i + 2','nonadjacent positive calibration')
    must(live,'STAT_CALIBRATION_POSITIVE_RAW','raw positive reservoir')
    must(live,'Positive calibration comes from raw measurements inside clean pyannote-consistent','selection bias fix')
    must(live,'STAT_HUMAN_LABEL_ANCHOR','stable label anchors')
    must(live,'speakerStatHumanLabelPolicy=stable-earliest-mode-anchor;unrelated-merges-do-not-renumber','label telemetry')
    must(live,'speakerStatCalibrationPositiveSource=raw-within-clean-episode-measurement-pairs','calibration telemetry')
    must(live,'STAT_BIOMETRIC_SEED_MARGIN = 0.060f','seed margin')
    must(live,'groups < 3','confirmation group floor')
    must(live,'corroborated >= 1 || seed >= 2','confirmation evidence')
    must(live,'statClusterMergeVetoLocked','cluster veto')
    must(live,'return human < 0 ? "?" : statHumanLabel(human) + "?"','live provisional')
    must(ctl,'Spanish Dub Study v2.33.44 structural episode-family statistical speaker identity diagnostics','header')
    print('v2.33.44 source audit: PASS')
    print('- same independence-group chunks structurally union without adding independent confirmation')
    print('- positive calibration is collected before mode splitting, removing v43 selection bias')
    print('- display labels use stable earliest-mode anchors')
    print('- v43 clock/PCM/clean-slot/turn-boundary and conservative confirmation gates retained')
if __name__=='__main__': main()
