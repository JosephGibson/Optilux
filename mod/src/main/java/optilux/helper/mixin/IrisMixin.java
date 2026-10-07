package optilux.helper.mixin;

import net.irisshaders.iris.Iris;
import optilux.helper.Hooks;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * Iris 1.11.7's load failure (roadmap.md F5): createPipeline and loadExternalShaderpack hand the
 * exception to handleException, which in a world sends a chat message and keeps nothing; the hook
 * sees it first and lets Iris go on as it would.
 */
@Mixin(Iris.class)
public abstract class IrisMixin {
    @Inject(method = "handleException(Ljava/lang/Exception;)V", at = @At("HEAD"))
    private static void optilux$loadFailed(Exception error, CallbackInfo info) {
        Hooks.irisFailed(error);
    }
}
