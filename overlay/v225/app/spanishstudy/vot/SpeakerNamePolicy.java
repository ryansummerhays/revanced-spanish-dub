package app.spanishstudy.vot;

import java.util.Locale;
import java.util.Set;

/** Accepts a human-readable speaker name only when the supplied transcript itself supports it. */
public final class SpeakerNamePolicy {
    public static final double MIN_NAME_CONFIDENCE = 0.88;
    private static final Set<String> GENERIC = Set.of(
            "host", "guest", "speaker", "narrator", "interviewer", "interviewee",
            "man", "woman", "male", "female", "person", "unknown", "anonymous",
            "speaker a", "speaker b", "speaker c", "speaker d", "speaker e", "speaker f",
            "a", "b", "c", "d", "e", "f", "g", "h");

    private SpeakerNamePolicy() {}

    public static String acceptedName(String candidate, double confidence,
                                      String evidence, String transcriptCorpus) {
        String name = cleanName(candidate);
        if (name.isEmpty() || confidence < MIN_NAME_CONFIDENCE) return "";
        String ev = normalize(evidence);
        String corpus = normalize(transcriptCorpus);
        if (ev.isEmpty() || corpus.isEmpty() || !corpus.contains(ev)) return "";

        // The model must point to transcript language that actually contains the proposed name,
        // not merely provide a nearby quote and infer identity from voice/face/world knowledge.
        if (!ev.contains(normalize(name))) return "";
        return name;
    }

    public static String cleanName(String raw) {
        if (raw == null) return "";
        String s = raw.replace('\n', ' ').replace('\r', ' ').trim().replaceAll("\\s+", " ");
        s = s.replaceAll("^[\\[({]+|[\\])}]+$", "").trim();
        if (s.isEmpty() || s.length() > 48) return "";
        String lower = s.toLowerCase(Locale.ROOT);
        if (GENERIC.contains(lower) || lower.startsWith("speaker ")) return "";
        String[] words = s.split(" ");
        if (words.length > 6) return "";
        int letters = 0;
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if (Character.isLetter(c)) letters++;
            else if (!(Character.isWhitespace(c) || c == '-' || c == '\'' || c == '’' || c == '.'))
                return "";
        }
        return letters >= 2 ? s : "";
    }

    static String normalize(String raw) {
        if (raw == null) return "";
        return raw.toLowerCase(Locale.ROOT)
                .replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
                .replaceAll("\\s+", " ").trim();
    }
}
