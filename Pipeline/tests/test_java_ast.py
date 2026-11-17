"""Tests for Pipeline/java_ast.py (tree-sitter parser), stage A1: class header.

Four kinds of checks:
1. EXPECTED: the five A1 fields for every sample, written by hand.
2. Regex comparison: AST must equal Context_gen.analyze_java_file on every sample, except the
   intentional fixes listed in KNOWN_DEVIATIONS (where the regex output is pinned too).
   Any other difference fails the test.
3. Shape: same keys, same key order and same value types as the regex dict.
4. Parse errors: a JavaParseWarning exactly for the samples in EXPECT_PARSE_WARNING.
"""
import os
import warnings

import pytest

import Context_gen
import java_ast

SAMPLES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "java_samples", "a1")
A1_FIELDS = ("module", "package", "type", "parent", "implements")

# Parse warnings are checked by the test_parse_warning* tests; elsewhere they are expected noise.
pytestmark = pytest.mark.filterwarnings("ignore::java_ast.JavaParseWarning")


def _header(module, package, type_, parent, implements):
    return {"module": module, "package": package, "type": type_,
            "parent": parent, "implements": implements}


# Expected AST output (A1 fields only). None = file has no top-level type.
EXPECTED = {
    "SimpleClass.java":          _header("SimpleClass", "org.example.game", "class", None, []),
    "NoPackage.java":            _header("NoPackage", "", "class", None, []),
    "AbstractChild.java":        _header("AbstractChild", "org.example.game", "abstract class",
                                         "Base", ["Runnable", "KeyListener"]),
    "AbstractPublicOrder.java":  _header("AbstractPublicOrder", "org.example.game", "abstract class",
                                         "Base", []),
    "Shape.java":                _header("Shape", "org.example.geom", "abstract interface", None, []),
    # Decision 9: interface `extends Shape, Comparable<...>` -> parent = first one (regex compatibility).
    "ExtendingInterface.java":   _header("ExtendingInterface", "org.example.geom", "abstract interface",
                                         "Shape", []),
    "Color.java":                _header("Color", "org.example.ui", "enum", None, ["Runnable"]),
    "MultilineImplements.java":  _header("MultilineImplements", "org.example.ui", "abstract class",
                                         "JComponent", ["MouseListener", "KeyListener"]),
    "QualifiedParent.java":      _header("QualifiedParent", "org.example.ui", "class",
                                         "javax.swing.JPanel", ["java.io.Serializable"]),
    # Decision 10: type arguments are dropped in parent and implements.
    "GenericParent.java":        _header("GenericParent", "org.example.util", "class",
                                         "ArrayList", ["Comparable"]),
    "GenericBound.java":         _header("GenericBound", "org.example.util", "class", "Base", []),
    "CommentMentionsClass.java": _header("CommentMentionsClass", "org.example.game", "class", "Base", []),
    "NestedClass.java":          _header("NestedClass", "org.example.game", "class", None, []),
    "TwoTopLevel.java":          _header("TwoTopLevel", "org.example.game", "class", None, []),
    "OneLetter.java":            _header("A", "org.example.game", "class", "Base", []),
    "Annotated.java":            _header("Annotated", "org.example.ui", "class", "JPanel", []),
    "NoType.java":               None,
    # Annotation types (@interface) are not context modules in stage A (known difference A1-L4).
    "AnnotationType.java":       None,
    "AnnotationTypeSpaced.java": None,
    "Broken.java":              _header("Broken", "org.example.game", "class", "Base", ["Runnable"]),
    # Review 2026-11-16, 3.1: comments and annotations inside extends / implements are not names.
    "CommentInImplements.java":      _header("CommentInImplements", "org.example.game", "class",
                                             "Base", ["Runnable", "KeyListener"]),
    "BlockCommentInImplements.java": _header("BlockCommentInImplements", "org.example.game", "class",
                                             None, ["Runnable", "KeyListener"]),
    "CommentAfterExtends.java":      _header("CommentAfterExtends", "org.example.game", "class",
                                             "Base", ["Runnable"]),
    "CommentInQualifiedParent.java": _header("CommentInQualifiedParent", "org.example.game", "class",
                                             "javax.swing.JPanel", []),
    "AnnotatedSupertype.java":       _header("AnnotatedSupertype", "org.example.game", "class",
                                             "Base", ["Comparable"]),
    "InterfaceExtendsComment.java":  _header("InterfaceExtendsComment", "org.example.game",
                                             "abstract interface", "Shape", []),
    # Review 3.2: parse errors. An error in the header of the main type -> file skipped (as regex);
    # an error before the type or in a body keeps the header. All of them warn (EXPECT_PARSE_WARNING).
    "BrokenHeader.java":             None,
    "BrokenBeforeReal.java":         _header("Real", "org.example.game", "class", "Base", []),
    "UnclosedComment.java":          _header("UnclosedComment", "org.example.game", "class", "Base", []),
    # Review 3.3: regex bugs that compat_report.md did not list.
    "PackageInComment.java":         _header("PackageInComment", "org.example.game", "class", None, []),
    "Bom.java":                      _header("Bom", "org.example.game", "class", "Base", []),
    "ClassInAnnotationString.java":  _header("ClassInAnnotationString", "org.example.game", "class",
                                             "Base", []),
    "LowercaseName.java":            _header("lowercaseName", "org.example.game", "class", "Base", []),
    "UnderscoreName.java":           _header("_Underscore", "org.example.game", "class", "Base", []),
}

