package optilux.helper.mixin;

import net.irisshaders.iris.gl.GLDebug;
import optilux.helper.Hooks;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * The per-pass timers' hooks (plans/m2.md D53): Iris 1.11.7's static GLDebug.pushGroup and
 * popGroup only hand the call to its debug state, a no-op unless enableDebugOptions is on, and
 * Iris calls them around every phase (setPhase), composite renderer and pass (renderAll), the
 * final pass, the shadow composite and the texture clears, so their HEAD sees each pass on the
 * bench tier (read in the pinned jar's bytecode).
 */
@Mixin(GLDebug.class)
public abstract class GLDebugMixin {
    @Inject(method = "pushGroup(ILjava/lang/String;)V", at = @At("HEAD"))
    private static void optilux$groupPushed(int id, String name, CallbackInfo info) {
        Hooks.groupPushed(name);
    }

    @Inject(method = "popGroup()V", at = @At("HEAD"))
    private static void optilux$groupPopped(CallbackInfo info) {
        Hooks.groupPopped();
    }
}
