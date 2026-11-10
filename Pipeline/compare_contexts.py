#!/usr/bin/env python3
"""Compare two directories of generated context JSONs (e.g. regex vs AST parser output).

Usage:
    python Pipeline/compare_contexts.py <dir_old> <dir_new> [--out report.md] [--max-examples N]

Files are paired by name (<Game>_<Kind>.json, top level of each directory only).
For every pair the tool reports:
  * modules / methods / fields / constants added or removed,
  * value differences in every field; lists are compared as multisets, except the
    ones whose order carries meaning (ORDERED_LISTS, e.g. method params),
  * order-only differences (same items or keys, different order) - not a content
    change, but it changes the bytes the LLM sees, so it is reported separately,
  * schema differences (missing / extra keys in a record, changed value types),
  * token counts of the file text, which is what run.py uploads to the model
    (cl100k_base via tiktoken: an OpenAI tokenizer, so a comparable estimate, not Gemini's count).
    Line endings are normalized to LF first: the repository stores LF, but a Windows checkout
    (core.autocrlf) or a Windows run of Context_gen.py writes CRLF, and the count must not
    depend on the OS.

The report is Markdown, written to --out or to stdout. Exit code is 0 whether or not
differences were found; it is non-zero only on usage or input errors.
"""

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass

# Record keys whose value is a map of named entities (name -> value), not a fixed record.
ENTITY_MAPS = {"fields", "constants", "methods", "capabilities", "methods_execution"}
# Keys that hold a module's methods (one per context kind), used for the method counts.
METHOD_MAPS = {"methods", "capabilities", "methods_execution"}
METHOD_LISTS = {"method_signatures"}
# Lists whose order is meaningful and therefore compared as sequences.
ORDERED_LISTS = {"params"}
# Category of the top-level entries (one per Java class).
MODULE_CATEGORY = "(module)"

CONTENT_KINDS = ("removed", "added", "changed", "items")
ORDER_KINDS = ("order", "key_order")
SCHEMA_KINDS = ("keys", "type")
KIND_ORDER = CONTENT_KINDS + ORDER_KINDS + SCHEMA_KINDS
KIND_TITLES = {
    "removed": "entry removed",
    "added": "entry added",
    "changed": "value changed",
    "items": "list items differ",
    "order": "list order only",
    "key_order": "key order only",
    "keys": "record keys missing/extra",
    "type": "value type changed",
}
CONTEXT_KINDS = ("Structural", "Functional", "Behavioral", "Context")
DETAIL_LIMIT = 300


@dataclass
class Diff:
    category: str  # path with entity names replaced by [*], e.g. "methods[*].calls"
    kind: str  # one of KIND_ORDER
    where: str  # concrete location, e.g. "ApoBotApplet.methods[init].calls"
    detail: str = ""
    n_removed: int = 0  # entries / list items present only in the old file
    n_added: int = 0  # entries / list items present only in the new file


# ---------------------------------------------------------------- diffing

def _type_name(value):
    return "null" if value is None else type(value).__name__


def _short(value):
    text = json.dumps(value, ensure_ascii=False)
    return text if len(text) <= DETAIL_LIMIT else text[:DETAIL_LIMIT] + "..."


def _child(where, key):
    return f"{where}.{key}" if where else key


def _sub_category(category, key):
    return key if category == MODULE_CATEGORY else f"{category}.{key}"


def compare_entity_map(old, new, where, category, out):
    """Compare two name -> value maps (modules, methods, fields, constants...)."""
    def entry(name):
        return name if not where else f"{where}[{name}]"

    for name in old:
        if name not in new:
            out.append(Diff(category, "removed", entry(name), n_removed=1))
    for name in new:
        if name not in old:
            out.append(Diff(category, "added", entry(name), n_added=1))
    common_old = [k for k in old if k in new]
    common_new = [k for k in new if k in old]
    if common_old != common_new:
        out.append(Diff(category, "key_order", where or "(top level)",
                        f"{len(common_old)} common entries in a different order"))
    for name in common_old:
        compare_value(old[name], new[name], entry(name), category, out)


def compare_record(old, new, where, category, out):
    """Compare two fixed-schema records (a module, a method, a constant)."""
    missing = [k for k in old if k not in new]
    extra = [k for k in new if k not in old]
    if missing or extra:
        out.append(Diff(category, "keys", where,
                        f"missing {missing}; extra {extra}",
                        n_removed=len(missing), n_added=len(extra)))
    common_old = [k for k in old if k in new]
    common_new = [k for k in new if k in old]
    if common_old != common_new:
        out.append(Diff(category, "key_order", where, f"{common_old} -> {common_new}"))
    for key in common_old:
        sub_where = _child(where, key)
        sub_category = _sub_category(category, key)
        o, n = old[key], new[key]
        if key in ENTITY_MAPS and isinstance(o, dict) and isinstance(n, dict):
            compare_entity_map(o, n, sub_where, sub_category + "[*]", out)
        else:
            compare_value(o, n, sub_where, sub_category, out, field=key)


