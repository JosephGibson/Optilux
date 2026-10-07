package optilux.helper;

import java.util.concurrent.Callable;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Executor;
import net.minecraft.client.Minecraft;
import optilux.helper.core.Protocol;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * Game work from a request's worker (docs/mod.md#4-architecture): a task runs on its thread (the
 * render thread through Minecraft.execute, the server thread through the integrated server's) and
 * the worker waits; the request's timeout or cancel interrupts the wait, and work queued for a
 * request that was answered first skips its change and logs skipped-late.
 */
final class Tasks {
    private static final Logger LOG = LoggerFactory.getLogger("optilux-helper");

    private Tasks() {
    }

    /** Resolved at use: the adapters are built in the entrypoint, during Minecraft's constructor. */
    static Minecraft minecraft() {
        return Minecraft.getInstance();
    }

    static <T> T onRender(Callable<T> task) throws Exception {
        return on(minecraft(), task);
    }

    static <T> T on(Executor thread, Callable<T> task) throws Exception {
        CompletableFuture<T> done = new CompletableFuture<>();
        thread.execute(() -> {
            try {
                done.complete(task.call());
            } catch (Throwable thrown) {
                done.completeExceptionally(thrown);
            }
        });
        return unwrap(done);
    }

    /** The future's value; its failure rethrown as itself (a coded refusal stays coded). */
    static <T> T unwrap(CompletableFuture<T> future) throws Exception {
        try {
            return future.get();
        } catch (ExecutionException failed) {
            Throwable cause = failed.getCause();
            if (cause instanceof Exception exception) {
                throw exception;
            }
            if (cause instanceof Error error) {
                throw error;
            }
            throw failed;
        }
    }

    /** True, logged, when the request was answered before its game work ran. */
    static boolean skippedLate(Protocol.Request request) {
        if (request.live()) {
            return false;
        }
        LOG.info("optilux-helper: {} {} skipped-late: answered before its game work ran",
            request.command(), request.id());
        return true;
    }
}
