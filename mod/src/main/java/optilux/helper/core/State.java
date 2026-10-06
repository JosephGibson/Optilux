package optilux.helper.core;

import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

/**
 * The state owner (docs/mod.md#4-architecture): the one holder of the mod's session state, no
 * global statics. It holds the exclusive resources (window, capture, path, timers) and who holds
 * each, the input block, and what a reconnecting client is told. Leaving the world resets it. On
 * a disconnect state survives and work does not: the protocol cancels the running requests and
 * hands their ids here, and the input block is released unless a client says hello again within
 * {@link #INPUT_RELEASE}: long enough for a client restart, short enough that a crashed harness
 * never leaves the game locked.
 */
public final class State {
    public static final Duration INPUT_RELEASE = Duration.ofSeconds(10);

    /** What `hello` reports: whether an earlier client said hello, and the ids its disconnect cancelled. */
    public record Resume(boolean resumed, List<Object> cancelled) {
    }

    private final ScheduledExecutorService timers;
    private final Duration release;
    private final Map<String, Object> held = new LinkedHashMap<>();
    private boolean inputBlocked;
    private ScheduledFuture<?> pendingRelease;
    private Runnable onInputReleased = () -> { };
    private int hellos;
    private List<Object> lastCancelled = List.of();

    public State(ScheduledExecutorService timers, Duration release) {
        this.timers = timers;
        this.release = release;
    }

    /** Called when the input block is released by the state (a disconnect or a reset). */
    public synchronized void onInputReleased(Runnable action) {
        onInputReleased = action;
    }

    public synchronized boolean acquire(String resource, Object owner) {
        if (held.containsKey(resource)) {
            return false;
        }
        held.put(resource, owner);
        return true;
    }

    /** Release a resource if this owner still holds it. */
    public synchronized void release(String resource, Object owner) {
        if (held.containsKey(resource) && held.get(resource).equals(owner)) {
            held.remove(resource);
        }
    }

    /** Release a resource whoever holds it: the command that ends it ran (timers.stop). */
    public synchronized void release(String resource) {
        held.remove(resource);
    }

    /** The held resources and their owners. */
    public synchronized Map<String, Object> held() {
        return new LinkedHashMap<>(held);
    }

    public synchronized boolean anyHeld() {
        return !held.isEmpty();
    }

    public synchronized boolean inputBlocked() {
        return inputBlocked;
    }

    public synchronized void blockInput(boolean on) {
        inputBlocked = on;
        cancelRelease();
    }

    /** A client said hello: the resume facts, and no release pending any more. */
    public synchronized Resume hello() {
        Resume resume = new Resume(hellos > 0, lastCancelled);
        hellos++;
        cancelRelease();
        return resume;
    }

    /** The client left: remember what was cancelled; release the input block after the delay. */
    public synchronized void disconnected(List<Object> cancelled) {
        lastCancelled = List.copyOf(cancelled);
        cancelRelease();
        if (inputBlocked) {
            pendingRelease = timers.schedule(this::releaseInput, release.toNanos(),
                TimeUnit.NANOSECONDS);
        }
    }

    /** The world was left: every resource freed and the input released. */
    public synchronized void reset() {
        held.clear();
        cancelRelease();
        if (inputBlocked) {
            inputBlocked = false;
            onInputReleased.run();
        }
    }

    private synchronized void releaseInput() {
        pendingRelease = null;
        if (inputBlocked) {
            inputBlocked = false;
            onInputReleased.run();
        }
    }

    private void cancelRelease() {
        if (pendingRelease != null) {
            pendingRelease.cancel(false);
            pendingRelease = null;
        }
    }
}
