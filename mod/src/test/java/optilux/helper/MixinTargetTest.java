package optilux.helper;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.zip.ZipFile;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.Type;
import org.objectweb.asm.tree.AbstractInsnNode;
import org.objectweb.asm.tree.AnnotationNode;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;

/**
 * Every target of every mixin the config lists, read with ASM from the pinned jars' bytecode, the
 * authority (roadmap.md F9): the target class, the injected method by name and descriptor, and
 * each INVOKE inside it. A mixin annotation, or an @Inject or @At value, that this test does not
 * read fails it, so a new kind of target cannot pass unread.
 */
class MixinTargetTest {
    private static final String MIXIN = "Lorg/spongepowered/asm/mixin/Mixin;";
    private static final String INJECT = "Lorg/spongepowered/asm/mixin/injection/Inject;";
    private static final List<String> MIXIN_PACKAGES =
        List.of("Lorg/spongepowered/asm/mixin/", "Lcom/llamalad7/mixinextras/");
    private static final List<String> PLAIN_POINTS = List.of("HEAD", "RETURN", "TAIL");
    // The @Inject and @At values this test reads or that name no target; any other (slice,
    // ordinal, locals, shift, ...) fails it until the test reads it.
    private static final List<String> INJECT_KEYS = List.of("method", "at", "cancellable");
    private static final List<String> AT_KEYS = List.of("value", "target");
    private static final List<ZipFile> JARS = new ArrayList<>();

    @BeforeAll
    static void openPinnedJars() {
        for (JsonElement element : Pinned.inputs().getAsJsonArray("targetJars")) {
            JsonObject jar = element.getAsJsonObject();
            JARS.add(Pinned.open(Path.of(jar.get("path").getAsString()),
                jar.get("algorithm").getAsString(), jar.get("digest").getAsString()));
        }
    }

    @AfterAll
    static void closePinnedJars() throws IOException {
        for (ZipFile jar : JARS) {
            jar.close();
        }
    }

    @Test
    void everyTargetIsInThePinnedJars() {
        JsonObject config = resourceJson("optilux-helper.mixins.json");
        String pkg = config.get("package").getAsString();
        List<String> mixins = new ArrayList<>();
        for (String side : List.of("mixins", "client", "server")) {
            if (config.has(side)) {
                config.getAsJsonArray(side).forEach(name -> mixins.add(name.getAsString()));
            }
        }
        assertTrue(!mixins.isEmpty(), "the config lists no mixin");
        List<String> problems = new ArrayList<>();
        List<String> checked = new ArrayList<>();
        for (String name : mixins) {
            ClassNode mixin = read(ownClass(pkg + "." + name));
            List<ClassNode> targets = new ArrayList<>();
            for (String targetName : targets(mixin, problems)) {
                ClassNode target = pinnedClass(targetName);
                if (target == null) {
                    problems.add(name + ": target class " + targetName + " is in no pinned jar");
                } else {
                    targets.add(target);
                }
            }
            for (var field : mixin.fields) {
                unread(name + "." + field.name, all(field.visibleAnnotations,
                    field.invisibleAnnotations), problems);
            }
            for (MethodNode method : mixin.methods) {
                String where = name + "." + method.name;
                List<AnnotationNode> others = new ArrayList<>();
                for (AnnotationNode annotation : all(method)) {
                    if (annotation.desc.equals(INJECT)) {
                        for (ClassNode target : targets) {
                            checkInject(where, annotation, target, problems, checked);
                        }
                    } else {
                        others.add(annotation);
                    }
                }
                unread(where, others, problems);
            }
        }
        assertEquals(List.of(), problems);
        assertEquals(List.of("GameRendererMixin.optilux$frameHead: "
            + "net/minecraft/client/renderer/GameRenderer.render()V HEAD"), checked);
    }

    private static void checkInject(String where, AnnotationNode inject, ClassNode target,
        List<String> problems, List<String> checked) {
        @SuppressWarnings("unchecked")
        List<String> selectors = (List<String>) value(inject, "method");
        @SuppressWarnings("unchecked")
        List<AnnotationNode> points = (List<AnnotationNode>) value(inject, "at");
        unreadKeys(where + " @Inject", inject, INJECT_KEYS, problems);
        for (AnnotationNode at : points) {
            unreadKeys(where + " @At", at, AT_KEYS, problems);
        }
        for (String selector : selectors) {
            int paren = selector.indexOf('(');
            if (paren < 0) {
                problems.add(where + ": selector " + selector + " has no descriptor");
                continue;
            }
            MethodNode method = method(target, selector.substring(0, paren),
                selector.substring(paren));
            if (method == null) {
                problems.add(where + ": " + target.name + "." + selector + " is not in the jar");
                continue;
            }
            for (AnnotationNode at : points) {
                String point = (String) value(at, "value");
                String seen = target.name + "." + selector + " " + point;
                if (PLAIN_POINTS.contains(point)) {
                    checked.add(where + ": " + seen);
                } else if (point.equals("INVOKE")) {
                    String call = (String) value(at, "target");
                    if (invokes(method, call)) {
                        checked.add(where + ": " + seen + " " + call);
                    } else {
                        problems.add(where + ": " + seen + ": no call to " + call);
                    }
                } else {
                    problems.add(where + ": injection point " + point + " is not read by this test");
                }
            }
        }
    }

