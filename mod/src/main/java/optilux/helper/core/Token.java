package optilux.helper.core;

/**
 * The launch token (docs/mod.md#5-safety): {@code -Doptilux.token}, 32-128 characters of
 * {@code [A-Za-z0-9_-]}, fresh per launch. Without a valid one the mod is inert: no pipe, no
 * thread, no mixin. Messages never quote the token.
 */
public final class Token {
    public static final String PROPERTY = "optilux.token";
    public static final int MIN_LENGTH = 32;
    public static final int MAX_LENGTH = 128;

    private Token() {
    }

    public static boolean valid(String token) {
        return problem(token) == null;
    }

    /** Why a token is refused, or null when it is valid. */
    public static String problem(String token) {
        if (token == null) {
            return "no -D" + PROPERTY;
        }
        if (token.length() < MIN_LENGTH || token.length() > MAX_LENGTH) {
            return "-D" + PROPERTY + " is " + token.length() + " characters, not "
                + MIN_LENGTH + "-" + MAX_LENGTH;
        }
        for (int i = 0; i < token.length(); i++) {
            if (!allowed(token.charAt(i))) {
                return "-D" + PROPERTY + " holds a character outside [A-Za-z0-9_-]";
            }
        }
        return null;
    }

    // ASCII only: Character.isLetterOrDigit would pass any script's letters.
    private static boolean allowed(char c) {
        return c >= 'A' && c <= 'Z' || c >= 'a' && c <= 'z' || c >= '0' && c <= '9'
            || c == '_' || c == '-';
    }
}
