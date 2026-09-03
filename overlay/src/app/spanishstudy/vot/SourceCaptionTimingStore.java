package app.spanishstudy.vot;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Preserves the finest timing information available from YouTube JSON3 caption segments.
 *
 * JSON3 caption events frequently contain several inner `segs` with tOffsetMs values. Morphe used
 * to concatenate those pieces and discard their timing before later sentence/clause segmentation.
 * This store keeps a lightweight word timeline so a natural phrase can inherit the time of its
 * actual source words. Character-proportional sentence timing remains a fallback when a track does
 * not expose usable inner offsets or alignment is ambiguous.
 */
public final class SourceCaptionTimingStore {
    private static final Pattern WORD = Pattern.compile(
            "[\\p{L}\\p{N}]+(?:['’\\-][\\p{L}\\p{N}]+)*");
    private static final List<TimedWord> WORDS = new ArrayList<>();

    private SourceCaptionTimingStore() {}

    public static synchronized void beginTranscript() {
        WORDS.clear();
    }

    /**
     * Adds one timed JSON3 inner segment. If it contains several words, timing is distributed within
     * that small segment by character position; the important improvement is that the real JSON3
     * segment boundaries/tOffsetMs are retained instead of spreading an entire sentence uniformly.
     */
    public static synchronized void addTimedChunk(long startMs, long endMs, String rawText) {
        if (rawText == null || rawText.isBlank()) return;
        long safeStart = Math.max(0L, startMs);
        long safeEnd = Math.max(safeStart + 1L, endMs);

        Matcher matcher = WORD.matcher(rawText);
        List<Match> matches = new ArrayList<>();
        while (matcher.find()) {
            String token = normalizeToken(matcher.group());
            if (!token.isEmpty()) matches.add(new Match(token, matcher.start(), matcher.end()));
        }
        if (matches.isEmpty()) return;

        int textSpan = Math.max(1, rawText.length());
        long duration = safeEnd - safeStart;
        for (Match match : matches) {
            long tokenStart = safeStart + Math.round(duration * (match.start / (double) textSpan));
            long tokenEnd = safeStart + Math.round(duration * (match.end / (double) textSpan));
            tokenStart = Math.max(safeStart, Math.min(safeEnd - 1L, tokenStart));
            tokenEnd = Math.max(tokenStart + 1L, Math.min(safeEnd, tokenEnd));
            WORDS.add(new TimedWord(match.token, tokenStart, tokenEnd));
        }
    }

    /**
     * Returns the measured silence after each lexical word in {@code sentenceText}, aligned to the
     * preserved JSON3 word timeline. This is the local prosody signal used by v2.11 punctuation
     * restoration. A null result means alignment was not reliable enough and callers must fall back
     * to text-only parsing.
     */
    public static synchronized long[] interWordGaps(long sentenceStartMs,
                                                     long sentenceEndMs,
                                                     String sentenceText) {
        Alignment alignment = alignSentence(sentenceStartMs, sentenceEndMs, sentenceText);
        if (alignment == null || alignment.words.size() < 2) return null;

        long[] gaps = new long[alignment.words.size() - 1];
        for (int i = 0; i < gaps.length; i++) {
            TimedWord left = alignment.candidates.get(alignment.aligned[i]);
            TimedWord right = alignment.candidates.get(alignment.aligned[i + 1]);
            gaps[i] = Math.max(0L, right.startMs - left.endMs);
        }
        return gaps;
    }

    /**
     * @return an end timestamp for every phrase, or null when source-word alignment is not reliable.
     * The final timestamp is always sentenceEndMs. Returned boundaries are strictly increasing.
     */
    public static synchronized long[] phraseEndTimes(long sentenceStartMs,
                                                     long sentenceEndMs,
                                                     String sentenceText,
                                                     List<String> phrases) {
        if (phrases == null || phrases.size() < 2 || sentenceEndMs <= sentenceStartMs) return null;

        Alignment alignment = alignSentence(sentenceStartMs, sentenceEndMs, sentenceText);
        if (alignment == null || alignment.words.size() < phrases.size()) return null;

        List<String> flattened = new ArrayList<>();
        int[] cumulativeWords = new int[phrases.size()];
        for (int i = 0; i < phrases.size(); i++) {
            List<String> part = lexicalWords(phrases.get(i));
            if (part.isEmpty()) return null;
            flattened.addAll(part);
            cumulativeWords[i] = flattened.size();
        }
        if (!flattened.equals(alignment.words)) return null;

        long[] ends = new long[phrases.size()];
        long previous = sentenceStartMs;
        for (int i = 0; i < phrases.size() - 1; i++) {
            int wordCount = cumulativeWords[i];
            if (wordCount <= 0 || wordCount >= alignment.aligned.length) return null;
            TimedWord left = alignment.candidates.get(alignment.aligned[wordCount - 1]);
            TimedWord right = alignment.candidates.get(alignment.aligned[wordCount]);
            long boundary;
            if (right.startMs > left.endMs) boundary = (left.endMs + right.startMs) / 2L;
            else boundary = Math.max(left.endMs, right.startMs);
            boundary = Math.max(previous + 1L, Math.min(sentenceEndMs - 1L, boundary));
            ends[i] = boundary;
            previous = boundary;
        }
        ends[ends.length - 1] = sentenceEndMs;
        return ends;
    }

    private static Alignment alignSentence(long sentenceStartMs, long sentenceEndMs, String sentenceText) {
        if (sentenceEndMs <= sentenceStartMs) return null;
        List<String> sentenceWords = lexicalWords(sentenceText);
        if (sentenceWords.isEmpty()) return null;

        List<TimedWord> candidates = new ArrayList<>();
        final long toleranceMs = 120L;
        for (TimedWord word : WORDS) {
            long mid = (word.startMs + word.endMs) / 2L;
            if (mid >= sentenceStartMs - toleranceMs && mid <= sentenceEndMs + toleranceMs) {
                candidates.add(word);
            }
        }
        if (candidates.size() < sentenceWords.size()) return null;

        // Align the exact raw sentence word sequence to the timing stream. Caption tracks sometimes
        // contain harmless duplicate/overlap tokens, so allow a few candidates to be skipped.
        int[] aligned = new int[sentenceWords.size()];
        int candidateAt = 0;
        int skipped = 0;
        for (int i = 0; i < sentenceWords.size(); i++) {
            String expected = sentenceWords.get(i);
            int found = -1;
            int searchLimit = Math.min(candidates.size(), candidateAt + 5);
            for (int j = candidateAt; j < searchLimit; j++) {
                if (expected.equals(candidates.get(j).token)) {
                    found = j;
                    break;
                }
            }
            if (found < 0) return null;
            skipped += found - candidateAt;
            aligned[i] = found;
            candidateAt = found + 1;
        }
        if (skipped > Math.max(3, sentenceWords.size() / 4)) return null;
        return new Alignment(sentenceWords, candidates, aligned);
    }

    private static List<String> lexicalWords(String text) {
        List<String> out = new ArrayList<>();
        if (text == null) return out;
        Matcher matcher = WORD.matcher(text);
        while (matcher.find()) {
            String token = normalizeToken(matcher.group());
            if (!token.isEmpty()) out.add(token);
        }
        return out;
    }

    private static String normalizeToken(String token) {
        return token == null ? "" : token.toLowerCase(Locale.ROOT).replace('’', '\'').trim();
    }

    private record Match(String token, int start, int end) {}
    private record TimedWord(String token, long startMs, long endMs) {}
    private record Alignment(List<String> words, List<TimedWord> candidates, int[] aligned) {}
}
