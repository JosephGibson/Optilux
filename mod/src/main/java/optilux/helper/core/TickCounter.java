package optilux.helper.core;

import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.concurrent.CompletableFuture;

/**
 * Server ticks as the game layer reports them at the end of every server tick: whether the tick ran
 * the game (26.3's TickRateManager.runsNormally: not frozen, or a stepped tick while frozen) and the
 * server's tick count. `ticks.step n` waits here for n ticks that ran, so it answers after the ticks
 * and not after `/tick step`'s feedback, which comes first (docs/mod.md#6-time-and-determinism).
 * A waiter counts only the ticks that end after it was registered; leaving the world fails it.
 */
public final class TickCounter {
    private final List<Waiter> waiters = new ArrayList<>();
    private Long lastTick;

    private static final class Waiter {
        final int wanted;
        int ran;
        final CompletableFuture<Integer> done = new CompletableFuture<>();

        Waiter(int wanted) {
            this.wanted = wanted;
        }
    }

    /** A future completed with the count once {@code n} ticks that ran have ended. */
    public synchronized CompletableFuture<Integer> await(int n) {
        if (n < 1) {
            throw new IllegalArgumentException("n must be at least 1, not " + n);
        }
        Waiter waiter = new Waiter(n);
        waiters.add(waiter);
        return waiter.done;
    }

    /** One server tick ended (on the server thread). */
    public void tick(boolean ran, long tickCount) {
        List<Waiter> finished = new ArrayList<>();
        synchronized (this) {
            lastTick = tickCount;
            if (ran) {
                for (Iterator<Waiter> it = waiters.iterator(); it.hasNext(); ) {
                    Waiter waiter = it.next();
                    if (++waiter.ran >= waiter.wanted) {
                        it.remove();
                        finished.add(waiter);
                    }
                }
            }
        }
        for (Waiter waiter : finished) {
            waiter.done.complete(waiter.ran);
        }
    }

    /** Stop counting for this future (its request ended first). */
    public synchronized void cancel(CompletableFuture<Integer> future) {
        waiters.removeIf(waiter -> waiter.done == future);
    }

    /** The world was left: no server ticks any more; every waiter fails with the reason. */
    public void reset(String why) {
        List<Waiter> failed;
        synchronized (this) {
            lastTick = null;
            failed = new ArrayList<>(waiters);
            waiters.clear();
        }
        for (Waiter waiter : failed) {
            waiter.done.completeExceptionally(new IllegalStateException(why));
        }
    }

    /** The server's tick count at the last tick end, null before one or after a reset. */
    public synchronized Long lastTick() {
        return lastTick;
    }

    public synchronized int waiting() {
        return waiters.size();
    }
}
