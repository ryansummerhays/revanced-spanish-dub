#!/usr/bin/env python3
from pathlib import Path
import shutil, sys

def rep(path, old, new, label):
    t=path.read_text(encoding='utf-8'); n=t.count(old)
    if n!=1: raise RuntimeError(f'{label}: expected 1, found {n}')
    path.write_text(t.replace(old,new,1),encoding='utf-8'); print('patched:',label)

def main():
    if len(sys.argv)!=3: raise SystemExit('usage: patch_v2240_larger_cards.py <morphe-root> <repo-root>')
    root=Path(sys.argv[1]).resolve(); repo=Path(sys.argv[2]).resolve()
    study=root/'extensions/youtube/src/main/java/app/spanishstudy/vot'
    ctl=study/'SpanishStudyController.java'
    shutil.copy2(repo/'overlay/v224/app/spanishstudy/vot/SubtitlePagePolicy.java', study/'SubtitlePagePolicy.java')
    print('copied: v2.24 SubtitlePagePolicy.java')
    rep(ctl,'report.append("Spanish Dub Study v2.23.0 diagnostics\\n");',
            'report.append("Spanish Dub Study v2.24.0 diagnostics\\n");','bump diagnostics')
    rep(ctl,'report.append("subtitleLinePolicy=lossless-pagination-10words-68chars+3-line-safety\\n");',
            'report.append("subtitleLinePolicy=lossless-bilingual-pagination-13words-88chars+3-line-safety\\n");','publish roomier card size')
    # v2.20 renamed this diagnostics string while changing the request transport. Normalize the
    # text-only anchor on the v2.25 branch so the following release patch can replace it cleanly.
    rep(ctl,'report.append("speakerBackend=gemini-3.7-flash-youtube-agentic-audio-sidecar\\n");',
            'report.append("speakerBackend=gemini-3.7-flash-youtube-audio-sidecar\\n");','normalize v2.25 speaker backend anchor')
    print('v2.24 larger synchronized bilingual cards complete')

if __name__=='__main__': main()