def compare_list(old, new, where, category, out, field=None):
    if field in ORDERED_LISTS:
        if old != new:
            out.append(Diff(category, "changed", where, f"{_short(old)} -> {_short(new)}"))
        return
    old_items = Counter(json.dumps(x, sort_keys=True) for x in old)
    new_items = Counter(json.dumps(x, sort_keys=True) for x in new)
    removed = old_items - new_items
    added = new_items - old_items
    if removed or added:
        parts = []
        if removed:
            parts.append("- " + _short(sorted(json.loads(x) for x in removed.elements())))
        if added:
            parts.append("+ " + _short(sorted(json.loads(x) for x in added.elements())))
        out.append(Diff(category, "items", where, " ".join(parts),
                        n_removed=sum(removed.values()), n_added=sum(added.values())))
    elif old != new:
        out.append(Diff(category, "order", where, "same items, different order"))


def compare_value(old, new, where, category, out, field=None):
    if _type_name(old) != _type_name(new):
        out.append(Diff(category, "type", where,
                        f"{_type_name(old)} -> {_type_name(new)}: {_short(old)} -> {_short(new)}"))
    elif isinstance(old, dict):
        compare_record(old, new, where, category, out)
    elif isinstance(old, list):
        compare_list(old, new, where, category, out, field=field)
    elif old != new:
        out.append(Diff(category, "changed", where, f"{_short(old)} -> {_short(new)}"))


def compare_contexts(old, new):
    """Return the list of differences between two loaded context JSON objects."""
    if not isinstance(old, dict) or not isinstance(new, dict):
        raise ValueError("a context file must contain a JSON object at the top level")
    out = []
    compare_entity_map(old, new, "", MODULE_CATEGORY, out)
    return out


def count_methods(data):
    """Method entries over all modules, including '(inherited from X)' copies."""
    total = 0
    for module in data.values():
        if isinstance(module, dict):
            for key in METHOD_MAPS:
                if isinstance(module.get(key), dict):
                    total += len(module[key])
            for key in METHOD_LISTS:
                if isinstance(module.get(key), list):
                    total += len(module[key])
    return total


# ---------------------------------------------------------------- tokens

_ENCODER = None


def count_tokens(text):
    """cl100k_base token count. No len//4 fallback, so numbers stay comparable."""
    global _ENCODER
    if _ENCODER is None:
        try:
            import tiktoken
        except ImportError:
            sys.exit("ERROR: tiktoken is not installed. Token counts require the cl100k_base "
                     "tokenizer; no len//4 fallback is used so numbers stay comparable. "
                     "Install: python -m pip install -r Pipeline/requirements-ast.txt")
        _ENCODER = tiktoken.get_encoding("cl100k_base")
    return len(_ENCODER.encode(text, disallowed_special=()))


# ---------------------------------------------------------------- files

@dataclass
class FileResult:
    name: str
    identical_bytes: bool
    modules: tuple  # (old, new)
    methods: tuple  # (old, new)
    tokens: tuple  # (old, new)
    diffs: list


def _lf(text):
    return text.replace("\r\n", "\n")


def _read(path):
    with open(path, "rb") as f:
        raw = f.read()
    try:
        text = raw.decode("utf-8")
        return raw, text, json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        sys.exit(f"ERROR: cannot parse {path}: {e}")


def compare_files(old_path, new_path):
    old_raw, old_text, old = _read(old_path)
    new_raw, new_text, new = _read(new_path)
    try:
        diffs = compare_contexts(old, new)
    except ValueError as e:
        sys.exit(f"ERROR: {old_path} / {new_path}: {e}")
    return FileResult(
        name=os.path.basename(old_path),
        identical_bytes=old_raw == new_raw,
        modules=(len(old), len(new)),
        methods=(count_methods(old), count_methods(new)),
        tokens=(count_tokens(_lf(old_text)), count_tokens(_lf(new_text))),
        diffs=diffs,
    )


def _json_files(directory):
    return sorted(f for f in os.listdir(directory)
                  if f.endswith(".json") and os.path.isfile(os.path.join(directory, f)))


def compare_dirs(old_dir, new_dir):
    old_files, new_files = _json_files(old_dir), _json_files(new_dir)
    paired = [f for f in old_files if f in new_files]
    results = [compare_files(os.path.join(old_dir, f), os.path.join(new_dir, f)) for f in paired]
    only_old = [f for f in old_files if f not in new_files]
    only_new = [f for f in new_files if f not in old_files]
    return results, only_old, only_new


# ---------------------------------------------------------------- report

def _kind_of_file(name):
    stem = name[:-len(".json")]
    return stem.rsplit("_", 1)[-1] if "_" in stem else stem


def _delta(old, new):
    d = new - old
    pct = f"{d / old * 100:+.1f}%" if old else "n/a"
    return f"{d:+,}", pct


def _group(diffs):
    """(category, kind) -> list of diffs, in a stable order."""
    groups = defaultdict(list)
    for d in diffs:
        groups[(d.category, d.kind)].append(d)
    return sorted(groups.items(), key=lambda kv: (kv[0][0], KIND_ORDER.index(kv[0][1])))


def _count(diffs, kinds):
    return sum(1 for d in diffs if d.kind in kinds)


