package optilux.helper;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import optilux.helper.core.Token;
import org.junit.jupiter.api.Test;

/** The token rule: 32-128 characters of [A-Za-z0-9_-] (docs/mod.md#5-safety). */
class TokenTest {
    @Test
    void validTokens() {
        assertTrue(Token.valid("a".repeat(32)));
        assertTrue(Token.valid("Z".repeat(128)));
        // What `optilux launch` passes: secrets.token_urlsafe(32), 43 characters.
        assertTrue(Token.valid("AZaz09_-".repeat(5) + "abc"));
        assertNull(Token.problem("0123456789-_".repeat(3)));
    }

    @Test
    void refusedTokensSayWhyWithoutQuotingThem() {
        assertEquals("no -Doptilux.token", Token.problem(null));
        assertEquals("-Doptilux.token is 0 characters, not 32-128", Token.problem(""));
        assertEquals("-Doptilux.token is 31 characters, not 32-128", Token.problem("x".repeat(31)));
        assertEquals("-Doptilux.token is 129 characters, not 32-128",
            Token.problem("x".repeat(129)));
        for (String bad : new String[] {"=", "+", "/", " ", "\n", ".", "é", "١"}) {
            String token = "x".repeat(31) + bad;
            assertFalse(Token.valid(token), "accepted a token ending in U+"
                + Integer.toHexString(bad.charAt(0)));
            assertEquals("-Doptilux.token holds a character outside [A-Za-z0-9_-]",
                Token.problem(token));
        }
    }
}
