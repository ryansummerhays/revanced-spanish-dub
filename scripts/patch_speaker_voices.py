#!/usr/bin/env python3
from pathlib import Path
import sys

def rep(path,old,new,label):
    t=path.read_text(); c=t.count(old)
    if c!=1: raise RuntimeError(f"{label}: expected 1 anchor, found {c}")
    path.write_text(t.replace(old,new,1)); print("patched:",label)

def main():
    root=Path(sys.argv[1]).resolve()
    pkg=root/"extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    vot=pkg/"VoiceOverTranslationPatch.java"; vc=pkg/"VoiceCatalog.java"; pf=pkg/"TtsPrefetcher.java"

    rep(vc,
'''    @Nullable
    static String resolve(String lang, @Nullable String preferredVoiceId) {
        lang = getIso639(lang);

        List<Voice> voices = VOICES_BY_LANG.get(lang);
        if (voices == null || voices.isEmpty()) {
            voices = Objects.requireNonNull(VOICES_BY_LANG.get("en"));
        }
        if (preferredVoiceId != null) {
            Voice preferred = VOICES_BY_ID.get(preferredVoiceId);
            if (preferred != null) {
                for (Voice v : voices) {
                    if (v.id.equals(preferredVoiceId)) return v.id;
                }
            }
        }
        return voices.get(0).id;
    }
}''',
'''    @Nullable
    static String resolve(String lang, @Nullable String preferredVoiceId) {
        lang = getIso639(lang);

        List<Voice> voices = VOICES_BY_LANG.get(lang);
        if (voices == null || voices.isEmpty()) {
            voices = Objects.requireNonNull(VOICES_BY_LANG.get("en"));
        }
        if (preferredVoiceId != null) {
            Voice preferred = VOICES_BY_ID.get(preferredVoiceId);
            if (preferred != null) {
                for (Voice v : voices) {
                    if (v.id.equals(preferredVoiceId)) return v.id;
                }
            }
        }
        return voices.get(0).id;
    }

    /** Stable alternate native voice for a confirmed speaker; no gender/identity inference. */
    @Nullable
    static String resolveSpeakerVariant(String lang, @Nullable String preferredVoiceId, int speakerIndex) {
        final String base = resolve(lang, preferredVoiceId);
        if (speakerIndex <= 0 || base == null) return base;
        final String iso = getIso639(lang);
        List<Voice> all = VOICES_BY_LANG.get(iso);
        if (all == null || all.isEmpty()) return base;
        ArrayList<Voice> nativeVoices = new ArrayList<>();
        for (Voice v : all) if (v.languageTag.equalsIgnoreCase(iso)) nativeVoices.add(v);
        if (nativeVoices.size() <= 1) return base;
        int baseIndex = 0;
        for (int i = 0; i < nativeVoices.size(); i++) if (nativeVoices.get(i).id.equals(base)) { baseIndex = i; break; }
        int stride = Math.max(1, nativeVoices.size() / 3);
        while (gcd(stride, nativeVoices.size()) != 1 && stride < nativeVoices.size()) stride++;
        int idx = Math.floorMod(baseIndex + speakerIndex * stride, nativeVoices.size());
        if (nativeVoices.get(idx).id.equals(base)) idx = (idx + 1) % nativeVoices.size();
        return nativeVoices.get(idx).id;
    }

    private static int gcd(int a, int b) {
        while (b != 0) { int t = a % b; a = b; b = t; }
        return Math.abs(a);
    }
}''',"speaker voice variants")

    rep(vot,
'''        String voice = resolveVoice(lang);
        if (voice == null) return;

        final long speakFromMs''',
'''        String voice = resolveVoiceForSegment(seg, lang);
        if (voice == null) return;

        final long speakFromMs''',"speaker-aware playback voice")

    rep(vot,
'''    /**
     * @param lang ISO 639 (pt) or BCP 47 (pt-BR).
     */
    private static String resolveVoice(String lang) {
        return Settings.VOT_USE_NATIVE_TTS.get()
                ? TTS_ENGINE_SYSTEM
                : VoiceCatalog.resolve(lang, Settings.VOT_TTS_VOICE_TYPE.get());
    }''',
'''    /**
     * @param lang ISO 639 (pt) or BCP 47 (pt-BR).
     */
    private static String resolveVoice(String lang) {
        return Settings.VOT_USE_NATIVE_TTS.get()
                ? TTS_ENGINE_SYSTEM
                : VoiceCatalog.resolve(lang, Settings.VOT_TTS_VOICE_TYPE.get());
    }

    /** Package-visible so TtsPrefetcher uses the same voice playback will request. */
    static String resolveVoiceForSegment(TranscriptSegment seg, String lang) {
        String base = resolveVoice(lang);
        if (base == null || TTS_ENGINE_SYSTEM.equals(base)) return base;
        if (!SpanishStudyController.speakerVoicesEnabled()) return base;
        int speaker = SpanishStudyController.speakerIndex(seg);
        if (speaker < 0) return base;
        return VoiceCatalog.resolveSpeakerVariant(lang, Settings.VOT_TTS_VOICE_TYPE.get(), speaker);
    }''',"shared speaker-aware voice resolver")

    rep(pf,
'''                final boolean success = fetch(videoId, segments.get(next.index),
                        next.index, segments.size(), voice, voiceLang);''',
'''                final TranscriptSegment nextSegment = segments.get(next.index);
                final String segmentVoice = VoiceOverTranslationPatch.resolveVoiceForSegment(nextSegment, voiceLang);
                final boolean success = segmentVoice != null && fetch(videoId, nextSegment,
                        next.index, segments.size(), segmentVoice, voiceLang);''',"speaker-aware prefetch synthesis")

    rep(pf,
'''                if (TtsCache.notCached(videoId, i, voice, lang, seg.text)) {
                    return new NextFetch(i, i - firstFutureIndex, seg);
                }''',
'''                String candidateVoice = VoiceOverTranslationPatch.resolveVoiceForSegment(seg, lang);
                if (candidateVoice != null && TtsCache.notCached(videoId, i, candidateVoice, lang, seg.text)) {
                    return new NextFetch(i, i - firstFutureIndex, seg);
                }''',"speaker-aware future cache lookup")
    rep(pf,
'''            if (TtsCache.notCached(videoId, i, voice, lang, seg.text)) {
                return new NextFetch(i, firstFutureIndex - i, seg);
            }''',
'''            String candidateVoice = VoiceOverTranslationPatch.resolveVoiceForSegment(seg, lang);
            if (candidateVoice != null && TtsCache.notCached(videoId, i, candidateVoice, lang, seg.text)) {
                return new NextFetch(i, firstFutureIndex - i, seg);
            }''',"speaker-aware past cache lookup")

    print("Speaker-specific TTS voice integration complete")

if __name__=="__main__": main()