# Samples with syntax errors: the parser must warn on exactly these.
# Value: True if the error is in the header of the main type, so the file is skipped.
# AnnotationTypeSpaced.java is legal Java (`@ interface`), but the tree-sitter-java grammar does
# not accept a space after `@`: a grammar limitation; the result (None: no class/interface/enum)
# is the same as without the error.
EXPECT_PARSE_WARNING = {
    "Broken.java":               False,
    "BrokenHeader.java":         True,
    "BrokenBeforeReal.java":     False,
    "UnclosedComment.java":      False,
    "AnnotationTypeSpaced.java": False,
}

# Intentional fixes of regex bugs: the only samples where AST may differ from regex.
# "regex" pins what the regex parser returns today (A1 fields, or None), so a change in regex
# behaviour is noticed too. Keep in sync with .andrei/results/compat_report.md.
KNOWN_DEVIATIONS = {
    "AbstractPublicOrder.java": {
        "regex": _header("AbstractPublicOrder", "org.example.game", "class", "Base", []),
        "reason": "CLASS_PAT keeps only the last modifier, so `abstract public` loses `abstract`",
    },
    "GenericParent.java": {
        "regex": _header("GenericParent", "org.example.util", "class", "ArrayList", []),
        "reason": "IMPLEMENTS_PAT cannot pass `<`, so `implements Comparable<...>` gives []",
    },
    "GenericBound.java": {
        "regex": _header("GenericBound", "org.example.util", "class", "Comparable", []),
        "reason": "EXTENDS_PAT takes the first `extends` in the file: the type parameter bound",
    },
    "CommentMentionsClass.java": {
        "regex": _header("Helper", "org.example.game", "class", "nothing", []),
        "reason": "CLASS_PAT and EXTENDS_PAT match words inside the javadoc",
    },
    "NestedClass.java": {
        "regex": _header("NestedClass", "org.example.game", "class", "Thread", ["Runnable"]),
        "reason": "EXTENDS_PAT / IMPLEMENTS_PAT match the nested class header",
    },
    "TwoTopLevel.java": {
        "regex": _header("TwoTopLevel", "org.example.game", "class", "Base", ["Runnable"]),
        "reason": "EXTENDS_PAT / IMPLEMENTS_PAT match the second top-level type",
    },
    "OneLetter.java": {
        "regex": None,
        "reason": "CLASS_PAT requires a name of 2+ chars starting with A-Z, so the file is dropped",
    },
    # Known difference, not a fix (A1-L4, to be decided in stage B): regex skips the usual
    # `@interface` (no whitespace before `interface`), same as AST, but takes `@ interface`.
    "AnnotationTypeSpaced.java": {
        "regex": _header("AnnotationTypeSpaced", "org.example.game", "abstract interface", None, []),
        "reason": "CLASS_PAT matches `interface` after whitespace, so `@ interface` looks like an interface",
    },
    # Review 2026-11-16, 3.1 and 3.3 (A1-8 ... in compat_report.md).
    "CommentInImplements.java": {
        "regex": _header("CommentInImplements", "org.example.game", "class", "Base", []),
        "reason": "IMPLEMENTS_PAT cannot pass a comment, so the whole implements list is lost",
    },
    "BlockCommentInImplements.java": {
        "regex": _header("BlockCommentInImplements", "org.example.game", "class", None, []),
        "reason": "IMPLEMENTS_PAT cannot pass a comment, so the whole implements list is lost",
    },
    "CommentAfterExtends.java": {
        "regex": _header("CommentAfterExtends", "org.example.game", "class", None, ["Runnable"]),
        "reason": "EXTENDS_PAT expects the name right after `extends`; a comment in between loses parent",
    },
    "CommentInQualifiedParent.java": {
        "regex": _header("CommentInQualifiedParent", "org.example.game", "class", "javax.", []),
        "reason": "EXTENDS_PAT stops at the comment, so the qualified name is cut",
    },
    "AnnotatedSupertype.java": {
        "regex": _header("AnnotatedSupertype", "org.example.game", "class", None, []),
        "reason": "EXTENDS_PAT / IMPLEMENTS_PAT cannot pass a type annotation (`@NonNull Base`)",
    },
    "InterfaceExtendsComment.java": {
        "regex": _header("InterfaceExtendsComment", "org.example.game", "abstract interface", None, []),
        "reason": "EXTENDS_PAT expects the name right after `extends`; a comment in between loses parent",
    },
    "PackageInComment.java": {
        "regex": _header("PackageInComment", "org.example.old", "class", None, []),
        "reason": "PACKAGE_PAT matches a package line inside a block comment",
    },
    "Bom.java": {
        "regex": _header("Bom", "", "class", "Base", []),
        "reason": "PACKAGE_PAT does not match when a BOM stands before `package`",
    },
    "ClassInAnnotationString.java": {
        "regex": _header("Zed", "org.example.game", "class", "Qux", []),
        "reason": "CLASS_PAT and EXTENDS_PAT match words inside a string literal",
    },
    "LowercaseName.java": {
        "regex": None,
        "reason": "CLASS_PAT requires a name starting with A-Z, so the file is dropped",
    },
    "UnderscoreName.java": {
        "regex": None,
        "reason": "CLASS_PAT requires a name starting with A-Z, so the file is dropped",
    },
}


