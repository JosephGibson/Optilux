package optilux.helper;

import net.fabricmc.api.ClientModInitializer;
import optilux.helper.core.FrameClock;
import optilux.helper.core.Token;
import optilux.helper.win.Qpc;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * The mod's one entrypoint. Without a valid -Doptilux.token it logs why and starts nothing
 * (docs/mod.md#5-safety); with one it opens the frame clock for the frame hook.
 */
public final class HelperClient implements ClientModInitializer {
    private static final Logger LOG = LoggerFactory.getLogger("optilux-helper");

    @Override
    public void onInitializeClient() {
        String problem = Token.problem(System.getProperty(Token.PROPERTY));
        if (problem != null) {
            LOG.info("optilux-helper: inert ({}): no pipe, no thread, no mixin", problem);
            return;
        }
        Qpc qpc = Qpc.load();
        Hooks.open(new FrameClock(qpc::ticks, qpc.frequency()));
        LOG.info("optilux-helper: active: frame clock on QueryPerformanceCounter at {} Hz",
            qpc.frequency());
    }
}
