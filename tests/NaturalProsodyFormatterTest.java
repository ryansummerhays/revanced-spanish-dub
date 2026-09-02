package app.spanishstudy.vot;

public final class NaturalProsodyFormatterTest {
    public static void main(String[] args) {
        String comma = NaturalProsodyFormatter.toSsmlFragment("Sí, creo que funciona.");
        if (comma.contains("break")) throw new AssertionError("commas should not be over-paused: " + comma);

        String strong = NaturalProsodyFormatter.toSsmlFragment("Espera... ahora sí; vamos.");
        if (!strong.contains("180ms") || !strong.contains("95ms"))
            throw new AssertionError("strong punctuation pauses missing: " + strong);

        String escaped = NaturalProsodyFormatter.toSsmlFragment("A < B & C");
        if (!escaped.contains("&lt;") || !escaped.contains("&amp;"))
            throw new AssertionError("XML escaping missing: " + escaped);

        System.out.println("NaturalProsodyFormatterTest passed");
    }
}
