"""Tests for Pipeline/java_ast.py, stage A3: methods and constructors (without bodies).

Same structure as test_java_ast_a2.py:
1. EXPECTED: every method entry of every sample in java_samples/a3/ (keys in order, the six fields
   abstract / modifiers / return_type / params / signature / javadoc), written by hand.
2. Regex comparison on the fields the model sees (key order, abstract, params, signature,
   javadoc): AST must equal Context_gen.analyze_java_file, except the intentional fixes in
   KNOWN_DEVIATIONS (where the visible regex output is pinned too).
3. Decision 8: `modifiers` / `return_type` are written correctly (they are only in Context.json).
   The systematic difference from regex is checked by one rule (test_decision_8_rule).

Regex compatibility kept on purpose (decisions 16-17.11, removed later in stage B):
key = method name, overloads overwrite each other (first position, last value; B2); constructors
of the same arity too; `Override` first in the signature of a method with a body (B7); the
abstract signature is `abstract` + public / protected / static in this order (B7); javadoc = the
last `/** */` in the 400 characters before the regex match, may belong to a neighbour (B10);
interface methods without `abstract` and `native` methods are not found (B1); methods of nested,
anonymous and local classes go to the main type (B3).
"""
import os

import pytest

import Context_gen
import java_ast

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES_DIR = os.path.join(HERE, "java_samples", "a3")
OTHER_SAMPLE_DIRS = [os.path.join(HERE, "java_samples", d) for d in ("a1", "a2")]
ENTRY_KEYS = ["abstract", "modifiers", "return_type", "params", "signature", "javadoc",
              "calls", "logic_hints", "values_hint"]
VISIBLE = ("abstract", "params", "signature", "javadoc")   # what reaches S / F / B
PINNED_BODY_FIELDS = ("logic_hints", "values_hint")    # `calls`: A4 (test_java_ast_a4.py)

pytestmark = pytest.mark.filterwarnings("ignore::java_ast.JavaParseWarning")


def _m(signature, modifiers, return_type, params=(), javadoc="", abstract=False):
    return {"abstract": abstract, "modifiers": list(modifiers), "return_type": return_type,
            "params": list(params), "signature": signature, "javadoc": javadoc}


def _v(signature, params=(), javadoc="", abstract=False):
    """Visible fields of a regex entry (pinned in KNOWN_DEVIATIONS)."""
    return {"abstract": abstract, "params": list(params), "signature": signature, "javadoc": javadoc}


PUB = ["public"]
NEIGHBOUR_DOC = ("This comment is longer than one hundred and twenty characters, so only the first"
                 "        one hundred and twenty character")
ZURUECK_DOC = ("Gibt den x-Wert des Objektes zurück(also den linken Rand des Bildes"
               "              @return x-Wert des Objektes")

