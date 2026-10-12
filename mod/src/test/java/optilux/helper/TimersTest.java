package optilux.helper;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;
import optilux.helper.core.Errors;
import optilux.helper.core.Json;
import optilux.helper.core.Protocol;
import optilux.helper.core.State;
import optilux.helper.core.Timers;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

/**
 * The per-pass timers (plans/m2.md M2.P03) on a fake GPU whose stamps complete `lag` frames after
 * their frame ends: the pass stack (nesting, a pop without a push, a group cut at its frame's end,
 * the top level only), the query ring (a frame read maxPending frames after it ended, else dropped
 * late; a dropped frame's queries held until their results arrive; maxFrames; a frame over the
 * group cap), a failure (a throwing GL call, a group call off the render thread), and start, read
 * and stop through the protocol core with the real commands.json: busy both ways, not-ready, the
 * stop's drain and its bound, a release by a disconnect or a world leave, an undelivered start, a
 * cancelled stop. The fake GPU fails each test on a GL call off the render thread (this test's
 * thread), a query reissued or deleted while pending, availability asked of a query never issued,
 * and a result asked before it is available (the render thread would wait). A hang fails too.
 */
@Timeout(60)
class TimersTest {
    private static final long SECOND = 1_000_000_000L;

    /** A GPU whose stamps complete `lag` frames after the frame they were issued in ends. */
    private final class FakeGl implements Timers.Gl {
        final List<String> violations = Collections.synchronizedList(new ArrayList<>());
        final Set<Integer> live = new HashSet<>();
        final Map<Integer, Long> issuedAt = new HashMap<>();
        final Map<Integer, Long> stamps = new HashMap<>();
        long head;
        long clock;
        int lag;
        int timestamps;
        int throwAt = -1; // the stamp (1-based) that throws, as a failing driver call would
        int availableCalls;
        int throwAvailableAt = -1; // the availability call (1-based) that throws
        int nextName = 1;

        private void onRenderThread(String call) {
            if (Thread.currentThread() != renderThread) {
                violations.add(call + " on " + Thread.currentThread().getName());
            }
        }

        boolean done(int name) {
            Long at = issuedAt.get(name);
            return at != null && head - at - 1 >= lag;
        }

        @Override
        public void generate(int[] names) {
            onRenderThread("generate");
            for (int i = 0; i < names.length; i++) {
                names[i] = nextName++;
                live.add(names[i]);
            }
        }

        @Override
        public void timestamp(int name) {
            onRenderThread("timestamp");
            if (timestamps + 1 == throwAt) {
                throwAt = -1;
                throw new IllegalStateException("a failing glQueryCounter");
            }
            if (!live.contains(name)) {
                violations.add("timestamp on query " + name + ", which is not live");
            }
            if (issuedAt.containsKey(name) && !done(name)) {
                violations.add("query " + name + " reissued while its result was pending");
            }
            issuedAt.put(name, head);
            stamps.put(name, clock);
            timestamps++;
        }

        @Override
        public boolean available(int name) {
            onRenderThread("available");
            if (++availableCalls == throwAvailableAt) {
                throwAvailableAt = -1;
                throw new IllegalStateException("a failing glGetQueryObjectiv");
            }
            if (!issuedAt.containsKey(name)) {
                violations.add("availability of query " + name + ", never issued");
            }
            return done(name);
        }

        @Override
        public long result(int name) {
            onRenderThread("result");
            if (!done(name)) {
                violations.add("result of query " + name + " before it was available");
            }
            return stamps.get(name);
        }

        @Override
        public void delete(int[] names) {
            onRenderThread("delete");
            for (int name : names) {
                if (issuedAt.containsKey(name) && !done(name)) {
                    violations.add("query " + name + " deleted while its result was pending");
                }
                if (!live.remove(name)) {
                    violations.add("query " + name + " deleted twice");
                }
            }
        }
    }

