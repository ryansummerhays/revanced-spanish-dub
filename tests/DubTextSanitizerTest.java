package app.spanishstudy.vot;

public final class DubTextSanitizerTest {
    private static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        check("Hola".equals(DubTextSanitizer.cleanForSpeech("[1.8 seconds] Hola")), "seconds marker");
        check("Hola".equals(DubTextSanitizer.cleanForSpeech("1: [slot=1.8s] Hola")), "enum + slot");
        check("Hola".equals(DubTextSanitizer.cleanForSpeech("2: (2.4 sec): Hola")), "enum + parenthesized duration");
        check("Hola".equals(DubTextSanitizer.cleanForSpeech("3: Hola")), "plain batch enumeration");
        check("Hola".equals(DubTextSanitizer.cleanForSpeech("1: 2: [slot=1.8s] Hola")), "stacked protocol prefixes");
        check("Hola".equals(DubTextSanitizer.cleanForSpeech(": \"Hola")), "protocol punctuation");
        check(DubTextSanitizer.cleanForSpeech("[107200-109480] >> Hola") == null, "timestamp echo rejected");
        check(DubTextSanitizer.cleanForSpeech("<missing>") == null, "missing marker rejected");
        check("1.8 segundos después nos fuimos".equals(
                DubTextSanitizer.cleanForSpeech("1.8 segundos después nos fuimos")),
                "ordinary spoken duration preserved");
    }
}
