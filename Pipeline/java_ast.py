"""Tree-sitter based Java parser: drop-in replacement for Context_gen.analyze_java_file.

analyze_java_file_ast(content, filename) returns the same dict (same keys, same key order,
same value types) as the regex parser, so the rest of Context_gen (flatten_inheritance,
split_contexts, subtypes, combine, slice) works unchanged.

Stage A of the migration: reproduce the regex rules, except for documented regex bugs
(see the test list KNOWN_DEVIATIONS in tests/test_java_ast.py).

Filled so far:
    A1  module, package, type, parent, implements
    A2  fields, constants, assets
To do:
    A3  methods and constructors (signatures, javadoc)
    A4  calls
    A5  logic_hints, values_hint

Parse errors: tree-sitter always returns a tree, even for broken code. If the tree has errors,
analyze_java_file_ast issues a JavaParseWarning (file name, line:column of each error). An error
inside the header of the main type (before its body) makes the header unreliable, so the file is
skipped (None), as the regex parser does when it cannot match a class. An error elsewhere (e.g. in
a method body) keeps the result. Strict mode: warnings.simplefilter("error", JavaParseWarning).
"""
import re
import warnings

import tree_sitter_java as tsj
from tree_sitter import Language, Parser

JAVA = Language(tsj.language())
_PARSER = Parser(JAVA)

# Top-level declarations the regex parser recognises (CLASS_PAT: class|interface|enum).
TYPE_DECLS = ("class_declaration", "interface_declaration", "enum_declaration")
TYPE_KEYWORDS = {
    "class_declaration": "class",
    "interface_declaration": "interface",
    "enum_declaration": "enum",
}

# Comments are "extras" in tree-sitter: they can appear between any two tokens, also inside
# type lists and qualified names.
COMMENT_TYPES = ("line_comment", "block_comment")
# Cut out of a type name: type arguments, comments, annotations (`@NonNull Bar` -> `Bar`).
_SKIPPED_IN_NAMES = ("type_arguments", "marker_annotation", "annotation") + COMMENT_TYPES

_WS = re.compile(r"\s+")

# How many error positions a warning lists before "...".
_MAX_LISTED_ERRORS = 5


class JavaParseWarning(UserWarning):
    """tree-sitter found syntax errors in a Java file."""


# --- helpers -----------------------------------------------------------------

def parse(content):
    """Parse Java source text. Returns (tree, src_bytes); node offsets are byte offsets in src."""
    src = content.encode("utf-8")
    return _PARSER.parse(src), src


def node_text(node, src):
    return src[node.start_byte:node.end_byte].decode("utf-8")


def type_name(node, src):
    """Type or package name without type arguments, comments, annotations and whitespace:
    `Base<String>` -> `Base`, `javax.swing.JPanel` -> `javax.swing.JPanel`,
    `Outer<A>.Inner` -> `Outer.Inner`, `@NonNull Bar` -> `Bar`, `a. /* x */ b` -> `a.b`."""
    parts = []
    pos = node.start_byte
    for start, end in _skipped_spans(node):
        parts.append(src[pos:start])
        pos = end
    parts.append(src[pos:node.end_byte])
    return _WS.sub("", b"".join(parts).decode("utf-8"))


def _skipped_spans(node):
    """Byte spans of the outermost nodes inside `node` that are not part of a name
    (_SKIPPED_IN_NAMES), in source order."""
    spans = []
    stack = [node]
    while stack:
        cur = stack.pop()
        if cur.type in _SKIPPED_IN_NAMES:
            spans.append((cur.start_byte, cur.end_byte))
            continue
        stack.extend(cur.children)
    return sorted(spans)


def _non_comment_children(node):
    return [c for c in node.named_children if c.type not in COMMENT_TYPES]


