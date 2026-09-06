package app.spanishstudy.vot;

import java.util.List;

public final class ConversationalSubtitleV231Test {
    public static void main(String[] args) {
        testShortSentencesDoNotFlashAsTinyCards();
        testBilingualFirstThoughtStaysPaired();
        testSharedProgressIndexIsMonotonic();
        testNoTextLoss();
        System.out.println("ConversationalSubtitleV231Test passed");
    }

    private static void testShortSentencesDoNotFlashAsTinyCards() {
        String text = "No. Espera. No creo que eso sea lo que quiso decir. Tenemos que hablar con él primero.";
        List<SubtitlePagePolicy.Page> pages = SubtitlePagePolicy.paginate(text);
        require(!pages.isEmpty(), "pages missing");
        require(!pages.get(0).text.equals("No."), "one-word sentence became a flash card");
        require(!pages.get(0).text.equals("No. Espera."), "two tiny sentences became a tiny card");
    }

    private static void testBilingualFirstThoughtStaysPaired() {
        String es = "No puedo creerlo. Esto cambia todo lo que sabemos sobre este lugar. Tenemos que avisar a los demás antes de seguir.";
        String en = "I can't believe it. This changes everything we know about this place. We need to warn the others before we continue.";
        BilingualCardPolicy.PairPages pair = BilingualCardPolicy.build(es, en);
        require(pair.size() >= 2, "expected multiple bilingual cards");
        require(pair.spanish.get(0).toLowerCase().contains("creer"), "Spanish first thought missing");
        require(pair.english.get(0).toLowerCase().contains("believe"), "English first thought not paired");
    }

    private static void testSharedProgressIndexIsMonotonic() {
        String es = "Primero tenemos que salir de aquí. Después podemos hablar con ella y decidir qué hacer. No podemos quedarnos mucho tiempo.";
        String en = "First we have to get out of here. Then we can talk to her and decide what to do. We cannot stay much longer.";
        BilingualCardPolicy.PairPages pair = BilingualCardPolicy.build(es, en);
        int previous = -1;
        for (int i = 0; i <= 100; i++) {
            int index = pair.index(i / 100.0);
            require(index >= previous, "page index moved backward");
            previous = index;
        }
    }

    private static void testNoTextLoss() {
        String es = "El director quiere una respuesta ahora, pero todavía no sabemos qué ocurrió en la base. Necesitamos revisar el informe completo antes de responder.";
        String en = "The director wants an answer now, but we still do not know what happened at the base. We need to review the full report before responding.";
        BilingualCardPolicy.PairPages pair = BilingualCardPolicy.build(es, en);
        String joinedEs = String.join(" ", pair.spanish);
        String joinedEn = String.join(" ", pair.english);
        require(joinedEs.equals(SubtitlePagePolicy.cleanDisplayText(es)), "Spanish text lost or duplicated");
        require(joinedEn.equals(SubtitlePagePolicy.cleanDisplayText(en)), "English text lost or duplicated");
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
