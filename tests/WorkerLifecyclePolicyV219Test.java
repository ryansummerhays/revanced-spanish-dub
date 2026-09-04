package app.spanishstudy.vot;

public final class WorkerLifecyclePolicyV219Test {
    private static void check(boolean value, String message) {
        if (!value) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        check(WorkerLifecyclePolicy.shouldPublish(true, true, 7, 7), "current worker should publish");
        check(!WorkerLifecyclePolicy.shouldPublish(true, true, 6, 7), "stale worker must not publish");
        check(!WorkerLifecyclePolicy.shouldPublish(true, false, 7, 7), "disabled session must not publish");
        check(WorkerLifecyclePolicy.shouldStartImmediately(true, false), "idle video should start immediately");
        check(!WorkerLifecyclePolicy.shouldStartImmediately(true, true), "loading video must not start a second worker");
        check(WorkerLifecyclePolicy.shouldRestartAfterFinish(true, true, true, true,
                7, 7, false, false, false), "explicit re-arm request should restart");
        check(WorkerLifecyclePolicy.shouldRestartAfterFinish(true, true, true, false,
                6, 7, false, false, false), "stale epoch should restart after finish");
        check(!WorkerLifecyclePolicy.shouldRestartAfterFinish(true, false, true, true,
                6, 7, false, false, false), "disabled session must never resurrect worker");
        check(WorkerLifecyclePolicy.shouldRestartAfterFinish(true, true, true, false,
                7, 7, false, false, true), "provider change should restart");
        System.out.println("WorkerLifecyclePolicyV219Test OK");
    }
}