package optilux.helper;

import net.fabricmc.api.ClientModInitializer;
import optilux.helper.core.FrameClock;
import optilux.helper.core.Token;
import optilux.helper.win.Qpc;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * The mod's one entrypoint. Without a valid -Doptilux.token it logs why and starts nothing
 * (docs/mod.md#5-safety); with one it opens the frame clock for the frame hook and starts the
 * session: the protocol and the pipe server on its own thread.
 */
public final class HelperClient implements ClientModInitializer {
    private static final Logger LOG = LoggerFactory.getLogger("optilux-helper");
    private Session session;

    @Override
    public void onInitializeClient() {
        String token = System.getProperty(Token.PROPERTY);
        String problem = Token.problem(token);
        if (problem != null) {
            LOG.info("optilux-helper: inert ({}): no pipe, no thread, no mixin", problem);
            return;
        }
        Qpc qpc = Qpc.load();
        FrameClock clock = new FrameClock(qpc::ticks, qpc.frequency());
        Hooks.open(clock);
        LOG.info("optilux-helper: active: frame clock on QueryPerformanceCounter at {} Hz",
            qpc.frequency());
        session = Session.start(token, clock, qpc);
    }
}