EXPECTED = {
    # Constructors first (same arity: first position, last value), then methods with a body in
    # source order (overload: first position, last value). Javadoc of `size` is its neighbour's.
    "OverloadedMethods.java": [
        ("OverloadedMethods_constructor_0", _m("public OverloadedMethods()", PUB, "",
                                               javadoc="Creates an empty one.")),
        ("OverloadedMethods_constructor_1", _m(
            "protected OverloadedMethods(String label)", ["protected"], "", ["String label"],
            "Creates one from a label (same arity: overwrites the one above).")),
        ("move", _m("public void move(int dx, int dy)", PUB, "void", ["int dx", "int dy"],
                    "Moves by dx and dy.")),
        ("size", _m("public int size()", PUB, "int", javadoc="Moves by dx.")),
    ],
    # regex compat (B7): `Override` first in the signature; not in modifiers / return_type.
    "OverrideMethods.java": [
        ("run", _m("Override public void run()", PUB, "void")),
        ("compareTo", _m("Override public int compareTo(OverrideMethods other)", PUB, "int",
                         ["OverrideMethods other"])),
        ("toString", _m("Override public String toString()", PUB, "String")),
        ("plain", _m("public void plain()", PUB, "void")),
    ],
    # An annotation with arguments never reaches the signature (regex starts after its `)`).
    "SuppressWarningsMethod.java": [
        ("copy", _m("public List<String> copy()", PUB, "List<String>")),
        ("raw", _m("private void raw()", ["private"], "void")),
    ],
    # Abstract methods come after the methods with a body (third pass). Without public /
    # protected / static the abstract signature has two spaces.
    "AbstractMethods.java": [
        ("tick", _m("public void tick()", PUB, "void", javadoc="Updates by delta.")),
        ("render", _m("abstract public void render(Graphics2D g)", ["public", "abstract"], "void",
                      ["Graphics2D g"], "Draws the thing.", abstract=True)),
        ("update", _m("abstract protected boolean update(long delta)", ["protected", "abstract"],
                      "boolean", ["long delta"], "Updates by delta.", abstract=True)),
        ("score", _m("abstract  int score()", ["abstract"], "int", javadoc="Updates by delta.",
                     abstract=True)),
    ],
    # The abstract render(Graphics2D) overwrites the concrete render() but keeps its position.
    "AbstractAfterConcrete.java": [
        ("render", _m("abstract public void render(Graphics2D g)", ["public", "abstract"], "void",
                      ["Graphics2D g"], "Renders on g.", abstract=True)),
        ("update", _m("public void update()", PUB, "void", javadoc="Renders with defaults.")),
    ],
    # `void start();` without `abstract` is not found (B1); `default` / `static` with a body are.
    "InterfaceMethods.java": [
        ("reset", _m("default void reset()", ["default"], "void",
                     javadoc="Default method with a body.")),
        ("version", _m("static int version()", ["static"], "int",
                       javadoc="Default method with a body.")),
        ("score", _m("abstract public int score()", ["public", "abstract"], "int",
                     javadoc="Explicitly abstract.", abstract=True)),
        ("stop", _m("abstract  void stop()", ["abstract"], "void",
                    javadoc="Explicitly abstract.", abstract=True)),
    ],
    # Type parameters are in the signature, not in return_type (decision 8).
    "GenericMethods.java": [
        ("first", _m("public <T> T first(List<T> items)", PUB, "T", ["List<T> items"])),
        ("mapOf", _m("public static <K, V> Map<K, V> mapOf(K key, V value)", ["public", "static"],
                     "Map<K, V>", ["K key", "V value"])),
        ("table", _m("protected Map<String, List<Integer>> table(Map<String,Integer> seed, int n)",
                     ["protected"], "Map<String, List<Integer>>",
                     ["Map<String,Integer> seed", "int n"])),
        ("create", _m("abstract public <T> T create(Class<T> type)", ["public", "abstract"], "T",
                      ["Class<T> type"], abstract=True)),
    ],
    "ThrowsAndVarargs.java": [
        ("ThrowsAndVarargs_constructor_1", _m("public ThrowsAndVarargs(String... names)", PUB, "",
                                              ["String... names"])),
        ("load", _m("public void load(String path)", PUB, "void", ["String path"])),
        ("sum", _m("public static int sum(int... values)", ["public", "static"], "int",
                   ["int... values"])),
        ("copy", _m("public int[] copy(int[] source, String b[])", PUB, "int[]",
                    ["int[] source", "String b[]"])),
        ("save", _m("public void save(final String path, java.util.List<String> lines)", PUB,
                    "void", ["final String path", "java.util.List<String> lines"])),
    ],
    # Modifiers in source order; the abstract signature uses its fixed order. `native` is not
    # found (B1).
    "ModifierOrder.java": [
        ("main", _m("static public void main(String[] args)", ["static", "public"], "void",
                    ["String[] args"])),
        ("lock", _m("synchronized final void lock()", ["synchronized", "final"], "void")),
        ("count", _m("private static final synchronized int count()",
                     ["private", "static", "final", "synchronized"], "int")),
        ("draw", _m("abstract public void draw()", ["abstract", "public"], "void", abstract=True)),
    ],
    # regex compat (B10): javadoc is the last one in the 400 characters before the method, it may
    # be the neighbour's; a javadoc longer than the window is not found; cut to 120 characters.
    "JavadocNeighbour.java": [
        ("start", _m("public void start()", PUB, "void", javadoc=(
            "Starts the game.       Second line, with a tab and the size (Größe)."))),
        ("noDoc", _m("public void noDoc()", PUB, "void", javadoc=(
            "Starts the game.       Second line, with a tab and the size (Größe)."))),
        ("longDoc", _m("public void longDoc()", PUB, "void", javadoc=NEIGHBOUR_DOC)),
        ("farAway", _m("public void farAway()", PUB, "void", javadoc=NEIGHBOUR_DOC)),
        ("afterFar", _m("public void afterFar()", PUB, "void")),
        ("hugeDoc", _m("public void hugeDoc()", PUB, "void")),
    ],
    # regex compat (B3): methods of the anonymous class in a field, of an anonymous and a local
    # class in a method and of a nested class go to the main type (`run`, `tick`: last value).
    "NestedAndAnonymousMethods.java": [
        ("NestedAndAnonymousMethods_constructor_0", _m("public NestedAndAnonymousMethods()", PUB,
                                                       "")),
        ("run", _m("Override public void run()", PUB, "void")),
        ("start", _m("public void start()", PUB, "void")),
        ("value", _m("public int value()", PUB, "int")),
        ("tick", _m("public void tick()", PUB, "void")),
    ],
    "EnumMethods.java": [
        ("EnumMethods_constructor_1", _m("EnumMethods(int level)", [], "", ["int level"])),
        ("getLevel", _m("public int getLevel()", PUB, "int")),
    ],
    "BraceInBody.java": [
        ("open", _m("public char open()", PUB, "char")),
        ("close", _m("public String close()", PUB, "String")),
        ("both", _m("public String both()", PUB, "String")),
        ("after", _m("public void after()", PUB, "void")),
    ],
    "Constructors.java": [
        ("Constructors_constructor_0", _m("public Constructors()", PUB, "", javadoc="No arguments.")),
        ("Constructors_constructor_1", _m("protected Constructors(int a)", ["protected"], "",
                                          ["int a"], "Protected one.")),
        ("Constructors_constructor_2", _m("private Constructors(int a, int b)", ["private"], "",
                                          ["int a", "int b"], "Private one.")),
        ("Constructors_constructor_3", _m("Constructors(String s, int a, int b)", [], "",
                                          ["String s", "int a", "int b"], "Private one.")),
    ],

    # --- intentional fixes (KNOWN_DEVIATIONS) ---
    "ParenInJavadoc.java": [
        ("getX", _m("public float getX()", PUB, "float", javadoc=ZURUECK_DOC)),
        ("setX", _m("public void setX(float x)", PUB, "void", ["float x"], ZURUECK_DOC)),
    ],
    "MethodInComment.java": [
        ("real", _m("public void real()", PUB, "void")),
    ],
    "PackagePrivateVoid.java": [
        ("update", _m("void update()", [], "void")),
        ("count", _m("int count()", [], "int")),
        ("name", _m("String name()", [], "String")),
        ("visible", _m("public void visible()", PUB, "void")),
    ],
    "DeprecatedMethod.java": [
        ("old", _m("public void old()", PUB, "void")),
        ("toString", _m("Override public String toString()", PUB, "String")),
        ("current", _m("public void current()", PUB, "void")),
    ],
    "SecondTopLevelMethods.java": [
        ("mine", _m("public void mine()", PUB, "void")),
    ],
    "CommentInParams.java": [
        ("CommentInParams_constructor_1", _m("public CommentInParams(int size)", PUB, "",
                                             ["int size"])),
        ("move", _m("public void move(int dx, int dy)", PUB, "void", ["int dx", "int dy"])),
        ("scale", _m("public void scale(float factor)", PUB, "void", ["float factor"])),
    ],
    "LineCommentBeforeMethod.java": [
        ("reset", _m("public void reset()", PUB, "void")),
        ("getScore", _m("public int getScore()", PUB, "int")),
        ("block", _m("public void block()", PUB, "void")),
    ],
    "NestedConstructor.java": [
        ("NestedConstructor_constructor_0", _m("public NestedConstructor()", PUB, "")),
        ("start", _m("public void start()", PUB, "void")),
    ],
    "AnonymousSelf.java": [
        ("AnonymousSelf_constructor_0", _m("public AnonymousSelf()", PUB, "")),
        ("create", _m("public static AnonymousSelf create()", ["public", "static"], "AnonymousSelf")),
        ("toString", _m("Override public String toString()", PUB, "String")),
    ],
}

