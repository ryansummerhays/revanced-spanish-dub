#!/usr/bin/env python3
from pathlib import Path
import sys


def need(path: Path, needle: str, label: str) -> None:
    text = path.read_text(encoding='utf-8', errors='ignore')
    if needle not in text:
        raise RuntimeError(f'FAIL {label}: missing {needle!r} in {path}')
    print('PASS', label)


def forbid(path: Path, needle: str, label: str) -> None:
    text = path.read_text(encoding='utf-8', errors='ignore')
    if needle in text:
        raise RuntimeError(f'FAIL {label}: forbidden {needle!r} in {path}')
    print('PASS', label)


def main():
    if len(sys.argv) != 2:
        raise SystemExit('usage: audit_v23335_badge_translation_integrity.py <morphe-root>')
    root = Path(sys.argv[1]).resolve()
    live = root / 'extensions/youtube/src/main/java/app/spanishstudy/vot/LiveSpeakerOnline.java'
    controller = root / 'extensions/youtube/src/main/java/app/spanishstudy/vot/SpanishStudyController.java'
    translator = root / 'extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation/TranscriptTranslator.java'
    for p in (live, controller, translator):
        if not p.is_file(): raise RuntimeError(f'missing source {p}')

    need(live, 'speakerLiveMode=eres2net-short-window-online-human-identity-v23335', 'v35 live mode')
    need(live, 'speakerLiveBadgePolicy=confirmed-A-B;provisional-A?-B?;unassigned-?;never-blank-for-live-uncertainty', 'persistent badge policy')
    need(live, 'return labelFor(candidate.parentSpeaker) + "?";', 'parent provisional label')
    need(live, 'return "?";', 'explicit unknown label')
    need(live, 'return labelFor(TL_SPEAKER[i]) + "?";', 'bounded lag provisional label')
    need(live, 'c.count < 2', 'two-window style bridge')
    need(live, 'MAX_PROTOTYPES = 4', 'four prototypes per human')
    need(live, 'STYLE_PENDING_CONFIRMATIONS = 3', 'prototype quarantine retained')
    need(live, 'candidate.distinctSpeechRuns >= 2', 'new-human boundary evidence retained')
    need(translator, 'OpenRouter zero-parsed-output failure', 'zero parse fails closed')
    need(translator, 'throw new Exception("OpenRouter output alignment mismatch: zero parsed slots")', 'zero parse exception')
    need(translator, 'OpenRouter language-guard preserve-prefix=', 'valid prefix preservation')
    need(translator, 'OpenRouter recovery action=retry-once', 'retry-once recovery retained')
    need(translator, 'OpenRouter recovery action=google-batch-fallback-success', 'Google batch fallback retained')
    need(controller, 'Spanish Dub Study v2.33.35 persistent speaker badge + translation integrity diagnostics', 'v35 header')
    forbid(live, 'new AudioRecord(', 'no microphone capture')
    print('v2.33.35 source audit PASS')

if __name__ == '__main__': main()
