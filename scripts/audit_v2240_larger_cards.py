#!/usr/bin/env python3
from pathlib import Path
import sys

def req(text, needle, label):
    if needle not in text: raise RuntimeError(f'missing {label}: {needle}')
    print('ok:',label)

def main():
    if len(sys.argv)!=2: raise SystemExit('usage: audit_v2240_larger_cards.py <morphe-root>')
    root=Path(sys.argv[1]).resolve(); study=root/'extensions/youtube/src/main/java/app/spanishstudy/vot'
    policy=(study/'SubtitlePagePolicy.java').read_text(encoding='utf-8')
    ctl=(study/'SpanishStudyController.java').read_text(encoding='utf-8')
    ov=(study/'SpanishSubtitleOverlay.java').read_text(encoding='utf-8')
    req(policy,'TARGET_WORDS = 13','13-word target')
    req(policy,'TARGET_CHARS = 88','88-character target')
    req(ctl,'Spanish Dub Study v2.24.0 diagnostics','v2.24 diagnostics')
    req(ctl,'subtitleLinePolicy=lossless-bilingual-pagination-13words-88chars+3-line-safety','roomier card diagnostics')
    req(ctl,'subtitleBilingualCardSync=shared-count+shared-index+simultaneous-flip','shared bilingual card policy retained')
    req(ov,'BilingualCardPolicy.PairPages','paired page rendering retained')
    print('v2.24 larger bilingual card audit: OK')

if __name__=='__main__': main()