# Intentional fixes of regex bugs (A3-n in .andrei/results/compat_report.md). "regex" pins the
# visible fields the regex parser returns today, so a change in regex behaviour is noticed too.
KNOWN_DEVIATIONS = {
    "ParenInJavadoc.java": {
        "regex": [
            ("zurück", _v("Wert des Objektes zurück(also den linken Rand des Bildes * * @return "
                          "x-Wert des Objektes */ public float getX()",
                          ["also den linken Rand des Bildes * * @return x-Wert des Objektes */ "
                           "public float getX("])),
            ("setX", _v("public void setX(float x)", ["float x"], ZURUECK_DOC)),
        ],
        "reason": "`word(` inside a javadoc starts a phantom method that swallows getX up to its `) {`",
    },
    "MethodInComment.java": {
        "regex": [
            ("MethodInComment_constructor_1", _v("public MethodInComment(int x)", ["int x"])),
            ("ghost", _v("public void ghost()")),
            ("oldScore", _v("public int oldScore(int level)", ["int level"])),
            ("real", _v("public void real()")),
            ("gone", _v("abstract public void gone()", abstract=True)),
        ],
        "reason": "the patterns run over comments and string literals",
    },
    "PackagePrivateVoid.java": {
        "regex": [("name", _v("String name()")), ("visible", _v("public void visible()"))],
        "reason": "is_valid_method drops a method whose whole return type group is a primitive / void",
    },
    "DeprecatedMethod.java": {
        "regex": [("old", _v("Deprecated public void old()")),
                  ("toString", _v("Deprecated public String toString()")),
                  ("current", _v("public void current()"))],
        "reason": "the return type group starts after the last `@`: the last marker annotation "
                  "gets into the signature",
    },
    "SecondTopLevelMethods.java": {
        "regex": [("mine", _v("public void mine()")),
                  ("SecondTopLevelHelper", _v("public SecondTopLevelHelper()")),
                  ("theirs", _v("public void theirs()"))],
        "reason": "the patterns run over the whole file: methods (and the constructor, as a "
                  "method) of the second top-level type",
    },
    "CommentInParams.java": {
        "regex": [("CommentInParams_constructor_1", _v("public CommentInParams(int size /* in px */)",
                                                      ["int size /* in px */"])),
                  ("move", _v("public void move(int dx /* pixels */, int dy)",
                              ["int dx /* pixels */", "int dy"]))],
        "reason": "comments stay in the parameters; a comment between `)` and `{` loses the method",
    },
    "LineCommentBeforeMethod.java": {
        "regex": [("reset", _v("resets the score public void reset()")),
                  ("getScore", _v("public int getScore()")),
                  ("block", _v("public void block()"))],
        "reason": "the return type group starts inside the line comment before the method",
    },
    "NestedConstructor.java": {
        "regex": [("NestedConstructor_constructor_0", _v("public NestedConstructor()")),
                  ("Inner", _v("public Inner(int x)", ["int x"])),
                  ("start", _v("public void start()"))],
        "reason": "METHOD_CONCRETE_PAT takes the constructor of a nested class for a method "
                  "`Inner` with return type `public`",
    },
    "AnonymousSelf.java": {
        "regex": [("AnonymousSelf_constructor_0", _v("AnonymousSelf()")),
                  ("create", _v("public static AnonymousSelf create()")),
                  ("toString", _v("Override public String toString()"))],
        "reason": "CONSTRUCTOR_PAT takes `new AnonymousSelf() {` for a constructor and overwrites "
                  "the real one",
    },
}