    private final FakeGl gl = new FakeGl();
    private final AtomicBoolean inWorld = new AtomicBoolean(true);
    private final AtomicLong head = new AtomicLong();
    private final LinkedBlockingQueue<Map<String, Object>> lines = new LinkedBlockingQueue<>();
    private final Map<Object, Map<String, Object>> answered = new HashMap<>();
    private final List<Map<String, Object>> events = new ArrayList<>();
    private final Map<String, String> sent = new ConcurrentHashMap<>();
    private final CountDownLatch stepping = new CountDownLatch(1);
    // A permit per timers.start and timers.stop handler entered; a start waits on `startGate`.
    private final Semaphore startEntered = new Semaphore(0);
    private final Semaphore startExited = new Semaphore(0);
    private final Semaphore stopEntered = new Semaphore(0);
    private final AtomicReference<CountDownLatch> startGate = new AtomicReference<>(
        new CountDownLatch(0));
    private Thread renderThread;
    private Timers timers;
    private ExecutorService workers;
    private ScheduledExecutorService scheduler;
    private State state;
    private Protocol protocol;

    @BeforeEach
    void start() throws InterruptedException {
        renderThread = Thread.currentThread();
        timers = new Timers(gl, inWorld::get, (name, data) -> protocol.event(name, data));
        workers = Executors.newCachedThreadPool();
        scheduler = Executors.newSingleThreadScheduledExecutor();
        state = new State(scheduler, Duration.ofMillis(300));
        state.onReleased((resource, owner) -> {
            if (resource.equals(Session.TIMERS)) {
                timers.released(owner);
            }
        });
        Map<String, Protocol.Handler> handlers = new HashMap<>();
        handlers.put("timers.start", request -> {
            startEntered.release();
            try {
                awaitUninterruptibly(startGate.get()); // a disconnect interrupts: wait on
                return timers.start(request);
            } finally {
                startExited.release();
            }
        });
        handlers.put("timers.read", timers::read);
        handlers.put("timers.stop", request -> {
            stopEntered.release();
            return timers.stop(request);
        });
        handlers.put("command", request -> Map.of("succeeded", true, "messages", List.of(),
            "failures", List.of()));
        handlers.put("ticks.step", request -> {
            stepping.await();
            return Map.of("ticks", 1);
        });
        Protocol.Stamps stamps = new Protocol.Stamps() {
            @Override
            public long frameIndex() {
                return head.get();
            }

            @Override
            public Long sinceReload() {
                return head.get();
            }

            @Override
            public long qpcNs() {
                return head.get() * 7_000_000L;
            }
        };
        protocol = new Protocol(Wire.COMMANDS, ProtocolTest.TOKEN, handlers,
            () -> ProtocolTest.FACTS, stamps, state, workers, scheduler);
        connect();
    }

    @AfterEach
    void stop() {
        stepping.countDown();
        startGate.get().countDown();
        workers.shutdownNow();
        scheduler.shutdownNow();
        assertEquals(List.of(), gl.violations);
    }

    private void connect() throws InterruptedException {
        protocol.connected((line, after) -> {
            Map<String, Object> parsed = Wire.parse(line);
            if (parsed.containsKey("id") && parsed.get("id") != null) {
                Wire.check(sent.getOrDefault(parsed.get("id").toString(), "hello"), parsed);
            }
            lines.add(parsed);
            after.run();
        });
        String id = "h" + System.nanoTime();
        send(id, "hello", "{\"token\":\"" + ProtocolTest.TOKEN + "\"}");
        assertEquals(true, answer(id).get("ok"));
    }

    private static void awaitUninterruptibly(CountDownLatch latch) {
        boolean interrupted = false;
        while (true) {
            try {
                latch.await();
                break;
            } catch (InterruptedException again) {
                interrupted = true;
            }
        }
        if (interrupted) {
            Thread.currentThread().interrupt();
        }
    }

    // The render thread: this test's.

    /** Frame head n, the fake GPU at the same head. */
    private void head(long n) {
        head.set(n);
        gl.head = n;
        timers.frame(n);
    }

    /** One group of `nanos` on the GPU. */
    private void pass(String name, long nanos) {
        timers.pushed(name);
        gl.clock += nanos;
        timers.popped();
    }

