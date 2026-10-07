package optilux.helper.core;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.Supplier;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * The protocol core (docs/mod-protocol.md#envelope, docs/mod.md#4-architecture): the envelope with
 * strict JSON, the request registry, dispatch to a worker pool, coded errors, events after hello,
 * `cancel`, `busy` for the exclusive resources, and the hand-off to the state owner on a
 * disconnect or a world leave. The transport calls {@link #connected}, {@link #line},
 * {@link #refused} and {@link #disconnected} on its I/O thread; checks run there so a bad line is
 * answered at once and lines are judged in order, and every handler runs on a worker, so a long
 * request never blocks a short one. Exactly one answer leaves per request: the first of its
 * result, its timeout, a cancel, a disconnect or a world leave; a later one is dropped and logged.
 * Every answer is serialized before it counts as given, so a result without a JSON form becomes
 * `failed`; a resource is freed when its handler returns, or at once when it never ran.
 */
public final class Protocol {
    private static final Logger LOG = LoggerFactory.getLogger("optilux-helper");
    /** Requests running at once; more answer busy (docs/mod.md#5-safety: capped counts). */
    public static final int MAX_RUNNING = 32;
    static final Set<String> ENVELOPE = Set.of("id", "cmd", "args");
    static final String HELLO = "hello";
    static final String CANCEL = "cancel";

    /** The transport's write side; `after` runs once the line is written or dropped. */
    public interface Outbox {
        void send(String line, Runnable after);
    }

    /** The clocks every result and event carries at answer time. */
    public interface Stamps {
        long frameIndex();

        /** Null until the shader-loader adapter reads its counter. */
        Long sinceReload();

        long qpcNs();
    }

    /** A command's work: the result fields, or a coded refusal thrown. */
    @FunctionalInterface
    public interface Handler {
        Map<String, Object> run(Request request) throws Exception;
    }

    /** One request as a handler sees it. */
    public static final class Request {
        private final Object id;
        private final Commands.Command command;
        private final Map<String, Object> args;
        private final Map<?, ?> given;
        private final Connection connection;
        private final AtomicBoolean answered = new AtomicBoolean();
        // The worker running the handler, guarded by the request's lock: an early answer
        // interrupts it, never a FutureTask cancel, which would skip the handler and its release.
        private Thread worker;
        private volatile ScheduledFuture<?> timer;
        private volatile Runnable afterAnswer = () -> { };

        Request(Object id, Commands.Command command, Map<String, Object> args, Map<?, ?> given,
            Connection connection) {
            this.id = id;
            this.command = command;
            this.args = args;
            this.given = given;
            this.connection = connection;
        }

        public Object id() {
            return id;
        }

        public String command() {
            return command.name();
        }

        public Map<String, Object> args() {
            return args;
        }

        /** Whether an argument was written as an integer literal (`/tp` semantics read it). */
        public boolean integerLiteral(String name) {
            return given.get(name) instanceof Json.Num num && num.isInteger();
        }

        /**
         * False once the request was answered (timeout, cancel, disconnect, world leave): game work
         * queued for it then skips its mutation (docs/mod.md#4-architecture, skipped-late).
         */
        public boolean live() {
            return !answered.get();
        }

        /** Run `action` after this request's answer is written (quit stops the game after). */
        public void afterAnswer(Runnable action) {
            afterAnswer = action;
        }
    }

    static final class Connection {
        final Outbox outbox;
        volatile boolean authenticated;
        State.Resume resume;

        Connection(Outbox outbox) {
            this.outbox = outbox;
        }
    }

    private final Commands commands;
    private final byte[] token;
    private final Map<String, Handler> handlers;
    private final Supplier<Map<String, Object>> helloFacts;
    private final Stamps stamps;
    private final State state;
    private final ExecutorService workers;
    private final ScheduledExecutorService timers;
    private final Map<Object, Request> running = new HashMap<>();
    // Mutating requests whose handler has not ended, an early answer notwithstanding: no
    // measurement (an exclusive request) starts over one (docs/mod-protocol.md#envelope).
    private final Set<Request> mutations = new HashSet<>();
    private volatile Connection connection;

    /**
     * `handlers` holds the built commands besides hello and cancel, which the core answers;
     * `helloFacts` gives hello's mod, platform, versions and pid.
     */
    public Protocol(Commands commands, String token, Map<String, Handler> handlers,
        Supplier<Map<String, Object>> helloFacts, Stamps stamps, State state,
        ExecutorService workers, ScheduledExecutorService timers) {
        for (String name : handlers.keySet()) {
            if (commands.get(name) == null || name.equals(HELLO) || name.equals(CANCEL)) {
                throw new IllegalArgumentException("no handler may serve " + name);
            }
        }
        this.commands = commands;
        this.token = token.getBytes(StandardCharsets.UTF_8);
        this.handlers = Map.copyOf(handlers);
        this.helloFacts = helloFacts;
        this.stamps = stamps;
        this.state = state;
        this.workers = workers;
        this.timers = timers;
    }

    /** The commands this build answers, in the table's order; the rest answer unsupported. */
    public List<String> capabilities() {
        List<String> found = new ArrayList<>();
        for (String name : commands.all().keySet()) {
            if (name.equals(HELLO) || name.equals(CANCEL) || handlers.containsKey(name)) {
                found.add(name);
            }
        }
        return found;
    }

    public void connected(Outbox outbox) {
        connection = new Connection(outbox);
    }

    /**
     * The client left: its running requests are cancelled (their ids go to the state owner for
     * the next hello) and the state owner starts the input-block release.
     */
    public void disconnected() {
        Connection gone = connection;
        connection = null;
        if (gone == null) {
            return;
        }
        List<Request> mine = new ArrayList<>();
        synchronized (this) {
            for (Request request : running.values()) {
                if (request.connection == gone) {
                    mine.add(request);
                }
            }
        }
        List<Object> cancelled = new ArrayList<>();
        for (Request request : mine) {
            if (stop(request, Errors.CANCELLED, "the client disconnected")) {
                cancelled.add(request.id);
            }
        }
        // Resources held past a request (timers until timers.stop) stop with the client.
        for (Commands.Command command : commands.all().values()) {
            if (command.exclusiveUntil() != null) {
                state.release(command.exclusive());
            }
        }
        if (gone.authenticated) {
            state.disconnected(cancelled);
        }
        if (!cancelled.isEmpty()) {
            LOG.info("optilux-helper: disconnect cancelled requests {}", cancelled);
        }
    }

    /** The world was left: requests holding a resource fail, and the state owner resets. */
    public void worldLeft() {
        List<Request> holders = new ArrayList<>();
        synchronized (this) {
            for (Request request : running.values()) {
                if (request.command.exclusive() != null) {
                    holders.add(request);
                }
            }
        }
        for (Request request : holders) {
            stop(request, Errors.FAILED, "the world was left");
        }
        state.reset();
    }

    /** A framing refusal (line-too-long, bad-encoding): answered at once with id null. */
    public void refused(String code, String message) {
        Connection current = connection;
        if (current != null) {
            send(current, line(error(null, code, message)), null);
        }
    }

    /** Push an event; only an authenticated client receives events (after hello). */
    public void event(String name, Map<String, Object> data) {
        Connection current = connection;
        if (current == null || !current.authenticated) {
            return;
        }
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("event", name);
        body.put("data", data);
        stamp(body);
        String text;
        try {
            text = Json.write(body);
        } catch (IllegalArgumentException error) {
            LOG.warn("optilux-helper: event {} has no JSON form: {}", name, error.getMessage());
            return;
        }
        send(current, text, null);
    }

    @SuppressWarnings("unchecked")
    public void line(String text) {
        Connection current = connection;
        if (current == null) {
            return;
        }
        Object parsed;
        try {
            parsed = Json.parse(text);
        } catch (Json.Malformed error) {
            send(current, line(error(null, Errors.BAD_JSON, error.getMessage())), null);
            return;
        }
        if (!(parsed instanceof Map<?, ?>)) {
            send(current, line(error(null, Errors.BAD_REQUEST, "a request is a JSON object")),
                null);
            return;
        }
        Map<String, Object> request = (Map<String, Object>) parsed;
        Object id;
        try {
            if (!request.containsKey("id")) {
                throw new Errors.Refused(Errors.BAD_REQUEST, "the request has no id");
            }
            id = Commands.id(request.get("id"), "id");
        } catch (Errors.Refused refused) {
            send(current, line(error(null, refused.code(), refused.getMessage())), null);
            return;
        }
        try {
            for (String key : request.keySet()) {
                if (!ENVELOPE.contains(key)) {
                    throw new Errors.Refused(Errors.BAD_REQUEST, "unknown top-level field \"" + key
                        + "\"; a request holds id, cmd and args");
                }
            }
            if (!(request.get("cmd") instanceof String name)) {
                throw new Errors.Refused(Errors.BAD_REQUEST, "cmd must be a string");
            }
            if (!current.authenticated && !name.equals(HELLO)) {
                throw new Errors.Refused(Errors.UNAUTHENTICATED, "say hello with the token first");
            }
            Commands.Command command = commands.get(name);
            if (command == null) {
                throw new Errors.Refused(Errors.UNKNOWN_COMMAND, "no command " + name
                    + " (docs/mod-protocol.md#commands)");
            }
            Object written = request.containsKey("args") ? request.get("args") : Map.of();
            Map<String, Object> args = commands.check(command, written);
            if (name.equals(HELLO)) {
                byte[] given = ((String) args.get("token")).getBytes(StandardCharsets.UTF_8);
                if (!MessageDigest.isEqual(given, token)) {
                    throw new Errors.Refused(Errors.UNAUTHENTICATED, "the token does not match");
                }
                // Judged in line order: a request sent right after hello is authenticated.
                current.authenticated = true;
            }
            Handler handler = switch (name) {
                case HELLO -> this::hello;
                case CANCEL -> this::cancel;
                default -> handlers.get(name);
            };
            if (handler == null) {
                throw new Errors.Refused(Errors.UNSUPPORTED, name + " (phase " + command.phase()
                    + ") is not built in this mod; hello lists the capabilities");
            }
            dispatch(new Request(id, command, args, (Map<?, ?>) written, current), handler);
        } catch (Errors.Refused refused) {
            send(current, line(error(id, refused.code(), refused.getMessage())), null);
        }
    }

    private void dispatch(Request request, Handler handler) throws Errors.Refused {
        Commands.Command command = request.command;
        synchronized (this) {
            if (running.containsKey(request.id)) {
                throw new Errors.Refused(Errors.BAD_REQUEST, "id " + request.id
                    + " is in use by a running request");
            }
            if (!command.name().equals(CANCEL) && running.size() >= MAX_RUNNING) {
                throw new Errors.Refused(Errors.BUSY, MAX_RUNNING + " requests are running");
            }
            if (command.mutating() && state.anyHeld()) {
                throw new Errors.Refused(Errors.BUSY, String.join(", ", state.held().keySet())
                    + " active: no mutation lands inside a measurement");
            }
            if (command.exclusive() != null && !mutations.isEmpty()) {
                throw new Errors.Refused(Errors.BUSY, mutations.iterator().next().command()
                    + " is running: no measurement starts over a mutation");
            }
            if (command.exclusive() != null && !state.acquire(command.exclusive(), request)) {
                throw new Errors.Refused(Errors.BUSY, command.exclusive() + " is in use");
            }
            running.put(request.id, request);
            if (command.mutating()) {
                mutations.add(request);
            }
        }
        Object timeout = request.args.get("timeoutSeconds");
        if (timeout instanceof Double seconds) {
            request.timer = timers.schedule(
                () -> stop(request, Errors.TIMEOUT, "timeoutSeconds " + seconds + " expired"),
                (long) (seconds * 1e9), TimeUnit.NANOSECONDS);
        }
        try {
            workers.execute(() -> execute(request, handler));
        } catch (RejectedExecutionException error) {
            answer(request, error(request.id, Errors.BUSY, "no worker is free"));
            release(request, false);
            ended(request);
        }
    }

    private void execute(Request request, Handler handler) {
        boolean runs;
        synchronized (request) {
            runs = request.live();
            if (runs) {
                request.worker = Thread.currentThread();
            }
        }
        if (!runs) {
            release(request, false); // answered before it started: the handler never runs
            ended(request);
            return;
        }
        Map<String, Object> body;
        boolean ok = false;
        try {
            Map<String, Object> result = handler.run(request);
            Map<String, Object> fields = new LinkedHashMap<>(result == null ? Map.of() : result);
            stamp(fields);
            body = new LinkedHashMap<>();
            body.put("id", request.id);
            body.put("ok", true);
            body.put("result", fields);
            ok = true;
        } catch (Errors.Refused refused) {
            body = error(request.id, refused.code(), refused.getMessage());
        } catch (InterruptedException interrupted) {
            body = error(request.id, Errors.CANCELLED, "interrupted");
        } catch (Throwable thrown) {
            // An Error too: a coded answer, never a dead thread (docs/mod.md#4-architecture).
            LOG.warn("optilux-helper: {} failed", request.command(), thrown);
            body = error(request.id, Errors.FAILED, thrown.getClass().getSimpleName() + ": "
                + thrown.getMessage());
        } finally {
            synchronized (request) {
                request.worker = null;
                Thread.interrupted(); // an interrupt meant for this request ends with it
            }
            ended(request);
        }
        boolean holds = ok && request.command.exclusiveUntil() != null;
        if (!holds) {
            release(request, ok);
        }
        boolean delivered = answer(request, body);
        if (holds && !delivered) {
            release(request, false); // started, but the client was told it failed
        }
        if (!delivered) {
            LOG.info("optilux-helper: {} {} finished after its answer; result dropped",
                request.command(), request.id);
        }
    }

    /**
     * Free what the request holds (a resource held past the request only when `ok` is false);
     * a successful command also frees what it ends (timers.stop ends timers.start's).
     */
    private void release(Request request, boolean ok) {
        Commands.Command command = request.command;
        if (command.exclusive() != null && (command.exclusiveUntil() == null || !ok)) {
            state.release(command.exclusive(), request);
        }
        if (ok) {
            for (Commands.Command other : commands.all().values()) {
                if (command.name().equals(other.exclusiveUntil())) {
                    state.release(other.exclusive());
                }
            }
        }
    }

    /** The request's handler has ended (or never runs): a measurement may start over it now. */
    private synchronized void ended(Request request) {
        mutations.remove(request);
    }

    /** Answer early (timeout, cancel, disconnect, world leave) and interrupt a running handler. */
    private boolean stop(Request request, String code, String message) {
        boolean first = answer(request, error(request.id, code, message));
        if (first) {
            synchronized (request) {
                if (request.worker != null) {
                    request.worker.interrupt();
                }
            }
        }
        return first;
    }

    /** Give the request's one answer; false when it had one. */
    private boolean answer(Request request, Map<String, Object> body) {
        String text = line(body);
        if (!request.answered.compareAndSet(false, true)) {
            return false;
        }
        synchronized (this) {
            running.remove(request.id, request);
        }
        ScheduledFuture<?> timer = request.timer;
        if (timer != null) {
            timer.cancel(false);
        }
        send(request.connection, text, request.afterAnswer);
        return true;
    }

    /** The answer's line; a result with no JSON form (NaN, an unknown type) becomes failed. */
    private static String line(Map<String, Object> body) {
        try {
            return Json.write(body);
        } catch (IllegalArgumentException error) {
            return Json.write(error(body.get("id"), Errors.FAILED, "the result has no JSON form: "
                + error.getMessage()));
        }
    }

    private Map<String, Object> hello(Request request) {
        Connection current = request.connection;
        synchronized (current) {
            if (current.resume == null) {
                current.resume = state.hello();
            }
        }
        Map<String, Object> facts = helloFacts.get();
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("protocol", commands.protocol());
        result.put("mod", facts.get("mod"));
        result.put("platform", facts.get("platform"));
        result.put("versions", facts.get("versions"));
        result.put("capabilities", capabilities());
        result.put("pid", facts.get("pid"));
        result.put("resumed", current.resume.resumed());
        result.put("cancelled", current.resume.cancelled());
        return result;
    }

    private Map<String, Object> cancel(Request request) {
        Object target = request.args.get("id");
        Request found;
        synchronized (this) {
            found = running.get(target);
        }
        boolean cancelled = found != null && found != request
            && found.connection == request.connection
            && stop(found, Errors.CANCELLED, "cancelled by request " + request.id);
        return Map.of("cancelled", cancelled);
    }

    private void stamp(Map<String, Object> fields) {
        fields.put("frameIndex", stamps.frameIndex());
        fields.put("sinceReload", stamps.sinceReload());
        fields.put("qpcNs", stamps.qpcNs());
    }

    private static Map<String, Object> error(Object id, String code, String message) {
        Map<String, Object> detail = new LinkedHashMap<>();
        detail.put("code", code);
        detail.put("message", message == null ? code : message);
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("id", id);
        body.put("ok", false);
        body.put("error", detail);
        return body;
    }

    private static void send(Connection connection, String line, Runnable after) {
        connection.outbox.send(line, after == null ? () -> { } : after);
    }
}
