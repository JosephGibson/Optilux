package optilux.helper;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;
import optilux.helper.core.Errors;
import optilux.helper.core.FrameClock;
import optilux.helper.core.Json;
import optilux.helper.core.Protocol;
import optilux.helper.core.State;
import optilux.helper.core.Window;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

/**
 * window.measure on a fake clock (docs/mod.md#6-time-and-determinism): the skip from the reload's
 * completion or the request, the length from the start's HEAD stamp, the reload anchor and what
 * drops it, a failure inside; then through the protocol core with the real commands.json: the
 * answer and its events, the unbuilt arguments, busy both ways and a cancel.
 */
class WindowTest {
    // A frame every 7 ms: frame n's HEAD stamp at n x 7 ms, its swap 0.1 ms before.
    private static final long FRAME_NS = 7_000_000L;
    private static final long SECOND = 1_000_000_000L;

    private final AtomicLong now = new AtomicLong();
    private final AtomicLong last = new AtomicLong();
    private final AtomicBoolean inWorld = new AtomicBoolean(true);
    private final LinkedBlockingQueue<Map<String, Object>> lines = new LinkedBlockingQueue<>();
    private final Map<String, String> sent = new HashMap<>();
    private final CountDownLatch stepping = new CountDownLatch(1);
    private final CountDownLatch capturing = new CountDownLatch(1);
    private final Window window = new Window(now::get, inWorld::get,
        (name, data) -> this.protocol.event(name, data));
    private ExecutorService workers;
    private ScheduledExecutorService timers;
    private State state;
    private Protocol protocol;

    @BeforeEach
    void start() {
        workers = Executors.newCachedThreadPool();
        timers = Executors.newSingleThreadScheduledExecutor();
        state = new State(timers, Duration.ofMillis(300));
        Map<String, Protocol.Handler> handlers = new HashMap<>();
        handlers.put("window.measure", window::measure);
        handlers.put("command", request -> Map.of("succeeded", true, "messages", List.of(),
            "failures", List.of()));
        handlers.put("ticks.step", request -> {
            stepping.await();
            return Map.of("ticks", 1);
        });
        handlers.put("frames.capture", request -> {
            capturing.await();
            Map<String, Object> answer = new HashMap<>();
            answer.put("frames", List.of());
            answer.put("dropped", List.of());
            answer.put("ready", null);
            answer.put("manifest", "capture.json");
            return answer;
        });
        Protocol.Stamps stamps = new Protocol.Stamps() {
            @Override
            public long frameIndex() {
                return last.get();
            }

            @Override
            public Long sinceReload() {
                return 7L;
            }

            @Override
            public long qpcNs() {
                return now.get();
            }
        };
        protocol = new Protocol(Wire.COMMANDS, ProtocolTest.TOKEN, handlers,
            () -> ProtocolTest.FACTS, stamps, state, workers, timers);
        protocol.connected((line, after) -> {
            Map<String, Object> parsed = Wire.parse(line);
            if (parsed.containsKey("id") && parsed.get("id") != null) {
                Wire.check(sent.getOrDefault(parsed.get("id").toString(), "hello"), parsed);
            }
            lines.add(parsed);
            after.run();
        });
    }

    @AfterEach
    void stop() {
        stepping.countDown();
        capturing.countDown();
        workers.shutdownNow();
        timers.shutdownNow();
    }

    private static FrameClock.Stamp stamp(long n) {
        return new FrameClock.Stamp(n, n * FRAME_NS, n * FRAME_NS - 100_000L);
    }

    /** Frames `from` to `to`, their counter run from the reload after frame `reloadFrame`. */
    private void frames(long from, long to, long reloadFrame) {
        for (long n = from; n <= to; n++) {
            last.set(n);
            now.set(stamp(n).qpcNs());
            window.frame(stamp(n), n - reloadFrame);
        }
    }

