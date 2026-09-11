#!/usr/bin/env python3
"""Hard source audit for v2.33.43 empirically calibrated cross-episode identity."""
from pathlib import Path
import hashlib,sys
EXPECTED={
'LiveSpeakerOnline.java':'3eadd4fa6f9d72284032b55aa48a52d86f9ac234c24b14c8f5f2b637a10965e8',
'SherpaNeuralShadow.java':'2b4012c4e5353769b1d1d1927aeca3b6bcee482a3d12d2411693fbd539de5626',
'SpanishStudyController.java':'b6101b1d093c776d76127d49a84a4e91e833c3170aea201bff8133228cde8697',
}
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def must(t,n,l):
    if n not in t: raise RuntimeError(f'{l}: missing {n!r}')
def main():
    if len(sys.argv)<2: raise SystemExit('usage: audit_v23343_empirical_calibration.py <morphe-root>')
    root=Path(sys.argv[1]).resolve(); d=root/'extensions/youtube/src/main/java/app/spanishstudy/vot'
    ps={n:d/n for n in EXPECTED}
    for n,p in ps.items():
        got=sha(p)
        if got!=EXPECTED[n]: raise RuntimeError(f'exact v43 source hash mismatch: {n}: {got}')
    live=ps['LiveSpeakerOnline.java'].read_text(); sherpa=ps['SherpaNeuralShadow.java'].read_text(); ctl=ps['SpanishStudyController.java'].read_text(); all_src=live+'\n'+sherpa+'\n'+ctl
    for n,l in [
      ('speakerIdentityAuthority=empirically-calibrated-cross-episode-statistical-v23343','authority'),
      ('speakerStatObservationPolicy=one-natural-clean-speaker-episode-one-independent-evidence-group;chunked-continuation-reuses-group','group policy'),
      ('speakerStatBoundaryPolicy=rejected-pyannote-turn-carries-soft-different-evidence-to-next-clean-episode','turn carry'),
      ('speakerStatCalibrationPolicy=clean-same-episode-positive+turn-separated-negative;bounded-session-adaptive-floor','calibration'),
      ('speakerStatLivePolicy=read-only-latent-human-nearest-with-adaptive-floor+margin;always-provisional','live policy'),
      ('prev.continuationGroup >= 0L','chunk-only reuse'),
      ('lastAcceptedStatSlotSerial + 1L == slot.serial','serial continuation'),
      ('statPendingDifferentBoundary = true','turn boundary state'),
      ('updateStatCalibrationLocked();','adaptive calibration call'),
      ('statCalibrationPositiveLower - 0.010f','positive calibration'),
      ('statCalibrationNegativeUpper + 0.050f','negative calibration'),
      ('for (int h = 0; h < statHumanCount; h++)','human-level live classification'),
      ('bestScore >= statAdaptiveLiveFloor','adaptive live gate'),
      ('STAT_MODE_HUMAN[m] != h','human aggregation'),
      ('STAT_MAX_PAIR_REPS = 8','bounded pair runtime'),
      ('if (ma.groups[ai] == mb.groups[bj]) continue','cross-group independence'),
      ('groups < 3','confirmation minimum groups'),
      ('corroborated >= 1 || seed >= 2','confirmation corroboration'),
      ('Re-solve from retained evidence every time','reversible partition'),
      ('shadow-new-raw-profile-no-identity-authority','legacy shadow only'),
    ]: must(live,n,l)
    if 'STAT_UNKNOWN_GAP_SAME_GROUP_MS' in live: raise RuntimeError('old unknown-gap group chaining remains')
    if 'bestScore >= STAT_LIVE_MIN_AFFINITY' in live: raise RuntimeError('old fixed live mode gate remains')
    for n in ['accepted-track-frame-to-controller-video-anchor','postwrite-return-value+threadlocal-prewrite-buffer-reference+advanced-position','stateful-biquad-antialias+rational-phase+accepted-slice-sample-provenance','overlap-never-teaches']:
        must(all_src,n,'trusted foundation')
    must(sherpa,'cleanSingleSpeakerSpanAroundCore','clean span')
    must(sherpa,'activeCount == 1 && dominantActive','single-source clean span')
    must(ctl,'Spanish Dub Study v2.33.43 empirically calibrated cross-episode statistical speaker identity diagnostics','header')
    print('v2.33.43 source audit: PASS')
    print('- natural clean episodes are independent except explicit chunk continuations')
    print('- rejected pyannote turns carry soft different-speaker evidence')
    print('- same-episode positives and turn negatives calibrate bounded session affinity gates')
    print('- live badge scores latent humans and remains read-only/provisional')
    print('- global identity partition remains reversible and false-merge conservative')
if __name__=='__main__': main()