# Type parameters of generic methods (in the regex return type, not in the AST one; decision 8).
TYPE_PARAMETERS = {
    ("GenericMethods.java", "first"): "<T>",
    ("GenericMethods.java", "mapOf"): "<K, V>",
    ("GenericMethods.java", "create"): "<T>",
}


def _read(directory, name):
    with open(os.path.join(directory, name), encoding="utf-8") as f:
        return f.read()


def _methods(parse, directory, name):
    result = parse(_read(directory, name), name)
    return None if result is None else result["methods"]


def _six(methods):
    return [(k, {f: e[f] for f in ENTRY_KEYS[:6]}) for k, e in methods.items()]


def _visible(methods):
    return [(k, {f: e[f] for f in VISIBLE}) for k, e in methods.items()]


def test_every_sample_has_expectation():
    assert sorted(os.listdir(SAMPLES_DIR)) == sorted(EXPECTED)
    assert set(KNOWN_DEVIATIONS) <= set(EXPECTED)


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_expected(name):
    assert _six(_methods(java_ast.analyze_java_file_ast, SAMPLES_DIR, name)) == EXPECTED[name]


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_matches_regex_except_known_deviations(name):
    regex = _visible(_methods(Context_gen.analyze_java_file, SAMPLES_DIR, name))
    ast = _visible(_methods(java_ast.analyze_java_file_ast, SAMPLES_DIR, name))
    if name in KNOWN_DEVIATIONS:
        assert regex == KNOWN_DEVIATIONS[name]["regex"], "regex behaviour changed"
        assert ast != regex
    else:
        assert ast == regex


