package optilux.helper;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.concurrent.atomic.AtomicLong;
import optilux.helper.core.FrameClock;
import org.junit.jupiter.api.Test;

/** frameIndex, qpcNs and swapQpcNs from a fake counter (docs/mod.md#6-time-and-determinism). */
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
        assertEquals(new FrameClock.Stamp(0, 0, 0), clock.last());
        assertEquals(new FrameClock.Stamp(1, 2_500_000_000L, 0), clock.head());
        counter.addAndGet(166_667L);
        FrameClock.Stamp second = clock.head();
        assertEquals(new FrameClock.Stamp(2, 2_516_666_700L, 0), second);
        assertEquals(second, clock.last());
    }

    @Test
    void eachStampCarriesThePreviousFramesSwap() {
        AtomicLong counter = new AtomicLong(10_000_000L);
        FrameClock clock = new FrameClock(counter::get, 10_000_000L);
        clock.head();
        counter.addAndGet(60_000L); // the frame's work: 6 ms
        clock.swapped();
        counter.addAndGet(10_000L); // the tick and input work before the next frame: 1 ms
        FrameClock.Stamp second = clock.head();
        assertEquals(new FrameClock.Stamp(2, 1_007_000_000L, 1_006_000_000L), second);
        // No swap between two heads (the surface was not acquired): the older swap stays.
        counter.addAndGet(70_000L);
        assertEquals(new FrameClock.Stamp(3, 1_014_000_000L, 1_006_000_000L), clock.head());
    }

    @Test
    void aNonPositiveFrequencyIsRefused() {
        assertThrows(IllegalArgumentException.class, () -> new FrameClock(() -> 0L, 0L));
    }
}
