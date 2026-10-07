package optilux.helper;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import optilux.helper.core.TickCounter;
import org.junit.jupiter.api.Test;

/** The tick counter behind `ticks.step` (docs/mod.md#6-time-and-determinism). */
class TickCounterTest {
    @Test
    void aWaiterEndsAfterExactlyNTicksThatRan() throws Exception {
        TickCounter ticks = new TickCounter();
        ticks.tick(true, 100); // before the wait: not counted
        CompletableFuture<Integer> step = ticks.await(3);
        ticks.tick(true, 101);
        ticks.tick(false, 102); // frozen and not stepped: the game did not run
        ticks.tick(true, 103);
        assertFalse(step.isDone());
        ticks.tick(true, 104);
        assertEquals(3, step.get());
        assertEquals(0, ticks.waiting());
        assertEquals(104L, ticks.lastTick());
    }

    @Test
    void waitersCountIndependently() throws Exception {
        TickCounter ticks = new TickCounter();
        CompletableFuture<Integer> one = ticks.await(1);
        ticks.tick(true, 1);
        CompletableFuture<Integer> two = ticks.await(2);
        assertEquals(1, one.get());
        ticks.tick(true, 2);
        assertFalse(two.isDone());
        ticks.tick(true, 3);
        assertEquals(2, two.get());
    }

    @Test
    void leavingTheWorldFailsTheWaitersAndClearsTheTick() {
        TickCounter ticks = new TickCounter();
        ticks.tick(true, 7);
        CompletableFuture<Integer> step = ticks.await(5);
        ticks.reset("the world was left");
        ExecutionException failed = assertThrows(ExecutionException.class, step::get);
        assertTrue(failed.getCause() instanceof IllegalStateException);
        assertEquals("the world was left", failed.getCause().getMessage());
        assertNull(ticks.lastTick());
    }

    @Test
    void aCancelledWaiterStopsCounting() {
        TickCounter ticks = new TickCounter();
        CompletableFuture<Integer> step = ticks.await(1);
        ticks.cancel(step);
        ticks.tick(true, 1);
        assertFalse(step.isDone());
        assertEquals(0, ticks.waiting());
    }

    @Test
    void nMustBePositive() {
        assertThrows(IllegalArgumentException.class, () -> new TickCounter().await(0));
    }
}
