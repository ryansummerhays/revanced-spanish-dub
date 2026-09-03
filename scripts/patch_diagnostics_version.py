#!/usr/bin/env python3
from pathlib import Path
import sys
root=Path(sys.argv[1]).resolve()
p=root/'extensions/youtube/src/main/java/app/spanishstudy/vot/SpanishStudyController.java'
t=p.read_text(encoding='utf-8')
old='Spanish Dub Study v2.6.3 diagnostics'
new='Spanish Dub Study v2.6.4 diagnostics'
if t.count(old)!=1:
    raise RuntimeError(f'expected one diagnostics version label, found {t.count(old)}')
p.write_text(t.replace(old,new,1),encoding='utf-8')
print('patched: diagnostics version label')