    private static Errors.Refused failure(CompletableFuture<?> future) {
        assertTrue(future.isDone(), "not failed yet");
        ExecutionException thrown = assertThrows(ExecutionException.class, future::get);
        assertTrue(thrown.getCause() instanceof Errors.Refused, thrown.toString());
        return (Errors.Refused) thrown.getCause();
    }

    // The clock.

    @Test
    void theSkipCountsFromTheReloadAndTheLengthFromTheStart() throws Exception {
        frames(1, 100, 0);
        window.reloaded(stamp(100).qpcNs() + 300_000L); // Iris.reload returned 0.3 ms after frame 100
        frames(101, 150, 100);
        // The request comes 50 frames later; the skip still counts from the reload.
        Window.Measure measure = window.open(true, 1_500_000_000L, 2_500_000_000L);
        assertEquals(700_300_000L, measure.anchorNs());
        // The skip ends at 2200.3 ms: frame 314 (2198 ms) is short of it, frame 315 (2205 ms) starts.
        frames(151, 314, 100);
        assertFalse(measure.started().isDone());
        frames(315, 315, 100);
        Window.Mark start = measure.started().getNow(null);
        assertEquals(new Window.Mark(315, 215L, 2_205_000_000L, 2_204_900_000L), start);
        // 2.5 s after 2205 ms is 4705 ms: frame 672 (4704 ms) is short, frame 673 (4711 ms) ends.
        frames(316, 672, 100);
        assertFalse(measure.ended().isDone());
        frames(673, 700, 100);
        assertEquals(new Window.Mark(673, 573L, 4_711_000_000L, 4_710_900_000L),
            measure.ended().getNow(null));
        // Ended: it takes no more frames and the next window opens.
        window.close(window.open(false, 0, SECOND));
    }

    @Test
    void nowCountsTheSkipFromTheRequest() throws Exception {
        frames(1, 140, 0);
        now.set(990_000_000L); // the request, 10 ms before frame 142's 994 ms
        Window.Measure measure = window.open(false, 0, 10_000_000L);
        assertEquals(990_000_000L, measure.anchorNs());
        frames(141, 141, 0); // a frame the clock is fed late, before the anchor: not the start
        assertFalse(measure.started().isDone());
        frames(142, 143, 0);
        assertEquals(142, measure.started().getNow(null).frameIndex());
        assertFalse(measure.ended().isDone(), "frame 143 lies 7 ms after the start, short of 10");
        frames(144, 144, 0);
        assertEquals(144, measure.ended().getNow(null).frameIndex());
    }

    @Test
    void theReloadAnchorAndWhatDropsIt() throws Exception {
        Errors.Refused refused = assertThrows(Errors.Refused.class,
            () -> window.open(true, 0, SECOND));
        assertEquals(Errors.NOT_READY, refused.code());
        assertTrue(refused.getMessage().contains("fix: shaders.reload first"), refused.getMessage());
        window.reloaded(1_000L);
        window.close(window.open(true, 0, SECOND));
        window.lost("a dimension change (minecraft:overworld to minecraft:the_nether)");
        assertEquals(Errors.NOT_READY,
            assertThrows(Errors.Refused.class, () -> window.open(true, 0, SECOND)).code());
        // A pipeline creation only the counter shows: sinceReload falls.
        window.reloaded(stamp(10).qpcNs());
        frames(11, 20, 10);
        frames(21, 21, 21); // sinceReload 10, then 0
        assertEquals(Errors.NOT_READY,
            assertThrows(Errors.Refused.class, () -> window.open(true, 0, SECOND)).code());
        // Iris's counter wraps at 720720 without a reload: the anchor stays.
        window.reloaded(stamp(30).qpcNs());
        frames(31, 31, 31 - 720_719);
        frames(32, 33, 32);
        window.close(window.open(true, 0, SECOND));
        inWorld.set(false);
        assertEquals(Errors.NOT_READY,
            assertThrows(Errors.Refused.class, () -> window.open(false, 0, SECOND)).code());
    }

