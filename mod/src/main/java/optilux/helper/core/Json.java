package optilux.helper.core;

import com.google.gson.Strictness;
import com.google.gson.stream.JsonReader;
import com.google.gson.stream.JsonToken;
import java.io.IOException;
import java.io.StringReader;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;

/**
 * Strict JSON for the wire (docs/mod-protocol.md#envelope). A line is read with Gson's JsonReader
 * in STRICT mode into plain values: LinkedHashMap, ArrayList, String, Boolean, null, and numbers
 * as their literal ({@link Num}), so an integer is told from 1.0 and nothing is rounded. A
 * duplicate key, a lone surrogate, trailing data and nesting past {@link #MAX_DEPTH} are refused.
 * {@link #write} serializes the same kinds of values, plus Java numbers.
 */
public final class Json {
    /** Requests nest a few levels (args, an align object); 64 bounds the reader's recursion. */
    public static final int MAX_DEPTH = 64;
    private static final Pattern NUMBER = Pattern.compile("-?(0|[1-9][0-9]*)(\\.[0-9]+)?([eE][+-]?[0-9]+)?");
    private static final Pattern INTEGER = Pattern.compile("-?(0|[1-9][0-9]*)");

    private Json() {
    }

    /** A JSON number as written on the wire. */
    public record Num(String literal) {
        public boolean isInteger() {
            return INTEGER.matcher(literal).matches();
        }

        /** The value as a long; ArithmeticException outside the long range or for a fraction. */
        public long longValue() {
            return new BigDecimal(literal).longValueExact();
        }

        public double doubleValue() {
            return Double.parseDouble(literal);
        }

        @Override
        public String toString() {
            return literal;
        }
    }

    /** A line that is not one strict JSON value; the message says where. */
    public static final class Malformed extends Exception {
        public Malformed(String message) {
            super(message);
        }
    }

    public static Object parse(String text) throws Malformed {
        JsonReader reader = new JsonReader(new StringReader(text));
        reader.setStrictness(Strictness.STRICT);
        reader.setNestingLimit(MAX_DEPTH);
        try {
            Object value = read(reader);
            if (reader.peek() != JsonToken.END_DOCUMENT) {
                throw new Malformed("data after the JSON value at " + where(reader));
            }
            return value;
        } catch (IOException | IllegalStateException | NumberFormatException error) {
            throw new Malformed(message(error));
        }
    }

    private static Object read(JsonReader reader) throws IOException, Malformed {
        switch (reader.peek()) {
            case BEGIN_OBJECT -> {
                Map<String, Object> object = new LinkedHashMap<>();
                reader.beginObject();
                while (reader.hasNext()) {
                    String name = checked(reader.nextName(), reader);
                    if (object.containsKey(name)) {
                        throw new Malformed("duplicate key \"" + name + "\" at " + where(reader));
                    }
                    object.put(name, read(reader));
                }
                reader.endObject();
                return object;
            }
            case BEGIN_ARRAY -> {
                List<Object> array = new ArrayList<>();
                reader.beginArray();
                while (reader.hasNext()) {
                    array.add(read(reader));
                }
                reader.endArray();
                return array;
            }
            case STRING -> {
                return checked(reader.nextString(), reader);
            }
            case NUMBER -> {
                String literal = reader.nextString();
                if (!NUMBER.matcher(literal).matches()) {
                    throw new Malformed("number " + literal + " is not JSON at " + where(reader));
                }
                return new Num(literal);
            }
            case BOOLEAN -> {
                return reader.nextBoolean();
            }
            case NULL -> {
                reader.nextNull();
                return null;
            }
            default -> throw new Malformed("no JSON value at " + where(reader));
        }
    }

    /** A string with a lone surrogate (an escape such as \ud800) is no Unicode text. */
    private static String checked(String text, JsonReader reader) throws Malformed {
        for (int i = 0; i < text.length(); i++) {
            char c = text.charAt(i);
            if (Character.isHighSurrogate(c) && i + 1 < text.length()
                && Character.isLowSurrogate(text.charAt(i + 1))) {
                i++;
            } else if (Character.isSurrogate(c)) {
                throw new Malformed("a lone surrogate in a string at " + where(reader));
            }
        }
        return text;
    }

    private static String where(JsonReader reader) {
        return reader.getPath();
    }

    private static String message(Exception error) {
        String text = error.getMessage();
        if (text == null || text.isBlank()) {
            return error.getClass().getSimpleName();
        }
        // Gson appends a troubleshooting URL; the first sentence names the problem.
        int see = text.indexOf("\nSee ");
        return see > 0 ? text.substring(0, see) : text;
    }

    public static String write(Object value) {
        StringBuilder out = new StringBuilder();
        append(out, value);
        return out.toString();
    }

    private static void append(StringBuilder out, Object value) {
        if (value == null) {
            out.append("null");
        } else if (value instanceof String text) {
            quote(out, text);
        } else if (value instanceof Boolean flag) {
            out.append(flag);
        } else if (value instanceof Num num) {
            out.append(num.literal());
        } else if (value instanceof Long || value instanceof Integer || value instanceof Short
            || value instanceof Byte) {
            out.append(value);
        } else if (value instanceof Double || value instanceof Float) {
            double number = ((Number) value).doubleValue();
            if (!Double.isFinite(number)) {
                throw new IllegalArgumentException("JSON has no " + number);
            }
            out.append(number);
        } else if (value instanceof BigDecimal decimal) {
            out.append(decimal.toString());
        } else if (value instanceof Map<?, ?> map) {
            out.append('{');
            boolean first = true;
            for (Map.Entry<?, ?> entry : map.entrySet()) {
                if (!(entry.getKey() instanceof String key)) {
                    throw new IllegalArgumentException("a JSON key must be a string: " + entry.getKey());
                }
                if (!first) {
                    out.append(',');
                }
                first = false;
                quote(out, key);
                out.append(':');
                append(out, entry.getValue());
            }
            out.append('}');
        } else if (value instanceof Collection<?> list) {
            out.append('[');
            boolean first = true;
            for (Object item : list) {
                if (!first) {
                    out.append(',');
                }
                first = false;
                append(out, item);
            }
            out.append(']');
        } else {
            throw new IllegalArgumentException("no JSON form for " + value.getClass().getName());
        }
    }

    private static void quote(StringBuilder out, String text) {
        out.append('"');
        for (int i = 0; i < text.length(); i++) {
            char c = text.charAt(i);
            switch (c) {
                case '"' -> out.append("\\\"");
                case '\\' -> out.append("\\\\");
                case '\n' -> out.append("\\n");
                case '\r' -> out.append("\\r");
                case '\t' -> out.append("\\t");
                default -> {
                    if (c < 0x20 || c == 0x7f) {
                        out.append(String.format("\\u%04x", (int) c));
                    } else {
                        out.append(c);
                    }
                }
            }
        }
        out.append('"');
    }
}
