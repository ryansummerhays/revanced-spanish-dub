#!/usr/bin/env python3
from pathlib import Path
import shutil, sys

def rep(path, old, new, label, count=1):
    t=path.read_text(encoding='utf-8'); n=t.count(old)
    if n!=count: raise RuntimeError(f'{label}: expected {count}, found {n}')
    path.write_text(t.replace(old,new,count),encoding='utf-8'); print('patched:',label)

def ins(path, anchor, text, label):
    t=path.read_text(encoding='utf-8'); n=t.count(anchor)
    if n!=1: raise RuntimeError(f'{label}: expected 1 anchor, found {n}')
    path.write_text(t.replace(anchor,text+anchor,1),encoding='utf-8'); print('patched:',label)

def main():
    if len(sys.argv)!=3: raise SystemExit('usage: patch_v2230_bilingual_card_sync.py <morphe-root> <repo-root>')
    root=Path(sys.argv[1]).resolve(); repo=Path(sys.argv[2]).resolve()
    study=root/'extensions/youtube/src/main/java/app/spanishstudy/vot'
    ov=study/'SpanishSubtitleOverlay.java'; ctl=study/'SpanishStudyController.java'
    shutil.copy2(repo/'overlay/v223/app/spanishstudy/vot/BilingualCardPolicy.java',study/'BilingualCardPolicy.java')

    rep(ov,
'''    private static final Map<Integer, List<SubtitlePagePolicy.Page>> sourcePages = new HashMap<>();\n    private static final Map<Integer, Double> progressFloors = new HashMap<>();''',
'''    private static final Map<Integer, List<SubtitlePagePolicy.Page>> sourcePages = new HashMap<>();\n    private static final Map<Integer, BilingualCardPolicy.PairPages> pairedPages = new HashMap<>();\n    private static final Map<Integer, Double> progressFloors = new HashMap<>();''','add paired page cache')
    rep(ov,
'''        translatedPages.clear();\n    }\n\n    static void setSourceSegments''',
'''        translatedPages.clear();\n        pairedPages.clear();\n    }\n\n    static void setSourceSegments''','clear pair cache on translated update')
    rep(ov,
'''        sourcePages.clear();\n        translatedPages.clear();\n        progressFloors.clear();''',
'''        sourcePages.clear();\n        translatedPages.clear();\n        pairedPages.clear();\n        progressFloors.clear();''','clear pair cache on source update')
    rep(ov,
'''        translatedPages.clear();\n        sourcePages.clear();\n        progressFloors.clear();''',
'''        translatedPages.clear();\n        sourcePages.clear();\n        pairedPages.clear();\n        progressFloors.clear();''','clear pair cache on overlay clear')

    old='''        ShownPage sourcePage = pageFor(sourcePages, pairSourceIndex,\n                source == null ? "" : source.text, progress);\n        ShownPage translatedPage = pageFor(translatedPages, displayIndex,\n                translated == null ? "" : translated.text, progress);'''
    new='''        ShownPage sourcePage;\n        ShownPage translatedPage;\n        if (hasDubText && source != null && displayIndex >= 0) {\n            BilingualCardPolicy.PairPages pair = pairedPages.get(displayIndex);\n            if (pair == null) {\n                pair = BilingualCardPolicy.build(translated.text, source.text);\n                pairedPages.put(displayIndex, pair);\n            }\n            int sharedPage = BilingualCardPolicy.pairIndex(pair.size(), progress);\n            translatedPage = pairedPage(pair.spanish, sharedPage);\n            sourcePage = pairedPage(pair.english, sharedPage);\n        } else {\n            sourcePage = pageFor(sourcePages, pairSourceIndex, source == null ? "" : source.text, progress);\n            translatedPage = pageFor(translatedPages, displayIndex, translated == null ? "" : translated.text, progress);\n        }'''
    rep(ov,old,new,'use one shared bilingual card index')

    ins(ov,
'''    private static ShownPage pageFor(Map<Integer, List<SubtitlePagePolicy.Page>> cache,''',
'''    private static ShownPage pairedPage(List<String> pages, int index) {\n        if (pages == null || pages.isEmpty() || index < 0 || index >= pages.size())\n            return new ShownPage("", -1, pages == null ? 0 : pages.size());\n        return new ShownPage(pages.get(index), index, pages.size());\n    }\n\n''','add paired page renderer')

    rep(ctl,'report.append("Spanish Dub Study v2.22.0 diagnostics\\n");',
            'report.append("Spanish Dub Study v2.23.0 diagnostics\\n");','bump diagnostics')
    rep(ctl,'report.append("subtitleProgressSync=actual-audio-start+tts-window+source-only-fallback\\n");',
'''report.append("subtitleProgressSync=actual-audio-start+tts-window+source-only-fallback\\n");\n        report.append("subtitleBilingualCardSync=shared-count+shared-index+simultaneous-flip\\n");''','publish shared bilingual card policy')
    print('v2.23 bilingual card sync complete')

if __name__=='__main__': main()
