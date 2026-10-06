package optilux.helper;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.concurrent.atomic.AtomicLong;
import optilux.helper.core.FrameClock;
import org.junit.jupiter.api.Test;

/** frameIndex and qpcNs from a fake counter (docs/mod.md#6-time-and-determinism). */
class FrameClockTest {
    @Test
    void ticksToNanosecondsWithoutOverflow() {
        assertEquals(1_000_000_000L, FrameClock.nanos(10_000_000L, 10_000_000L));
        assertEquals(100L, FrameClock.nanos(1L, 10_000_000L));
        assertEquals(1_000L, FrameClock.nanos(3L, 3_000_000L));
        // Thirty days of uptime at 10 MHz: ticks x 1e9 would overflow a long.
        long ticks = 30L * 86_400L * 10_000_000L + 7L;
        assertEquals(30L * 86_400L * 1_000_000_000L + 700L, FrameClock.nanos(ticks, 10_000_000L));
    }

    @Test
    void eachHeadIsTheNextFrameAtTheCountersTime() {
        AtomicLong counter = new AtomicLong(25_000_000L);
        FrameClock clock = new FrameClock(counter::get, 10_000_000L);
        assertEquals(new FrameClock.Stamp(0, 0), clock.last());
        assertEquals(new FrameClock.Stamp(1, 2_500_000_000L), clock.head());
        counter.addAndGet(166_667L);
        FrameClock.Stamp second = clock.head();
        assertEquals(new FrameClock.Stamp(2, 2_516_666_700L), second);
        assertEquals(second, clock.last());
    }

    @Test
    void aNonPositiveFrequencyIsRefused() {
        assertThrows(IllegalArgumentException.class, () -> new FrameClock(() -> 0L, 0L));
    }
}
