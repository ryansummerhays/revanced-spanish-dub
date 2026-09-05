#!/usr/bin/env python3
from pathlib import Path
import sys


def require(label, condition):
    if not condition:
        raise RuntimeError('FAILED: ' + label)
    print('ok:', label)


def main():
    if len(sys.argv) != 2:
        raise SystemExit('usage: audit_v2250_cheap_speaker_style.py <morphe-root>')
    root = Path(sys.argv[1]).resolve()
    study = root/'extensions/youtube/src/main/java/app/spanishstudy/vot'
    side = (study/'GeminiSpeakerDiarizationSidecar.java').read_text(encoding='utf-8')
    store = (study/'SpeakerAssignmentStore.java').read_text(encoding='utf-8')
    ov = (study/'SpanishSubtitleOverlay.java').read_text(encoding='utf-8')
    ctl = (study/'SpanishStudyController.java').read_text(encoding='utf-8')
    sheet = (study/'SpanishStudySheet.java').read_text(encoding='utf-8')
    line = (study/'SubtitleLinePolicy.java').read_text(encoding='utf-8')
    name = (study/'SpeakerNamePolicy.java').read_text(encoding='utf-8')

    require('v2.25 diagnostics', 'Spanish Dub Study v2.25.0 diagnostics' in ctl)
    require('OpenRouter speaker endpoint', 'openrouter.ai/api/v1/chat/completions' in side)
    require('shared Morphe OpenRouter key', 'Settings.VOT_OPENROUTER_API_KEY.get()' in side)
    require('no direct Gemini API key gate', 'geminiApiKey(context)' not in side and 'speakerApiKey(context)' not in side)
    require('Google AI Studio pinned for YouTube URL', 'google-ai-studio' in side and 'allow_fallbacks' in side)
    require('agentic YouTube video input', 'video_url' in side and 'processing", "agentic"' in side)
    require('cheap first model', 'google/gemini-3.5-flash-lite' in side)
    require('strong fallback model', 'google/gemini-3.7-flash' in side and 'strongFallbacks' in side)
    require('Flex cheap tier', '"flex"' in side and 'service_tier' in side)
    require('structured JSON schema', 'json_schema' in side and 'strict' in side)
    require('response healing', 'response-healing' in side)
    require('actual OpenRouter cost telemetry', 'usage.optDouble("cost"' in side and 'speakerActualCostUsd' in side)
    require('one-shot completion latch', 'analysisComplete' in side)
    require('stale speaker work is dropped', 'isSpeakerRequestCurrent' in side and 'staleDrops' in side)

    require('name evidence must exist in transcript', 'corpus.contains(ev)' in name)
    require('name evidence itself contains proposed name', 'ev.contains(normalize(name))' in name)
    require('generic roles rejected', 'GENERIC' in name)
    require('anonymous speaker identity retained', 'speakerLabel(TranscriptSegment seg)' in store)
    require('human-readable display label separated', 'displayLabel(TranscriptSegment seg)' in store)
    require('voice routing still uses anonymous label', "c >= 'A' && c <= 'H'" in store)
    require('profile details expose verified name evidence', 'Transcript evidence:' in store)
    require('controller display uses verified alias', 'SpeakerAssignmentStore.displayLabel(segment)' in ctl)

    require('v2.23 shared bilingual card retained', 'BilingualCardPolicy.PairPages' in ov and 'sharedPage' in ov)
    require('v2.24 roomier pagination retained', '13words-88chars' in ctl)
    require('42 character line target', 'TARGET_CHARS_PER_LINE = 42' in line)
    require('two-line per-language policy', 'MAX_LINES = 2' in line and 'view.setMaxLines(2)' in ov)
    require('line formatting is lossless display-only', 'SubtitleLinePolicy.format(translatedPage.text)' in ov and 'SubtitleLinePolicy.format(sourcePage.text)' in ov)
    require('single coherent dark card', 'cardBackground.setColor(0xD6000000)' in ov)
    require('individual text backgrounds removed', 'view.setBackground(null)' in ov)
    require('English is secondary', 'sourceView.setTextColor(0xD9FFFFFF)' in ov)
    require('bracket speaker identifier', '"[" + speaker + "]"' in ov)
    require('content-hugging centered card', 'ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT' in ov)
    require('obsolete separate speaker key row removed', '"Speaker analysis API key"' not in sheet)
    require('sheet explains shared OpenRouter key', 'existing OpenRouter key' in sheet)
    require('sheet explains transcript-established names', 'transcript itself clearly establishes it' in sheet)

    print('v2.25 cheap OpenRouter speaker + subtitle standards audit: OK')


if __name__ == '__main__':
    main()