    @Test
    void aReloadADimensionChangeOrAPipelineCreationInsideFailsIt() throws Exception {
        window.reloaded(stamp(1).qpcNs());
        frames(1, 10, 1);
        Window.Measure measure = window.open(false, 0, SECOND);
        frames(11, 12, 1);
        assertTrue(measure.started().isDone());
        window.reloaded(stamp(12).qpcNs() + 1);
        Errors.Refused refused = failure(measure.ended());
        assertEquals(Errors.FAILED, refused.code());
        assertEquals("a shader reload fell inside the window; fix: measure it again",
            refused.getMessage());

        measure = window.open(true, SECOND, SECOND); // inside the skip, before the start
        window.lost("a dimension change (minecraft:overworld to minecraft:the_nether)");
        assertEquals("a dimension change (minecraft:overworld to minecraft:the_nether) fell inside"
            + " the window; fix: measure it again", failure(measure.started()).getMessage());

        window.reloaded(stamp(20).qpcNs());
        frames(21, 25, 20);
        measure = window.open(false, 0, SECOND);
        frames(26, 30, 20);
        frames(31, 31, 31);
        assertEquals("a pipeline creation (sinceReload 10 then 0) fell inside the window; fix:"
            + " measure it again", failure(measure.ended()).getMessage());
        // A failed window took no more frames: the next one opens.
        window.close(window.open(false, 0, SECOND));
    }

    // Through the protocol core.

    private void send(Object id, String command, String args) {
        sent.put(id.toString(), command);
        String idJson = id instanceof String text ? "\"" + text + "\"" : id.toString();
        protocol.line("{\"id\":" + idJson + ",\"cmd\":\"" + command + "\",\"args\":" + args + "}");
    }

    private Map<String, Object> next() throws InterruptedException {
        Map<String, Object> line = lines.poll(5, TimeUnit.SECONDS);
        assertNotNull(line, "nothing within 5 s");
        return line;
    }

    private static Object id(Map<String, Object> line) {
        Object id = line.get("id");
        return id instanceof Json.Num num ? num.longValue() : id;
    }

    @SuppressWarnings("unchecked")
    private static String code(Map<String, Object> answer) {
        assertEquals(false, answer.get("ok"), "expected an error: " + answer);
        return (String) ((Map<String, Object>) answer.get("error")).get("code");
    }

    private void hello() throws InterruptedException {
        send("h", "hello", "{\"token\":\"" + ProtocolTest.TOKEN + "\"}");
        assertEquals(true, next().get("ok"));
    }

    /** Frames from `from` on, a millisecond apart, until request `id` is answered; the events. */
    private Map<String, Object> feedUntil(Object id, long from, long reloadFrame,
        List<Map<String, Object>> events) throws InterruptedException {
        long until = System.nanoTime() + 10 * SECOND;
        for (long n = from; System.nanoTime() < until; n++) {
            frames(n, n, reloadFrame);
            Map<String, Object> line;
            while ((line = lines.poll(1, TimeUnit.MILLISECONDS)) != null) {
                if (!line.containsKey("id")) {
                    events.add(line);
                } else if (id.equals(id(line))) {
                    return line;
                }
            }
        }
        throw new AssertionError("no answer to " + id + " within 10 s");
    }

    private static long number(Object value) {
        return ((Json.Num) value).longValue();
    }