def parse_errors(root):
    """Syntax errors in the tree: list of (node, kind), kind "ERROR" (unexpected text) or
    "MISSING" (token inserted by the parser), in source order. ERROR nodes are not descended."""
    errors = []
    stack = [root]
    while stack:
        cur = stack.pop()
        if cur.is_error:
            errors.append((cur, "ERROR"))
            continue
        if cur.is_missing:
            errors.append((cur, "MISSING"))
            continue
        if cur.has_error:
            stack.extend(cur.children)
    return sorted(errors, key=lambda e: e[0].start_byte)


def _header_has_error(type_node, errors):
    """True if an error lies inside the header of `type_node` (from its start to its body)."""
    body = type_node.child_by_field_name("body")
    header_end = type_node.end_byte if body is None or body.is_missing else body.start_byte
    return any(type_node.start_byte <= node.start_byte < header_end for node, _ in errors)


def _warn_parse_errors(filename, errors, skipped):
    listed = ", ".join(f"{kind} at {node.start_point[0] + 1}:{node.start_point[1] + 1}"
                       for node, kind in errors[:_MAX_LISTED_ERRORS])
    more = ", ..." if len(errors) > _MAX_LISTED_ERRORS else ""
    tail = "; error in the class header, file skipped" if skipped else ""
    warnings.warn(f"{filename}: {len(errors)} parse error(s) ({listed}{more}){tail}",
                  JavaParseWarning, stacklevel=3)


# --- A1: class header ----------------------------------------------------------

def extract_package(root, src):
    """Package name, "" if there is no package declaration (as regex)."""
    for child in root.named_children:
        if child.type == "package_declaration":
            for sub in child.named_children:
                if sub.type in ("scoped_identifier", "identifier"):
                    return type_name(sub, src)  # drops comments inside `a. /* x */ b`
    return ""


def find_main_type(root):
    """First top-level class/interface/enum declaration, or None.

    Unlike regex (first `class|interface|enum Name` match anywhere in the text), comments,
    nested types and later top-level types are never picked up.
    """
    for child in root.named_children:
        if child.type in TYPE_DECLS:
            return child
    return None


def _modifier_keywords(type_node):
    for child in type_node.children:
        if child.type == "modifiers":
            return {m.type for m in child.children}
    return set()


def extract_type_kind(type_node):
    """"class" | "abstract class" | "abstract interface" | "enum" (as regex: an interface is
    always reported as abstract)."""
    kw = TYPE_KEYWORDS[type_node.type]
    if kw == "interface" or "abstract" in _modifier_keywords(type_node):
        return f"abstract {kw}"
    return kw


def _type_list(node):
    """Types of a super_interfaces / extends_interfaces node (children of its type_list),
    without the comments between them."""
    for child in node.named_children:
        if child.type == "type_list":
            return _non_comment_children(child)
    return []


def extract_parent(type_node, src):
    """Superclass name without type arguments, or None.

    Interface `extends Bar, Baz` -> "Bar" (regex compatibility, decision 9: the other
    super-interfaces are lost; to be revisited in stage B).
    """
    superclass = type_node.child_by_field_name("superclass")
    if superclass is not None:
        types = _non_comment_children(superclass)  # `extends /* base */ Bar`
        if types:
            return type_name(types[0], src)
    for child in type_node.children:
        if child.type == "extends_interfaces":
            types = _type_list(child)
            if types:
                return type_name(types[0], src)
    return None


def extract_implements(type_node, src):
    """Implemented interface names without type arguments (decision 10), [] if none."""
    interfaces = type_node.child_by_field_name("interfaces")
    if interfaces is None:
        return []
    return [type_name(t, src) for t in _type_list(interfaces)]


# --- A2: fields, constants, assets -------------------------------------------------
#
# Fields and constants are taken from the main type, including its nested, enum, anonymous and
# local classes (as regex, which runs over the whole text; decision 17.11, to be revisited in B3),
# but not from other top-level types, comments or string literals (fixes A2-n).
#
# Functions named _regex_compat_* repeat regex bugs that occur in the 4 games and reach the
# model (decision 17.11). Each one is removed separately in stage B4, with a measurement.

