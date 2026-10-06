package optilux.helper.core;

import java.util.List;

/** The error codes of docs/mod-protocol.md#errors; commands.json lists the same, a test checks. */
public final class Errors {
    public static final String BAD_JSON = "bad-json";
    public static final String BAD_ENCODING = "bad-encoding";
    public static final String LINE_TOO_LONG = "line-too-long";
    public static final String BAD_REQUEST = "bad-request";
    public static final String UNKNOWN_COMMAND = "unknown-command";
    public static final String UNSUPPORTED = "unsupported";
    public static final String UNAUTHENTICATED = "unauthenticated";
    public static final String NOT_READY = "not-ready";
    public static final String BUSY = "busy";
    public static final String TIMEOUT = "timeout";
    public static final String CANCELLED = "cancelled";
    public static final String IRIS_COMPILE_ERROR = "iris-compile-error";
    public static final String FAILED = "failed";

    public static final List<String> ALL = List.of(BAD_JSON, BAD_ENCODING, LINE_TOO_LONG,
        BAD_REQUEST, UNKNOWN_COMMAND, UNSUPPORTED, UNAUTHENTICATED, NOT_READY, BUSY, TIMEOUT,
        CANCELLED, IRIS_COMPILE_ERROR, FAILED);

    private Errors() {
    }

    /** A coded refusal: a handler throws it, the protocol answers {"ok": false, "error"}. */
    public static final class Refused extends Exception {
        private final String code;

        public Refused(String code, String message) {
            super(message);
            if (!ALL.contains(code)) {
                throw new IllegalArgumentException("no error code " + code);
            }
            this.code = code;
        }

        public String code() {
            return code;
        }
    }
}
