// The expression runner (docs/offline.md#tools, docs/gpu-iris.md#custom-uniforms): Iris's own
// custom-uniform engine outside the game, started by optilux/expressions.py through the pinned
// Temurin's java as a single source file, with the pinned Iris jar and the launch spec's JOML and
// fastutil jars on its classpath.
//
// Reads tab-separated lines on stdin, in order:
//   in    <type> <name> <values>      an input: comma-separated floats in Float.parseFloat's form
//                                     (hex for exactness), ints or true/false; a mat4's 16 values
//                                     column by column, as JOML's Matrix4f.set(float[]) reads them
//   expr  <type> <name> <expression>  parsed by kroppeb.stareval's Parser with IrisOptions.options,
//                                     resolved by ExpressionResolver with IrisFunctions.functions to
//                                     its type, evaluated; its value an input of the lines after it
// Types: bool, int, float, vec2, vec3, vec4 (a custom uniform's six) and mat4 (Iris's matrices).
// Prints one JSON object per expr line, {"name", "type", "value"}: a float by Float.toString, the
// shortest decimal that reads back as the same float32 (NaN and Infinity as Python's json reads
// them), a vector or a mat4 as a list, the mat4 column by column. A line it cannot read, parse or
// resolve prints {"line", "error"} and exits 1.

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;

import kroppeb.stareval.element.ExpressionElement;
import kroppeb.stareval.expression.Expression;
import kroppeb.stareval.expression.VariableExpression;
import kroppeb.stareval.function.BasicFunctionContext;
import kroppeb.stareval.function.FunctionReturn;
import kroppeb.stareval.function.Type;
import kroppeb.stareval.parser.Parser;
import kroppeb.stareval.resolver.ExpressionResolver;
import net.irisshaders.iris.parsing.IrisFunctions;
import net.irisshaders.iris.parsing.IrisOptions;
import net.irisshaders.iris.parsing.MatrixType;
import net.irisshaders.iris.parsing.VectorType;
import org.joml.Matrix4f;
import org.joml.Vector2f;
import org.joml.Vector3f;
import org.joml.Vector4f;

public class IrisExpressions {
    static final Map<String, Type> TYPES = Map.of(
        "bool", Type.Boolean,
        "int", Type.Int,
        "float", Type.Float,
        "vec2", VectorType.VEC2,
        "vec3", VectorType.VEC3,
        "vec4", VectorType.VEC4,
        "mat4", MatrixType.MAT4);

    final Map<String, Type> variables = new HashMap<>();
    final BasicFunctionContext context = new BasicFunctionContext();
    final ExpressionResolver resolver = new ExpressionResolver(IrisFunctions.functions, variables::get);

