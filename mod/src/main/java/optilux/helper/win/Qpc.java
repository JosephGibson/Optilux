package optilux.helper.win;

import com.sun.jna.Native;

/** QueryPerformanceCounter through {@link Kernel32}; loaded only when the mod is active. */
public final class Qpc {
    private final Kernel32 kernel32;
    private final long frequency;

    private Qpc(Kernel32 kernel32, long frequency) {
        this.kernel32 = kernel32;
        this.frequency = frequency;
    }

    /** The mod's kernel32 binding, loaded on first use. */
    public static Kernel32 kernel32() {
        return Native.load("kernel32", Kernel32.class);
    }

    public static Qpc load() {
        Kernel32 kernel32 = kernel32();
        long[] frequency = new long[1];
        if (!kernel32.QueryPerformanceFrequency(frequency) || frequency[0] <= 0) {
            throw new IllegalStateException("QueryPerformanceFrequency failed: " + frequency[0]);
        }
        return new Qpc(kernel32, frequency[0]);
    }

    public long frequency() {
        return frequency;
    }

    /** The counter now; thread-safe (each call has its own buffer). */
    public long ticks() {
        long[] count = new long[1];
        if (!kernel32.QueryPerformanceCounter(count)) {
            throw new IllegalStateException("QueryPerformanceCounter failed");
        }
        return count[0];
    }
}