def _read(name):
    with open(os.path.join(SAMPLES_DIR, name), encoding="utf-8") as f:
        return f.read()


def _a1(result):
    return None if result is None else {k: result[k] for k in A1_FIELDS}


def test_every_sample_has_expectation():
    assert sorted(os.listdir(SAMPLES_DIR)) == sorted(EXPECTED)
    assert set(KNOWN_DEVIATIONS) <= set(EXPECTED)
    assert set(EXPECT_PARSE_WARNING) <= set(EXPECTED)


def test_bom_sample_starts_with_bom():
    # The point of Bom.java; an editor could silently drop the BOM.
    assert _read("Bom.java").startswith("\ufeffpackage ")


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_parse_warning(name):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        java_ast.analyze_java_file_ast(_read(name), name)
    parse_warnings = [w for w in caught if issubclass(w.category, java_ast.JavaParseWarning)]
    if name in EXPECT_PARSE_WARNING:
        assert len(parse_warnings) == 1
        message = str(parse_warnings[0].message)
        assert message.startswith(f"{name}: ")
        assert ("file skipped" in message) == EXPECT_PARSE_WARNING[name]
    else:
        assert parse_warnings == []


def test_parse_warning_positions():
    # Broken.java: `public void run( {` (missing `)`) on line 4, `int x = ;` on line 5.
    with pytest.warns(java_ast.JavaParseWarning,
                      match=r"^Broken\.java: 2 parse error\(s\) \(MISSING at 4:\d+, ERROR at 5:\d+\)$"):
        java_ast.analyze_java_file_ast(_read("Broken.java"), "Broken.java")