    /** Whether a method calls {@code Lowner;name(desc)}. */
    private static boolean invokes(MethodNode method, String call) {
        int semicolon = call.indexOf(';');
        int paren = call.indexOf('(');
        if (!call.startsWith("L") || semicolon < 0 || paren < semicolon) {
            return false;
        }
        String owner = call.substring(1, semicolon);
        String name = call.substring(semicolon + 1, paren);
        String desc = call.substring(paren);
        for (AbstractInsnNode insn : method.instructions) {
            if (insn instanceof MethodInsnNode invoke && invoke.owner.equals(owner)
                && invoke.name.equals(name) && invoke.desc.equals(desc)) {
                return true;
            }
        }
        return false;
    }

    private static List<String> targets(ClassNode mixin, List<String> problems) {
        List<String> found = new ArrayList<>();
        for (AnnotationNode annotation : all(mixin.visibleAnnotations, mixin.invisibleAnnotations)) {
            if (!annotation.desc.equals(MIXIN)) {
                continue;
            }
            Object types = value(annotation, "value");
            if (types instanceof List<?> list) {
                list.forEach(type -> found.add(((Type) type).getInternalName()));
            }
            Object names = value(annotation, "targets");
            if (names instanceof List<?> list) {
                list.forEach(target -> found.add(((String) target).replace('.', '/')));
            }
        }
        if (found.isEmpty()) {
            problems.add(mixin.name + ": no @Mixin target");
        }
        return found;
    }

    /** A mixin annotation this test does not read is a problem: extend the test first. */
    private static void unread(String where, List<AnnotationNode> annotations,
        List<String> problems) {
        for (AnnotationNode annotation : annotations) {
            if (MIXIN_PACKAGES.stream().anyMatch(annotation.desc::startsWith)) {
                problems.add(where + ": " + annotation.desc + " is not read by this test");
            }
        }
    }

    private static void unreadKeys(String where, AnnotationNode annotation, List<String> read,
        List<String> problems) {
        if (annotation.values == null) {
            return;
        }
        for (int i = 0; i < annotation.values.size(); i += 2) {
            String key = (String) annotation.values.get(i);
            if (!read.contains(key)) {
                problems.add(where + ": " + key + " is not read by this test");
            }
        }
    }

    private static MethodNode method(ClassNode target, String name, String desc) {
        for (MethodNode method : target.methods) {
            if (method.name.equals(name) && method.desc.equals(desc)) {
                return method;
            }
        }
        return null;
    }

    private static ClassNode pinnedClass(String internalName) {
        for (ZipFile jar : JARS) {
            byte[] bytes = Pinned.bytes(jar, internalName + ".class");
            if (bytes != null) {
                return read(bytes);
            }
        }
        return null;
    }

    private static List<AnnotationNode> all(MethodNode method) {
        return all(method.visibleAnnotations, method.invisibleAnnotations);
    }

    @SafeVarargs
    private static List<AnnotationNode> all(List<AnnotationNode>... lists) {
        List<AnnotationNode> found = new ArrayList<>();
        for (List<AnnotationNode> list : lists) {
            if (list != null) {
                found.addAll(list);
            }
        }
        return found;
    }

    private static Object value(AnnotationNode annotation, String key) {
        Map<String, Object> values = new HashMap<>();
        if (annotation.values != null) {
            for (int i = 0; i + 1 < annotation.values.size(); i += 2) {
                values.put((String) annotation.values.get(i), annotation.values.get(i + 1));
            }
        }
        return values.get(key);
    }

    private static byte[] ownClass(String className) {
        return resource(className.replace('.', '/') + ".class");
    }

    private static JsonObject resourceJson(String name) {
        return com.google.gson.JsonParser.parseString(new String(resource(name),
            java.nio.charset.StandardCharsets.UTF_8)).getAsJsonObject();
    }

    private static byte[] resource(String name) {
        try (InputStream stream = MixinTargetTest.class.getClassLoader().getResourceAsStream(name)) {
            if (stream == null) {
                throw new IllegalStateException(name + " is not on the test classpath");
            }
            return stream.readAllBytes();
        } catch (IOException error) {
            throw new UncheckedIOException(error);
        }
    }

    private static ClassNode read(byte[] bytes) {
        ClassNode node = new ClassNode();
        new ClassReader(bytes).accept(node, 0);
        return node;
    }
}
