package app.spanishstudy.vot;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/** A candidate study word extracted from a translated transcript. */
public final class VocabularyEntry implements Comparable<VocabularyEntry> {
    public final String word;
    public int count;
    public double difficultyScore;
    public long firstTimestampMs = -1;
    private final List<String> examples = new ArrayList<>();

    public VocabularyEntry(String word) { this.word = word; }
    public void addOccurrence(long timestampMs, String sentence) { count++; if (firstTimestampMs < 0) firstTimestampMs = timestampMs; if (sentence != null && !sentence.isBlank() && examples.size() < 3 && !examples.contains(sentence)) examples.add(sentence); }
    public List<String> getExamples() { return Collections.unmodifiableList(examples); }
    @Override public int compareTo(VocabularyEntry other) { int score = Double.compare(other.difficultyScore, difficultyScore); if (score != 0) return score; int freq = Integer.compare(other.count, count); return freq != 0 ? freq : word.compareTo(other.word); }
}
