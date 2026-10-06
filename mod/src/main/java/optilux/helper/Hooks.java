package optilux.helper;

import optilux.helper.core.FrameClock;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * The one door from the game's mixins into the mod: the frame clock the entrypoint opens with a
 * valid token. Without a token no mixin is applied, so nothing here runs.
 */
public final class Hooks {
    private static final Logger LOG = LoggerFactory.getLogger("optilux-helper");
    private static volatile FrameClock frames;

    private Hooks() {
    }

    static void open(FrameClock clock) {
        frames = clock;
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
    }
}