    @Test
    @SuppressWarnings("unchecked")
    void theAnswerAndItsEventsCarryBothStampsAndTheFrames() throws Exception {
        hello();
        frames(1, 100, 0);
        window.reloaded(stamp(100).qpcNs());
        send(1, "window.measure", "{\"after\":\"reload\",\"skipSeconds\":0.1,\"seconds\":0.2}");
        List<Map<String, Object>> events = new ArrayList<>();
        Map<String, Object> answer = feedUntil(1L, 101, 100, events);
        assertEquals(true, answer.get("ok"), answer.toString()); // its fields: Wire.check
        Map<String, Object> result = (Map<String, Object>) answer.get("result");
        Map<String, Object> start = (Map<String, Object>) result.get("start");
        Map<String, Object> end = (Map<String, Object>) result.get("end");
        long frames = number(end.get("frameIndex")) - number(start.get("frameIndex"));
        assertEquals(frames, number(result.get("frames")));
        long startNs = number(start.get("qpcNs"));
        long endNs = number(end.get("qpcNs"));
        assertTrue(startNs >= stamp(100).qpcNs() + SECOND / 10, "started inside the skip");
        assertTrue(endNs - startNs >= SECOND / 5 && endNs - startNs < SECOND / 5 + FRAME_NS);
        assertEquals((endNs - startNs) / 1e9, ((Json.Num) result.get("seconds")).doubleValue());
        assertEquals((startNs - stamp(100).qpcNs()) / 1e9,
            ((Json.Num) result.get("skippedSeconds")).doubleValue());
        assertEquals(startNs - 100_000L, number(start.get("swapQpcNs")));
        assertEquals(number(start.get("frameIndex")) - 100, number(start.get("sinceReload")));
        assertEquals(List.of("window.start", "window.end"),
            events.stream().map(e -> e.get("event")).toList());
        assertEquals(start, events.get(0).get("data"));
        Map<String, Object> ended = new HashMap<>((Map<String, Object>) events.get(1).get("data"));
        assertEquals(frames, number(ended.remove("frames")));
        assertEquals(end, ended);
        assertFalse(state.anyHeld(), "the window resource outlived the answer");
    }

    @Test
    void theUnbuiltArgumentsAndAMissingOne() throws InterruptedException {
        hello();
        send(1, "window.measure", "{\"after\":\"now\",\"skipFrames\":3,\"frames\":10}");
        assertEquals(Errors.UNSUPPORTED, code(next()));
        send(2, "window.measure", "{\"after\":\"path\",\"skipSeconds\":1,\"seconds\":1}");
        assertEquals(Errors.UNSUPPORTED, code(next()));
        send(3, "window.measure", "{\"after\":\"now\",\"seconds\":1}");
        Map<String, Object> answer = next();
        assertEquals(Errors.BAD_REQUEST, code(answer));
        assertTrue(answer.toString().contains("missing argument skipSeconds"), answer.toString());
        send(4, "window.measure", "{\"after\":\"reload\",\"skipSeconds\":1,\"seconds\":1}");
        assertEquals(Errors.NOT_READY, code(next()));
        send(5, "window.measure", "{\"after\":\"now\",\"skipSeconds\":1,\"seconds\":0}");
        assertEquals(Errors.BAD_REQUEST, code(next()));
        assertFalse(state.anyHeld());
    }

    @Test
    void aWindowAndAMutationKeepEachOtherOut() throws Exception {
        hello();
        send(1, "window.measure", "{\"after\":\"now\",\"skipSeconds\":0,\"seconds\":100}");
        send(2, "command", "{\"text\":\"/tick freeze\",\"timeoutSeconds\":5}");
        Map<String, Object> answer = next();
        assertEquals(2L, id(answer));
        assertEquals(Errors.BUSY, code(answer));
        send(3, "window.measure", "{\"after\":\"now\",\"skipSeconds\":0,\"seconds\":1}");
        assertEquals(Errors.BUSY, code(next()));
        send(4, "cancel", "{\"id\":1}");
        List<Object> ids = List.of(id(next()), id(next()));
        assertTrue(ids.containsAll(List.of(1L, 4L)), ids.toString());
        long until = System.nanoTime() + 5 * SECOND;
        while (state.anyHeld() && System.nanoTime() < until) {
            Thread.sleep(5);
        }
        assertFalse(state.anyHeld(), "the cancelled window kept its resource");
        // A mutation still running keeps a window out until it ends.
        send(5, "ticks.step", "{\"n\":1,\"timeoutSeconds\":30}");
        send(6, "window.measure", "{\"after\":\"now\",\"skipSeconds\":0,\"seconds\":1}");
        answer = next();
        assertEquals(6L, id(answer));
        assertEquals(Errors.BUSY, code(answer));
        assertTrue(answer.toString().contains("ticks.step is running"), answer.toString());
        stepping.countDown();
        assertEquals(5L, id(next()));
    }