def test_strict_mode_turns_warning_into_error():
    with warnings.catch_warnings():
        warnings.simplefilter("error", java_ast.JavaParseWarning)
        with pytest.raises(java_ast.JavaParseWarning):
            java_ast.analyze_java_file_ast(_read("BrokenHeader.java"), "BrokenHeader.java")


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_expected_header(name):
    assert _a1(java_ast.analyze_java_file_ast(_read(name), name)) == EXPECTED[name]


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_matches_regex_except_known_deviations(name):
    content = _read(name)
    regex = _a1(Context_gen.analyze_java_file(content, name))
    ast = _a1(java_ast.analyze_java_file_ast(content, name))
    if name in KNOWN_DEVIATIONS:
        assert regex == KNOWN_DEVIATIONS[name]["regex"], "regex behaviour changed"
        assert ast != regex
    else:
        assert ast == regex


@pytest.mark.parametrize("name", sorted(n for n, e in EXPECTED.items() if e is not None))
def test_dict_shape(name):
    content = _read(name)
    ast = java_ast.analyze_java_file_ast(content, name)
    regex = Context_gen.analyze_java_file(content, name)
    if regex is not None:
        assert list(ast) == list(regex)  # same keys, same order (order goes into the JSON)
    assert list(ast) == ["module", "package", "type", "parent", "implements",
                         "fields", "constants", "assets", "methods"]
    assert isinstance(ast["module"], str) and ast["module"]
    assert isinstance(ast["package"], str)
    assert isinstance(ast["type"], str)
    assert ast["parent"] is None or isinstance(ast["parent"], str)
    assert isinstance(ast["implements"], list)
    assert all(isinstance(i, str) for i in ast["implements"])
    # Not filled until A2-A5, but already of the regex types.
    assert ast["fields"] == {} and ast["constants"] == {}
    assert ast["assets"] == [] and ast["methods"] == {}


def test_empty_source_returns_none():
    assert java_ast.analyze_java_file_ast("", "Empty.java") is None


def test_non_ascii_before_declaration():
    # Node offsets are bytes; text before the class must not shift the extracted names.
    content = "// Комментарий: ünïcödé\npackage a.b;\npublic class Foo extends Bar implements Baz {}\n"
    assert _a1(java_ast.analyze_java_file_ast(content, "Foo.java")) == _header(
        "Foo", "a.b", "class", "Bar", ["Baz"])


@pytest.mark.parametrize("decl, expected", [
    ("class X extends Map<String, List<Integer>> {}", "Map"),
    ("class X extends Outer<A>.Inner<B> {}", "Outer.Inner"),
    ("class X extends a.b.C<D> {}", "a.b.C"),
])
def test_type_arguments_are_dropped(decl, expected):
    assert java_ast.analyze_java_file_ast(decl, "X.java")["parent"] == expected


@pytest.mark.parametrize("decl, expected", [
    ("class X extends a. /* x */ b.C {}", "a.b.C"),
    ("class X extends a.b // c\n .C {}", "a.b.C"),
    ("class X extends @a.B(1) Bar {}", "Bar"),
    ("class X extends @A Baz<@B T> {}", "Baz"),
    ("class X extends Outer.@A Inner {}", "Outer.Inner"),
])
def test_comments_and_annotations_are_dropped_from_names(decl, expected):
    assert java_ast.analyze_java_file_ast(decl, "X.java")["parent"] == expected


def test_comment_inside_package_name():
    content = "package a. /* x */ b;\nclass Foo {}\n"
    assert java_ast.analyze_java_file_ast(content, "Foo.java")["package"] == "a.b"


def test_no_warning_for_valid_code():
    with warnings.catch_warnings():
        warnings.simplefilter("error", java_ast.JavaParseWarning)
        assert java_ast.analyze_java_file_ast("class Foo extends Bar {}", "Foo.java")["parent"] == "Bar"