    public static void main(String[] args) throws Exception {
        IrisExpressions runner = new IrisExpressions();
        BufferedReader in = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8));
        StringBuilder out = new StringBuilder();
        int number = 0;
        for (String line; (line = in.readLine()) != null; ) {
            number++;
            if (line.isEmpty()) {
                continue;
            }
            try {
                runner.line(line, out);
            } catch (Exception error) {
                System.out.print(out);
                System.out.println("{\"line\": " + number + ", \"error\": " + quote(error.toString()) + "}");
                System.exit(1);
            }
        }
        System.out.print(out);
    }

    void line(String line, StringBuilder out) throws Exception {
        String[] fields = line.split("\t", 4);
        if (fields.length != 4) {
            throw new IllegalArgumentException("not 4 tab-separated fields: " + line);
        }
        String kind = fields[0], typeName = fields[1], name = fields[2], text = fields[3];
        Type type = TYPES.get(typeName);
        if (type == null) {
            throw new IllegalArgumentException("unknown type " + typeName);
        }
        Object value;
        if (kind.equals("in")) {
            value = parse(typeName, text.split(","));
        } else if (kind.equals("expr")) {
            ExpressionElement element = Parser.parse(text, IrisOptions.options);
            Expression expression = resolver.resolveExpression(type, element);
            FunctionReturn result = new FunctionReturn();
            expression.evaluateTo(context, result);
            value = read(typeName, result);
            out.append("{\"name\": ").append(quote(name)).append(", \"type\": ").append(quote(typeName))
                .append(", \"value\": ").append(json(value)).append("}\n");
        } else {
            throw new IllegalArgumentException("unknown kind " + kind);
        }
        define(name, type, typeName, value);
    }

    static Object parse(String type, String[] parts) {
        float[] floats = new float[parts.length];
        switch (type) {
            case "bool":
                return Boolean.parseBoolean(single(parts, "true", "false"));
            case "int":
                return Integer.parseInt(single(parts, null, null));
            default:
                for (int i = 0; i < parts.length; i++) {
                    floats[i] = Float.parseFloat(parts[i]);
                }
        }
        int size = switch (type) {
            case "float" -> 1;
            case "vec2" -> 2;
            case "vec3" -> 3;
            case "vec4" -> 4;
            default -> 16;
        };
        if (floats.length != size) {
            throw new IllegalArgumentException(type + " takes " + size + " values, not " + floats.length);
        }
        return switch (type) {
            case "float" -> floats[0];
            case "vec2" -> new Vector2f(floats[0], floats[1]);
            case "vec3" -> new Vector3f(floats[0], floats[1], floats[2]);
            case "vec4" -> new Vector4f(floats[0], floats[1], floats[2], floats[3]);
            default -> new Matrix4f().set(floats);
        };
    }

    static String single(String[] parts, String yes, String no) {
        if (parts.length != 1 || (yes != null && !parts[0].equals(yes) && !parts[0].equals(no))) {
            throw new IllegalArgumentException("one value expected, not " + String.join(",", parts));
        }
        return parts[0];
    }

    static Object read(String type, FunctionReturn result) {
        return switch (type) {
            case "bool" -> result.booleanReturn;
            case "int" -> result.intReturn;
            case "float" -> result.floatReturn;
            default -> result.objectReturn;
        };
    }

    // The value as a variable of the lines after it; each evaluation hands out its own copy, so
    // no function can change the stored one.
    void define(String name, Type type, String typeName, Object value) {
        VariableExpression expression = (context, result) -> {
            switch (typeName) {
                case "bool" -> result.booleanReturn = (Boolean) value;
                case "int" -> result.intReturn = (Integer) value;
                case "float" -> result.floatReturn = (Float) value;
                case "vec2" -> result.objectReturn = new Vector2f((Vector2f) value);
                case "vec3" -> result.objectReturn = new Vector3f((Vector3f) value);
                case "vec4" -> result.objectReturn = new Vector4f((Vector4f) value);
                default -> result.objectReturn = new Matrix4f((Matrix4f) value);
            }
        };
        variables.put(name, type);
        context.setVariable(name, expression);
    }

    static String json(Object value) {
        if (value instanceof Vector2f v) {
            return list(new float[] {v.x, v.y});
        }
        if (value instanceof Vector3f v) {
            return list(new float[] {v.x, v.y, v.z});
        }
        if (value instanceof Vector4f v) {
            return list(new float[] {v.x, v.y, v.z, v.w});
        }
        if (value instanceof Matrix4f m) {
            return list(m.get(new float[16]));
        }
        return String.valueOf(value);
    }

    static String list(float[] values) {
        StringBuilder text = new StringBuilder("[");
        for (int i = 0; i < values.length; i++) {
            text.append(i == 0 ? "" : ", ").append(values[i]);
        }
        return text.append("]").toString();
    }

    static String quote(String text) {
        StringBuilder quoted = new StringBuilder("\"");
        for (char c : text.toCharArray()) {
            switch (c) {
                case '"' -> quoted.append("\\\"");
                case '\\' -> quoted.append("\\\\");
                case '\n' -> quoted.append("\\n");
                case '\r' -> quoted.append("\\r");
                case '\t' -> quoted.append("\\t");
                default -> {
                    if (c < 0x20) {
                        quoted.append(String.format("\\u%04x", (int) c));
                    } else {
                        quoted.append(c);
                    }
                }
            }
        }
        return quoted.append("\"").toString();
    }
}
