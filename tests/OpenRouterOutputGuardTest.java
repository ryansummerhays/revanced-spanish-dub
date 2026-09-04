package app.spanishstudy.vot;

import java.util.List;

public final class OpenRouterOutputGuardTest {
    private static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        OpenRouterOutputGuard.ParsedLine p = OpenRouterOutputGuard.parseNumberedLine(
                "2: [slot=6.18s]: Las vibraciones están afectando la circuitería.", 3);
        check(p != null && p.index == 1, "numbered line should parse");
        check("Las vibraciones están afectando la circuitería.".equals(p.text), "slot marker should strip");

        OpenRouterOutputGuard.ParsedLine duplicateProtocol = OpenRouterOutputGuard.parseNumberedLine(
                "1: 1: [slot=1.34s] Agarras una baya.", 2);
        check(duplicateProtocol != null && "Agarras una baya.".equals(duplicateProtocol.text),
                "duplicate enumeration before slot metadata must strip");

        check("Hola.".equals(OpenRouterOutputGuard.sanitizeTranslation("[1.8 seconds] Hola.")),
                "bracketed seconds metadata must strip");
        check("Hola.".equals(OpenRouterOutputGuard.sanitizeTranslation("[1.8 sec]: Hola.")),
                "bracketed sec metadata must strip");
        check("Hola.".equals(OpenRouterOutputGuard.sanitizeTranslation("(1.8s) Hola.")),
                "parenthesized seconds metadata must strip");
        check("1.8 segundos después nos fuimos.".equals(OpenRouterOutputGuard.sanitizeTranslation(
                "1.8 segundos después nos fuimos.")),
                "legitimate unbracketed duration speech must remain");

        check(OpenRouterOutputGuard.parseNumberedLine(
                "1: [107200-109480] >> ¿Estás bromeando?", 2) == null,
                "old raw-caption timestamp echo must be rejected");
        check(OpenRouterOutputGuard.parseNumberedLine("3: texto", 2) == null,
                "out-of-range line number must be rejected");
        check(OpenRouterOutputGuard.sanitizeTranslation("[6.7") == null,
                "broken metadata fragment must be rejected");
        check(OpenRouterOutputGuard.sanitizeTranslation("225") == null,
                "bare numeric fragment must be rejected");

        List<String> positional = OpenRouterOutputGuard.positionalFallback(
                "1: Hola\n1: Adiós", 2);
        check(positional != null && positional.size() == 2, "safe positional fallback should recover by order");
        check("Hola".equals(positional.get(0)) && "Adiós".equals(positional.get(1)),
                "positional recovery should preserve text order");
        check(OpenRouterOutputGuard.positionalFallback(
                "[124520-132239] ¿Qué Pokémon?\n2: Bien", 2) == null,
                "context echo must invalidate positional fallback");
    }
}
