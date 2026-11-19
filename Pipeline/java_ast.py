"""Tree-sitter based Java parser: drop-in replacement for Context_gen.analyze_java_file.

analyze_java_file_ast(content, filename) returns the same dict (same keys, same key order,
same value types) as the regex parser, so the rest of Context_gen (flatten_inheritance,
split_contexts, subtypes, combine, slice) works unchanged.

Stage A of the migration: reproduce the regex rules, except for documented regex bugs
(see the test list KNOWN_DEVIATIONS in tests/test_java_ast.py).

Filled so far:
    A1  module, package, type, parent, implements
    A2  fields, constants, assets
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


# --- A3: methods and constructors (without bodies) ---------------------------------
#
# Methods are taken from the main type, including its nested, enum, anonymous and local classes
# (as regex, B3), but not from other top-level types, comments or string literals (fixes A3-n).
# The dict is built in three passes in the regex order, because the key order goes into
# `method_signatures` of S:
#   1. constructors of the main type      key `Name_constructor_<number of params>`
#   2. methods with a body                key = name; abstract False
#   3. methods without a body + `abstract` key = name; abstract True, overwrite pass 2
# A repeated key keeps its first position and gets the last value (overloads and constructors of
# the same arity overwrite each other, as regex; B2). A method named like the module is skipped.
# Interface methods without `abstract` and `native` methods are not taken (as regex, B1).
#
# `modifiers` and `return_type` are written correctly (decision 8, 16.11): the model does not see
# them. `signature` and `javadoc` are visible to the model and repeat regex (_regex_compat_*).

# Same pattern as Context_gen.JAVADOC_PAT (a test checks this).
JAVADOC_PAT = re.compile(r'/\*\*.*?\*/', re.DOTALL)
_JAVADOC_WINDOW = 400      # Context_gen.get_javadoc_before: characters searched before the match
_JAVADOC_MAX = 120         # ... and length of the cleaned javadoc
_JAVADOC_JUNK = re.compile(r'[\n\r\t/*]+')
# METHOD_CONCRETE_PAT: the modifiers and the return type are made of these characters only.
_CONCRETE_PREFIX_CHAR = re.compile(r'[\w<>\[\].,\s]')
# METHOD_ABSTRACT_PAT: the match starts with a chain of these words before `abstract`.
_ABSTRACT_CHAIN_WORD = re.compile(r'(?:public|protected|abstract|static)\s+$')
_ABSTRACT_CHAIN_LOOKBACK = 200
# METHOD_ABSTRACT_PAT: modifiers that reach the abstract signature, in this order.
_ABSTRACT_SIGNATURE_MODIFIERS = ("public", "protected", "static")
PARAM_TYPES = ("formal_parameter", "spread_parameter", "receiver_parameter")


def _char_pos(src, content, byte_pos):
    """Node offsets are bytes in UTF-8; the regex parser works with character offsets."""
    if len(src) == len(content):        # ASCII only
        return byte_pos
    return len(src[:byte_pos].decode("utf-8"))


def _child_of_type(node, type_):
    return next((c for c in node.children if c.type == type_), None)


def _params(decl, src):
    """Parameter texts without comments, whitespace collapsed (= Context_gen.clean_params on
    normal code). Fix (A3-n): regex keeps comments that are inside the parameter list."""
    params = decl.child_by_field_name("parameters")
    return [_clean_node(p, src) for p in params.named_children if p.type in PARAM_TYPES]


def _return_type(decl, src):
    """Declared return type; C-style brackets after the parameters (`int foo()[]`) are added."""
    text = _clean_node(decl.child_by_field_name("type"), src)
    dims = decl.child_by_field_name("dimensions")
    return text + (_clean_node(dims, src).replace(" ", "") if dims is not None else "")


def _type_parameters(decl, src):
    tp = decl.child_by_field_name("type_parameters")
    return _clean_node(tp, src) if tp is not None else ""


def _has_override(decl, src):
    mods = _child_of_type(decl, "modifiers")
    return mods is not None and any(
        c.type == "marker_annotation" and node_text(c.child_by_field_name("name"), src) == "Override"
        for c in mods.children)


def _regex_compat_signature(decl, tokens, name, params, src):
    """regex compat -> B7. Signature of a method with a body as METHOD_CONCRETE_PAT builds it: its
    return type group starts after `@` of the annotation, so `Override` comes first
    (`Override public void init()`). Modifiers in source order, then `<T>` and the return type.
    Fix (A3-n): other marker annotations (`@Deprecated`), comments and words of a line comment
    before the method do not get into the signature."""
    words = (["Override"] if _has_override(decl, src) else []) + tokens
    words += [w for w in (_type_parameters(decl, src), _return_type(decl, src)) if w]
    return f"{' '.join(words)} {name}({', '.join(params)})"


def _regex_compat_abstract_signature(decl, tokens, name, params, src):
    """regex compat -> B7. Signature of an abstract method as Context_gen builds it: `abstract`,
    then public / protected / static in this fixed order, then `<T>` and the return type. Without
    other modifiers there are two spaces after `abstract` (`abstract  int score()`)."""
    mods = " ".join(m for m in _ABSTRACT_SIGNATURE_MODIFIERS if m in tokens)
    ret = " ".join(w for w in (_type_parameters(decl, src), _return_type(decl, src)) if w)
    return f"abstract {mods} {ret} {name}({', '.join(params)})".strip()


def _concrete_match_start(content, name_pos):
    """Where METHOD_CONCRETE_PAT starts its match: right after the last character before the name
    that cannot be part of the modifiers / return type group (`@`, `)`, `/`, `;`, `{`, `}`, ...)."""
    pos = name_pos
    while pos > 0 and _CONCRETE_PREFIX_CHAR.match(content, pos - 1):
        pos -= 1
    return pos


def _constructor_match_start(content, access_pos, access_end, name_pos):
    """Where CONSTRUCTOR_PAT `(?:^|\\s)((?:public|protected|private)\\s+)?Name(` starts its match:
    the whitespace character before the access modifier (or before the name if there is no
    modifier right before it)."""
    if (access_pos is not None and access_end < name_pos and content[access_end:name_pos].isspace()
            and (access_pos == 0 or content[access_pos - 1].isspace())):
        return max(access_pos - 1, 0)
    if name_pos > 0 and content[name_pos - 1].isspace():
        return name_pos - 1
    return name_pos


def _abstract_match_start(content, abstract_pos):
    """Where METHOD_ABSTRACT_PAT starts its match: the first word of the chain
    `public|protected|abstract|static` (separated by whitespace) that ends with `abstract`."""
    pos = abstract_pos
    while True:
        m = _ABSTRACT_CHAIN_WORD.search(content, max(0, pos - _ABSTRACT_CHAIN_LOOKBACK), pos)
        if m is None:
            return pos
        pos = m.start()


def _regex_compat_javadoc(content, match_start):
    """regex compat -> B10 (Context_gen.get_javadoc_before): the last `/** */` that lies entirely in
    the 400 characters before the position where the regex match starts, cleaned, at most 120
    characters. It may belong to a neighbouring method, and a long javadoc is not found."""
    preceding = content[max(0, match_start - _JAVADOC_WINDOW):match_start]
    matches = list(JAVADOC_PAT.finditer(preceding))
    if not matches:
        return ""
    return _JAVADOC_JUNK.sub(" ", matches[-1].group(0)).strip()[:_JAVADOC_MAX]


def _method_entry(abstract, modifiers, return_type, params, signature, javadoc, calls,
                  logic_hints, values_hint):
    """Same keys in the same order as Context_gen."""
    return {
        "abstract": abstract,
        "modifiers": modifiers,
        "return_type": return_type,
        "params": params,
        "signature": signature,
        "javadoc": javadoc,
        "calls": calls,
        "logic_hints": logic_hints,
        "values_hint": values_hint,
    }


def _modifier_node_pos(decl, keywords, src, content):
    """(start, end) character offsets of the first modifier token of `decl` in `keywords`,
    or (None, None)."""
    mods = _child_of_type(decl, "modifiers")
    if mods is not None:
        for c in mods.children:
            if c.type in keywords:
                return _char_pos(src, content, c.start_byte), _char_pos(src, content, c.end_byte)
    return None, None


def extract_methods(type_node, module, src, content, known_fields):
    """Methods and constructors of the main type, as Context_gen.analyze_java_file builds them
    (three passes, see the comment above); `calls` from A4, `logic_hints` (only fields in
    `known_fields`) and `values_hint` from A5."""
    decls = list(_iter_nodes(type_node, ("constructor_declaration", "method_declaration")))
    methods = {}

    for decl in decls:                                       # pass 1: constructors
        if decl.type != "constructor_declaration":
            continue
        name_node = decl.child_by_field_name("name")
        if node_text(name_node, src) != module:
            continue
        tokens = _modifier_tokens(decl)
        params = _params(decl, src)
        access_pos, access_end = _modifier_node_pos(decl, ACCESS_MODIFIERS, src, content)
        start = _constructor_match_start(content, access_pos, access_end,
                                         _char_pos(src, content, name_node.start_byte))
        methods[f"{module}_constructor_{len(params)}"] = _method_entry(
            False, tokens, "", params, " ".join(tokens + [f"{module}({', '.join(params)})"]),
            _regex_compat_javadoc(content, start), extract_calls(decl, src),
            extract_logic_hints(decl, src, known_fields), extract_values_hint(decl, src))

    for decl in decls:                                       # pass 2: methods with a body
        if decl.type != "method_declaration" or decl.child_by_field_name("body") is None:
            continue
        name_node = decl.child_by_field_name("name")
        name = node_text(name_node, src)
        if name == module:
            continue
        tokens = _modifier_tokens(decl)
        params = _params(decl, src)
        start = _concrete_match_start(content, _char_pos(src, content, name_node.start_byte))
        methods[name] = _method_entry(
            False, tokens, _return_type(decl, src), params,
            _regex_compat_signature(decl, tokens, name, params, src),
            _regex_compat_javadoc(content, start), extract_calls(decl, src),
            extract_logic_hints(decl, src, known_fields), extract_values_hint(decl, src))

    for decl in decls:                                       # pass 3: abstract methods
        if decl.type != "method_declaration" or decl.child_by_field_name("body") is not None:
            continue
        tokens = _modifier_tokens(decl)
        name = node_text(decl.child_by_field_name("name"), src)
        if "abstract" not in tokens or name == module:
            continue
        params = _params(decl, src)
        abstract_pos, _ = _modifier_node_pos(decl, ("abstract",), src, content)
        methods[name] = _method_entry(
            True, tokens, _return_type(decl, src), params,
            _regex_compat_abstract_signature(decl, tokens, name, params, src),
            _regex_compat_javadoc(content, _abstract_match_start(content, abstract_pos)), [], [], [])

    return methods


# --- A4: calls ---------------------------------------------------------------------
#
# `calls` of a method or constructor: the calls in its body, written as Context_gen writes them
# (`receiver.name`, without repeats, sorted). Unlike regex, which runs CALL_PAT `(\w+)\.(\w+)\(`
# over the body text cut out by counting braces, only AST nodes are read, so calls in comments and
# string literals are not taken and braces in comments / literals do not move the end of the body
# (fixes A4-1..A4-4, decision 17.11). Calls of nested, anonymous and local classes and lambdas
# also go to the enclosing method (as regex, B3); an abstract method has none.
# What regex can and cannot see is repeated by the _regex_compat_* functions below
# (B5b; the receiver filter: B5a).

# Context_gen.extract_method_calls drops calls on these receivers (a test checks the tuple).
REGEX_CALL_FILTER = ('this', 'super', 'self', 'Math', 'System', 'String', 'Integer', 'Boolean',
                     'Object')
_CALL_NODES = ("method_invocation", "object_creation_expression")
_WORD = re.compile(r"\w+")
_WORD_SUFFIX = re.compile(r"\w+$")


def _regex_compat_receiver(obj, src):
    """regex compat -> B5b. (receiver, node that ends with it): the name CALL_PAT sees right before
    the dot. identifier -> its text; field access -> the field (`this.x.foo()` -> `x`,
    `System.out.println()` -> `out`, `Outer.this.foo()` -> `this`); this / super -> `this` /
    `super`; class literal `X.class` -> `class`. (None, None) for what regex cannot see: chains
    `a().foo()`, `arr[i].foo()`, `(x).foo()`, `new X().foo()`, literals, no receiver at all."""
    if obj is None:
        return None, None
    if obj.type in ("identifier", "this", "super"):
        last = obj
    elif obj.type == "field_access":
        last = obj.child_by_field_name("field")
    elif obj.type == "class_literal":
        return "class", obj
    else:
        return None, None
    m = _WORD_SUFFIX.search(node_text(last, src))     # `a$b` -> `b`, as `(\w+)`
    return (m.group(), last) if m else (None, None)


def _regex_compat_adjacent(last, name, src):
    """regex compat -> B5b. CALL_PAT needs `receiver.name(` written without anything in between:
    a space, line break, comment or type arguments (`x.<T>foo(`) lose the call."""
    return (src[last.end_byte:name.start_byte] == b"."
            and src[name.end_byte:name.end_byte + 1] == b"("
            and _WORD.fullmatch(node_text(name, src)) is not None)


def _regex_compat_qualified_new(node, src):
    """regex compat -> B5b. A constructor call with a qualified type is taken by CALL_PAT for a
    method call: `new Rectangle2D.Float(...)` -> ("Rectangle2D", "Float"), `new java.awt.Point()`
    -> ("awt", "Point"). None for a simple or generic type (`new Point(`, `new a.B<T>(`)."""
    type_node = node.child_by_field_name("type")
    if type_node is None or type_node.type != "scoped_type_identifier":
        return None
    parts = _non_comment_children(type_node)
    prefix, name = parts[0], parts[-1]
    if prefix.type == "scoped_type_identifier":
        prefix = _non_comment_children(prefix)[-1]
    if prefix.type != "type_identifier" or not _regex_compat_adjacent(prefix, name, src):
        return None
    m = _WORD_SUFFIX.search(node_text(prefix, src))
    return (m.group(), node_text(name, src)) if m else None


def _regex_compat_receiver_dropped(receiver):
    """regex compat -> B5a. Context_gen.extract_method_calls drops calls on this / super and on a
    few receiver names (REGEX_CALL_FILTER), also when they are variables."""
    return receiver in REGEX_CALL_FILTER


def _call_candidates(body, src):
    """(receiver, method name) of every call in `body` that CALL_PAT would see, before the
    receiver filter, in source order (with repeats)."""
    for node in _iter_nodes(body, _CALL_NODES):
        if node.type == "object_creation_expression":
            pair = _regex_compat_qualified_new(node, src)
            if pair is not None:
                yield pair
            continue
        name = node.child_by_field_name("name")
        receiver, last = _regex_compat_receiver(node.child_by_field_name("object"), src)
        if receiver is not None and _regex_compat_adjacent(last, name, src):
            yield receiver, node_text(name, src)


def extract_calls(decl, src):
    """`calls` of a method or constructor declaration: `receiver.name`, unique, sorted; [] without
    a body."""
    body = decl.child_by_field_name("body")
    if body is None:
        return []
    return sorted({f"{receiver}.{name}" for receiver, name in _call_candidates(body, src)
                   if not _regex_compat_receiver_dropped(receiver)})


# --- A5: logic_hints, values_hint ------------------------------------------------------
#
# Context_gen runs two patterns over the body text (cut out by counting braces):
#   logic_hints  ASSIGN_PAT `(this\.\w+)\s*=\s*([^;\n]{1,60})` -> "field = expr", only fields in
#                known_fields, repeats kept, at most 4;
#   values_hint  NUMERIC_PAT `\b(\d{2,5})\b` -> numbers without repeats, in order of first
#                occurrence, at most 6 (decision 11).
# Here the candidates come from AST nodes of the body: `this.f` field accesses and literals. So
# comments (decision 19.11, fix A5-1) and string literals are not searched, and the body ends where
# the method ends (decision 17.11, as in A4). What regex sees in the 4 games is repeated by the
# _regex_compat_* functions below (removed in stage B11, with a measurement).

# Context_gen.ASSIGN_PAT is `(this\.\w+)` + this pattern (a test checks it).
_ASSIGN_TAIL = re.compile(r'\s*=\s*([^;\n]{1,60})')
# The expression after the `=` of an assignment regex cannot see (fix A5-n): same text rule.
_ASSIGN_EXPR = re.compile(r'\s*([^;\n]{1,60})')
# Same pattern as Context_gen.NUMERIC_PAT (a test checks this).
NUMERIC_PAT = re.compile(r'\b(\d{2,5})\b')
_MAX_LOGIC_HINTS = 4     # Context_gen.extract_logic_hints: hints[:4]
_MAX_VALUES = 6          # Context_gen.analyze_java_file: [:6]
_NUMBER_LITERALS = ("decimal_integer_literal", "hex_integer_literal", "octal_integer_literal",
                    "binary_integer_literal", "decimal_floating_point_literal",
                    "hex_floating_point_literal")
_TEXT_LITERALS = ("string_literal", "character_literal")


def _body_text(body, src):
    """(text of the body, function: byte offset in src -> character offset in that text).
    The regex parser matches on the body text, so positions are characters of the body."""
    raw = src[body.start_byte:body.end_byte]
    text = raw.decode("utf-8")
    if len(raw) == len(text):        # ASCII only
        return text, lambda byte_pos: byte_pos - body.start_byte
    return text, lambda byte_pos: len(raw[:byte_pos - body.start_byte].decode("utf-8"))


def _regex_compat_this_token(field_access):
    """regex compat -> B11. The `this` that ASSIGN_PAT sees before the field: `this.f`, and also
    `Outer.this.f` (a field of the outer class written from an anonymous class; 11 in the games).
    None for other objects (`other.f`, `this.a.f`, `super.f`)."""
    obj = field_access.child_by_field_name("object")
    if obj is None:
        return None
    if obj.type == "this":
        return obj
    if obj.type == "field_access":
        last = obj.child_by_field_name("field")
        if last is not None and last.type == "this":
            return last
    return None


def _regex_compat_assign_tail(text, pos):
    """regex compat -> B11. ASSIGN_PAT after `this.name` (`pos` = right after the name): `=` with
    optional whitespace around it (line breaks too), then the expression = raw text up to the first
    `;` or line end, at most 60 characters. So `this.f == x` is taken as `f = = x) {` (252 hints
    in the games), a long expression is cut, the text may run past the expression (`) {`) and a
    `;` inside a string literal cuts it (`"a;b"` -> `"a`). Returns the match or None."""
    return _ASSIGN_TAIL.match(text, pos)


def _plain_assignment_operator(field_access):
    """The `=` token of `field_access = ...` (not `+=` etc.), or None."""
    parent = field_access.parent
    if (parent is None or parent.type != "assignment_expression"
            or parent.child_by_field_name("left") != field_access):
        return None
    op = parent.child_by_field_name("operator")
    return op if op is not None and op.type == "=" else None


def extract_logic_hints(decl, src, known_fields):
    """`logic_hints` of a method or constructor: "field = expr" for `this.field = expr` in the body,
    as Context_gen.extract_logic_hints (only fields in `known_fields`, repeats kept, at most 4);
    [] without a body.

    regex compat -> B11 (_regex_compat_*): `Outer.this.f`, `this.f == x`, the expression text, and
    the non-overlapping matches of findall: a candidate that starts inside the text of the previous
    match is skipped (`this.a == 1 || this.a == 2` gives one hint; 38 in the games), also when the
    previous match was not kept by the known_fields filter.
    Fixes: nothing from comments (A5-1) or string literals; `this . f = 1` and `this.f /* c */ = 1`
    are taken (A5-n: regex cannot see them)."""
    body = decl.child_by_field_name("body")
    if body is None:
        return []
    text, char_pos = _body_text(body, src)
    hints, consumed = [], 0
    for fa in _iter_nodes(body, ("field_access",)):
        this = _regex_compat_this_token(fa)
        if this is None or char_pos(this.start_byte) < consumed:
            continue
        field = fa.child_by_field_name("field")
        m = None
        if src[this.end_byte:field.start_byte] == b".":
            m = _regex_compat_assign_tail(text, char_pos(field.end_byte))
        if m is None:
            op = _plain_assignment_operator(fa)
            if op is None:
                continue
            m = _ASSIGN_EXPR.match(text, char_pos(op.end_byte))
            if m is None:
                continue
        consumed = m.end()
        name = node_text(field, src)
        if name in known_fields:
            hints.append(f"{name} = {m.group(1).strip()}")
    return hints[:_MAX_LOGIC_HINTS]


def _regex_compat_numbers(literal_text):
    """regex compat -> B11. NUMERIC_PAT over the text of one literal: numbers of 2-5 digits, also
    inside string literals (`"200"` -> `200`) and the parts of a decimal number (`1000.0` -> `1000`,
    `0.004` -> `004`); a literal with a suffix (`100f`, `10L`) gives nothing."""
    return NUMERIC_PAT.findall(literal_text)


def extract_values_hint(decl, src):
    """`values_hint` of a method or constructor: the numbers of its number, string and character
    literals (_regex_compat_numbers), without repeats, in order of first occurrence, at most 6
    (decision 11); [] without a body. Fix A5-1: numbers in comments are not taken."""
    body = decl.child_by_field_name("body")
    if body is None:
        return []
    found = []
    for lit in _iter_nodes(body, _NUMBER_LITERALS + _TEXT_LITERALS, descend_into_matches=False):
        found.extend(_regex_compat_numbers(node_text(lit, src)))
    return list(dict.fromkeys(found))[:_MAX_VALUES]


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

    module = node_text(type_node.child_by_field_name("name"), src)
    fields, constants = extract_fields_and_constants(type_node, src)
    return {
        "module":     module,
        "package":    extract_package(root, src),
        "type":       extract_type_kind(type_node),
        "parent":     extract_parent(type_node, src),
        "implements": extract_implements(type_node, src),
        "fields":     fields,
        "constants":  constants,
        "assets":     extract_assets(root, src),
        # known_fields = the field names (as Context_gen: the same set as the keys of `fields`)
        "methods":    extract_methods(type_node, module, src, content, set(fields)),
    }