    @Test
    void aWindowAndACaptureKeepEachOtherOut() throws Exception {
        // commands.json `excludes`: PNG writes and readback stalls never land inside a window.
        hello();
        send(1, "frames.capture", "{\"directory\":\"d\",\"count\":3,\"timeoutSeconds\":30}");
        send(2, "window.measure", "{\"after\":\"now\",\"skipSeconds\":0,\"seconds\":1}");
        Map<String, Object> answer = next();
        assertEquals(2L, id(answer));
        assertEquals(Errors.BUSY, code(answer));
        assertTrue(answer.toString().contains("capture is in use"), answer.toString());
        capturing.countDown();
        assertEquals(1L, id(next()));
        send(3, "window.measure", "{\"after\":\"now\",\"skipSeconds\":0,\"seconds\":100}");
        send(4, "frames.capture", "{\"directory\":\"d\",\"count\":3,\"timeoutSeconds\":30}");
        answer = next();
        assertEquals(4L, id(answer));
        assertEquals(Errors.BUSY, code(answer));
        assertTrue(answer.toString().contains("window is in use"), answer.toString());
        send(5, "cancel", "{\"id\":3}");
        List<Object> ids = List.of(id(next()), id(next()));
        assertTrue(ids.containsAll(List.of(3L, 5L)), ids.toString());
    }

    @Test
    void aCancelledWindowTakesNoMoreFramesAndTheNextOneRuns() throws Exception {
        hello();
        send(1, "window.measure", "{\"after\":\"now\",\"skipSeconds\":0,\"seconds\":100}");
        List<Map<String, Object>> events = new ArrayList<>();
        long n = 1;
        long until = System.nanoTime() + 5 * SECOND;
        while (events.isEmpty() && System.nanoTime() < until) {
            frames(n, n, 0);
            n++;
            Map<String, Object> line = lines.poll(1, TimeUnit.MILLISECONDS);
            if (line != null) {
                events.add(line);
            }
        }
        assertEquals("window.start", events.get(0).get("event"));
        send(2, "cancel", "{\"id\":1}");
        Map<String, Object> first = next();
        Map<String, Object> second = next();
        Map<String, Object> cancelled = id(first).equals(1L) ? first : second;
        assertEquals(Errors.CANCELLED, code(cancelled));
        until = System.nanoTime() + 5 * SECOND;
        while (state.anyHeld() && System.nanoTime() < until) {
            Thread.sleep(5);
        }
        frames(n, n + 10, 0); // well inside its 100 s: no window.end
        assertNull(lines.poll(100, TimeUnit.MILLISECONDS));
        // The next window opens while the cancelled one's 100 s are still running: closed.
        send(3, "window.measure", "{\"after\":\"now\",\"skipSeconds\":0,\"seconds\":0.05}");
        events.clear();
        assertEquals(true, feedUntil(3L, n + 11, 0, events).get("ok"));
        assertEquals(2, events.size());
    }

    @Test
    void aFailedReloadDropsTheAnchorWithoutAFalseFailureLater() throws Exception {
        window.reloaded(stamp(10).qpcNs());
        frames(11, 20, 10);
        window.reloadFailed(); // Iris fell back: a new pipeline, its counter restarted
        assertEquals(Errors.NOT_READY,
            assertThrows(Errors.Refused.class, () -> window.open(true, 0, SECOND)).code());
        Window.Measure measure = window.open(false, 0, SECOND);
        frames(21, 25, 21); // sinceReload 0 after 10: the failed reload's restart, not a new one
        assertTrue(measure.started().isDone());
        assertFalse(measure.ended().isDone(), "the failed reload's restart failed a later window");
        window.close(measure);
    }
}
