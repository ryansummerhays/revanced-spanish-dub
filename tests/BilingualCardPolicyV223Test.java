package app.spanishstudy.vot;

import java.util.List;

public final class BilingualCardPolicyV223Test {
    public static void main(String[] args) {
        sameCountAndLossless();
        sharedIndex();
        shortSideCapsCount();
        System.out.println("BilingualCardPolicyV223Test passed");
    }

    private static void sameCountAndLossless() {
        String es = "Esta es una frase bastante larga para probar las tarjetas bilingües. Después seguimos con otra idea que también debe aparecer completa y sin perder palabras.";
        String en = "This is a fairly long sentence for testing bilingual cards. Then we continue with another thought that should also remain complete without losing any words at all.";
        BilingualCardPolicy.PairPages p = BilingualCardPolicy.build(es, en);
        req(p.size() > 1, "expected multiple cards");
        req(p.spanish.size() == p.english.size(), "languages must have identical card counts");
        req(String.join(" ", p.spanish).equals(SubtitlePagePolicy.cleanDisplayText(es)), "Spanish must be lossless");
        req(String.join(" ", p.english).equals(SubtitlePagePolicy.cleanDisplayText(en)), "English must be lossless");
        for (int i = 0; i < p.size(); i++) {
            req(!p.spanish.get(i).isBlank(), "Spanish pair page cannot be blank");
            req(!p.english.get(i).isBlank(), "English pair page cannot be blank");
        }
    }

    private static void sharedIndex() {
        req(BilingualCardPolicy.pairIndex(5, 0.00) == 0, "start");
        req(BilingualCardPolicy.pairIndex(5, 0.21) == 1, "second card");
        req(BilingualCardPolicy.pairIndex(5, 0.99) == 4, "last card");
    }

    private static void shortSideCapsCount() {
        BilingualCardPolicy.PairPages p = BilingualCardPolicy.build(
                "uno dos tres cuatro cinco seis siete ocho nueve diez once doce trece catorce quince",
                "one two three");
        req(p.size() <= 3, "cannot create more non-empty pairs than shorter language words");
        req(p.spanish.size() == p.english.size(), "same count after cap");
    }

    private static void req(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }
}
