package optilux.helper.core;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.function.BiConsumer;
import java.util.function.BooleanSupplier;
import java.util.function.LongSupplier;

/**
 * `window.measure` (docs/mod.md#6-time-and-determinism): a window the mod times on the QPC clock,
 * PresentMon's. The skip counts from the trigger, `after: reload` from the last reload's completion
 * inside the mod (never a harness sleep), `after: now` from the request; the window starts at the
 * first frame whose HEAD stamp lies at or past the skip's end and ends at the first whose HEAD
 * stamp lies `seconds` or more after the start's, so it spans end - start frames, the rows the
 * harness cuts from PresentMon between the two stamps. From the request to the end, a reload, a
 * dimension change, a world join or leave, or a pipeline creation the frame counter shows
 * (sinceReload falling, its wrap aside) fails it; each also drops the reload anchor, so `after:
 * reload` never counts from a pipeline that is gone. {@link #frame} runs at every frame head on
 * the render thread; the handler waits on a worker.
 */
public final class Window {
    /** Iris's frameCounter runs (count + 1) % 720720 (docs/gpu-iris.md#frame-counters-and-reload). */
    static final long COUNTER_WRAP = 720_720;
    private static final double NANOS = 1e9;

    /** A frame's HEAD stamp with the frames since the last pipeline creation. */
    public record Mark(long frameIndex, Long sinceReload, long qpcNs, long swapQpcNs) {
        Map<String, Object> fields() {
            Map<String, Object> found = new LinkedHashMap<>();
            found.put("frameIndex", frameIndex);
            found.put("sinceReload", sinceReload);
            found.put("qpcNs", qpcNs);
            found.put("swapQpcNs", swapQpcNs);
            return found;
        }
    }

    /** One window from its request to its end: its start and end marks as they come. */
    public static final class Measure {
        private final long anchorNs;
        private final long startNs;
        private final long lengthNs;
        private final CompletableFuture<Mark> started = new CompletableFuture<>();
        private final CompletableFuture<Mark> ended = new CompletableFuture<>();
        private Mark start; // guarded by the Window

        private Measure(long anchorNs, long skipNs, long lengthNs) {
            this.anchorNs = anchorNs;
            this.startNs = anchorNs + skipNs;
            this.lengthNs = lengthNs;
        }

        /** The trigger's qpcNs: the reload's completion, or the request. */
        public long anchorNs() {
            return anchorNs;
        }

        public CompletableFuture<Mark> started() {
            return started;
        }

        public CompletableFuture<Mark> ended() {
            return ended;
        }
    }

    private final LongSupplier now;
    private final BooleanSupplier inWorld;
    private final BiConsumer<String, Map<String, Object>> events;
    // Guarded by this: the last reload's completion (null once its pipeline is gone), the counter
    // at the last frame head, the window running.
    private Long reloadNs;
    private Long lastSinceReload;
    private Measure pending;

    /** `now` reads qpcNs; window.start and window.end go to `events`. */
    public Window(LongSupplier now, BooleanSupplier inWorld,
        BiConsumer<String, Map<String, Object>> events) {
        this.now = now;
        this.inWorld = inWorld;
        this.events = events;
    }

    /** window.measure (a worker): both marks, the frames between them, its seconds and the skip's. */
    public Map<String, Object> measure(Protocol.Request request) throws Exception {
        Map<String, Object> args = request.args();
        for (String name : new String[] {"skipFrames", "frames"}) {
            if (args.get(name) != null) {
                throw new Errors.Refused(Errors.UNSUPPORTED, "window.measure." + name
                    + " is not built in this mod: suite.json times windows in seconds");
            }
        }
        if (args.get("after").equals("path")) {
            throw new Errors.Refused(Errors.UNSUPPORTED,
                "window.measure.after path waits for camera.path (M5)");
        }
        for (String name : new String[] {"skipSeconds", "seconds"}) {
            if (args.get(name) == null) {
                throw new Errors.Refused(Errors.BAD_REQUEST, "window.measure: missing argument "
                    + name + " (skipFrames and frames are not built)");
            }
        }
        Measure window = open(args.get("after").equals("reload"),
            nanos((Double) args.get("skipSeconds")), nanos((Double) args.get("seconds")));
        try {
            Mark start = await(window.started);
            if (request.live()) { // a cancelled window's marks never reach the client as events
                events.accept("window.start", start.fields());
            }
            Mark end = await(window.ended);
            long frames = end.frameIndex() - start.frameIndex();
            Map<String, Object> data = end.fields();
            data.put("frames", frames);
            if (request.live()) {
                events.accept("window.end", data);
            }
            Map<String, Object> found = new LinkedHashMap<>();
            found.put("start", start.fields());
            found.put("end", end.fields());
            found.put("frames", frames);
            found.put("seconds", (end.qpcNs() - start.qpcNs()) / NANOS);
            found.put("skippedSeconds", (start.qpcNs() - window.anchorNs) / NANOS);
            return found;
        } finally {
            close(window);
        }
    }

