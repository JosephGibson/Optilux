package optilux.helper;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.Callable;
import java.util.concurrent.CompletableFuture;
import java.util.function.LongSupplier;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientLevelEvents;
import net.fabricmc.fabric.api.client.networking.v1.ClientPlayConnectionEvents;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents;
import net.minecraft.client.KeyMapping;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.Hud;
import net.minecraft.client.gui.screens.LevelLoadingScreen;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.commands.CommandSource;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.core.registries.Registries;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.Identifier;
import net.minecraft.resources.ResourceKey;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.ServerTickRateManager;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.server.permissions.LevelBasedPermissionSet;
import net.minecraft.world.level.Level;
import net.minecraft.world.phys.Vec3;
import optilux.helper.core.Errors;
import optilux.helper.core.Feedback;
import optilux.helper.core.Protocol;
import optilux.helper.core.State;
import optilux.helper.core.TickCounter;
import optilux.helper.core.TpSemantics;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * The MC 26.3 game adapter (docs/mod.md#4-architecture; targets in
 * docs/platform.md#mod-adapter-surface, each read in the pinned jar): `state`, `world.wait`,
 * `command`, `ticks.step`, `camera.place`, `camera.get`, `hud.set` and `input.block`, and the world,
 * dimension, focus and screen events. Game state is read and changed on its own thread: the render
 * thread through Minecraft.execute, the server thread through the integrated server's; the worker
 * waits. Work queued for a request that was answered first (timeout, cancel) skips its change and
 * logs skipped-late. Fabric's events give the join and leave, the level change and the server tick
 * end; the frame hook's poll gives focus, screens and the in-world frame count.
 */
final class GameAdapter {
    private static final Logger LOG = LoggerFactory.getLogger("optilux-helper");
    /**
     * world.wait answers at the second frame head in the world with no level-loading screen: the
     * frame between them rendered the world, and Iris builds its pipeline inside the first such
     * frame (3 s on Unbound; docs/gpu-iris.md#frame-counters-and-reload).
     */
    private static final int WORLD_FRAMES = 2;
    /** How often camera.place looks for the client's arrival. */
    private static final long ARRIVAL_POLL_MILLIS = 5;

    private final State state;
    private final LongSupplier qpcNs;
    private final TickCounter ticks = new TickCounter();
    private volatile Protocol protocol;

    // The world, as the render thread last saw it.
    private volatile boolean joined;
    private volatile long joinedQpcNs;
    private volatile UUID playerId;
    private CompletableFuture<Void> inWorld = new CompletableFuture<>(); // guarded by this
    // The frame poll's memory: render thread only.
    private int worldFrames;
    private String dimension;
    private Boolean focused;
    private Object shown;

    GameAdapter(State state, LongSupplier qpcNs) {
        this.state = state;
        this.qpcNs = qpcNs;
    }

    /** The commands this adapter answers. */
    Map<String, Protocol.Handler> handlers() {
        Map<String, Protocol.Handler> found = new LinkedHashMap<>();
        found.put("state", this::state);
        found.put("world.wait", this::worldWait);
        found.put("command", this::command);
        found.put("ticks.step", this::ticksStep);
        found.put("camera.place", this::cameraPlace);
        found.put("camera.get", this::cameraGet);
        found.put("input.block", this::inputBlock);
        found.put("hud.set", this::hudSet);
        return found;
    }

    /** Start listening to Fabric's events; events go to `protocol`. The session polls {@link #frame}. */
    void listen(Protocol protocol) {
        this.protocol = protocol;
        ClientPlayConnectionEvents.JOIN.register((listener, sender, client) -> joined());
        ClientPlayConnectionEvents.DISCONNECT.register((listener, client) -> left());
        ClientLevelEvents.AFTER_CLIENT_LEVEL_CHANGE.register((client, level) -> levelChanged(level));
        ServerTickEvents.END_SERVER_TICK.register(server -> ticks.tick(
            server.tickRateManager().runsNormally(), server.getTickCount()));
    }

    // Events and the frame poll (render thread).

    private void joined() {
        LocalPlayer player = minecraft().player;
        playerId = player == null ? null : player.getUUID();
        joinedQpcNs = qpcNs.getAsLong();
        worldFrames = 0;
        // The join's own dimension, so the first change after it is reported whether or not the
        // level-change event fired for the join itself.
        String at = dimensionOf(minecraft().level);
        if (at != null) {
            dimension = at;
        }
        joined = true;
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("dimension", dimensionOf(minecraft().level));
        event("world.joined", data);
    }

    private void left() {
        joined = false;
        playerId = null;
        dimension = null;
        synchronized (this) {
            if (inWorld.isDone()) {
                inWorld = new CompletableFuture<>(); // a pending world.wait waits for the next join
            }
        }
        ticks.reset("the world was left");
        event("world.left", Map.of());
        protocol.worldLeft();
    }

    private void levelChanged(ClientLevel level) {
        String to = dimensionOf(level);
        if (dimension != null && to != null && !dimension.equals(to)) {
            Map<String, Object> data = new LinkedHashMap<>();
            data.put("from", dimension);
            data.put("to", to);
            event("dimension.changed", data);
        }
        dimension = to;
    }

    /** At every frame head: focus and screen changes, and the frames rendered in the world. */
    void frame() {
        boolean active = minecraft().isWindowActive();
        if (focused != null && focused != active) {
            event(active ? "focus.gained" : "focus.lost", Map.of());
        }
        focused = active;
        Screen screen = minecraft().gui.screen();
        Object now = minecraft().gui.overlay() != null ? minecraft().gui.overlay() : screen;
        if (now != shown && now != null) {
            event("screen.opened", Map.of("screen", now.getClass().getName()));
        }
        shown = now;
        if (!joined) {
            return;
        }
        boolean inside = minecraft().level != null && minecraft().player != null
            && minecraft().gui.overlay() == null && !(screen instanceof LevelLoadingScreen);
        worldFrames = inside ? worldFrames + 1 : 0;
        if (worldFrames == WORLD_FRAMES) {
            synchronized (this) {
                inWorld.complete(null);
            }
        }
    }

    private void event(String name, Map<String, Object> data) {
        Protocol current = protocol;
        if (current != null) {
            current.event(name, data);
        }
    }

    // Commands (worker threads).

    private Map<String, Object> state(Protocol.Request request) throws Exception {
        return onRender(() -> {
            Map<String, Object> found = new LinkedHashMap<>();
            LocalPlayer player = minecraft().player;
            found.put("inWorld", inWorldNow());
            found.put("dimension", dimensionOf(minecraft().level));
            found.put("gamemode", player == null || minecraft().gameMode == null ? null
                : minecraft().gameMode.getPlayerMode().getName());
            Object open = minecraft().gui.overlay() != null ? minecraft().gui.overlay()
                : minecraft().gui.screen();
            found.put("screen", open == null ? null : open.getClass().getName());
            found.put("paused", minecraft().isPaused());
            found.put("focused", minecraft().isWindowActive());
            found.put("tick", ticks.lastTick());
            return found;
        });
    }

    private Map<String, Object> worldWait(Protocol.Request request) throws Exception {
        CompletableFuture<Void> ready;
        synchronized (this) {
            ready = inWorld;
        }
        ready.get(); // the request's timeoutSeconds interrupts the wait
        return onRender(() -> {
            if (!inWorldNow()) {
                throw new Errors.Refused(Errors.NOT_READY, "the world was left during the wait");
            }
            Map<String, Object> found = new LinkedHashMap<>();
            found.put("pose", pose(minecraft().player));
            found.put("time", minecraft().level.getOverworldClockTime());
            found.put("joinedQpcNs", joinedQpcNs);
            return found;
        });
    }

    private Map<String, Object> command(Protocol.Request request) throws Exception {
        String text = (String) request.args().get("text");
        MinecraftServer server = server();
        return onServer(server, () -> {
            if (skippedLate(request)) {
                return null;
            }
            return run(server, player(server), text).outcome();
        });
    }

    private Map<String, Object> ticksStep(Protocol.Request request) throws Exception {
        int n = Math.toIntExact((Long) request.args().get("n"));
        MinecraftServer server = server();
        CompletableFuture<Integer> stepped = onServer(server, () -> {
            if (skippedLate(request)) {
                return null;
            }
            ServerTickRateManager rate = server.tickRateManager();
            if (!rate.isFrozen()) {
                throw new Errors.Refused(Errors.FAILED,
                    "ticks are not frozen; fix: command /tick freeze first");
            }
            if (rate.isSteppingForward()) {
                throw new Errors.Refused(Errors.BUSY, "a tick step is running");
            }
            CompletableFuture<Integer> counted = ticks.await(n); // before the step: no tick slips by
            rate.stepGameIfPaused(n);
            return counted;
        });
        if (stepped == null) {
            return null;
        }
        try {
            return Map.of("ticks", unwrap(stepped));
        } catch (IllegalStateException left) {
            throw new Errors.Refused(Errors.FAILED, left.getMessage());
        } finally {
            ticks.cancel(stepped);
        }
    }

    private Map<String, Object> cameraPlace(Protocol.Request request) throws Exception {
        Map<String, Object> args = request.args();
        double x = (Double) args.get("x");
        double y = (Double) args.get("y");
        double z = (Double) args.get("z");
        double yaw = (Double) args.get("yaw");
        double pitch = (Double) args.get("pitch");
        TpSemantics.Pose target;
        if ((Boolean) args.get("tpSemantics")) {
            target = TpSemantics.apply(x, request.integerLiteral("x"), y, z,
                request.integerLiteral("z"), yaw, pitch);
        } else {
            if (!(pitch >= -90.0 && pitch <= 90.0)) {
                throw new Errors.Refused(Errors.BAD_REQUEST, "camera.place.pitch " + pitch
                    + " lies outside -90..90, where the game clamps it; fix: give it in range, or"
                    + " tpSemantics true for /tp's clamp");
            }
            target = new TpSemantics.Pose(x, y, z, (float) yaw, (float) pitch);
        }
        String wanted = (String) args.get("dimension");
        MinecraftServer server = server();
        long start = System.nanoTime();
        String arrival = onServer(server, () -> {
            if (skippedLate(request)) {
                return null;
            }
            ServerPlayer player = player(server);
            if (!player.isSpectator() && !player.getAbilities().flying) {
                // Gravity or a push would move the pose before the client is seen holding it.
                throw new Errors.Refused(Errors.NOT_READY, "camera.place needs a spectator or a"
                    + " flying player; fix: command /gamemode spectator");
            }
            ServerLevel level = wanted == null ? player.level() : level(server, wanted);
            String id = level.dimension().identifier().toString();
            if (player.level() != level) {
                // The dimension through /execute in <dim> run tp (docs/plans/m1.md 0.01.06); the
                // exact pose follows in this same server task.
                String text = "execute in " + id + " run tp @s "
                    + TpSemantics.literal(target.x()) + " " + TpSemantics.literal(target.y()) + " "
                    + TpSemantics.literal(target.z());
                Feedback feedback = run(server, player, text);
                if (!feedback.succeeded()) {
                    throw new Errors.Refused(Errors.FAILED, "/" + text + ": " + feedback.outcome());
                }
                player = player(server);
            }
            player.teleportTo(level, target.x(), target.y(), target.z(), Set.of(), target.yaw(),
                target.pitch(), true);
            return id;
        });
        if (arrival == null) {
            return null;
        }
        Map<String, Object> pose = arrive(request, arrival, target);
        if (pose == null) {
            return null;
        }
        Map<String, Object> found = new LinkedHashMap<>();
        found.put("pose", pose);
        found.put("arrivedSeconds", (System.nanoTime() - start) / 1e9);
        return found;
    }

    /**
     * Wait on the render thread until the client holds the pose, then give it the previous-tick
     * position and rotation too, so no frame interpolates from the old pose.
     */
    private Map<String, Object> arrive(Protocol.Request request, String id, TpSemantics.Pose target)
        throws Exception {
        while (true) {
            Map<String, Object> pose = onRender(() -> {
                if (!joined) {
                    throw new Errors.Refused(Errors.FAILED, "the world was left before arrival");
                }
                LocalPlayer player = minecraft().player;
                if (player == null || !id.equals(dimensionOf(minecraft().level))
                    || player.getX() != target.x() || player.getY() != target.y()
                    || player.getZ() != target.z() || player.getYRot() != target.yaw()
                    || player.getXRot() != target.pitch()) {
                    return null;
                }
                if (skippedLate(request)) {
                    return Map.of();
                }
                player.setOldPosAndRot();
                player.yHeadRot = player.yHeadRotO = player.yBodyRot = player.yBodyRotO =
                    player.getYRot();
                player.yBob = player.yBobO = player.getYRot();
                player.xBob = player.xBobO = player.getXRot();
                return pose(player);
            });
            if (pose != null) {
                return pose.isEmpty() ? null : pose;
            }
            Thread.sleep(ARRIVAL_POLL_MILLIS); // the request's timeoutSeconds interrupts
        }
    }

    private Map<String, Object> cameraGet(Protocol.Request request) throws Exception {
        return onRender(() -> {
            if (!inWorldNow()) {
                throw new Errors.Refused(Errors.NOT_READY, "not in a world; fix: world.wait first");
            }
            LocalPlayer player = minecraft().player;
            Vec3 eye = player.getEyePosition();
            Map<String, Object> found = new LinkedHashMap<>();
            found.put("pose", pose(player));
            found.put("eye", Map.of("x", eye.x, "y", eye.y, "z", eye.z));
            return found;
        });
    }

    private Map<String, Object> inputBlock(Protocol.Request request) throws Exception {
        boolean on = (Boolean) request.args().get("on");
        if (!state.blockInput(on, request::live)) {
            skippedLate(request); // answered (a disconnect, a cancel) before the change
            return null;
        }
        if (on) {
            // Keys held now would stay down: their release is blocked from here on.
            onRender(() -> {
                KeyMapping.releaseAll();
                return null;
            });
        }
        LOG.info("optilux-helper: input.block {}", on ? "on" : "off");
        return Map.of("on", state.inputBlocked());
    }

    private Map<String, Object> hudSet(Protocol.Request request) throws Exception {
        Boolean hide = (Boolean) request.args().get("hideGui");
        Boolean debug = (Boolean) request.args().get("debugOverlay");
        return onRender(() -> {
            Hud hud = minecraft().gui.hud;
            if (!skippedLate(request)) {
                if (hide != null && hud.isHidden() != hide) {
                    hud.toggle(); // F1's own path on 26.3 (Options.hideGui is gone)
                }
                if (debug != null) {
                    minecraft().debugEntries.setOverlayVisible(debug); // F3's flag
                }
            }
            Map<String, Object> found = new LinkedHashMap<>();
            found.put("hideGui", hud.isHidden());
            found.put("debugOverlay", minecraft().debugEntries.isOverlayVisible());
            return found;
        });
    }

    // Helpers.

    /** In a world with a level and a player (any thread; the render thread reads it exactly). */
    boolean inWorldNow() {
        return joined && minecraft().level != null && minecraft().player != null;
    }

    private MinecraftServer server() throws Errors.Refused {
        MinecraftServer server = minecraft().getSingleplayerServer();
        if (server == null || !joined) {
            throw new Errors.Refused(Errors.NOT_READY, "no world is open; fix: world.wait first");
        }
        return server;
    }

    private ServerPlayer player(MinecraftServer server) throws Errors.Refused {
        UUID id = playerId;
        ServerPlayer player = id == null ? null : server.getPlayerList().getPlayer(id);
        if (player == null) {
            throw new Errors.Refused(Errors.NOT_READY, "the player is not on the server");
        }
        return player;
    }

    private static ServerLevel level(MinecraftServer server, String name) throws Errors.Refused {
        Identifier id = Identifier.tryParse(name);
        ServerLevel level = id == null ? null
            : server.getLevel(ResourceKey.create(Registries.DIMENSION, id));
        if (level == null) {
            List<String> known = new ArrayList<>();
            for (ResourceKey<Level> key : server.levelKeys()) {
                known.add(key.identifier().toString());
            }
            throw new Errors.Refused(Errors.BAD_REQUEST, "camera.place.dimension " + name
                + " is no dimension of this world; it has " + String.join(", ", known));
        }
        return level;
    }

    /**
     * One command at OWNER on the server thread, as the player, its feedback collected: messages,
     * failures (sendFailure's red wrapper) and each context's result through the source's callback.
     */
    private static Feedback run(MinecraftServer server, ServerPlayer player, String text) {
        Feedback feedback = new Feedback();
        CommandSource collector = new CommandSource() {
            @Override
            public void sendSystemMessage(Component message) {
                String failure = CommandFeedback.failureText(message);
                if (failure != null) {
                    feedback.failure(failure);
                } else {
                    feedback.message(message.getString());
                }
            }

            @Override
            public boolean acceptsSuccess() {
                return true;
            }

            @Override
            public boolean acceptsFailure() {
                return true;
            }

            @Override
            public boolean shouldInformAdmins() {
                return false;
            }
        };
        CommandSourceStack source = player.createCommandSourceStack()
            .withSource(collector)
            .withPermission(LevelBasedPermissionSet.OWNER)
            .withCallback(feedback::result);
        server.getCommands().performPrefixedCommand(source, text);
        LOG.info("optilux-helper: command /{}: {}", text, feedback.outcome());
        return feedback;
    }

    private static Map<String, Object> pose(LocalPlayer player) {
        Map<String, Object> found = new LinkedHashMap<>();
        found.put("dimension", dimensionOf(player.level()));
        found.put("x", player.getX());
        found.put("y", player.getY());
        found.put("z", player.getZ());
        found.put("yaw", player.getYRot());
        found.put("pitch", player.getXRot());
        return found;
    }

    private static String dimensionOf(Level level) {
        return level == null ? null : level.dimension().identifier().toString();
    }

    private static boolean skippedLate(Protocol.Request request) {
        return Tasks.skippedLate(request);
    }

    private <T> T onRender(Callable<T> task) throws Exception {
        return Tasks.onRender(task);
    }

    private static Minecraft minecraft() {
        return Tasks.minecraft();
    }

    private static <T> T onServer(MinecraftServer server, Callable<T> task) throws Exception {
        return Tasks.on(server, task);
    }

    private static <T> T unwrap(CompletableFuture<T> future) throws Exception {
        return Tasks.unwrap(future);
    }
}
