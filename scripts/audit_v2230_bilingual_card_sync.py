#!/usr/bin/env python3
from pathlib import Path
import sys

def req(t,n,label):
    if n not in t: raise RuntimeError(f'missing {label}: {n}')
    print('ok:',label)

def main():
    root=Path(sys.argv[1]).resolve(); study=root/'extensions/youtube/src/main/java/app/spanishstudy/vot'
    ov=(study/'SpanishSubtitleOverlay.java').read_text(encoding='utf-8')
    ctl=(study/'SpanishStudyController.java').read_text(encoding='utf-8')
    req(ov,'BilingualCardPolicy.PairPages','paired cache')
    req(ov,'int sharedPage = BilingualCardPolicy.pairIndex(pair.size(), progress);','shared page index')
    req(ov,'translatedPage = pairedPage(pair.spanish, sharedPage);','Spanish shared card')
    req(ov,'sourcePage = pairedPage(pair.english, sharedPage);','English shared card')
    req(ctl,'Spanish Dub Study v2.23.0 diagnostics','version')
    req(ctl,'subtitleBilingualCardSync=shared-count+shared-index+simultaneous-flip','diagnostic policy')
    print('v2.23 bilingual card sync audit: OK')
if __name__=='__main__': main()
