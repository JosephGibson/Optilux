package optilux.helper;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import optilux.helper.core.Token;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

/**
 * The mixin config plugin's decision as Mixin drives it: onLoad, then shouldApplyMixin per mixin,
 * with -Doptilux.token absent, malformed and valid.
 */
class MixinGateTest {
    private static final String TARGET = "net.minecraft.client.renderer.GameRenderer";
    private static final String MIXIN = "optilux.helper.mixin.GameRendererMixin";

    @AfterEach
    void clearToken() {
        System.clearProperty(Token.PROPERTY);
    }

    private static boolean applies(String token) {
        if (token == null) {
            System.clearProperty(Token.PROPERTY);
        } else {
            System.setProperty(Token.PROPERTY, token);
        }
        MixinGate gate = new MixinGate();
        gate.onLoad("optilux.helper.mixin");
        assertNull(gate.getMixins());
        assertNull(gate.getRefMapperConfig());
        return gate.shouldApplyMixin(TARGET, MIXIN);
    }

    @Test
    void noTokenAppliesNoMixin() {
        assertFalse(applies(null));
    }

    @Test
    void aMalformedTokenAppliesNoMixin() {
        assertFalse(applies(""));
        assertFalse(applies("x".repeat(31)));
        assertFalse(applies("x".repeat(40) + "="));
    }

    @Test
    void aValidTokenAppliesTheMixin() {
        assertTrue(applies("T".repeat(43)));
    }

    @Test
    void aGateNeverLoadedAppliesNothing() {
        System.setProperty(Token.PROPERTY, "T".repeat(43));
        assertFalse(new MixinGate().shouldApplyMixin(TARGET, MIXIN));
    }
}
