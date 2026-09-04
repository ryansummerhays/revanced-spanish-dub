package app.spanishstudy.vot;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Conservative local repair for obvious auto-caption punctuation/fragment boundaries. */
public final class CaptionTextRepair {
    private static final Set<String> DANGLING = new HashSet<>(List.of(
            "a","an","the","and","or","but","of","to","for","with","from","our","your",
            "their","his","her","my","its","this","that","these","those"
    ));
    private static final Pattern WORD = Pattern.compile("[\\p{L}\\p{N}]+(?:['’\\-][\\p{L}\\p{N}]+)*");
    private static final Pattern INTERNAL_DANGLING = Pattern.compile(
            "(?i)\\b(a|an|the|and|or|but|of|to|for|with|from|our|your|their|his|her|my|its|this|that|these|those)\\.\\s+(?=[\\p{Ll}])");
    private static final Pattern SHORT_FRAGMENT = Pattern.compile(
            "(^|[!?]\\s+)([\\p{L}\\p{N}'’\\-]+(?:\\s+[\\p{L}\\p{N}'’\\-]+)?)\\.\\s+(?=[\\p{Ll}])");

    private CaptionTextRepair() {}

    public record RepairResult(List<SpeechUnitPlanner.Unit> units, int boundaryMerges, int textRepairs) {}

    public static RepairResult repair(List<SpeechUnitPlanner.Unit> input) {
        List<SpeechUnitPlanner.Unit> work = new ArrayList<>();
        int textRepairs = 0;
        if (input != null) {
            for (SpeechUnitPlanner.Unit unit : input) {
                if (unit == null || unit.text().isBlank()) continue;
                String repaired = repairInternal(unit.text());
                if (!repaired.equals(unit.text())) textRepairs++;
                work.add(new SpeechUnitPlanner.Unit(unit.startMs(), unit.endMs(), repaired,
                        unit.hardBoundaryBefore()));
            }
        }

        int merges = 0;
        for (int i = 0; i + 1 < work.size();) {
            SpeechUnitPlanner.Unit left = work.get(i);
            SpeechUnitPlanner.Unit right = work.get(i + 1);
            if (shouldMerge(left, right)) {
                work.set(i, new SpeechUnitPlanner.Unit(left.startMs(), right.endMs(),
                        joinBoundary(left.text(), right.text()), left.hardBoundaryBefore()));
                work.remove(i + 1);
                merges++;
            } else {
                i++;
            }
        }
        return new RepairResult(work, merges, textRepairs);
    }

    private static String joinBoundary(String left, String right) {
        String l = normalize(left);
        String token = lastWord(l).toLowerCase(Locale.ROOT);
        if (DANGLING.contains(token) && l.endsWith(".")) {
            l = l.substring(0, l.length() - 1).trim();
        }
        return normalize(l + " " + right);
    }

    private static boolean shouldMerge(SpeechUnitPlanner.Unit left, SpeechUnitPlanner.Unit right) {
        if (right.hardBoundaryBefore()) return false;
        long gap = right.startMs() - left.endMs();
        if (gap > SpeechUnitPlanner.MAX_JOIN_GAP_MS) return false;
        long duration = Math.max(left.endMs(), right.endMs()) - Math.min(left.startMs(), right.startMs());
        if (duration > SpeechUnitPlanner.MAX_UNIT_MS) return false;
        if ((left.text().length() + right.text().length() + 1) > SpeechUnitPlanner.MAX_UNIT_CHARS) return false;

        String token = lastWord(left.text()).toLowerCase(Locale.ROOT);
        if (DANGLING.contains(token)) return true;
        if (endsTerminal(left.text()) && startsLowercase(right.text()) && lexicalWordCount(left.text()) <= 3) {
            return true;
        }
        return false;
    }

    static String repairInternal(String text) {
        String out = normalize(text);
        out = INTERNAL_DANGLING.matcher(out).replaceAll("$1 ");
        for (int pass = 0; pass < 3; pass++) {
            Matcher matcher = SHORT_FRAGMENT.matcher(out);
            if (!matcher.find()) break;
            out = matcher.replaceAll("$1$2 ");
        }
        return normalize(out);
    }

    private static String lastWord(String text) {
        Matcher m = WORD.matcher(text == null ? "" : text);
        String last = "";
        while (m.find()) last = m.group();
        return last;
    }

    private static int lexicalWordCount(String text) {
        Matcher m = WORD.matcher(text == null ? "" : text);
        int n = 0;
        while (m.find()) n++;
        return n;
    }

    private static boolean endsTerminal(String text) {
        String t = text == null ? "" : text.trim();
        return t.endsWith(".") || t.endsWith("!") || t.endsWith("?");
    }

    private static boolean startsLowercase(String text) {
        if (text == null) return false;
        for (int i = 0; i < text.length(); i++) {
            char c = text.charAt(i);
            if (Character.isLetter(c)) return Character.isLowerCase(c);
        }
        return false;
    }

    private static String normalize(String text) {
        return text == null ? "" : text.trim().replaceAll("\\s+", " ");
    }
}