def _decision_8_regex_fields(sample, key, ast):
    """(modifiers, return_type) that regex writes for an AST entry (decision 8):
    method with a body: modifiers [], return_type = [Override] + modifiers + <T> + type;
    abstract method: modifiers public / protected / abstract / static in this order,
                     return_type = <T> + type;
    constructor: the same as AST."""
    if key.endswith(f"_constructor_{len(ast['params'])}") and ast["return_type"] == "":
        return ast["modifiers"], ""
    tparams = TYPE_PARAMETERS.get((sample, key), "")
    if ast["abstract"]:
        mods = [m for m in ("public", "protected", "abstract", "static") if m in ast["modifiers"]]
        return mods, " ".join(w for w in (tparams, ast["return_type"]) if w)
    override = ["Override"] if ast["signature"].startswith("Override ") else []
    return [], " ".join(override + ast["modifiers"] + [w for w in (tparams, ast["return_type"]) if w])


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_decision_8_rule(name):
    # modifiers / return_type differ from regex only by the rule above (keys both parsers have).
    regex = _methods(Context_gen.analyze_java_file, SAMPLES_DIR, name)
    ast = _methods(java_ast.analyze_java_file_ast, SAMPLES_DIR, name)
    common = [k for k in ast if k in regex and regex[k]["signature"] == ast[k]["signature"]]
    assert common or name in KNOWN_DEVIATIONS
    for key in common:
        expected = _decision_8_regex_fields(name, key, ast[key])
        assert (regex[key]["modifiers"], regex[key]["return_type"]) == expected, key


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_entry_shape(name):
    content = _read(SAMPLES_DIR, name)
    ast = java_ast.analyze_java_file_ast(content, name)["methods"]
    regex = Context_gen.analyze_java_file(content, name)["methods"]
    for key, entry in ast.items():
        assert list(entry) == ENTRY_KEYS
        if key in regex:
            assert list(entry) == list(regex[key])
        assert isinstance(entry["abstract"], bool)
        assert all(isinstance(m, str) for m in entry["modifiers"])
        assert isinstance(entry["return_type"], str)
        assert all(isinstance(p, str) for p in entry["params"])
        assert isinstance(entry["signature"], str) and isinstance(entry["javadoc"], str)
        for field in PINNED_BODY_FIELDS:         # filled in A5
            assert entry[field] == []