ACCESS_MODIFIERS = ("public", "protected", "private")
FIELD_DECLS = ("field_declaration", "constant_declaration")   # constant_declaration: interface body
ANNOTATION_TYPES = ("marker_annotation", "annotation")

# Same pattern as Context_gen.ASSET_PAT (a test checks this).
ASSET_PAT = re.compile(r'"([^"]+\.(?:png|jpg|wav|mp3|gif|ttf))"')

# Names Context_gen.analyze_java_file never reports as fields (plus any one-letter name).
_REGEX_SKIPPED_FIELD_NAMES = frozenset({
    "int", "void", "boolean", "String", "true", "false", "null", "new", "return", "class"})

# Context_gen.CONST_PAT: constant value cut to this many characters.
_CONST_VALUE_MAX = 60


def _iter_nodes(node, types, descend_into_matches=True):
    """Nodes of the given types inside `node`, in source order (pre-order)."""
    stack = [node]
    while stack:
        cur = stack.pop()
        if cur.type in types:
            yield cur
            if not descend_into_matches:
                continue
        stack.extend(reversed(cur.children))


def _clean_span(src, start, end, scope):
    """Source text between byte offsets `start`..`end` without comments, whitespace collapsed
    (as Context_gen.clean_type). `scope` is a node that contains the span (comments are looked
    up inside it)."""
    parts = []
    pos = start
    for c in _iter_nodes(scope, COMMENT_TYPES):
        if start <= c.start_byte and c.end_byte <= end:
            parts.append(src[pos:c.start_byte])
            pos = c.end_byte
    parts.append(src[pos:end])
    return _WS.sub(" ", b"".join(parts).decode("utf-8")).strip()


def _clean_node(node, src):
    return _clean_span(src, node.start_byte, node.end_byte, node)


def _modifier_tokens(decl):
    """Modifier keywords of a declaration in source order; annotations and comments left out."""
    for child in decl.children:
        if child.type == "modifiers":
            return [m.type for m in child.children if not m.is_named]
    return []


def _declarators(decl):
    return [c for c in decl.children if c.type == "variable_declarator"]


def _dimensions(declarator, src):
    """C-style brackets after the name (`int grid[]` -> `[]`), "" if none."""
    for c in declarator.children:
        if c.type == "dimensions":
            return _clean_node(c, src).replace(" ", "")
    return ""


def _regex_compat_declarator(declarators):
    """regex compat -> B4. FIELD_PAT keeps one declarator of `int a, b = 1, c;`: the first one
    with an initializer, otherwise the last one; the others are lost."""
    for d in declarators:
        if d.child_by_field_name("value") is not None:
            return d
    return declarators[-1]


def _regex_compat_type_modifiers(tokens):
    """regex compat -> B4. FIELD_PAT starts at the access modifier and then skips an optional
    `static`, `final`, `static`; the modifiers after that become part of the type
    (`private volatile boolean` -> `volatile boolean`). Modifiers before the access modifier
    are not seen."""
    access = next(i for i, t in enumerate(tokens) if t in ACCESS_MODIFIERS)
    rest = tokens[access + 1:]
    for kw in ("static", "final", "static"):
        if rest and rest[0] == kw:
            rest = rest[1:]
    return rest


def _regex_compat_field_type(decl, declarator, tokens, src):
    """regex compat -> B4. Field type as FIELD_PAT reports it: modifiers left in the type
    (_regex_compat_type_modifiers) + the text from the type to the name of the kept declarator,
    so `int a, b;` gives `int a,` for `b`.

    Fix (A2-n): with C-style brackets on the kept declarator (`int grid[]`) regex loses the field;
    here the type is the declared type plus the brackets (`int[]`)."""
    type_node = decl.child_by_field_name("type")
    dims = _dimensions(declarator, src)
    if dims:
        text = _clean_node(type_node, src) + dims
    else:
        name = declarator.child_by_field_name("name")
        text = _clean_span(src, type_node.start_byte, name.start_byte, decl)
    return " ".join(_regex_compat_type_modifiers(tokens) + [text])


