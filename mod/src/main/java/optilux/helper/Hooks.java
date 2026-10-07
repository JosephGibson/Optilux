package optilux.helper;

import java.util.function.BooleanSupplier;
import java.util.function.Consumer;
import optilux.helper.core.FrameClock;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * The one door from the game's mixins into the mod: the frame clock the entrypoint opens with a
 * valid token, the game adapter's per-frame poll, and the input block the mixins ask about. Without
 * a token no mixin is applied, so nothing here runs.
 */
public final class Hooks {
    private static final Logger LOG = LoggerFactory.getLogger("optilux-helper");
    private static volatile FrameClock frames;
    private static volatile Runnable eachFrame = () -> { };
    private static volatile BooleanSupplier inputBlocked = () -> false;
    private static volatile Consumer<String> hookError = message -> { };
    // Render thread only: whether the last poll failed, so a run of failures reports once.
    private static boolean failing;

    private Hooks() {
    }

    static void open(FrameClock clock) {
        frames = clock;
    }

    /**
     * The game adapter: its poll at every frame head, the state owner's input block, and where a
     * failed poll is reported (the `hook.error` event).
     */
    static void attach(Runnable poll, BooleanSupplier blocked, Consumer<String> onError) {
        eachFrame = poll;
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
        try {
            eachFrame.run();
            failing = false;
        } catch (Throwable error) {
            // A frame hook never breaks the frame (docs/mod.md#4-architecture): the first failure
            // of a run is logged with its trace and sent as hook.error, so the session marks the
            // run invalid; the run ends at the next poll that passes.
            if (!failing) {
                failing = true;
                LOG.warn("optilux-helper: frame poll failed at frame {}", stamp.frameIndex(), error);
                hookError.accept("frame poll at frame " + stamp.frameIndex() + ": " + error);
            }
        }
    }

    /** Whether `input.block` holds: the input mixins cancel the game's handling while it does. */
    public static boolean inputBlocked() {
        return inputBlocked.getAsBoolean();
    }
}
