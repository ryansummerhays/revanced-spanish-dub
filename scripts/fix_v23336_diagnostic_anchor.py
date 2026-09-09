#!/usr/bin/env python3
from pathlib import Path

p = Path('scripts/patch_v23336_streaming_context.py')
s = p.read_text(encoding='utf-8')
old = '+ lastCandidateParent +'
new = '+ (candidate != null ? candidate.parentSpeaker : lastCandidateParent) +'
if s.count(old) != 2:
    raise SystemExit(f'v23336 diagnostic anchor fix expected 2 stale expressions, found {s.count(old)}')
p.write_text(s.replace(old, new), encoding='utf-8')
print('fixed: v2.33.36 candidate-parent diagnostic anchor')