# A1 / A2 samples where the methods differ on purpose; "regex" pins the visible regex output.
OTHER_KNOWN_DEVIATIONS = {
    "a1/TwoTopLevel.java": {
        "regex": [("first", _v("public void first()")), ("run", _v("public void run()"))],
        "reason": "methods of the second top-level type (as SecondTopLevelMethods.java)",
    },
    "a1/Broken.java": {
        "regex": [],
        "reason": "`run( {` is a syntax error: tree-sitter recovers the method (JavaParseWarning), "
                  "regex does not see it",
    },
}


def _other_samples():
    return [(d, n) for d in OTHER_SAMPLE_DIRS for n in sorted(os.listdir(d))]


def _sample_id(directory, name):
    return f"{os.path.basename(directory)}/{name}"


@pytest.mark.parametrize("directory, name", _other_samples(),
                         ids=[_sample_id(d, n) for d, n in _other_samples()])
def test_a1_a2_samples_match_regex(directory, name):
    # A1 / A2 samples: where both parsers return a module, the visible method fields agree
    # (nested and second top-level types, enums, generics, comments, broken code).
    regex = _methods(Context_gen.analyze_java_file, directory, name)
    ast = _methods(java_ast.analyze_java_file_ast, directory, name)
    if regex is None or ast is None:
        return
    known = OTHER_KNOWN_DEVIATIONS.get(_sample_id(directory, name))
    if known is not None:
        assert _visible(regex) == known["regex"], "regex behaviour changed"
        assert _visible(ast) != _visible(regex)
    else:
        assert _visible(ast) == _visible(regex)


def test_other_known_deviations_exist():
    ids = {_sample_id(d, n) for d, n in _other_samples()}
    assert set(OTHER_KNOWN_DEVIATIONS) <= ids


def test_javadoc_pattern_is_the_regex_one():
    assert java_ast.JAVADOC_PAT.pattern == Context_gen.JAVADOC_PAT.pattern
    assert java_ast.JAVADOC_PAT.flags == Context_gen.JAVADOC_PAT.flags


def _window_sample(decl, filler_len, ch):
    """A javadoc, then a line comment of `filler_len` characters `ch` that ends with `;` (so the
    regex match of a method starts after it), then the declaration."""
    return ("public abstract class Foo {\n    /** Größe der Welt. */\n"
            "    // " + ch * filler_len + ";\n    " + decl + "\n}\n")


DECLS = [
    "public void foo() {\n    }",
    "@Override\n    public String toString() {\n        return \"\";\n    }",
    "public Foo(int a) {\n    }",
    "Foo() {\n    }",
    "protected abstract void bar();",
    "abstract public static void baz();",
]


@pytest.mark.parametrize("decl", DECLS)
def test_javadoc_window_in_characters(decl):
    # The 400-character window counts characters, not bytes. Around the edge of the window AST
    # and regex agree for every filler length, and the edge (the first length where the javadoc
    # is no longer found) is the same for ASCII and for non-ASCII filler.
    edges = {}
    for ch in ("a", "ä"):
        found = []
        for n in range(360, 400):
            content = _window_sample(decl, n, ch)
            regex = Context_gen.analyze_java_file(content, "Foo.java")["methods"]
            ast = java_ast.analyze_java_file_ast(content, "Foo.java")["methods"]
            assert _visible(ast) == _visible(regex), (ch, n)
            found.append([e["javadoc"] for e in ast.values()] == ["Größe der Welt."])
        assert found[0] and not found[-1], "the window edge is not inside the tested range"
        edges[ch] = found.index(False)
    assert edges["a"] == edges["ä"]


def test_constructor_at_line_start_and_after_comment():
    # CONSTRUCTOR_PAT needs whitespace (or a line start) before the access modifier.
    content = ("class Foo {\n/** A. */\npublic Foo() {\n}\n/** B. */public Foo(int a) {\n}\n}\n")
    regex = Context_gen.analyze_java_file(content, "Foo.java")["methods"]
    ast = java_ast.analyze_java_file_ast(content, "Foo.java")["methods"]
    assert [(k, e["javadoc"]) for k, e in ast.items()] == [
        ("Foo_constructor_0", "A."), ("Foo_constructor_1", "B.")]
    assert [(k, e["javadoc"]) for k, e in ast.items()] == [(k, e["javadoc"]) for k, e in regex.items()]
