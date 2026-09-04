package app.spanishstudy.vot;

import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Trusts speaker identity only when the caption text explicitly names the speaker after a >> marker.
 * Bare >> markers remain boundary-only and deliberately clear identity until another name appears.
 */
public final class CaptionNamedSpeakerStore {
    private static final Pattern NAMED = Pattern.compile(
            "^\\s*(?:\\[)?([A-Z][A-Z0-9'’-]*(?:\\s+[A-Z][A-Z0-9'’-]*){0,3})(?:\\])?\\s*:\\s*");
    private static final TreeMap<Long, Integer> TURN_IDENTITIES = new TreeMap<>();
    private static final Map<String, Integer> NAME_TO_INDEX = new LinkedHashMap<>();
    private static final int MAX_SPEAKERS = 8;
    private static final long NEAR_MS = 500L;

    private CaptionNamedSpeakerStore() {}

    public static synchronized void beginTranscript() {
        TURN_IDENTITIES.clear();
        NAME_TO_INDEX.clear();
    }

    /** Records one turn. Pass the text immediately after >>, not the entire caption chunk. */
    public static synchronized void markTurn(long timeMs, String afterMarker) {
        String name = extractName(afterMarker);
        if (name == null) {
            TURN_IDENTITIES.put(Math.max(0L, timeMs), -1);
            return;
        }
        Integer index = NAME_TO_INDEX.get(name);
        if (index == null) {
            if (NAME_TO_INDEX.size() >= MAX_SPEAKERS) {
                TURN_IDENTITIES.put(Math.max(0L, timeMs), -1);
                return;
            }
            index = NAME_TO_INDEX.size();
            NAME_TO_INDEX.put(name, index);
        }
        TURN_IDENTITIES.put(Math.max(0L, timeMs), index);
    }

    /** -1 means the caption track does not provide a trustworthy identity at this time. */
    public static synchronized int speakerIndexAt(long startMs) {
        Map.Entry<Long, Integer> floor = TURN_IDENTITIES.floorEntry(startMs + NEAR_MS);
        return floor == null ? -1 : floor.getValue();
    }

    public static synchronized int namedSpeakerCount() {
        return NAME_TO_INDEX.size();
    }

    static String extractName(String afterMarker) {
        if (afterMarker == null) return null;
        Matcher m = NAMED.matcher(afterMarker);
        if (!m.find()) return null;
        String name = m.group(1).replaceAll("\\s+", " ").trim().toUpperCase(Locale.ROOT);
        // Avoid common non-name caption prefixes which can otherwise look like ALL-CAPS labels.
        if (name.equals("NOTE") || name.equals("MUSIC") || name.equals("LAUGHTER")
                || name.equals("APPLAUSE") || name.equals("SOUND") || name.equals("SFX")) return null;
        return name;
    }
}
