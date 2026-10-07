package optilux.helper;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import optilux.helper.core.Errors;
import optilux.helper.core.Json;
import optilux.helper.core.Protocol;
import optilux.helper.core.State;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

/**
 * The protocol core against docs/mod-protocol.md#envelope and #errors, with handlers under real
 * command names: every answer is checked against commands.json as it arrives (Wire.check).
 */
class ProtocolTest {
    static final String TOKEN = "T".repeat(43);
    static final Map<String, Object> FACTS = Map.of(
        "mod", Map.of("id", "optilux-helper", "version", "0.1.0"),
        "platform", "mc-26.3",
        "versions", Map.of("minecraft", "26.3"),
        "pid", 4242L);

    private final LinkedBlockingQueue<Map<String, Object>> answers = new LinkedBlockingQueue<>();
    private final Map<Object, String> sentCommands = Collections.synchronizedMap(new HashMap<>());
    private final List<String> order = Collections.synchronizedList(new ArrayList<>());
    private final AtomicLong frames = new AtomicLong(100);
    private final AtomicInteger generation = new AtomicInteger();
    private final CountDownLatch release = new CountDownLatch(1);
    private final AtomicBoolean waitInterrupted = new AtomicBoolean();
    private final AtomicBoolean waitLiveAfter = new AtomicBoolean(true);
    private final CountDownLatch waitEnded = new CountDownLatch(1);
    private ExecutorService workers;
    private ScheduledExecutorService timers;
    private State state;
    private Protocol protocol;
    private final Map<String, Protocol.Handler> handlers = new LinkedHashMap<>();
    private Protocol.Stamps stamps;

    @BeforeEach
    void start() {
        workers = Executors.newCachedThreadPool();
        timers = Executors.newSingleThreadScheduledExecutor();
        state = new State(timers, Duration.ofMillis(300));
        handlers.put("frames.index", request -> Map.of());
        handlers.put("shaders.options", request -> Map.of("pack", "x", "values", Double.NaN));
        handlers.put("world.wait", request -> {
            try {
                release.await();
            } catch (InterruptedException interrupted) {
                waitInterrupted.set(true);
                throw interrupted;
            } finally {
                waitLiveAfter.set(request.live());
                waitEnded.countDown();
            }
            return Map.of("pose", Map.of(), "time", 0, "joinedQpcNs", 0);
        });
        handlers.put("frames.capture", request -> {
            release.await();
            return Map.of("frames", List.of(), "dropped", List.of(), "manifest", "capture.json");
        });
        handlers.put("camera.place", request -> Map.of("pose", Map.of(
            "xInteger", request.integerLiteral("x"), "zInteger", request.integerLiteral("z"),
            "yInteger", request.integerLiteral("y")), "arrivedSeconds", 0.0));
        handlers.put("command", request -> Map.of("succeeded", true, "messages", List.of(),
            "failures", List.of()));
        handlers.put("timers.start", request -> Map.of("on", true));
        handlers.put("timers.stop", request -> Map.of("frames", List.of()));
        handlers.put("selftest", request -> {
            throw new AssertionError("an Error inside a handler");
        });
        handlers.put("quit", request -> {
            request.afterAnswer(() -> order.add("stopped"));
            return Map.of();
        });
        stamps = new Protocol.Stamps() {
            @Override
            public long frameIndex() {
                return frames.get();
            }

            @Override
            public Long sinceReload() {
                return null;
            }

            @Override
            public long qpcNs() {
                return 123_456_789L;
            }
        };
        protocol = new Protocol(Wire.COMMANDS, TOKEN, handlers, () -> FACTS, stamps, state, workers,
            timers);
        connect();
    }

    @AfterEach
    void stop() {
        release.countDown();
        workers.shutdownNow();
        timers.shutdownNow();
    }

    /** A transport drops the lines of a connection that is gone, as the pipe server does. */
    private void connect() {
        int mine = generation.incrementAndGet();
        protocol.connected((line, after) -> {
            if (generation.get() != mine) {
                after.run();
                return;
            }
            Map<String, Object> answer = Wire.parse(line);
            order.add(line);
            if (answer.containsKey("id")) {
                Wire.check(sentCommands.getOrDefault(answer.get("id") == null ? "" : answer.get("id").toString(),
                    "hello"), answer);
            }
            answers.add(answer);
            after.run();
        });
    }

    private void disconnect() {
        generation.incrementAndGet();
        protocol.disconnected();
    }