def render_report(old_dir, new_dir, results, only_old, only_new, max_examples=10):
    lines = []
    w = lines.append
    total_diffs = sum(len(r.diffs) for r in results)
    identical = total_diffs == 0 and not only_old and not only_new

    w("# Context comparison")
    w("")
    w(f"- Old: `{old_dir}`")
    w(f"- New: `{new_dir}`")
    w(f"- Paired files: {len(results)}; only in old: {len(only_old)}; only in new: {len(only_new)}")
    w("- Tokens: cl100k_base (tiktoken) over the file text, i.e. what run.py uploads, with line "
      "endings normalized to LF (OS-independent). OpenAI tokenizer: a comparable estimate, "
      "not Gemini's exact count.")
    w("- Methods: entries in `methods` / `capabilities` / `methods_execution` / `method_signatures`, "
      "including `(inherited from X)` copies (not the number of methods declared in source). "
      "\"Same bytes\" compares the raw files (CRLF vs LF counts as different).")
    w("- Lists are compared as multisets, except " + ", ".join(f"`{k}`" for k in sorted(ORDERED_LISTS))
      + " (ordered). Order-only differences are counted separately.")
    w("")
    if identical:
        w("**Result: no differences** (all paired files match, including order).")
    else:
        w(f"**Result: {total_diffs} difference(s)** in "
          f"{sum(1 for r in results if r.diffs)} of {len(results)} paired file(s)"
          + (f"; unpaired files: {len(only_old) + len(only_new)}" if only_old or only_new else "")
          + ".")
    w("")

    if only_old or only_new:
        w("## Unpaired files")
        w("")
        for f in only_old:
            w(f"- only in old: `{f}`")
        for f in only_new:
            w(f"- only in new: `{f}`")
        w("")

    if results:
        w("## Summary")
        w("")
        w("| File | Same bytes | Modules old → new | Methods old → new "
          "| Content diffs | Order-only | Schema |")
        w("|---|---|---|---|---|---|---|")
        for r in results:
            w(f"| {r.name} | {'yes' if r.identical_bytes else 'no'} "
              f"| {r.modules[0]:,} → {r.modules[1]:,} | {r.methods[0]:,} → {r.methods[1]:,} "
              f"| {_count(r.diffs, CONTENT_KINDS):,} | {_count(r.diffs, ORDER_KINDS):,} "
              f"| {_count(r.diffs, SCHEMA_KINDS):,} |")
        w("")

        w("## Tokens (cl100k_base)")
        w("")
        w("| File | Old | New | Δ | Δ % |")
        w("|---|---:|---:|---:|---:|")
        per_kind = defaultdict(lambda: [0, 0])
        for r in results:
            d, pct = _delta(*r.tokens)
            w(f"| {r.name} | {r.tokens[0]:,} | {r.tokens[1]:,} | {d} | {pct} |")
            k = _kind_of_file(r.name)
            per_kind[k][0] += r.tokens[0]
            per_kind[k][1] += r.tokens[1]
        kinds = [k for k in CONTEXT_KINDS if k in per_kind] + sorted(set(per_kind) - set(CONTEXT_KINDS))
        for k in kinds:
            o, n = per_kind[k]
            d, pct = _delta(o, n)
            w(f"| **all {k}** | **{o:,}** | **{n:,}** | **{d}** | **{pct}** |")
        w("")

    for r in results:
        if not r.diffs:
            continue
        w(f"## {r.name}")
        w("")
        w("| Category | Kind | Count | Items − | Items + |")
        w("|---|---|---:|---:|---:|")
        groups = _group(r.diffs)
        for (category, kind), ds in groups:
            w(f"| `{category}` | {KIND_TITLES[kind]} | {len(ds):,} "
              f"| {sum(d.n_removed for d in ds):,} | {sum(d.n_added for d in ds):,} |")
        w("")
        if max_examples > 0:
            for (category, kind), ds in groups:
                shown = ds[:max_examples]
                w(f"**`{category}` — {KIND_TITLES[kind]}** "
                  f"({len(shown)} of {len(ds):,} shown)")
                w("")
                for d in shown:
                    w(f"- `{d.where}`" + (f": {d.detail}" if d.detail else ""))
                w("")

    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------- CLI

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Compare two directories of context JSONs and write a Markdown report.")
    parser.add_argument("dir_old", help="directory with the reference JSONs (e.g. regex baseline)")
    parser.add_argument("dir_new", help="directory with the JSONs to check (e.g. AST output)")
    parser.add_argument("--out", help="write the report to this file instead of stdout")
    parser.add_argument("--max-examples", type=int, default=10,
                        help="examples listed per category and kind (default 10, 0 = none)")
    args = parser.parse_args(argv)

    for d in (args.dir_old, args.dir_new):
        if not os.path.isdir(d):
            parser.error(f"not a directory: {d}")

    results, only_old, only_new = compare_dirs(args.dir_old, args.dir_new)
    report = render_report(args.dir_old, args.dir_new, results, only_old, only_new,
                           max_examples=args.max_examples)
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(report)
        print(f"Report written to {args.out}")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdout.write(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