def _regex_compat_field_name_ok(name):
    """regex compat -> B4. analyze_java_file drops one-letter names (`x`, `y`) and a few words."""
    return len(name) >= 2 and name not in _REGEX_SKIPPED_FIELD_NAMES


def _regex_compat_is_constant(tokens):
    """regex compat -> B4. CONST_PAT needs the modifiers in the order `public static final`
    (`public final static` is not a constant). Annotations and comments between them do not
    matter (fix A2-n: regex loses such a constant)."""
    return any(tokens[i:i + 3] == ["public", "static", "final"] for i in range(len(tokens)))


def _regex_compat_constant_value(value, src):
    """regex compat -> B4. CONST_PAT value: raw text from the initializer to the first `;`, even
    inside a string literal (`"a;b"` -> `"a`) or past the next declarator (`1, MAX = 9`),
    stripped, at most 60 characters."""
    end = src.find(b";", value.start_byte)
    if end == -1:
        end = value.end_byte
    return src[value.start_byte:end].decode("utf-8").strip()[:_CONST_VALUE_MAX]


def extract_fields_and_constants(type_node, src):
    """(fields, constants) of the main type, as Context_gen.analyze_java_file builds them:
    fields {name: type}: declarations with an access modifier (package-private and interface
    fields without written modifiers are skipped, as regex);
    constants {name: {"type", "value"}}: `public static final` with an initializer; only the first
    declarator (regex compat). A repeated name keeps its first position and the last value."""
    fields, constants = {}, {}
    for decl in _iter_nodes(type_node, FIELD_DECLS):
        declarators = _declarators(decl)
        if not declarators:
            continue
        tokens = _modifier_tokens(decl)
        if any(t in ACCESS_MODIFIERS for t in tokens):
            kept = _regex_compat_declarator(declarators)
            name = node_text(kept.child_by_field_name("name"), src)
            if _regex_compat_field_name_ok(name):
                fields[name] = _regex_compat_field_type(decl, kept, tokens, src)
        if _regex_compat_is_constant(tokens):
            first = declarators[0]
            value = first.child_by_field_name("value")
            if value is not None:
                ctype = _clean_node(decl.child_by_field_name("type"), src) + _dimensions(first, src)
                constants[node_text(first.child_by_field_name("name"), src)] = {
                    "type": ctype, "value": _regex_compat_constant_value(value, src)}
    return fields, constants


def extract_assets(root, src):
    """Asset file names (ASSET_PAT) from the string literals of the whole file, without repeats,
    in order of first occurrence (decision 11). Fix (A2-n): regex also takes them from comments."""
    found = []
    for lit in _iter_nodes(root, ("string_literal",), descend_into_matches=False):
        found.extend(ASSET_PAT.findall(node_text(lit, src)))
    return list(dict.fromkeys(found))


# --- entry point -----------------------------------------------------------------

def analyze_java_file_ast(content, filename):
    """Same contract as Context_gen.analyze_java_file: dict for the main type, or None.

    `filename` is only used in parse warnings (the regex version ignores it).
    On syntax errors issues a JavaParseWarning; returns None if an error is in the header of
    the main type (see the module docstring).
    """
    tree, src = parse(content)
    root = tree.root_node
    type_node = find_main_type(root)
    if root.has_error:
        errors = parse_errors(root)
        skipped = type_node is not None and _header_has_error(type_node, errors)
        _warn_parse_errors(filename, errors, skipped)
        if skipped:
            return None
    if type_node is None:
        return None

    name = type_node.child_by_field_name("name")
    fields, constants = extract_fields_and_constants(type_node, src)
    return {
        "module":     node_text(name, src),
        "package":    extract_package(root, src),
        "type":       extract_type_kind(type_node),
        "parent":     extract_parent(type_node, src),
        "implements": extract_implements(type_node, src),
        "fields":     fields,
        "constants":  constants,
        "assets":     extract_assets(root, src),
        "methods":    {},   # A3-A5
    }
