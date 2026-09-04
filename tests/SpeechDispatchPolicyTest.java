package app.spanishstudy.vot;

public final class SpeechDispatchPolicyTest {
    private static void expect(boolean expected, boolean actual, String name) {
        if (expected != actual) throw new AssertionError(name + ": expected=" + expected + " actual=" + actual);
    }

    public static void main(String[] args) {
        expect(true, SpeechDispatchPolicy.mayDispatch(5, 4, -1, false, false), "normal next segment");
        expect(false, SpeechDispatchPolicy.mayDispatch(5, 4, 5, false, false), "same index already pending");
        expect(false, SpeechDispatchPolicy.mayDispatch(5, 5, -1, false, false), "same index already spoken");
        expect(false, SpeechDispatchPolicy.mayDispatch(4, 5, -1, false, false), "ordinary backwards replay blocked");
        expect(false, SpeechDispatchPolicy.mayDispatch(6, 5, -1, true, false), "prior speech still active");
        expect(true, SpeechDispatchPolicy.mayDispatch(3, 7, -1, true, true), "explicit seek may restart older segment");
        expect(false, SpeechDispatchPolicy.mayDispatch(3, 7, 3, true, true), "explicit seek still cannot duplicate in-flight index");
        System.out.println("SpeechDispatchPolicyTest passed");
    }
}
