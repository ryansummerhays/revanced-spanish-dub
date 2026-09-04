package app.spanishstudy.vot;

public final class StartupSpeechPolicyTest {
    public static void main(String[] args) {
        require(StartupSpeechPolicy.shouldStartNetwork(5000, 3500), "1500ms remaining should synthesize");
        require(StartupSpeechPolicy.shouldStartNetwork(5000, 3800), "exact 1200ms floor should synthesize");
        require(!StartupSpeechPolicy.shouldStartNetwork(5000, 3801), "1199ms remaining should skip network synthesis");
        require(!StartupSpeechPolicy.shouldStartNetwork(5000, 5200), "past phrase must not synthesize");
        System.out.println("startup speech policy: OK");
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
