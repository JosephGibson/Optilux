package optilux.helper;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.SynchronousQueue;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import net.fabricmc.loader.api.FabricLoader;
import net.fabricmc.loader.api.ModContainer;
import net.fabricmc.loader.api.metadata.CustomValue;
import net.minecraft.client.Minecraft;
import optilux.helper.core.Commands;
import optilux.helper.core.FrameClock;
import optilux.helper.core.PipeName;
import optilux.helper.core.Protocol;
import optilux.helper.core.State;
import optilux.helper.win.Kernel32;
import optilux.helper.win.PipeServer;
import optilux.helper.win.Qpc;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * The active mod's wiring (docs/mod.md#4-architecture): the command table from this mod's own
 * commands.json, the state owner, the protocol core with the built commands, the worker pool and
 * the timer thread, and the pipe server on its I/O thread. Built from the entrypoint only with a
 * valid token. hello's facts come from Fabric Loader, `quit` goes through Minecraft.stop on the
 * render thread (what the window's close button does: Window.shouldClose, then stop() in
 * Minecraft.runTick of 26.3), and the game adapter answers the rest and owns the world leave.
 */
final class Session {
    private static final Logger LOG = LoggerFactory.getLogger("optilux-helper");
    static final String MOD_ID = "optilux-helper";
    /** fabric.mod.json's custom value naming the platform the jar was built for. */
    static final String PLATFORM_KEY = "optilux:platform";
    static final String COMMANDS = "commands.json";
    // Workers beyond MAX_RUNNING serve `cancel`, which a full registry must still accept.
    private static final int WORKERS = Protocol.MAX_RUNNING + 8;
    private static final long WORKER_IDLE_SECONDS = 30;

    private final Protocol protocol;

    private Session(Protocol protocol) {
        this.protocol = protocol;
    }

    static Session start(String token, FrameClock clock, Qpc qpc) {
        ModContainer self = FabricLoader.getInstance().getModContainer(MOD_ID)
            .orElseThrow(() -> new IllegalStateException("no mod " + MOD_ID));
        Commands commands = Commands.parse(read(self, COMMANDS));
        ScheduledThreadPoolExecutor timers = new ScheduledThreadPoolExecutor(1, daemons("optilux-timer"));
        timers.setRemoveOnCancelPolicy(true);
        ThreadPoolExecutor workers = new ThreadPoolExecutor(0, WORKERS, WORKER_IDLE_SECONDS,
            TimeUnit.SECONDS, new SynchronousQueue<>(), daemons("optilux-worker"));
        State state = new State(timers, State.INPUT_RELEASE);
        Map<String, Object> facts = facts(self);
        GameAdapter game = new GameAdapter(state,
            () -> FrameClock.nanos(qpc.ticks(), qpc.frequency()));
        Map<String, Protocol.Handler> handlers = new LinkedHashMap<>(game.handlers());
        handlers.put("frames.index", request -> Map.of());
        handlers.put("quit", request -> {
            request.afterAnswer(() -> {
                LOG.info("optilux-helper: quit: stopping the game");
                Minecraft minecraft = Minecraft.getInstance();
                minecraft.execute(minecraft::stop);
            });
            return Map.of();
        });
        Protocol.Stamps stamps = new Protocol.Stamps() {
            @Override
            public long frameIndex() {
                return clock.last().frameIndex();
            }

            @Override
            public Long sinceReload() {
                return null; // the Iris adapter's SystemTimeUniforms.COUNTER, 0.01.07
            }

            @Override
            public long qpcNs() {
                return FrameClock.nanos(qpc.ticks(), qpc.frequency());
            }
        };
        Protocol protocol = new Protocol(commands, token, handlers, () -> facts, stamps, state,
            workers, timers);
        game.listen(protocol);
        state.onInputReleased(() -> LOG.info("optilux-helper: input.block released by the state owner"));
        String name = PipeName.of(token);
        PipeServer server = new PipeServer(name, protocol, Qpc.kernel32());
        Thread thread = new Thread(server, "optilux-pipe");
        thread.setDaemon(true);
        thread.start();
        LOG.info("optilux-helper: protocol {}, commands {}", commands.protocol(),
            String.join(", ", protocol.capabilities()));
        return new Session(protocol);
    }

    Protocol protocol() {
        return protocol;
    }

    /** hello's mod, platform, versions and pid; fixed for the game's life. */
    private static Map<String, Object> facts(ModContainer self) {
        FabricLoader loader = FabricLoader.getInstance();
        Map<String, Object> mod = new LinkedHashMap<>();
        mod.put("id", MOD_ID);
        mod.put("version", self.getMetadata().getVersion().getFriendlyString());
        CustomValue platform = self.getMetadata().getCustomValue(PLATFORM_KEY);
        Map<String, Object> versions = new LinkedHashMap<>();
        for (String[] pair : new String[][] {{"minecraft", "minecraft"},
            {"loader", "fabricloader"}, {"iris", "iris"}, {"sodium", "sodium"}}) {
            versions.put(pair[0], loader.getModContainer(pair[1])
                .map(container -> container.getMetadata().getVersion().getFriendlyString())
                .orElse(null));
        }
        versions.put("java", Runtime.version().toString());
        Map<String, Object> facts = new LinkedHashMap<>();
        facts.put("mod", mod);
        facts.put("platform", platform == null ? null : platform.getAsString());
        facts.put("versions", versions);
        facts.put("pid", ProcessHandle.current().pid());
        return facts;
    }

    /** A file from this mod's own jar, never another mod's resource of the same name. */
    private static String read(ModContainer self, String file) {
        Path path = self.findPath(file)
            .orElseThrow(() -> new IllegalStateException(MOD_ID + " holds no " + file));
        try {
            return Files.readString(path);
        } catch (IOException error) {
            throw new IllegalStateException("cannot read " + file + ": " + error, error);
        }
    }

    private static ThreadFactory daemons(String prefix) {
        AtomicInteger count = new AtomicInteger();
        return task -> {
            Thread thread = new Thread(task, prefix + "-" + count.incrementAndGet());
            thread.setDaemon(true);
            return thread;
        };
    }
}