    /**
     * Open a window: its skip from the last reload's completion or from now; not-ready outside a
     * world, or after a reload with none since the last pipeline creation.
     */
    public synchronized Measure open(boolean afterReload, long skipNs, long lengthNs)
        throws Errors.Refused {
        if (!inWorld.getAsBoolean()) {
            throw new Errors.Refused(Errors.NOT_READY, "not in a world; fix: world.wait first");
        }
        if (afterReload && reloadNs == null) {
            throw new Errors.Refused(Errors.NOT_READY, "no shader reload since the last pipeline"
                + " creation (a join, a dimension change, a failed reload); fix: shaders.reload first");
        }
        if (pending != null) { // the window resource keeps a second one out
            throw new Errors.Refused(Errors.BUSY, "a window is running");
        }
        pending = new Measure(afterReload ? reloadNs : now.getAsLong(), skipNs, lengthNs);
        return pending;
    }

    /** The window ended or was answered first (cancel, disconnect): it takes no more frames. */
    public synchronized void close(Measure window) {
        if (pending == window) {
            pending = null;
        }
    }

    /** A frame's HEAD (render thread): a counter that fell fails the window; it starts or ends. */
    public synchronized void frame(FrameClock.Stamp stamp, Long sinceReload) {
        Long last = lastSinceReload;
        lastSinceReload = sinceReload;
        if (last != null && sinceReload != null && sinceReload < last
            && !(last == COUNTER_WRAP - 1 && sinceReload == 0)) {
            lost("a pipeline creation (sinceReload " + last + " then " + sinceReload + ")");
            return;
        }
        Measure window = pending;
        if (window == null) {
            return;
        }
        Mark mark = new Mark(stamp.frameIndex(), sinceReload, stamp.qpcNs(), stamp.swapQpcNs());
        if (window.start == null) {
            if (stamp.qpcNs() >= window.startNs) {
                window.start = mark;
                window.started.complete(mark);
            }
        } else if (stamp.qpcNs() - window.start.qpcNs() >= window.lengthNs) {
            pending = null;
            window.ended.complete(mark);
        }
    }

    /** A shader reload completed at `qpcNs` (render thread, Iris.reload returned): the anchor. */
    public synchronized void reloaded(long qpcNs) {
        fail("a shader reload");
        reloadNs = qpcNs;
        lastSinceReload = null; // the reload reset the counter
    }

    /**
     * A shader reload failed (render thread, Iris.reload returned): no anchor; the counter that
     * reload may have restarted is not read as a later pipeline creation.
     */
    public synchronized void reloadFailed() {
        lost("a failed shader reload");
        lastSinceReload = null;
    }

    /** The reload's pipeline is gone (a join, a leave, a dimension change, a failed reload). */
    public synchronized void lost(String why) {
        reloadNs = null;
        fail(why);
    }

    private void fail(String why) {
        Measure window = pending;
        if (window == null) {
            return;
        }
        pending = null;
        Errors.Refused failed = new Errors.Refused(Errors.FAILED, why
            + " fell inside the window; fix: measure it again");
        window.started.completeExceptionally(failed);
        window.ended.completeExceptionally(failed);
    }

    private static long nanos(double seconds) {
        return Math.round(seconds * NANOS);
    }

    /** The mark; a failure rethrown as itself (a coded refusal stays coded). */
    private static Mark await(CompletableFuture<Mark> future) throws Exception {
        try {
            return future.get();
        } catch (ExecutionException failed) {
            if (failed.getCause() instanceof Exception cause) {
                throw cause;
            }
            throw failed;
        }
    }
}