    /** Frame heads from `from` on, `inside` run in each frame, until request `id` is answered. */
    private Map<String, Object> feedUntil(Object id, long from, Runnable inside)
        throws InterruptedException {
        long until = System.nanoTime() + 10 * SECOND;
        for (long n = from; System.nanoTime() < until; n++) {
            head(n);
            inside.run();
            Map<String, Object> found = poll(id, 1);
            if (found != null) {
                return found;
            }
        }
        throw new AssertionError("no answer to " + id + " within 10 s");
    }

    // The protocol.

    private void send(Object id, String command, String args) {
        sent.put(id.toString(), command);
        String idJson = id instanceof String text ? "\"" + text + "\"" : id.toString();
        protocol.line("{\"id\":" + idJson + ",\"cmd\":\"" + command + "\",\"args\":" + args + "}");
    }

    /** Request `id`'s answer, waiting `millis` at most; events and other answers are kept. */
    private Map<String, Object> poll(Object id, long millis) throws InterruptedException {
        Object key = id instanceof Integer number ? Long.valueOf(number) : id;
        long until = System.nanoTime() + millis * 1_000_000L;
        while (true) {
            Map<String, Object> found = answered.remove(key);
            if (found != null) {
                return found;
            }
            long left = until - System.nanoTime();
            Map<String, Object> line = left <= 0 ? lines.poll()
                : lines.poll(left, TimeUnit.NANOSECONDS);
            if (line == null) {
                return null;
            }
            if (!line.containsKey("id")) {
                events.add(line);
            } else {
                answered.put(id(line), line);
            }
        }
    }

    private Map<String, Object> answer(Object id) throws InterruptedException {
        Map<String, Object> found = poll(id, 10_000);
        assertNotNull(found, "no answer to " + id + " within 10 s");
        return found;
    }