    private void send(Object id, String command, String args) {
        sentCommands.put(id.toString(), command);
        String idJson = id instanceof String text ? "\"" + text + "\"" : id.toString();
        protocol.line("{\"id\":" + idJson + ",\"cmd\":\"" + command + "\",\"args\":" + args + "}");
    }

    private Map<String, Object> next() throws InterruptedException {
        Map<String, Object> answer = answers.poll(5, TimeUnit.SECONDS);
        assertNotNull(answer, "no answer within 5 s");
        return answer;
    }

    @SuppressWarnings("unchecked")
    private static String code(Map<String, Object> answer) {
        assertEquals(false, answer.get("ok"), "expected an error: " + answer);
        return (String) ((Map<String, Object>) answer.get("error")).get("code");
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> result(Map<String, Object> answer) {
        assertEquals(true, answer.get("ok"), "expected a result: " + answer);
        return (Map<String, Object>) answer.get("result");
    }

    private Map<String, Object> hello() throws InterruptedException {
        send("h", "hello", "{\"token\":\"" + TOKEN + "\"}");
        return result(next());
    }

    private static Object id(Map<String, Object> answer) {
        Object id = answer.get("id");
        return id instanceof Json.Num num ? num.longValue() : id;
    }

    @Test
    void helloFirstAndWithTheToken() throws InterruptedException {
        send(1, "frames.index", "{}");
        assertEquals(Errors.UNAUTHENTICATED, code(next()));
        send(2, "hello", "{\"token\":\"" + "U".repeat(43) + "\"}");
        assertEquals(Errors.UNAUTHENTICATED, code(next()));
        send(3, "hello", "{\"token\":\"short\"}");
        assertEquals(Errors.BAD_REQUEST, code(next()));
        Map<String, Object> hello = hello();
        assertEquals("1", hello.get("protocol").toString());
        assertEquals("mc-26.3", hello.get("platform"));
        assertEquals("4242", hello.get("pid").toString());
        assertEquals(false, hello.get("resumed"));
        assertEquals(List.of(), hello.get("cancelled"));
        assertEquals(List.of("hello", "selftest", "world.wait", "command", "camera.place",
            "shaders.options",
            "frames.index", "frames.capture", "timers.start", "timers.stop", "cancel", "quit"),
            hello.get("capabilities"));
        assertNull(hello.get("sinceReload"));
        assertEquals("100", hello.get("frameIndex").toString());
        assertEquals("123456789", hello.get("qpcNs").toString());
        // A request right behind hello is judged after it, in line order.
        send("h2", "hello", "{\"token\":\"" + TOKEN + "\"}");
        send(4, "frames.index", "{}");
        List<Object> ids = new ArrayList<>(List.of(id(next()), id(next())));
        Collections.sort(ids, (a, b) -> a.toString().compareTo(b.toString()));
        assertEquals(List.of(4L, "h2"), ids);
    }

    @Test
    void envelopeAndCodedErrorsAnsweredAtOnce() throws InterruptedException {
        hello();
        protocol.line("{\"id\":1,\"cmd\":\"frames.index\"");
        Map<String, Object> answer = next();
        assertNull(answer.get("id"));
        assertEquals(Errors.BAD_JSON, code(answer));
        protocol.line("{'id':1}");
        assertEquals(Errors.BAD_JSON, code(next()));
        protocol.line("{\"id\":1,\"id\":2,\"cmd\":\"frames.index\"}");
        assertEquals(Errors.BAD_JSON, code(next()));
        protocol.line("[1]");
        assertEquals(Errors.BAD_REQUEST, code(next()));
        for (String id : new String[] {"1.5", "\"\"", "\"" + "x".repeat(65) + "\"", "true", "null"}) {
            protocol.line("{\"id\":" + id + ",\"cmd\":\"frames.index\"}");
            answer = next();
            assertNull(answer.get("id"), id);
            assertEquals(Errors.BAD_REQUEST, code(answer), id);
        }
        protocol.line("{\"cmd\":\"frames.index\"}");
        assertEquals(Errors.BAD_REQUEST, code(next()));
        protocol.line("{\"id\":7,\"cmd\":\"frames.index\",\"args\":{},\"extra\":1}");
        answer = next();
        assertEquals(7L, id(answer));
        assertEquals(Errors.BAD_REQUEST, code(answer));
        protocol.line("{\"id\":8,\"cmd\":3}");
        assertEquals(Errors.BAD_REQUEST, code(next()));
        send(9, "camera.spin", "{}");
        assertEquals(Errors.UNKNOWN_COMMAND, code(next()));
        send(10, "camera.get", "{}");
        assertEquals(Errors.UNSUPPORTED, code(next()));
        send(11, "frames.index", "{\"x\":1}");
        assertEquals(Errors.BAD_REQUEST, code(next()));
        send(12, "command", "{\"text\":\"/time set day\"}");
        assertEquals(Errors.BAD_REQUEST, code(next()));
        send(13, "command", "{\"text\":5,\"timeoutSeconds\":1}");
        assertEquals(Errors.BAD_REQUEST, code(next()));
        send(14, "command", "{\"text\":\"/tick freeze\",\"timeoutSeconds\":0}");
        assertEquals(Errors.BAD_REQUEST, code(next()));
        send(15, "frames.capture", "{\"directory\":\"d\",\"count\":4097,\"timeoutSeconds\":1}");
        assertEquals(Errors.BAD_REQUEST, code(next()));
        send(16, "frames.capture", "{\"directory\":\"d\",\"count\":1.0,\"timeoutSeconds\":1}");
        assertEquals(Errors.BAD_REQUEST, code(next()));
        protocol.refused(Errors.LINE_TOO_LONG, "line 1 passed 1048576 bytes");
        answer = next();
        assertNull(answer.get("id"));
        assertEquals(Errors.LINE_TOO_LONG, code(answer));
        send("ok", "frames.index", "{}");
        assertEquals("ok", id(next()));
    }

    @Test
    void twoConcurrentRequestsAnsweredOutOfOrder() throws InterruptedException {
        hello();
        send(1, "world.wait", "{\"timeoutSeconds\":30}");
        send(2, "frames.index", "{}");
        assertEquals(2L, id(next()));
        release.countDown();
        Map<String, Object> waited = next();
        assertEquals(1L, id(waited));
        assertEquals(true, waited.get("ok"));
    }

    @Test
    void cancelAnswersTheRequestOnceAndInterruptsIt() throws InterruptedException {
        hello();
        send(1, "world.wait", "{\"timeoutSeconds\":30}");
        send(1, "frames.index", "{}");
        assertEquals(Errors.BAD_REQUEST, code(next()));
        send(2, "cancel", "{\"id\":1}");
        Map<String, Object> first = next();
        Map<String, Object> second = next();
        Map<String, Object> cancelled = id(first).equals(1L) ? first : second;
        Map<String, Object> cancel = id(first).equals(1L) ? second : first;
        assertEquals(Errors.CANCELLED, code(cancelled));
        assertEquals(true, result(cancel).get("cancelled"));
        assertTrue(waitEnded.await(5, TimeUnit.SECONDS));
        assertTrue(waitInterrupted.get());
        assertFalse(waitLiveAfter.get());
        send(3, "cancel", "{\"id\":1}");
        assertEquals(false, result(next()).get("cancelled"));
        send(4, "cancel", "{\"id\":\"nothing\"}");
        assertEquals(false, result(next()).get("cancelled"));
        send(5, "frames.index", "{}");
        assertEquals(5L, id(next()));
        assertNull(answers.poll(200, TimeUnit.MILLISECONDS), "a second answer for request 1");
    }

    @Test
    void theRequestsOwnTimeout() throws InterruptedException {
        hello();
        send(1, "world.wait", "{\"timeoutSeconds\":0.05}");
        Map<String, Object> answer = next();
        assertEquals(1L, id(answer));
        assertEquals(Errors.TIMEOUT, code(answer));
        assertTrue(waitEnded.await(5, TimeUnit.SECONDS));
        assertFalse(waitLiveAfter.get(), "the handler still saw the request live");
    }

    @Test
    void exclusiveResourcesAnswerBusy() throws InterruptedException {
        hello();
        send(1, "frames.capture", "{\"directory\":\"d\",\"count\":3,\"timeoutSeconds\":30}");
        send(2, "frames.capture", "{\"directory\":\"d\",\"count\":3,\"timeoutSeconds\":30}");
        assertEquals(Errors.BUSY, code(next()));
        send(3, "command", "{\"text\":\"/tick freeze\",\"timeoutSeconds\":5}");
        assertEquals(Errors.BUSY, code(next()));
        send(4, "frames.index", "{}");
        assertEquals(4L, id(next()));
        release.countDown();
        assertEquals(1L, id(next()));
        send(5, "command", "{\"text\":\"/tick freeze\",\"timeoutSeconds\":5}");
        assertEquals(true, next().get("ok"));
        // timers hold their resource past the start's answer, until timers.stop.
        send(6, "timers.start", "{}");
        assertEquals(true, next().get("ok"));
        send(7, "command", "{\"text\":\"/tick freeze\",\"timeoutSeconds\":5}");
        assertEquals(Errors.BUSY, code(next()));
        send(8, "timers.stop", "{}");
        assertEquals(true, next().get("ok"));
        send(9, "command", "{\"text\":\"/tick freeze\",\"timeoutSeconds\":5}");
        assertEquals(true, next().get("ok"));
    }

    @Test
    @SuppressWarnings("unchecked")
    void aHandlerTellsAnIntegerLiteralFromADecimal() throws InterruptedException {
        hello();
        send(1, "camera.place", "{\"x\":10,\"y\":64,\"z\":10.0,\"yaw\":0,\"pitch\":0,"
            + "\"timeoutSeconds\":5}");
        Map<String, Object> pose = (Map<String, Object>) result(next()).get("pose");
        assertEquals(Map.of("xInteger", true, "yInteger", true, "zInteger", false), pose);
        send(2, "camera.place", "{\"x\":1e1,\"y\":-0.5,\"z\":-3,\"yaw\":0,\"pitch\":0,"
            + "\"timeoutSeconds\":5}");
        pose = (Map<String, Object>) result(next()).get("pose");
        assertEquals(Map.of("xInteger", false, "yInteger", false, "zInteger", true), pose);
    }

    @Test
    void theInputBlockChangesOnlyWhileItsRequestIsLive() {
        assertFalse(state.blockInput(true, () -> false));
        assertFalse(state.inputBlocked());
        assertTrue(state.blockInput(true, () -> true));
        assertTrue(state.inputBlocked());
    }

    @Test
    void anErrorInAHandlerIsACodedAnswer() throws InterruptedException {
        hello();
        send(1, "selftest", "{}");
        Map<String, Object> answer = next();
        assertEquals(Errors.FAILED, code(answer));
        send(2, "frames.index", "{}");
        assertEquals(true, next().get("ok"));
    }

    @Test
    void eventsOnlyAfterHello() throws InterruptedException {
        protocol.event("world.left", Map.of());
        assertNull(answers.poll(100, TimeUnit.MILLISECONDS));
        hello();
        frames.set(250);
        protocol.event("world.left", Map.of("reason", "test"));
        Map<String, Object> event = next();
        assertEquals("world.left", event.get("event"));
        assertEquals(Map.of("reason", "test"), event.get("data"));
        assertEquals("250", event.get("frameIndex").toString());
        assertTrue(event.containsKey("sinceReload") && event.containsKey("qpcNs"));
        assertFalse(event.containsKey("id"));
    }

    @Test
    void quitStopsOnlyAfterItsAnswer() throws InterruptedException {
        hello();
        order.clear();
        send(1, "quit", "{}");
        assertEquals(true, next().get("ok"));
        assertEquals(2, order.size());
        assertTrue(order.get(0).startsWith("{\"id\":1,\"ok\":true"));
        assertEquals("stopped", order.get(1));
    }

    @Test
    void theWorldLeaveResetsTheState() throws InterruptedException {
        AtomicBoolean released = new AtomicBoolean();
        state.onInputReleased(() -> released.set(true));
        hello();
        state.blockInput(true);
        send(1, "frames.capture", "{\"directory\":\"d\",\"count\":3,\"timeoutSeconds\":30}");
        send(2, "world.wait", "{\"timeoutSeconds\":30}");
        assertTrue(state.anyHeld());
        protocol.worldLeft();
        Map<String, Object> answer = next();
        assertEquals(1L, id(answer));
        assertEquals(Errors.FAILED, code(answer));
        assertFalse(state.anyHeld());
        assertFalse(state.inputBlocked());
        assertTrue(released.get());
        send(3, "command", "{\"text\":\"/tick freeze\",\"timeoutSeconds\":5}");
        assertEquals(3L, id(next()));
        release.countDown();
        assertEquals(2L, id(next()), "a request holding nothing survives the leave");
    }

    @Test
    void aDisconnectCancelsWorkAndAReconnectIsResumed() throws InterruptedException {
        AtomicBoolean released = new AtomicBoolean();
        state.onInputReleased(() -> released.set(true));
        hello();
        state.blockInput(true);
        send(1, "world.wait", "{\"timeoutSeconds\":30}");
        send("two", "frames.capture", "{\"directory\":\"d\",\"count\":3,\"timeoutSeconds\":30}");
        disconnect();
        assertTrue(waitEnded.await(5, TimeUnit.SECONDS));
        assertTrue(waitInterrupted.get());
        connect();
        send(3, "frames.index", "{}");
        assertEquals(Errors.UNAUTHENTICATED, code(next()), "a new connection says hello again");
        Map<String, Object> hello = hello();
        assertEquals(true, hello.get("resumed"));
        List<Object> cancelled = new ArrayList<>();
        for (Object item : (List<?>) hello.get("cancelled")) {
            cancelled.add(item instanceof Json.Num num ? num.longValue() : item);
        }
        Collections.sort(cancelled, (a, b) -> a.toString().compareTo(b.toString()));
        assertEquals(List.of(1L, "two"), cancelled);
        // The hello came within the release delay: the input block stays.
        Thread.sleep(500);
        assertTrue(state.inputBlocked());
        assertFalse(released.get());
        // Without a hello after the next disconnect, it is released after the delay.
        disconnect();
        long began = System.nanoTime();
        while (!released.get() && System.nanoTime() - began < 5_000_000_000L) {
            Thread.sleep(10);
        }
        assertTrue(released.get());
        assertFalse(state.inputBlocked());
        assertTrue((System.nanoTime() - began) / 1e6 >= 250, "released before the delay");
    }

    @Test
    void theRunningCountIsCapped() throws InterruptedException {
        hello();
        for (int i = 0; i < Protocol.MAX_RUNNING; i++) {
            send(100 + i, "world.wait", "{\"timeoutSeconds\":30}");
        }
        send(1, "frames.index", "{}");
        assertEquals(Errors.BUSY, code(next()));
        send(2, "cancel", "{\"id\":100}");
        List<Object> ids = List.of(id(next()), id(next()));
        assertTrue(ids.contains(100L) && ids.contains(2L), ids.toString());
    }

    @Test
    void aResultWithNoJsonFormIsAFailedAnswer() throws InterruptedException {
        hello();
        send(1, "shaders.options", "{}");
        Map<String, Object> answer = next();
        assertEquals(Errors.FAILED, code(answer));
        assertTrue(((Map<?, ?>) answer.get("error")).get("message").toString()
            .startsWith("the result has no JSON form"));
        protocol.event("world.left", Map.of("bad", Double.NaN));
        send(2, "frames.index", "{}");
        assertEquals(2L, id(next()), "an event with no JSON form is dropped, nothing thrown");
    }

    @Test
    void aRequestStoppedBeforeItsWorkerStartsFreesItsResource() throws InterruptedException {
        // One worker, busy: the capture is accepted (its resource taken) but cannot start.
        java.util.concurrent.ThreadPoolExecutor one = new java.util.concurrent.ThreadPoolExecutor(
            1, 1, 0, TimeUnit.SECONDS, new LinkedBlockingQueue<>());
        CountDownLatch gate = new CountDownLatch(1);
        one.execute(() -> {
            try {
                gate.await();
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            }
        });
        protocol = new Protocol(Wire.COMMANDS, TOKEN, handlers, () -> FACTS, stamps, state, one,
            timers);
        connect();
        send("h", "hello", "{\"token\":\"" + TOKEN + "\"}");
        send(1, "frames.capture", "{\"directory\":\"d\",\"count\":3,\"timeoutSeconds\":0.05}");
        Map<String, Object> answer = next();
        assertEquals(1L, id(answer));
        assertEquals(Errors.TIMEOUT, code(answer));
        assertTrue(state.anyHeld(), "held until its task runs");
        gate.countDown();
        assertEquals("h", id(next()));
        long until = System.nanoTime() + 5_000_000_000L;
        while (state.anyHeld() && System.nanoTime() < until) {
            Thread.sleep(5);
        }
        assertFalse(state.anyHeld(), "the capture was never freed");
        one.shutdownNow();
    }

    @Test
    void timersHeldPastTheirStartStopWithTheClient() throws InterruptedException {
        hello();
        send(1, "timers.start", "{}");
        assertEquals(true, next().get("ok"));
        assertTrue(state.anyHeld());
        disconnect();
        assertFalse(state.anyHeld());
    }
}
