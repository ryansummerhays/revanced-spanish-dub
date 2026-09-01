import app.spanishstudy.vot.VocabularyAnalyzer;
import app.spanishstudy.vot.VocabularyEntry;

import java.util.HashSet;
import java.util.List;

public class VocabularyAnalyzerTest {
    public static void main(String[] args) {
        List<VocabularyAnalyzer.Segment> segments = List.of(
                new VocabularyAnalyzer.Segment(0, "Necesitamos reposicionarnos completamente antes de la pelea."),
                new VocabularyAnalyzer.Segment(3000, "Viene otro equipo, empujen ahora."),
                new VocabularyAnalyzer.Segment(7000, "El posicionamiento es excelente, pero necesitamos comunicacion."),
                new VocabularyAnalyzer.Segment(10000, "Reposicionarnos durante la pelea puede ser diferente."),
                new VocabularyAnalyzer.Segment(13000, "Tenemos que mantener el posicionamiento."));

        List<VocabularyEntry> result = VocabularyAnalyzer.analyze(segments, new HashSet<>(), 40, false);
        if (result.isEmpty()) throw new AssertionError("Expected vocabulary candidates");
        boolean found = result.stream().anyMatch(v -> v.word.equals("reposicionarnos"));
        if (!found) throw new AssertionError("Expected reposicionarnos in vocabulary output");
        System.out.println("PASS: " + result.size() + " candidates");
        for (VocabularyEntry e : result) {
            System.out.printf("%s\t%d\t%.2f%n", e.word, e.count, e.difficultyScore);
        }
    }
}