    private static Object id(Map<String, Object> line) {
        Object id = line.get("id");
        return id instanceof Json.Num num ? num.longValue() : id;
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> result(Map<String, Object> answer) {
        assertEquals(true, answer.get("ok"), "expected a result: " + answer);
        return (Map<String, Object>) answer.get("result");
    }

    @SuppressWarnings("unchecked")
    private static String code(Map<String, Object> answer) {
        assertEquals(false, answer.get("ok"), "expected an error: " + answer);
        return (String) ((Map<String, Object>) answer.get("error")).get("code");
    }

    @SuppressWarnings("unchecked")
    private static String message(Map<String, Object> answer) {
        return (String) ((Map<String, Object>) answer.get("error")).get("message");
    }

    private static long number(Object value) {
        return ((Json.Num) value).longValue();
    }

    /** A read or stop's frames as "index: name/depth/nanos, ..." lines. */
    @SuppressWarnings("unchecked")
    private static List<String> frames(Map<String, Object> result) {
        List<String> found = new ArrayList<>();
        for (Object item : (List<Object>) result.get("frames")) {
            Map<String, Object> frame = (Map<String, Object>) item;
            List<String> passes = new ArrayList<>();
            for (Object pass : (List<Object>) frame.get("passes")) {
                Map<String, Object> fields = (Map<String, Object>) pass;
                passes.add(fields.get("name") + "/" + number(fields.get("depth")) + "/"
                    + number(fields.get("gpuNanos")));
            }
            found.add(number(frame.get("frameIndex")) + ": " + String.join(", ", passes));
        }
        return found;
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Long> dropped(Map<String, Object> result) {
        Map<String, Long> found = new HashMap<>();
        ((Map<String, Object>) result.get("dropped")).forEach((key, value) -> found.put(key,
            number(value)));
        return found;
    }

    @SuppressWarnings("unchecked")
    private static String event(Map<String, Object> line) {
        Map<String, Object> data = (Map<String, Object>) line.get("data");
        return line.get("event") + " " + number(data.get("count")) + " "
            + number(data.get("frameIndex")) + " " + data.get("reason");
    }

    private Map<String, Object> started(String args) throws InterruptedException {
        String id = "s" + System.nanoTime();
        send(id, "timers.start", args);
        return result(answer(id));
    }

    /** A read whose frames need heads from `from` on, `inside` each. */
    private Map<String, Object> read(Object id, long from, Runnable inside)
        throws InterruptedException {
        send(id, "timers.read", "{}");
        return result(feedUntil(id, from, inside));
    }

    /** A request whose handler waits for heads: sent, seen waiting, before any head runs. */
    private void sendWaiting(Object id, String command, Semaphore entered)
        throws InterruptedException {
        send(id, command, "{}");
        if (entered != null) {
            assertTrue(entered.tryAcquire(5, TimeUnit.SECONDS), command + " never ran");
        }
        assertNull(poll(id, 200), command + " answered before its frames");
    }

    // The pass stack.

    @Test
    void passesNestInPushOrderWithTheirDepths() throws InterruptedException {
        Map<String, Object> on = started("{}");
        assertEquals("true true 3 1000", on.get("on") + " " + on.get("perPass") + " "
            + number(on.get("maxPending")) + " " + number(on.get("maxFrames")));
        head(1);
        pass("Clear textures", 100);
        timers.pushed("deferred");
        pass("deferred1", 300);
        pass("deferred2", 200);
        timers.popped();
        pass("final", 50);
        head(2);
        Map<String, Object> read = read(1, 3, () -> { });
        assertEquals("1: Clear textures/0/100, deferred/0/500, deferred1/1/300,"
            + " deferred2/1/200, final/0/50", frames(read).get(0));
        assertEquals(Map.of("late", 0L, "full", 0L, "overflow", 0L, "lost", 0L), dropped(read));
        assertEquals(0L, number(read.get("unmatchedPops")));
    }

    @Test
    void aPopWithoutAPushIsIgnoredAndCountedAndAGroupOpenAtTheHeadIsCut()
        throws InterruptedException {
        started("{\"maxPending\":1}");
        head(1);
        timers.popped(); // setPhase pops before its frame's first push
        pass("Sky", 400);
        timers.pushed("Hand");
        gl.clock += 70; // open at the head: cut there
        head(2);
        timers.popped(); // Hand's pop, a frame late: nothing open
        head(3);
        Map<String, Object> read = read(1, 4, () -> { });
        assertEquals(List.of("1: Sky/0/400, Hand/0/70", "2: "), frames(read).subList(0, 2));
        assertEquals(2L, number(read.get("unmatchedPops")));
        assertEquals(1L, number(read.get("cutPasses")));
    }

    @Test
    void perPassFalseTimesOnlyTheTopLevel() throws InterruptedException {
        started("{\"perPass\":false,\"maxPending\":1}");
        head(1);
        int before = gl.timestamps;
        timers.pushed("deferred");
        pass("deferred1", 300);
        pass("deferred2", 200);
        timers.popped();
        pass("final", 50);
        assertEquals(4, gl.timestamps - before, "two stamps per top-level group, none nested");
        head(2);
        assertEquals("1: deferred/0/500, final/0/50", frames(read(1, 3, () -> { })).get(0));
    }

    // The query ring.

    @Test
    void aFrameIsReadMaxPendingFramesLaterAndAReadWaitsForTheFramesBeforeIt()
        throws InterruptedException {
        gl.lag = 3; // the GPU finishes a frame 3 frames after it ends: maxPending 3 keeps it
        started("{\"maxPending\":3}");
        for (long n = 1; n <= 10; n++) {
            head(n);
            pass("composite", 1000);
        }
        // Frame n is read at head n + 4: at head 10, frames 1-6; the read waits for 7-9.
        sendWaiting(1, "timers.read", null);
        head(11);
        pass("composite", 1000);
        head(12);
        pass("composite", 1000);
        assertNull(poll(1L, 200), "the read answered without frame 9");
        head(13);
        Map<String, Object> read = result(answer(1L));
        List<String> frames = frames(read);
        assertEquals(9, frames.size(), frames.toString());
        for (int n = 1; n <= 9; n++) {
            assertEquals(n + ": composite/0/1000", frames.get(n - 1));
        }
        assertEquals(0L, dropped(read).get("late"));
        assertEquals(List.of(), events);
    }

    @Test
    void aFrameStillPendingAfterMaxPendingFramesIsDroppedAndItsQueriesWaitForTheirResults()
        throws InterruptedException {
        gl.lag = 4; // one frame later than maxPending 3 allows: every frame is dropped
        started("{\"maxPending\":3}");
        for (long n = 1; n <= 40; n++) {
            head(n);
            pass("composite", 1000);
        }
        // Frame n was dropped at head n + 4: 1-36. The GPU catches up: 37-40 are read at 41-44.
        gl.lag = 0;
        Map<String, Object> read = read(1, 41, () -> pass("composite", 1000));
        assertEquals(List.of("37: composite/0/1000", "38: composite/0/1000",
            "39: composite/0/1000"), frames(read).subList(0, 3));
        assertEquals(36L, dropped(read).get("late"));
        // One event until the read; each dropped frame's queries came back only once in, so 40
        // frames ran on one batch (the fake fails a query reissued while pending).
        assertEquals(List.of("timers.dropped 1 1 late"), events.stream().map(TimersTest::event)
            .toList());
        assertEquals(Timers.BATCH, gl.live.size(), "the pool grew past one batch");
        // After the read the next drop is reported again, once, its count the start's: four
        // empty frames let the timed ones in flight be read first.
        events.clear();
        long next = head.get() + 1;
        for (int i = 0; i < 4; i++) {
            head(next++);
        }
        gl.lag = 4;
        long firstDropped = next;
        for (int i = 0; i < 11; i++) {
            head(next++);
            pass("composite", 1000);
        }
        poll("none", 100);
        assertEquals(List.of("timers.dropped 37 " + firstDropped + " late"), events.stream()
            .map(TimersTest::event).toList());
    }

    @Test
    void atMostMaxFramesAreHeldAndAFrameOverTheGroupCapIsDropped() throws InterruptedException {
        started("{\"maxPending\":1,\"maxFrames\":2}");
        for (long n = 1; n <= 6; n++) {
            head(n);
            pass("final", 10);
        }
        // Frames 1-4 are in by head 6; the read waits for frame 5, in at head 7.
        sendWaiting(1, "timers.read", null);
        head(7);
        Map<String, Object> read = result(answer(1L));
        assertEquals(List.of("1: final/0/10", "2: final/0/10"), frames(read));
        assertEquals(3L, dropped(read).get("full"));
        assertEquals(List.of("timers.dropped 1 3 full"), events.stream().map(TimersTest::event)
            .toList());
        events.clear();
        head(8); // frame 6 is read, held again: the read made room
        for (int i = 0; i <= Timers.MAX_PASSES; i++) { // one group over the cap
            pass("composite" + i, 1);
        }
        timers.pushed("Hand"); // open at the head, then dropped with its frame
        head(9); // frame 7 (no groups) is read; frame 8 is dropped after it
        read = result(sendAndAnswer(2, "timers.read"));
        assertEquals(List.of("6: final/0/10", "7: "), frames(read));
        assertEquals(Map.of("late", 0L, "full", 3L, "overflow", 1L, "lost", 0L), dropped(read),
            "the counts run from the start");
        assertEquals(List.of("timers.dropped 4 8 overflow"), events.stream()
            .map(TimersTest::event).toList());
    }

    private Map<String, Object> sendAndAnswer(Object id, String command)
        throws InterruptedException {
        send(id, command, "{}");
        return answer(id);
    }

    // A failure.

    @Test
    void aThrowingGlCallFailsTheTimersAtOnceAndCountsTheirFramesLost()
        throws InterruptedException {
        started("{}");
        head(1);
        pass("final", 10);
        head(2);
        pass("Sky", 10);
        gl.throwAt = gl.timestamps + 1;
        assertThrows(IllegalStateException.class, () -> timers.pushed("Terrain solid"));
        int stamps = gl.timestamps;
        pass("deferred", 10); // the failed timers take no more groups
        head(3);
        assertEquals(stamps, gl.timestamps, "a failed session issued a query");
        Map<String, Object> read = sendAndAnswer(1, "timers.read");
        assertEquals(Errors.FAILED, code(read));
        assertTrue(message(read).contains("GLDebug.pushGroup threw"), message(read));
        Map<String, Object> stopped = result(sendAndAnswer(2, "timers.stop"));
        assertEquals(List.of(), frames(stopped));
        assertEquals(2L, dropped(stopped).get("lost"), "frames 1 and 2, never read");
        send(3, "command", "{\"text\":\"/tick freeze\",\"timeoutSeconds\":5}");
        assertEquals(true, answer(3L).get("ok"), "the stop kept the resource");
        for (long n = 4; n <= 10; n++) {
            head(n);
        }
        assertEquals(1, gl.live.size(), "only the name whose stamp threw stays: " + gl.live);
    }

    @Test
    void aThrowAtAFrameHeadFailsTheTimersAndLosesNoQuery() throws InterruptedException {
        gl.lag = 3; // maxPending 1: every frame is dropped late, its queries wait in `late`
        started("{\"maxPending\":1}");
        for (long n = 1; n <= 6; n++) {
            head(n);
            pass("final", 10);
        }
        // At head 7 the late list's drain asks first: its second call throws mid-drain.
        gl.throwAvailableAt = gl.availableCalls + 2;
        assertThrows(IllegalStateException.class, () -> head(7));
        Map<String, Object> read = sendAndAnswer(1, "timers.read");
        assertEquals(Errors.FAILED, code(read));
        assertTrue(message(read).contains("a frame head threw"), message(read));
        Map<String, Object> stopped = result(sendAndAnswer(2, "timers.stop"));
        Map<String, Long> dropped = dropped(stopped);
        assertEquals(6L, dropped.get("late") + dropped.get("lost"), "frames 1-6, each once");
        assertEquals(2L, dropped.get("lost"), "frames 5 and 6, in flight");
        gl.lag = 0;
        for (long n = 8; n <= 12; n++) {
            head(n);
        }
        assertEquals(Set.of(), gl.live, "a query lost, or deleted twice, after the throw");
        started("{}"); // the timers start again
        head(13);
        pass("final", 10);
        assertEquals(2, gl.timestamps - 12, "the next session's stamps");
    }

    @Test
    void anOverflowBeforeAFailureCountsEachFrameOnce() throws InterruptedException {
        started("{}");
        head(1);
        pass("final", 10);
        head(2);
        for (int i = 0; i <= Timers.MAX_PASSES; i++) {
            pass("composite" + i, 1);
        }
        head(3); // frame 2 dropped overflow while frame 1 waits
        gl.throwAt = gl.timestamps + 1;
        assertThrows(IllegalStateException.class, () -> timers.pushed("final"));
        Map<String, Long> dropped = dropped(result(sendAndAnswer(1, "timers.stop")));
        assertEquals(Map.of("late", 0L, "full", 0L, "overflow", 1L, "lost", 2L), dropped,
            "frames 1 and 3 lost, frame 2 overflow");
    }

    @Test
    void twoDropsAtOneHeadReportTheOlderFrame() throws InterruptedException {
        started("{\"maxPending\":1,\"maxFrames\":1}");
        head(1);
        pass("final", 10);
        head(2);
        pass("final", 10);
        head(3); // frame 1 held: maxFrames reached
        for (int i = 0; i <= Timers.MAX_PASSES; i++) {
            pass("composite" + i, 1);
        }
        head(4); // frame 2 dropped full, frame 3 dropped overflow
        poll("none", 100);
        assertEquals(List.of("timers.dropped 2 2 full"), events.stream().map(TimersTest::event)
            .toList());
    }

    @Test
    void aStopThatGivesUpBeforeTheFirstFrameLosesNothing() throws InterruptedException {
        started("{}");
        Map<String, Object> stopped = result(sendAndAnswer(1, "timers.stop"));
        assertEquals(List.of(), frames(stopped));
        assertEquals(0L, dropped(stopped).get("lost"));
        head(1);
        pass("final", 10);
        assertEquals(0, gl.timestamps, "a stopped session was taken up");
    }

    @Test
    void aGroupCallOffTheRenderThreadFailsTheTimers() throws Exception {
        started("{}");
        head(1);
        int before = gl.timestamps;
        AtomicReference<Throwable> thrown = new AtomicReference<>();
        Thread other = new Thread(() -> {
            try {
                timers.pushed("composite");
            } catch (RuntimeException error) {
                thrown.set(error);
            }
        }, "not-the-render-thread");
        other.start();
        other.join();
        assertEquals(before, gl.timestamps, "a query issued off the render thread");
        assertTrue(thrown.get() instanceof IllegalStateException, String.valueOf(thrown.get()));
        head(2);
        Map<String, Object> read = sendAndAnswer(1, "timers.read");
        assertEquals(Errors.FAILED, code(read));
        assertTrue(message(read).contains("not-the-render-thread"), message(read));
        assertEquals(1L, dropped(result(sendAndAnswer(2, "timers.stop"))).get("lost"));
    }

    // Through the protocol: start, read, stop and the resource.

    @Test
    void stopDrainsTheFramesInFlightFreesTheResourceAndIssuesNoMoreQueries()
        throws InterruptedException {
        gl.lag = 2;
        started("{}");
        for (long n = 1; n <= 3; n++) {
            head(n);
            pass("final", 10);
        }
        send(2, "command", "{\"text\":\"/tick freeze\",\"timeoutSeconds\":5}");
        assertEquals(Errors.BUSY, code(answer(2L)), "a mutation inside the timers");
        send(3, "timers.start", "{}");
        assertEquals(Errors.BUSY, code(answer(3L)), "a second start");
        // The stop comes during frame 3: frame 3 is the last recorded, then 1-3 are read.
        sendWaiting(4, "timers.stop", stopEntered);
        Map<String, Object> stopped = result(feedUntil(4L, 4, () -> pass("final", 10)));
        assertEquals(List.of("1: final/0/10", "2: final/0/10", "3: final/0/10"), frames(stopped));
        int stamps = gl.timestamps;
        for (long n = 100; n <= 103; n++) {
            head(n);
            pass("final", 10);
        }
        assertEquals(stamps, gl.timestamps, "stopped, a query was issued");
        assertEquals(Set.of(), gl.live, "stopped with queries left");
        send(5, "command", "{\"text\":\"/tick freeze\",\"timeoutSeconds\":5}");
        assertEquals(true, answer(5L).get("ok"), "the resource stayed held");
        send(6, "timers.read", "{}");
        assertEquals(Errors.NOT_READY, code(answer(6L)));
        send(7, "timers.stop", "{}");
        assertEquals(Errors.NOT_READY, code(answer(7L)));
    }

    @Test
    void aStopWhoseFramesNeverComeCountsThemLostAndStillFreesTheResource()
        throws InterruptedException {
        started("{}");
        head(1);
        pass("final", 10);
        head(2);
        pass("final", 10);
        // No head runs while the stop waits: after its 5 s bound, frames 1 and 2 count lost.
        Map<String, Object> stopped = result(sendAndAnswer(1, "timers.stop"));
        assertEquals(List.of(), frames(stopped));
        assertEquals(2L, dropped(stopped).get("lost"));
        send(2, "command", "{\"text\":\"/tick freeze\",\"timeoutSeconds\":5}");
        assertEquals(true, answer(2L).get("ok"));
        for (long n = 3; n <= 8; n++) {
            head(n);
        }
        assertEquals(Set.of(), gl.live, "a stop past its bound left queries");
    }

    @Test
    void aStartWaitsForARunningMutationAndOutsideAWorldIsNotReady() throws InterruptedException {
        send(1, "ticks.step", "{\"n\":5,\"timeoutSeconds\":30}");
        send(2, "timers.start", "{}");
        assertEquals(Errors.BUSY, code(answer(2L)), "timers over a running mutation");
        stepping.countDown();
        assertEquals(true, answer(1L).get("ok"));
        inWorld.set(false);
        send(3, "timers.start", "{}");
        assertEquals(Errors.NOT_READY, code(answer(3L)));
        send(4, "command", "{\"text\":\"/tick freeze\",\"timeoutSeconds\":5}");
        assertEquals(true, answer(4L).get("ok"), "a refused start kept its resource");
        inWorld.set(true);
        started("{}");
        send(5, "ticks.step", "{\"n\":5,\"timeoutSeconds\":30}");
        assertEquals(Errors.BUSY, code(answer(5L)), "a mutation inside the timers");
    }

    @Test
    void aStopBeforeTheFirstFrameEndsAtTheNextHead() throws InterruptedException {
        started("{}");
        sendWaiting(1, "timers.stop", stopEntered);
        Map<String, Object> stopped = result(feedUntil(1L, 1, () -> pass("final", 10)));
        assertEquals(List.of(), frames(stopped));
        assertEquals(0, gl.timestamps);
    }

    @Test
    void aCancelledStopKeepsTheResourceUntilAStopAnswers() throws InterruptedException {
        started("{}");
        head(1);
        pass("final", 10);
        sendWaiting(1, "timers.stop", stopEntered);
        send(2, "cancel", "{\"id\":1}");
        assertEquals(Errors.CANCELLED, code(answer(1L)));
        assertEquals(true, result(answer(2L)).get("cancelled"));
        for (long n = 2; n <= 8; n++) { // the stopped timers end, their frame read
            head(n);
        }
        send(3, "command", "{\"text\":\"/tick freeze\",\"timeoutSeconds\":5}");
        assertEquals(Errors.BUSY, code(answer(3L)), "the resource went with a cancelled stop");
        Map<String, Object> stopped = result(sendAndAnswer(4, "timers.stop"));
        assertEquals(List.of("1: final/0/10"), frames(stopped));
        send(5, "command", "{\"text\":\"/tick freeze\",\"timeoutSeconds\":5}");
        assertEquals(true, answer(5L).get("ok"));
    }

    @Test
    void aDisconnectOrAWorldLeaveStopsTheTimersAndTheirQueriesGo() throws InterruptedException {
        gl.lag = 2;
        started("{}");
        for (long n = 1; n <= 3; n++) {
            head(n);
            pass("final", 10);
        }
        timers.pushed("Hand"); // open when released: never stamped
        protocol.disconnected();
        assertTrue(state.held().isEmpty());
        int stamps = gl.timestamps;
        for (long n = 4; n <= 10; n++) {
            head(n);
            pass("final", 10);
        }
        assertEquals(stamps, gl.timestamps, "released, a query was issued");
        assertEquals(Set.of(), gl.live, "released with queries left");

        // A new session taken up at the head where nothing of the old one is left.
        connect();
        started("{}");
        for (long n = 11; n <= 13; n++) {
            head(n);
            pass("final", 10);
        }
        // A world leave while a stop waits: the stop answers failed, the resource is free.
        sendWaiting(8, "timers.stop", stopEntered);
        protocol.worldLeft();
        assertEquals(Errors.FAILED, code(answer(8L)));
        stamps = gl.timestamps;
        for (long n = 14; n <= 20; n++) {
            head(n);
            pass("final", 10);
        }
        assertEquals(stamps, gl.timestamps, "left, a query was issued");
        assertEquals(Set.of(), gl.live, "left with queries left");
        send(9, "timers.read", "{}");
        assertEquals(Errors.NOT_READY, code(answer(9L)));
    }

    @Test
    void aStartAnsweredBeforeItsHandlerPublishedNoSession() throws InterruptedException {
        // A disconnect answers the start and frees its resource while the handler still runs:
        // the session must not start later with nothing holding the resource.
        startGate.set(new CountDownLatch(1));
        startExited.drainPermits();
        send(1, "timers.start", "{}");
        assertTrue(startEntered.tryAcquire(5, TimeUnit.SECONDS), "timers.start never ran");
        protocol.disconnected();
        startGate.get().countDown();
        assertTrue(startExited.tryAcquire(5, TimeUnit.SECONDS), "timers.start never returned");
        for (long n = 1; n <= 4; n++) {
            head(n);
            pass("final", 10);
        }
        assertEquals(0, gl.timestamps, "timers ran with no resource held");
        assertTrue(state.held().isEmpty());
        connect();
        startGate.set(new CountDownLatch(0));
        started("{}");
        head(5);
        pass("final", 10);
        assertEquals(2, gl.timestamps, "a start after the reconnect");
    }
}
