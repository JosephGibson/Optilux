package optilux.helper.core;

import java.util.function.LongSupplier;

/**
 * The frame clock (docs/mod.md#6-time-and-determinism): frameIndex counts frames since the mod
 * started, and each frame's stamp is taken at the HEAD of the frame hook as qpcNs,
 * QueryPerformanceCounter ticks x 1e9 / QueryPerformanceFrequency, PresentMon's clock. Each stamp
 * also carries swapQpcNs, the return of the previous frame's swap (plans/m1.md D26: PresentMon's
 * CPU start is the previous Present's return), 0 before the first swap. {@link #head()} and
 * {@link #swapped()} run on the render thread only; {@link #last()} may be read from any thread.
 */
public final class FrameClock {
    private static final long NANOS = 1_000_000_000L;

    /** One frame's stamp: its index, the QPC time of its frame-hook HEAD and of the swap before. */
    public record Stamp(long frameIndex, long qpcNs, long swapQpcNs) {
    }

    private final LongSupplier ticks;
    private final long frequency;
    private volatile Stamp last = new Stamp(0, 0, 0);
    private long swap; // render thread only

    public FrameClock(LongSupplier ticks, long frequency) {
        if (frequency <= 0) {
            throw new IllegalArgumentException("QPC frequency " + frequency + " is not positive");
        }
        this.ticks = ticks;
        this.frequency = frequency;
    }

    /** Stamp a new frame: the next index, the counter's time now and the last swap's return. */
    public Stamp head() {
        Stamp stamp = new Stamp(last.frameIndex() + 1, now(), swap);
        last = stamp;
        return stamp;
    }

    /** The swap returned: the next frame's stamp carries this time as swapQpcNs. */
    public void swapped() {
        swap = now();
    }

    /** The newest frame's stamp; frameIndex 0 before the first frame. */
    public Stamp last() {
        return last;
    }

    /** The counter's time now, in ns. */
    public long now() {
        return nanos(ticks.getAsLong(), frequency);
    }

    /**
     * Ticks to nanoseconds without overflow: whole seconds and the remainder are scaled apart,
     * so ticks x 1e9 never forms (it would overflow after 922 s at 10 MHz). Exact for any
     * frequency under 9.2 GHz.
     */
    public static long nanos(long ticks, long frequency) {
        return ticks / frequency * NANOS + ticks % frequency * NANOS / frequency;
    }
}
