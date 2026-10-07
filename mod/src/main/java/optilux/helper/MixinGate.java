package optilux.helper;

import java.util.List;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import optilux.helper.core.Token;
import org.objectweb.asm.tree.ClassNode;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.spongepowered.asm.mixin.extensibility.IMixinConfigPlugin;
import org.spongepowered.asm.mixin.extensibility.IMixinInfo;

/**
 * The mixin config's plugin, the inert gate's mixin layer (docs/mod.md#5-safety): every mixin
 * is refused unless -Doptilux.token is valid, and each decision is logged, so a session's log
 * shows which mixins were applied; `selftest` reads the applied ones back.
 */
public final class MixinGate implements IMixinConfigPlugin {
    private static final Logger LOG = LoggerFactory.getLogger("optilux-helper");
    /** The simple names of the mixins applied in this game. */
    static final Set<String> APPLIED = ConcurrentHashMap.newKeySet();
    private String problem = "not loaded";

    @Override
    public void onLoad(String mixinPackage) {
        problem = Token.problem(System.getProperty(Token.PROPERTY));
    }

    @Override
    public String getRefMapperConfig() {
        return null;
    }

    @Override
    public boolean shouldApplyMixin(String targetClassName, String mixinClassName) {
        if (problem != null) {
            LOG.info("optilux-helper: mixin {} not applied to {}: inert ({})", mixinClassName,
                targetClassName, problem);
            return false;
        }
        return true;
    }

    @Override
    public void acceptTargets(Set<String> myTargets, Set<String> otherTargets) {
    }

    @Override
    public List<String> getMixins() {
        return null;
    }

    @Override
    public void preApply(String targetClassName, ClassNode targetClass, String mixinClassName,
        IMixinInfo mixinInfo) {
    }

    @Override
    public void postApply(String targetClassName, ClassNode targetClass, String mixinClassName,
        IMixinInfo mixinInfo) {
        LOG.info("optilux-helper: mixin {} applied to {}", mixinClassName, targetClassName);
        APPLIED.add(mixinClassName.substring(mixinClassName.lastIndexOf('.') + 1));
    }
}
