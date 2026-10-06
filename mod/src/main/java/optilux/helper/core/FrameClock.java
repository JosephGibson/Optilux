package optilux.helper.core;

import java.util.function.LongSupplier;

/**
 * The frame clock (docs/mod.md#6-time-and-determinism): frameIndex counts frames since the mod
 * started, and each frame's stamp is taken at the HEAD of the frame hook as qpcNs,
 * QueryPerformanceCounter ticks x 1e9 / QueryPerformanceFrequency, PresentMon's clock.
 * {@link #head()} runs on the render thread only; {@link #last()} may be read from any thread.
 */
public final class FrameClock {
    private static final long NANOS = 1_000_000_000L;

    /** One frame's stamp: its index and the QPC time of its frame-hook HEAD. */
    public record Stamp(long frameIndex, long qpcNs) {
    }

    private final LongSupplier ticks;
    private final long frequency;
    private volatile Stamp last = new Stamp(0, 0);

    public FrameClock(LongSupplier ticks, long frequency) {
        if (frequency <= 0) {
            throw new IllegalArgumentException("QPC frequency " + frequency + " is not positive");
        }
        this.ticks = ticks;
        this.frequency = frequency;
    }

    /** Stamp a new frame: the next index and the counter's time now. */
    public Stamp head() {
        Stamp stamp = new Stamp(last.frameIndex() + 1, nanos(ticks.getAsLong(), frequency));
        last = stamp;
        return stamp;
    }

    /** The newest frame's stamp; frameIndex 0 before the first frame. */
    public Stamp last() {
        return last;
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
