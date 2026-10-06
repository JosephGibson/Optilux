package optilux.helper.win;

import com.sun.jna.Library;

/**
 * The mod's own kernel32 binding over the JNA the game ships: jna-platform 5.17.0 lacks
 * QueryPerformanceCounter and QueryPerformanceFrequency (docs/plans/m1.md P12). Each takes a
 * pointer to one LARGE_INTEGER, passed as a one-element array that JNA copies back.
 */
public interface Kernel32 extends Library {
    boolean QueryPerformanceCounter(long[] count);

    boolean QueryPerformanceFrequency(long[] frequency);
}
