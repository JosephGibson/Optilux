package optilux.helper.core;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.function.BiConsumer;
import java.util.function.BooleanSupplier;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * The per-pass GPU timers (docs/mod.md#4-architecture; plans/m2.md D53). Iris brackets its passes
 * with the static GLDebug.pushGroup and popGroup (each phase, each composite renderer and its
 * passes, the shadow composite, the final pass), which it calls on the bench tier too, where the
 * debug groups themselves do nothing. While timers run, a mixin at the HEAD of each hands the call
 * here on the render thread: a query from a pool records a GL_TIMESTAMP (glQueryCounter, written
 * once every earlier command is done), and a pass's gpuNanos is its pop's stamp minus its push's.
 * The stack follows the debug state's: a pop closes the newest open group; a pop with none open
 * is ignored and counted; a group still open at a frame head is cut there and counted.
 *
 * A frame runs from one frame head to the next. At each head the frame that ended goes in flight;
 * `maxPending` frames after it ended it is read, if every query's GL_QUERY_RESULT_AVAILABLE holds,
 * else dropped and counted late, so the render thread never waits on the GPU. A query goes back to
 * the pool only once its result is available, so none is reissued while the GPU may still write
 * it. Read frames wait for timers.read, at most `maxFrames` of them; a frame past that is dropped
 * too. Every GL call is made on the render thread ({@link #frame}, {@link #pushed},
 * {@link #popped}); the handlers only hand a session over and wait. A throw there, or a group call
 * on another thread, fails the session: nothing more is issued for it, its frames not yet read are
 * counted lost, timers.read answers `failed` and timers.stop still frees the resource. Stopped, no
 * query is issued, and the pool is deleted once the queries in flight are back.
 */
public final class Timers {
    private static final Logger LOG = LoggerFactory.getLogger("optilux-helper");
    /** Groups per frame at most: Iris's four composite stages of 100 passes, its phases, final. */
    public static final int MAX_PASSES = 512;
    /** Query names generated at once when the pool is empty. */
    public static final int BATCH = 64;
    /** Pass names kept canonical, so held frames share one string per name. */
    static final int MAX_NAMES = 4096;
    /** timers.read's wait for the frames that ended before it: maxPending frames at 8 fps. */
    public static final long READ_WAIT_NANOS = 2_000_000_000L;
    /** timers.stop's wait for its frames in flight; past it they are counted lost. */
    public static final long DRAIN_NANOS = 5_000_000_000L;
    static final String LATE = "late";
    static final String FULL = "full";
    static final String OVERFLOW = "overflow";
    static final String LOST = "lost";

    /** The GL query calls, made on the render thread only: LWJGL in the game, a fake in tests. */
    public interface Gl {
        /** glGenQueries into `names`. */
        void generate(int[] names);

        /** glQueryCounter(name, GL_TIMESTAMP). */
        void timestamp(int name);

        /** GL_QUERY_RESULT_AVAILABLE, which never waits. */
        boolean available(int name);

        /** GL_QUERY_RESULT, asked only once available, so it never waits. */
        long result(int name);

        /** glDeleteQueries. */
        void delete(int[] names);
    }

    /** One group's time on the GPU; depth 0 is a group no other group holds. */
    public record Pass(String name, int depth, long gpuNanos) {
    }

    /** One frame's passes in push order, its frameIndex the frame clock's. */
    public record Frame(long frameIndex, List<Pass> passes) {
    }

    /** One timers.start until its stop or its release; the client's side, under its own lock. */
    static final class Session {
        final Object owner;
        final boolean perPass;
        final int maxPending;
        final int maxFrames;
        // Guarded by this; the counts run from the start.
        final ArrayDeque<Frame> frames = new ArrayDeque<>();
        long late;
        long full;
        long overflow;
        long lost;
        long unmatched;
        long cut;
        boolean adopted; // the render thread records for it
        long resolvedThrough; // once adopted: every frame up to it read or dropped
        long unresolved; // frames recorded, the one in progress included, not read or dropped
        boolean stopping; // timers.stop came: no frame starts after the one in progress
        boolean abandoned; // nothing more is recorded or read for it
        boolean released; // its resource was freed under it (a disconnect, a world leave)
        String failure; // why the timers failed, or null
        boolean ended; // the render thread is done with it
        boolean dropReported; // timers.dropped went out since the start or the last read

        Session(Object owner, boolean perPass, int maxPending, int maxFrames) {
            this.owner = owner;
            this.perPass = perPass;
            this.maxPending = maxPending;
            this.maxFrames = maxFrames;
        }

        synchronized boolean running() {
            return !ended && !abandoned;
        }

        /** Frames recorded and neither read nor dropped yet count lost (under this lock). */
        void loseUnread() {
            if (!abandoned) {
                lost += unresolved;
                unresolved = 0;
            }
        }
    }

    /** A frame being recorded or in flight (render thread): its groups and the open ones. */
    private static final class Recording {
        final long frameIndex;
        final List<Entry> entries = new ArrayList<>();
        int[] open = new int[16]; // the stack: an entry's index, or -1 for an untimed group
        int depth;
        int unmatched;
        int cut;
        boolean overflow;
        int newest = -1; // the query this frame issued last

        Recording(long frameIndex) {
            this.frameIndex = frameIndex;
        }

        void push(int entry) {
            if (depth == open.length) {
                open = Arrays.copyOf(open, depth * 2);
            }
            open[depth++] = entry;
        }
    }

    private static final class Entry {
        final String name;
        final int depth;
        final int start;
        int end = -1;

        Entry(String name, int depth, int start) {
            this.name = name;
            this.depth = depth;
            this.start = start;
        }
    }

    /** What one frame head dropped, for the session and the event (the oldest frame's). */
    private static final class Drops {
        long late;
        long overflow;
        long full;
        long firstFrame = -1;
        String firstReason;

        void add(long frameIndex, String reason) {
            switch (reason) {
                case LATE -> late++;
                case OVERFLOW -> overflow++;
                default -> full++;
            }
            if (firstReason == null || frameIndex < firstFrame) {
                firstFrame = frameIndex;
                firstReason = reason;
            }
        }
    }

    private final Gl gl;
    private final BooleanSupplier inWorld;
    private final BiConsumer<String, Map<String, Object>> events;
    private volatile Session wanted; // the client's session; written under this
    private volatile long lastHead; // the newest frame head's frameIndex
    private volatile String offThread; // a group call seen on another thread, for the next head

    // Render thread only.
    private Thread renderThread;
    private Session serving;
    private Recording recording;
    private final ArrayDeque<Recording> pending = new ArrayDeque<>();
    private int[] pool = new int[BATCH];
    private int free;
    private int[] late = new int[BATCH];
    private int lateCount;
    private final Map<String, String> names = new HashMap<>();
    private Map<String, Object> dropEvent; // serve's timers.dropped, sent at the head's end
    private boolean failing; // a failure was logged and no frame head has passed since

    /** timers.dropped goes to `events`; timers.start needs `inWorld`. */
    public Timers(Gl gl, BooleanSupplier inWorld, BiConsumer<String, Map<String, Object>> events) {
        this.gl = gl;
        this.inWorld = inWorld;
        this.events = events;
    }

    // The render thread.

    /** GLDebug.pushGroup HEAD: a group opens; timed when the frame records it. */
    public void pushed(String name) {
        Recording frame = recording;
        if (frame == null) {
            return;
        }
        if (Thread.currentThread() != renderThread) {
            offThread("GLDebug.pushGroup");
        }
        try {
            int entry = -1;
            if ((serving.perPass || frame.depth == 0) && !frame.overflow) {
                if (frame.entries.size() == MAX_PASSES) {
                    frame.overflow = true;
                } else {
                    int query = take();
                    gl.timestamp(query); // a name whose stamp throws is left out of the pool
                    frame.newest = query;
                    entry = frame.entries.size();
                    frame.entries.add(new Entry(canonical(name), frame.depth, query));
                }
            }
            frame.push(entry);
        } catch (RuntimeException | Error error) {
            failed("GLDebug.pushGroup threw " + error);
            throw error;
        }
    }

    /** GLDebug.popGroup HEAD: the newest open group closes; with none open, counted. */
    public void popped() {
        Recording frame = recording;
        if (frame == null) {
            return;
        }
        if (Thread.currentThread() != renderThread) {
            offThread("GLDebug.popGroup");
        }
        try {
            if (frame.depth == 0) {
                frame.unmatched++;
                return;
            }
            int entry = frame.open[--frame.depth];
            if (entry >= 0) {
                int query = take();
                gl.timestamp(query);
                frame.newest = query;
                frame.entries.get(entry).end = query;
            }
        } catch (RuntimeException | Error error) {
            failed("GLDebug.popGroup threw " + error);
            throw error;
        }
    }

    /**
     * A group call on a thread other than the render thread's: no GL call here; the session
     * fails at the next frame head, where its frames are counted, and the throw reaches Hooks.
     */
    private void offThread(String call) {
        String why = call + " on thread " + Thread.currentThread().getName()
            + ", not the render thread";
        offThread = why;
        throw new IllegalStateException(why);
    }

    /**
     * A frame head: the frame that ended goes in flight, frames maxPending frames old are read or
     * dropped, a stopped or released session ends once nothing of it is in flight, a started one
     * is taken up, and the next frame records while a session runs.
     */
    public void frame(long frameIndex) {
        if (renderThread == null) {
            renderThread = Thread.currentThread();
        } else if (Thread.currentThread() != renderThread) {
            return;
        }
        Map<String, Object> event = null;
        try {
            lastHead = frameIndex;
            String elsewhere = offThread;
            if (elsewhere != null) {
                offThread = null;
                failed(elsewhere);
            }
            drainLate();
            boolean records = false;
            if (serving != null) {
                records = serve(serving, frameIndex);
                event = dropEvent;
                dropEvent = null;
            }
            if (serving == null) {
                records = adopt(frameIndex);
            }
            if (serving == null && pending.isEmpty() && lateCount == 0 && free > 0) {
                gl.delete(Arrays.copyOf(pool, free)); // stopped: every name is back, none in use
                free = 0;
            }
            recording = records ? new Recording(frameIndex) : null;
            failing = false;
        } catch (RuntimeException | Error error) {
            failed("a frame head threw " + error);
            throw error;
        }
        if (event != null) {
            events.accept("timers.dropped", event);
        }
    }

    /**
     * The timers fail (render thread): the session served, or the one started and not yet taken
     * up, has its frames not yet read counted lost; their stamps wait in `late` until their
     * results are in, and nothing more is recorded for it. Logged once per run of failures.
     */
    private void failed(String why) {
        if (recording != null) {
            retire(recording);
            recording = null;
        }
        while (!pending.isEmpty()) {
            retire(pending.removeFirst());
        }
        if (!failing) {
            failing = true;
            LOG.warn("optilux-helper: timers failed: {}", why);
        }
        Session session = serving != null ? serving : wanted;
        if (session == null) {
            return;
        }
        synchronized (session) {
            if (!session.ended) {
                session.loseUnread();
                if (session.failure == null) {
                    session.failure = why;
                }
                session.abandoned = true;
            }
            session.notifyAll();
        }
    }

    /**
     * One head for the session served: whether it records the next frame; a timers.dropped to
     * send goes to `dropEvent`. A frame leaves `recording` or `pending` only once its queries are
     * in the pool or in `late`, and the session's counts change together under its lock, so after
     * a throw failed() retires and counts each frame once.
     */
    private boolean serve(Session session, long head) {
        boolean stopping;
        boolean abandoned;
        synchronized (session) {
            stopping = session.stopping;
            abandoned = session.abandoned;
        }
        Drops drops = new Drops();
        long unmatched = 0;
        long cuts = 0;
        if (recording != null) {
            Recording ended = recording;
            if (abandoned) {
                retire(ended); // nothing more is issued for it
            } else {
                cut(ended);
                unmatched = ended.unmatched;
                cuts = ended.cut;
                if (ended.overflow) {
                    retire(ended);
                    drops.add(ended.frameIndex, OVERFLOW);
                } else {
                    pending.addLast(ended);
                }
            }
            recording = null;
        }
        List<Frame> read = new ArrayList<>();
        if (abandoned) {
            while (!pending.isEmpty()) {
                retire(pending.removeFirst());
            }
        } else {
            resolve(session, head, read, drops);
        }
        boolean done = (stopping || abandoned) && pending.isEmpty();
        boolean records = !done && !stopping && !abandoned;
        long resolvedThrough = pending.isEmpty() ? head - 1 : pending.peekFirst().frameIndex - 1;
        synchronized (session) {
            if (session.abandoned) {
                records = false; // released meanwhile: the next head retires what is left
            } else {
                for (Frame frame : read) {
                    if (session.frames.size() < session.maxFrames) {
                        session.frames.addLast(frame);
                    } else {
                        drops.add(frame.frameIndex(), FULL);
                    }
                }
                session.late += drops.late;
                session.overflow += drops.overflow;
                session.full += drops.full;
                session.unmatched += unmatched;
                session.cut += cuts;
                session.unresolved -= read.size() + drops.late + drops.overflow;
                session.resolvedThrough = resolvedThrough;
                records = records && !session.stopping;
                if (records) {
                    session.unresolved++; // the frame this head starts
                }
                if (drops.firstReason != null && !session.dropReported) {
                    session.dropReported = true;
                    dropEvent = new LinkedHashMap<>();
                    dropEvent.put("count", session.late + session.full + session.overflow
                        + session.lost);
                    dropEvent.put("frameIndex", drops.firstFrame);
                    dropEvent.put("reason", drops.firstReason);
                }
            }
            if (done) {
                session.ended = true;
            }
            session.notifyAll();
        }
        if (done) {
            serving = null;
        }
        return records;
    }

    /**
     * Frames in flight whose maxPending newer frames have ended (a frame ends at the head after
     * its own), oldest first: read when every query is in, else dropped late.
     */
    private void resolve(Session session, long head, List<Frame> read, Drops drops) {
        while (!pending.isEmpty() && head - pending.peekFirst().frameIndex > session.maxPending) {
            Recording oldest = pending.peekFirst();
            if (available(oldest)) {
                Frame frame = results(oldest);
                pending.removeFirst();
                read.add(frame);
            } else {
                pending.removeFirst();
                retire(oldest);
                drops.add(oldest.frameIndex, LATE);
            }
        }
    }

    /** Groups still open at the frame's end close at its head (the stamp issued now). */
    private void cut(Recording frame) {
        while (frame.depth > 0) {
            int entry = frame.open[--frame.depth];
            if (entry >= 0) {
                int query = take();
                gl.timestamp(query);
                frame.newest = query;
                frame.entries.get(entry).end = query;
                frame.cut++;
            }
        }
    }

    /** Whether every query of the frame has its result; the newest is asked first. */
    private boolean available(Recording frame) {
        if (frame.newest >= 0 && !gl.available(frame.newest)) {
            return false;
        }
        for (Entry entry : frame.entries) {
            if (!gl.available(entry.start) || !gl.available(entry.end)) {
                return false;
            }
        }
        return true;
    }

    /** The frame's passes from available results; then its queries go back to the pool. */
    private Frame results(Recording frame) {
        List<Pass> passes = new ArrayList<>(frame.entries.size());
        for (Entry entry : frame.entries) {
            passes.add(new Pass(entry.name, entry.depth, gl.result(entry.end) - gl.result(entry.start)));
        }
        for (Entry entry : frame.entries) {
            giveBack(entry.start);
            giveBack(entry.end);
        }
        return new Frame(frame.frameIndex, List.copyOf(passes));
    }

    /** A frame not read: its queries wait in `late` until their results are available. */
    private void retire(Recording frame) {
        for (Entry entry : frame.entries) {
            keepLate(entry.start);
            if (entry.end >= 0) {
                keepLate(entry.end);
            }
        }
    }

    /** Late queries whose results arrived go back to the pool; after a throw the rest stay. */
    private void drainLate() {
        int kept = 0;
        int next = 0;
        try {
            for (; next < lateCount; next++) {
                int query = late[next];
                if (gl.available(query)) {
                    giveBack(query);
                } else {
                    late[kept++] = query;
                }
            }
        } finally {
            int rest = lateCount - next;
            System.arraycopy(late, next, late, kept, rest);
            lateCount = kept + rest;
        }
    }

    /** Take up the client's session, unless it stopped or was released before its first frame. */
    private boolean adopt(long head) {
        Session target = wanted;
        if (target == null) {
            return false;
        }
        synchronized (target) {
            if (target.ended || target.adopted) {
                return false;
            }
            if (target.stopping || target.abandoned) {
                target.ended = true; // nothing recorded, nothing in flight
                target.notifyAll();
                return false;
            }
            target.adopted = true;
            target.resolvedThrough = head - 1;
            target.unresolved = 1; // the frame this head starts
        }
        serving = target;
        return true;
    }

    private int take() {
        if (free == 0) {
            int[] fresh = new int[BATCH];
            gl.generate(fresh);
            for (int name : fresh) {
                giveBack(name);
            }
        }
        return pool[--free];
    }

    private void giveBack(int query) {
        if (free == pool.length) {
            pool = Arrays.copyOf(pool, free * 2);
        }
        pool[free++] = query;
    }

    private void keepLate(int query) {
        if (lateCount == late.length) {
            late = Arrays.copyOf(late, lateCount * 2);
        }
        late[lateCount++] = query;
    }

    private String canonical(String name) {
        String known = names.get(name);
        if (known != null) {
            return known;
        }
        if (names.size() < MAX_NAMES) {
            names.put(name, name);
        }
        return name;
    }

    // The workers.

    /**
     * timers.start: a session from the next frame head on, held until timers.stop or a release;
     * not-ready outside a world, busy while another runs. Published only while the request is
     * live, under this lock: a release that answered it first finds no session to stop.
     */
    public Map<String, Object> start(Protocol.Request request) throws Errors.Refused {
        if (!inWorld.getAsBoolean()) {
            throw new Errors.Refused(Errors.NOT_READY, "not in a world; fix: world.wait first");
        }
        Map<String, Object> args = request.args();
        Session session = new Session(request, (Boolean) args.get("perPass"),
            Math.toIntExact((Long) args.get("maxPending")),
            Math.toIntExact((Long) args.get("maxFrames")));
        synchronized (this) {
            if (!request.live()) {
                throw new Errors.Refused(Errors.CANCELLED, "answered before the timers started");
            }
            Session old = wanted;
            if (old != null && old.running()) {
                throw new Errors.Refused(Errors.BUSY, "timers are running");
            }
            wanted = session;
        }
        Map<String, Object> found = new LinkedHashMap<>();
        found.put("on", true);
        found.put("perPass", session.perPass);
        found.put("maxPending", session.maxPending);
        found.put("maxFrames", session.maxFrames);
        return found;
    }

    /**
     * timers.read: once every frame that ended before the request is read or dropped (maxPending
     * frames later, READ_WAIT_NANOS at most), the frames read so far, drained; `failed` when the
     * timers failed or their resource was freed meanwhile.
     */
    public Map<String, Object> read(Protocol.Request request) throws Exception {
        Session session = active();
        long through = lastHead - 1;
        synchronized (session) {
            long until = System.nanoTime() + READ_WAIT_NANOS;
            while (session.adopted && !session.ended && !session.abandoned
                && session.resolvedThrough < through) {
                long left = until - System.nanoTime();
                if (left <= 0) {
                    break;
                }
                TimeUnit.NANOSECONDS.timedWait(session, left);
            }
            refuseIfGone(session);
        }
        return drain(session);
    }

    /**
     * timers.stop: no frame starts after the one in progress; once its frames in flight are read
     * or dropped, the frames not yet read, and the protocol frees the resource. Past DRAIN_NANOS
     * (the render thread ran no frames) the frames still in flight count lost; a failed session
     * stops at once. `failed` when the resource was freed meanwhile.
     */
    public Map<String, Object> stop(Protocol.Request request) throws Exception {
        Session session = active();
        boolean gaveUp = false;
        synchronized (session) {
            session.stopping = true;
            long until = System.nanoTime() + DRAIN_NANOS;
            while (!session.ended && !session.abandoned) {
                long left = until - System.nanoTime();
                if (left <= 0) {
                    gaveUp = true;
                    session.loseUnread();
                    session.abandoned = true;
                    session.notifyAll();
                    break;
                }
                TimeUnit.NANOSECONDS.timedWait(session, left);
            }
            if (session.released) {
                refuseIfGone(session);
            }
        }
        if (gaveUp) {
            LOG.warn("optilux-helper: timers.stop: frames still in flight after {} s count lost",
                DRAIN_NANOS / 1_000_000_000L);
        }
        Map<String, Object> answer = drain(session);
        synchronized (this) {
            if (wanted == session) {
                wanted = null;
            }
        }
        return answer;
    }

    /**
     * The timers resource was freed (a stop's answer, a disconnect, a world leave, an undelivered
     * start): a session still held stops at the next frame head, its frames in flight discarded.
     */
    public void released(Object owner) {
        Session session;
        synchronized (this) {
            session = wanted;
            if (session == null || session.owner != owner) {
                return;
            }
            wanted = null;
        }
        synchronized (session) {
            if (!session.ended) {
                session.abandoned = true;
                session.released = true;
            }
            session.notifyAll();
        }
    }

    /** The client's session; not-ready when none was started or its resource was freed. */
    private Session active() throws Errors.Refused {
        Session session = wanted;
        if (session != null) {
            synchronized (session) {
                if (!session.released) {
                    return session;
                }
            }
        }
        throw new Errors.Refused(Errors.NOT_READY, "timers are not running; fix: timers.start"
            + " first");
    }

    /** `failed` for a session that failed or whose resource was freed (under its lock). */
    private static void refuseIfGone(Session session) throws Errors.Refused {
        if (session.released) {
            throw new Errors.Refused(Errors.FAILED, "the timers stopped: their resource was freed"
                + " (a disconnect or a world leave); fix: timers.start again");
        }
        if (session.failure != null) {
            throw new Errors.Refused(Errors.FAILED, "the timers failed: " + session.failure
                + "; fix: timers.stop frees them, latest.log has the trace");
        }
    }

    /** The frames read so far, taken; the counts since the start. */
    private static Map<String, Object> drain(Session session) {
        List<Frame> frames;
        Map<String, Object> dropped = new LinkedHashMap<>();
        Map<String, Object> found = new LinkedHashMap<>();
        synchronized (session) {
            frames = new ArrayList<>(session.frames);
            session.frames.clear();
            session.dropReported = false;
            dropped.put(LATE, session.late);
            dropped.put(FULL, session.full);
            dropped.put(OVERFLOW, session.overflow);
            dropped.put(LOST, session.lost);
            found.put("unmatchedPops", session.unmatched);
            found.put("cutPasses", session.cut);
        }
        List<Map<String, Object>> list = new ArrayList<>(frames.size());
        for (Frame frame : frames) {
            list.add(fields(frame));
        }
        Map<String, Object> answer = new LinkedHashMap<>();
        answer.put("frames", list);
        answer.put("dropped", dropped);
        answer.putAll(found);
        return answer;
    }

    static Map<String, Object> fields(Frame frame) {
        List<Map<String, Object>> passes = new ArrayList<>(frame.passes().size());
        for (Pass pass : frame.passes()) {
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("name", pass.name());
            item.put("depth", pass.depth());
            item.put("gpuNanos", pass.gpuNanos());
            passes.add(item);
        }
        Map<String, Object> found = new LinkedHashMap<>();
        found.put("frameIndex", frame.frameIndex());
        found.put("passes", passes);
        return found;
    }
}
