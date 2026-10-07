package optilux.helper;

import java.util.List;
import java.util.function.BooleanSupplier;
import java.util.function.Consumer;
import optilux.helper.core.FrameClock;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * The one door from the game's mixins into the mod: the frame clock the entrypoint opens with a
 * valid token, the adapters' per-frame polls, the capture point, the swap's return, Iris's load
 * failure, and the input block the mixins ask about. Without a token no mixin is applied, so
 * nothing here runs.
 */
public final class Hooks {
    private static final Logger LOG = LoggerFactory.getLogger("optilux-helper");

    /** One adapter's poll at every frame head, run apart from the others. */
    record Poll(String name, Runnable run) {
    }

    // The polls and, render thread only, whether each one's last run failed, so a run of
    // failures reports once per poll.
    private record Polls(List<Poll> polls, boolean[] failing) {
    }

    private static volatile FrameClock frames;
    private static volatile Polls eachFrame = new Polls(List.of(), new boolean[0]);
    private static volatile Runnable capture = () -> { };
    private static volatile Consumer<Exception> irisFailure = error -> { };
    private static volatile BooleanSupplier inputBlocked = () -> false;
    private static volatile Consumer<String> hookError = message -> { };
    // Render thread only: whether the last capture point failed.
    private static boolean captureFailing;

    private Hooks() {
    }

    static void open(FrameClock clock) {
        frames = clock;
    }

    /**
     * The adapters: their polls at every frame head, the capture point, Iris's load failure, the
     * state owner's input block, and where a failed hook is reported (the `hook.error` event).
     */
    static void attach(List<Poll> polls, Runnable capturePoint, Consumer<Exception> onIrisFailure,
        BooleanSupplier blocked, Consumer<String> onError) {
        eachFrame = new Polls(List.copyOf(polls), new boolean[polls.size()]);
        capture = capturePoint;
        irisFailure = onIrisFailure;
        inputBlocked = blocked;
        hookError = onError;
    }

    /** GameRenderer.render HEAD, once per frame on the render thread. */
    public static void frameHead() {
        FrameClock clock = frames;
        if (clock == null) {
            return;
        }
        FrameClock.Stamp stamp = clock.head();
        if (stamp.frameIndex() == 1) {
            LOG.info("optilux-helper: frame hook: frame 1 at qpcNs {}", stamp.qpcNs());
        }
        Polls current = eachFrame;
        for (int i = 0; i < current.polls().size(); i++) {
            Poll poll = current.polls().get(i);
            try {
                poll.run().run();
                current.failing()[i] = false;
            } catch (Throwable error) {
                // A frame hook never breaks the frame (docs/mod.md#4-architecture), and one
                // adapter's failure never stops another's poll: the first failure of a run is
                // logged with its trace and sent as hook.error, so the session marks the run
                // invalid; the run ends at the next poll that passes.
                if (!current.failing()[i]) {
                    current.failing()[i] = true;
                    report("frame poll " + poll.name(), stamp.frameIndex(), error);
                }
            }
        }
    }

    /** After the world and its post effects, before the GUI (GameRenderer.render, in a level). */
    public static void capturePoint() {
        FrameClock clock = frames;
        if (clock == null) {
            return;
        }
        try {
            capture.run();
            captureFailing = false;
        } catch (Throwable error) {
            if (!captureFailing) {
                captureFailing = true;
                report("capture point", clock.last().frameIndex(), error);
            }
        }
    }

    /** The swap returned (Minecraft.renderFrame, after GpuSurface.present). */
    public static void swapped() {
        FrameClock clock = frames;
        if (clock != null) {
            clock.swapped();
        }
    }

    /** Iris.handleException HEAD: a shader pack failed to load. */
    public static void irisFailed(Exception error) {
        if (frames != null) {
            irisFailure.accept(error);
        }
    }

    /** Whether `input.block` holds: the input mixins cancel the game's handling while it does. */
    public static boolean inputBlocked() {
        return inputBlocked.getAsBoolean();
    }

    private static void report(String where, long frameIndex, Throwable error) {
        LOG.warn("optilux-helper: {} failed at frame {}", where, frameIndex, error);
        hookError.accept(where + " at frame " + frameIndex + ": " + error);
    }
}
