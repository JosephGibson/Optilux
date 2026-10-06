package optilux.helper.core;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * The command table, read from commands.json (docs/mod.md#11-build-and-test): every command of
 * docs/mod-protocol.md#commands with its arguments, result fields, phase and busy rules. The
 * protocol checks every request's arguments here before a handler runs, so a handler sees only
 * known, typed, in-range values with the defaults filled.
 */
public final class Commands {
    /** The argument keys commands.json may use; any other is refused at load. */
    static final Set<String> ARG_KEYS = Set.of("type", "required", "default", "min", "max", "gt",
        "minLength", "maxLength", "values");
    static final Set<String> TYPES = Set.of("string", "integer", "number", "boolean", "object",
        "array", "id");
    /** A request id: an integer, or a string of 1 to 64 characters (docs/mod-protocol.md#envelope). */
    public static final int MAX_ID_LENGTH = 64;

    public record Arg(String name, String type, boolean required, Object defaultValue, Double min,
        Double max, Double gt, Integer minLength, Integer maxLength, List<String> values) {
    }

    public record Command(String name, String phase, Map<String, Arg> args,
        Map<String, String> result, boolean mutating, String exclusive, String exclusiveUntil) {
    }

    private final int protocol;
    private final Map<String, String> common;
    private final List<String> errors;
    private final List<String> resources;
    private final Map<String, Command> commands;

    private Commands(int protocol, Map<String, String> common, List<String> errors,
        List<String> resources, Map<String, Command> commands) {
        this.protocol = protocol;
        this.common = common;
        this.errors = errors;
        this.resources = resources;
        this.commands = commands;
    }

    public int protocol() {
        return protocol;
    }

    /** The fields every result and event carries, name to type. */
    public Map<String, String> common() {
        return common;
    }

    public List<String> errors() {
        return errors;
    }

    public List<String> resources() {
        return resources;
    }

    /** Every command in the table's order. */
    public Map<String, Command> all() {
        return commands;
    }

    public Command get(String name) {
        return commands.get(name);
    }

    /** The table from commands.json's text; IllegalArgumentException names what is wrong. */
    @SuppressWarnings("unchecked")
    public static Commands parse(String text) {
        Map<String, Object> root;
        try {
            root = (Map<String, Object>) Json.parse(text);
        } catch (Json.Malformed | ClassCastException error) {
            throw new IllegalArgumentException("commands.json is not a JSON object: " + error.getMessage());
        }
        int protocol = (int) ((Json.Num) root.get("protocol")).longValue();
        Map<String, String> common = strings((Map<String, Object>) root.get("common"), "common");
        List<String> errors = (List<String>) (List<?>) root.get("errors");
        if (!errors.equals(Errors.ALL)) {
            throw new IllegalArgumentException("commands.json errors " + errors + " are not " + Errors.ALL);
        }
        List<String> resources = (List<String>) (List<?>) root.get("resources");
        Map<String, Command> commands = new LinkedHashMap<>();
        for (Object item : (List<Object>) root.get("commands")) {
            Map<String, Object> entry = (Map<String, Object>) item;
            String name = (String) entry.get("name");
            Map<String, Arg> args = new LinkedHashMap<>();
            for (Map.Entry<String, Object> arg : ((Map<String, Object>) entry.get("args")).entrySet()) {
                args.put(arg.getKey(), arg(name, arg.getKey(), (Map<String, Object>) arg.getValue()));
            }
            String exclusive = (String) entry.get("exclusive");
            if (exclusive != null && !resources.contains(exclusive)) {
                throw new IllegalArgumentException(name + ": exclusive " + exclusive + " is no resource");
            }
            Command command = new Command(name, (String) entry.get("phase"),
                Collections.unmodifiableMap(args),
                strings((Map<String, Object>) entry.get("result"), name + " result"),
                Boolean.TRUE.equals(entry.get("mutating")), exclusive,
                (String) entry.get("exclusiveUntil"));
            if (commands.put(name, command) != null) {
                throw new IllegalArgumentException("commands.json lists " + name + " twice");
            }
        }
        return new Commands(protocol, common, List.copyOf(errors), List.copyOf(resources),
            Collections.unmodifiableMap(commands));
    }

    @SuppressWarnings("unchecked")
    private static Arg arg(String command, String name, Map<String, Object> spec) {
        for (String key : spec.keySet()) {
            if (!ARG_KEYS.contains(key)) {
                throw new IllegalArgumentException(command + "." + name + ": unknown key " + key);
            }
        }
        String type = (String) spec.get("type");
        if (!TYPES.contains(type)) {
            throw new IllegalArgumentException(command + "." + name + ": unknown type " + type);
        }
        return new Arg(name, type, Boolean.TRUE.equals(spec.get("required")), spec.get("default"),
            number(spec.get("min")), number(spec.get("max")), number(spec.get("gt")),
            integer(spec.get("minLength")), integer(spec.get("maxLength")),
            spec.containsKey("values") ? List.copyOf((List<String>) (List<?>) spec.get("values")) : null);
    }

    private static Map<String, String> strings(Map<String, Object> map, String where) {
        Map<String, String> found = new LinkedHashMap<>();
        for (Map.Entry<String, Object> entry : map.entrySet()) {
            if (!(entry.getValue() instanceof String type)) {
                throw new IllegalArgumentException(where + "." + entry.getKey() + " is not a type name");
            }
            found.put(entry.getKey(), type);
        }
        return Collections.unmodifiableMap(found);
    }

    private static Double number(Object value) {
        return value == null ? null : ((Json.Num) value).doubleValue();
    }

    private static Integer integer(Object value) {
        return value == null ? null : (int) ((Json.Num) value).longValue();
    }

    /**
     * A request's arguments checked against the command: an object, no unknown name, every
     * required one present, each of its type and in range; the defaults filled. Integers come
     * back as Long, numbers as Double, ids as Long or String. Refused as bad-request.
     */
    public Map<String, Object> check(Command command, Object args) throws Errors.Refused {
        if (!(args instanceof Map<?, ?> given)) {
            throw bad(command.name() + ": args must be an object");
        }
        List<String> unknown = new ArrayList<>();
        for (Object key : given.keySet()) {
            if (!command.args().containsKey(key)) {
                unknown.add((String) key);
            }
        }
        if (!unknown.isEmpty()) {
            throw bad(command.name() + ": unknown argument " + String.join(", ", unknown)
                + (command.args().isEmpty() ? "; it takes none"
                    : "; it takes " + String.join(", ", command.args().keySet())));
        }
        Map<String, Object> checked = new LinkedHashMap<>();
        for (Arg arg : command.args().values()) {
            if (!given.containsKey(arg.name())) {
                if (arg.required()) {
                    throw bad(command.name() + ": missing argument " + arg.name());
                }
                if (arg.defaultValue() != null) {
                    checked.put(arg.name(), value(command, arg, arg.defaultValue()));
                }
                continue;
            }
            checked.put(arg.name(), value(command, arg, given.get(arg.name())));
        }
        return checked;
    }

    private static Object value(Command command, Arg arg, Object value) throws Errors.Refused {
        String where = command.name() + "." + arg.name();
        switch (arg.type()) {
            case "string" -> {
                if (!(value instanceof String text)) {
                    throw bad(where + " must be a string");
                }
                if (arg.minLength() != null && text.length() < arg.minLength()
                    || arg.maxLength() != null && text.length() > arg.maxLength()) {
                    throw bad(where + " is " + text.length() + " characters, not "
                        + (arg.minLength() == null ? 0 : arg.minLength()) + "-"
                        + (arg.maxLength() == null ? "any" : arg.maxLength()));
                }
                if (arg.values() != null && !arg.values().contains(text)) {
                    throw bad(where + " must be one of " + String.join(", ", arg.values()));
                }
                return text;
            }
            case "integer" -> {
                long number = integer(where, value);
                range(where, arg, number);
                return number;
            }
            case "number" -> {
                if (!(value instanceof Json.Num num)) {
                    throw bad(where + " must be a number");
                }
                double number = num.doubleValue();
                if (!Double.isFinite(number)) {
                    throw bad(where + " is out of the double range");
                }
                range(where, arg, number);
                return number;
            }
            case "boolean" -> {
                if (!(value instanceof Boolean flag)) {
                    throw bad(where + " must be true or false");
                }
                return flag;
            }
            case "object" -> {
                if (!(value instanceof Map<?, ?>)) {
                    throw bad(where + " must be an object");
                }
                return value;
            }
            case "array" -> {
                if (!(value instanceof List<?>)) {
                    throw bad(where + " must be an array");
                }
                return value;
            }
            case "id" -> {
                return id(value, where);
            }
            default -> throw new IllegalStateException(where + ": type " + arg.type());
        }
    }

    /** A request id as the envelope allows it: Long or String(1..64); else bad-request. */
    public static Object id(Object value, String where) throws Errors.Refused {
        if (value instanceof String text) {
            if (text.isEmpty() || text.length() > MAX_ID_LENGTH) {
                throw bad(where + " is a string of " + text.length() + " characters, not 1-" + MAX_ID_LENGTH);
            }
            return text;
        }
        if (value instanceof Json.Num) {
            return integer(where, value);
        }
        throw bad(where + " must be an integer or a string of 1-" + MAX_ID_LENGTH + " characters");
    }

    private static long integer(String where, Object value) throws Errors.Refused {
        if (!(value instanceof Json.Num num) || !num.isInteger()) {
            throw bad(where + " must be an integer");
        }
        try {
            return num.longValue();
        } catch (ArithmeticException error) {
            throw bad(where + " is outside the 64-bit range");
        }
    }

    private static void range(String where, Arg arg, double value) throws Errors.Refused {
        if (arg.gt() != null && !(value > arg.gt())) {
            throw bad(where + " must be greater than " + plain(arg.gt()));
        }
        if (arg.min() != null && value < arg.min() || arg.max() != null && value > arg.max()) {
            throw bad(where + " must lie in " + (arg.min() == null ? "-inf" : plain(arg.min()))
                + ".." + (arg.max() == null ? "inf" : plain(arg.max())));
        }
    }

    private static String plain(double value) {
        return value == Math.rint(value) && Math.abs(value) < 1e15
            ? Long.toString((long) value) : Double.toString(value);
    }

    private static Errors.Refused bad(String message) {
        return new Errors.Refused(Errors.BAD_REQUEST, message);
    }
}
