import os, re, json, zipfile, tempfile

PKG_PAT = re.compile(r'^\s*package\s+([\w.]+)\s*;', re.MULTILINE)
CLASS_PAT = re.compile(
    r'(?:^|\s)((?:public|protected|private|abstract|final|static)\s+)*'
    r'(class|interface|enum)\s+([A-Z]\w+)',
    re.MULTILINE
)
EXTENDS_PAT = re.compile(r'\bextends\s+([\w.]+)')
IMPLEMENTS_PAT = re.compile(r'\bimplements\s+([\w.,\s]+?)(?:\s*\{|\s+extends|\s+implements)')
FIELD_PAT = re.compile(
    r'(?:public|protected|private)'
    r'(?:\s+static)?(?:\s+final)?(?:\s+static)?'
    r'\s+([\w<>\[\].,\s]+?)\s+(\w+)'
    r'(?:\s*=\s*[^;]+)?;'
)
CONST_PAT = re.compile(
    r'public\s+static\s+final\s+([\w<>\[\]]+)\s+(\w+)\s*=\s*([^;]+);'
)
CONSTRUCTOR_PAT = re.compile(
    r'(?:^|\s)((?:public|protected|private)\s+)?'
    r'\b([A-Z]\w+)\s*'
    r'\(([^)]*)\)'
    r'(?:\s+throws\s+[\w,.\s]+)?'
    r'\s*\{',
    re.MULTILINE
)
METHOD_CONCRETE_PAT = re.compile(
    r'((?:(?:public|protected|private|static|final|synchronized|native|default)\s+)*)'
    r'([\w<>\[\].,\s]+?)\s+'
    r'(\w+)\s*'
    r'\(([^)]*)\)'
    r'(?:\s+throws\s+[\w,.\s]+)?'
    r'\s*\{'
)
METHOD_ABSTRACT_PAT = re.compile(
    r'((?:(?:public|protected|abstract|static)\s+)*abstract\s+(?:(?:public|protected|static)\s+)*)'
    r'([\w<>\[\].,\s]+?)\s+'
    r'(\w+)\s*'
    r'\(([^)]*)\)'
    r'(?:\s+throws\s+[\w,.\s]+)?'
    r'\s*;'
)
CALL_PAT = re.compile(r'(\w+)\.(\w+)\(')
ASSIGN_PAT = re.compile(r'(this\.\w+)\s*=\s*([^;\n]{1,60})')
ASSET_PAT = re.compile(r'"([^"]+\.(?:png|jpg|wav|mp3|gif|ttf))"')
JAVADOC_PAT = re.compile(r'/\*\*.*?\*/', re.DOTALL)
NUMERIC_PAT = re.compile(r'\b(\d{2,5})\b')


JAVA_KEYWORDS = frozenset({
    "if","for","while","switch","catch","else","try","return",
    "new","case","do","finally","throw","assert","synchronized",
    "void","int","long","float","double","boolean","char","byte","short",
})

def is_valid_method(name, ret_type):
    if name in JAVA_KEYWORDS: return False
    if ret_type.strip() in JAVA_KEYWORDS: return False
    return True

def clean_type(t):
    return re.sub(r'\s+', ' ', t).strip()

def clean_params(params_str):
    if not params_str.strip():
        return []
    result = []
    current = []
    depth = 0
    for char in params_str:
        if char == '<': depth += 1
        elif char == '>': depth -= 1
        elif char == ',' and depth == 0:
            result.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    if current:
        result.append("".join(current).strip())
    
    return [re.sub(r'\s+', ' ', p) for p in result if p]

def extract_block(text, start_pos):
    depth = 0
    for i in range(start_pos, len(text)):
        if text[i] == '{': depth += 1
        elif text[i] == '}': depth -= 1
        if depth == 0:
            return text[start_pos:i+1]
    return text[start_pos:start_pos+800] 

def get_javadoc_before(content, pos):
    preceding = content[max(0, pos-400):pos]
    matches = list(JAVADOC_PAT.finditer(preceding))
    if matches:
        raw = matches[-1].group(0)
        return re.sub(r'[\n\r\t/*]+', ' ', raw).strip()[:120]
    return ""

def extract_method_calls(body):
    calls = set()
    for obj, meth in CALL_PAT.findall(body):
        if obj not in ('this', 'super', 'self', 'Math', 'System',
                       'String', 'Integer', 'Boolean', 'Object'):
            calls.add(f"{obj}.{meth}")
    return sorted(calls)

def extract_logic_hints(body, known_fields):
    hints = []
    for var, expr in ASSIGN_PAT.findall(body):
        fname = var.replace('this.', '')
        if fname in known_fields:
            hints.append(f"{fname} = {expr.strip()}")
    return hints[:4]



def analyze_java_file(content, filename):
    # Package
    pkg_m = PKG_PAT.search(content)
    package = pkg_m.group(1) if pkg_m else ""

    # Class declaration
    class_m = CLASS_PAT.search(content)
    if not class_m:
        return None

    modifiers   = (class_m.group(1) or "").strip()
    type_kw     = class_m.group(2)   # class / interface / enum
    module_name = class_m.group(3)
    is_abstract = 'abstract' in modifiers or type_kw == 'interface'

    # Extends / implements
    extends_m = EXTENDS_PAT.search(content)
    parent    = extends_m.group(1) if extends_m else None

    implements_m  = IMPLEMENTS_PAT.search(content)
    implements    = []
    if implements_m:
        implements = [i.strip() for i in implements_m.group(1).split(',') if i.strip()]

    # Fields
    fields       = {}
    known_fields = set()
    for m in FIELD_PAT.finditer(content):
        ftype = clean_type(m.group(1))
        fname = m.group(2)
        if fname in ('int', 'void', 'boolean', 'String', 'true', 'false',
                     'null', 'new', 'return', 'class') or len(fname) < 2:
            continue
        fields[fname]  = ftype
        known_fields.add(fname)

    # Static constants
    constants = {}
    for m in CONST_PAT.finditer(content):
        ctype  = clean_type(m.group(1))
        cname  = m.group(2)
        cvalue = m.group(3).strip()[:60]
        constants[cname] = {"type": ctype, "value": cvalue}

    # Assets
    assets = list(set(ASSET_PAT.findall(content)))

    methods = {}

    # Constructors
    for m in CONSTRUCTOR_PAT.finditer(content):
        raw_mods = (m.group(1) or "").strip()
        cname = m.group(2)
        if cname != module_name: 
            continue
        params = clean_params(m.group(3))
        
        start_pos = content.rfind('{', m.start(), m.end())
        body = extract_block(content, start_pos)
        
        calls = extract_method_calls(body)
        logic = extract_logic_hints(body, known_fields)
        numerics = list(set(NUMERIC_PAT.findall(body)))[:6]
        javadoc = get_javadoc_before(content, m.start())

        mods = [mod for mod in ('public','protected','private') if mod in raw_mods]
        
        sig_key = f"{cname}_constructor_{len(params)}"
        methods[sig_key] = {
            "abstract": False,
            "modifiers": mods,
            "return_type": "",
            "params": params,
            "signature": f"{' '.join(mods)} {cname}({', '.join(params)})".strip(),
            "javadoc": javadoc,
            "calls": calls,
            "logic_hints": logic,
            "values_hint": numerics,
        }

    for m in METHOD_CONCRETE_PAT.finditer(content):
        raw_mods  = (m.group(1) or "").strip()
        ret_type  = clean_type(m.group(2))
        mname     = m.group(3)
        params    = clean_params(m.group(4))

        if mname == module_name:
            continue
        if not is_valid_method(mname, ret_type):
            continue

        mods = []
        for mod in ('public','protected','private','static','final',
                    'synchronized','native','default'):
            if mod in raw_mods:
                mods.append(mod)

        # Body 
        start_pos = content.rfind('{', m.start(), m.end())
        body = extract_block(content, start_pos)
        
        calls     = extract_method_calls(body)
        logic     = extract_logic_hints(body, known_fields)
        numerics  = list(set(NUMERIC_PAT.findall(body)))[:6]
        javadoc   = get_javadoc_before(content, m.start())

        methods[mname] = {
            "abstract":    False,
            "modifiers":   mods,
            "return_type": ret_type,
            "params":      params,
            "signature":   f"{' '.join(mods)} {ret_type} {mname}({', '.join(params)})".strip(),
            "javadoc":     javadoc,
            "calls":       calls,
            "logic_hints": logic,
            "values_hint": numerics,
        }

    # Methods - abstract
    for m in METHOD_ABSTRACT_PAT.finditer(content):
        raw_mods = (m.group(1) or "").strip()
        ret_type = clean_type(m.group(2))
        mname    = m.group(3)
        params   = clean_params(m.group(4))

        if mname == module_name:
            continue

        mods = []
        for mod in ('public','protected','abstract','static'):
            if mod in raw_mods:
                mods.append(mod)
        if 'abstract' not in mods:
            mods.append('abstract')

        javadoc = get_javadoc_before(content, m.start())

        methods[mname] = {
            "abstract":    True,
            "modifiers":   mods,
            "return_type": ret_type,
            "params":      params,
            "signature":   f"abstract {' '.join(m for m in mods if m != 'abstract')} {ret_type} {mname}({', '.join(params)})".strip(),
            "javadoc":     javadoc,
            "calls":       [],
            "logic_hints": [],
            "values_hint": [],
        }

    return {
        "module":       module_name,
        "package":      package,
        "type":         f"abstract {type_kw}" if is_abstract else type_kw,
        "parent":       parent,
        "implements":   implements,
        "fields":       fields,
        "constants":    constants,
        "assets":       assets,
        "methods":      methods,
    }


def flatten_inheritance(full_context):
    for _ in range(3):
        for name, data in full_context.items():
            parent_name = data.get("parent")
            if parent_name and parent_name in full_context:
                pdata = full_context[parent_name]
                for fname, ftype in pdata.get("fields", {}).items():
                    if fname not in data["fields"]:
                        data["fields"][f"{fname} (from {parent_name})"] = ftype
                
                for mname, mdata in pdata.get("methods", {}).items():
                    if "constructor" in mname:
                        continue
                    if mname not in data["methods"]:
                        data["methods"][f"{mname} (inherited from {parent_name})"] = mdata
    return full_context


def split_contexts(full_context):
    structural = {}
    functional = {}
    behavioral = {}

    for module, data in full_context.items():
        sig_list = []
        for mname, mdata in data.get("methods", {}).items():
            sig_list.append(mdata["signature"])

        structural[module] = {
            "module":      data["module"],
            "package":     data["package"],
            "type":        data["type"],
            "parent":      data["parent"],
            "implements":  data["implements"],
            "fields":      data["fields"],
            "constants":   data["constants"],
            "method_signatures": sig_list,
        }

        capabilities = {}
        for mname, mdata in data.get("methods", {}).items():
            capabilities[mname] = {
                "signature": mdata["signature"],
                "intent":    mdata["javadoc"] or "No documentation",
                "abstract":  mdata["abstract"],
            }

        role_tags = _compute_roles(data)

        functional[module] = {
            "roles":        role_tags,
            "capabilities": capabilities,
        }

        method_behavior = {}
        for mname, mdata in data.get("methods", {}).items():
            if mdata.get("calls") or mdata.get("logic_hints") or mdata.get("values_hint"):
                method_behavior[mname] = {
                    "calls":       mdata["calls"],
                    "logic_hints": mdata["logic_hints"],
                    "values_hint": mdata["values_hint"],
                }

        behavioral[module] = {
            "methods_execution": method_behavior,
        }

    return structural, functional, behavioral


def generate_context(zip_path, game_name, output_dir="."):
    print(f"Processing {game_name} from {zip_path}...")
    full_context = {}

    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(zip_path, 'r') as z:
            z.extractall(tmp)

        for root, dirs, files in os.walk(tmp):
            for fname in files:
                if not fname.endswith(".java"):
                    continue
                if fname.startswith("."):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    data = analyze_java_file(content, fname)
                    if data:
                        full_context[data["module"]] = data
                except Exception as e:
                    print(f"  Error reading {fname}: {e}")

    print(f"  Analyzed {len(full_context)} classes")

    full_context = flatten_inheritance(full_context)
    structural, functional, behavioral = split_contexts(full_context)

    os.makedirs(output_dir, exist_ok=True)
    paths = {}
    for label, obj in [("Context", full_context),
                        ("Structural", structural),
                        ("Functional", functional),
                        ("Behavioral", behavioral)]:
        path = os.path.join(output_dir, f"{game_name}_{label}.json")
        with open(path, 'w') as f:
            json.dump(obj, f, indent=2)
        paths[label] = path
        print(f"  Saved {path}")

    return paths


def resolve_dependency(var_name, all_classes):
    if var_name in all_classes:
        return var_name
    lower_map = {k.lower(): k for k in all_classes}
    if var_name.lower() in lower_map:
        return lower_map[var_name.lower()]
    matches = [c for c in all_classes if var_name.lower() in c.lower()]
    return sorted(matches, key=len)[0] if matches else None

def generate_slice(context_path, query_list, output_path=None, depth=1):
    with open(context_path) as f:
        full = json.load(f)

    all_classes = list(full.keys())
    targets = set()

    for q in query_list:
        if q in full:
            targets.add(q)
        else:
            found = [c for c in all_classes if q.lower() in c.lower()]
            if found:
                print(f"  '{q}' matched: {found}")
                targets.update(found)
            else:
                print(f"  WARNING: no class matching '{q}'")

    sliced = {}
    queue  = list(targets)
    seen   = set()

    while queue:
        cur = queue.pop(0)
        if cur in seen or cur not in full:
            continue
        seen.add(cur)
        sliced[cur] = full[cur]

        parent = full[cur].get("parent") or full[cur].get("Parent")
        if parent and parent not in seen:
            queue.append(parent)

        if len(seen) <= 15:
            methods = full[cur].get("methods", {})
            for mdata in methods.values():
                for call in mdata.get("calls", []):
                    if "." in call:
                        var = call.split(".")[0]
                        resolved = resolve_dependency(var, all_classes)
                        if resolved and resolved not in seen:
                            if resolved not in ("Math", "System", "String"):
                                queue.append(resolved)

    print(f"  Sliced to {len(sliced)} classes from {len(full)}")

    if output_path:
        with open(output_path, 'w') as f:
            json.dump(sliced, f, indent=2)
        print(f"  Saved slice → {output_path}")

    return sliced


ALL_SUBTYPES = {
    "S": ["S_hierarchy", "S_fields", "S_constants", "S_signatures"],
    "F": ["F_roles", "F_intent"],
    "B": ["B_calls", "B_logic", "B_values"],
}

VALID_SUBTYPES = [st for group in ALL_SUBTYPES.values() for st in group]

def extract_subtype(module_data, subtype):
    d = module_data
    if subtype == "S_hierarchy":
        return {
            "module":     d.get("module", ""),
            "package":    d.get("package", ""),
            "type":       d.get("type", ""),
            "parent":     d.get("parent"),
            "implements": d.get("implements", []),
        }
    elif subtype == "S_fields":
        return {"fields": d.get("fields", {})}
    elif subtype == "S_constants":
        return {"constants": d.get("constants", {})}
    elif subtype == "S_signatures":
        sigs = {}
        for mname, mdata in d.get("methods", {}).items():
            sigs[mname] = {
                "signature": mdata.get("signature", "").strip(),
                "abstract":  mdata.get("abstract", False),
            }
        return {"method_signatures": sigs}
    elif subtype == "F_roles":
        return {"roles": _compute_roles(d)}
    elif subtype == "F_intent":
        intents = {}
        for mname, mdata in d.get("methods", {}).items():
            doc = mdata.get("javadoc", "")
            if doc:
                intents[mname] = doc
        return {"method_intent": intents}
    elif subtype == "B_calls":
        calls = {}
        for mname, mdata in d.get("methods", {}).items():
            if mdata.get("calls"):
                calls[mname] = mdata["calls"]
        return {"method_calls": calls}
    elif subtype == "B_logic":
        logic = {}
        for mname, mdata in d.get("methods", {}).items():
            if mdata.get("logic_hints"):
                logic[mname] = mdata["logic_hints"]
        return {"method_logic": logic}
    elif subtype == "B_values":
        values = {}
        for mname, mdata in d.get("methods", {}).items():
            if mdata.get("values_hint"):
                values[mname] = mdata["values_hint"]
        return {"method_values": values}
    return {}

def _compute_roles(d):
    roles = []
    fields_str  = " ".join(d.get("fields", {}).keys()).lower()
    methods_str = " ".join(d.get("methods", {}).keys()).lower()
    combined    = fields_str + " " + methods_str

    if any(k in combined for k in ["background", "image", "render", "draw", "paint"]): roles.append("UI")
    if any(k in combined for k in ["x ", " y ", "velocity", "width", "height", "rect"]): roles.append("Entity")
    if any(k in combined for k in ["think", "update", "tick", "run"]): roles.append("GameLoop")
    if any(k in combined for k in ["key", "mouse", "button", "input", "released"]): roles.append("Input")
    if any(k in combined for k in ["highscore", "score", "points", "rank"]): roles.append("Highscore")
    if any(k in combined for k in ["achievement", "unlock", "milestone"]): roles.append("Achievements")
    if any(k in combined for k in ["sound", "music", "options", "settings"]): roles.append("Options")
    return roles if roles else ["Utility"]

def build_combined_context(full_context, subtypes):
    result = {}
    for module, data in full_context.items():
        merged = {"module": data.get("module", module)}
        for st in subtypes:
            extracted = extract_subtype(data, st)
            merged.update(extracted)
        result[module] = merged
    return result

def generate_subtype_files(full_context, game_name, subtypes=None, output_dir="."):
    if subtypes is None:
        subtypes = VALID_SUBTYPES
    os.makedirs(output_dir, exist_ok=True)
    paths = {}
    for st in subtypes:
        if st not in VALID_SUBTYPES:
            continue
        context_slice = {}
        for module, data in full_context.items():
            context_slice[module] = {
                "module": data.get("module", module),
                **extract_subtype(data, st),
            }
        path = os.path.join(output_dir, f"{game_name}_{st}.json")
        with open(path, "w") as f:
            json.dump(context_slice, f, indent=2)
        paths[st] = path
    return paths

def generate_combined_file(full_context, game_name, subtypes, output_dir="."):
    os.makedirs(output_dir, exist_ok=True)
    combined = build_combined_context(full_context, subtypes)
    label    = "+".join(subtypes)
    path     = os.path.join(output_dir, f"{game_name}_{label}.json")
    with open(path, "w") as f:
        json.dump(combined, f, indent=2)
    print(f"  Saved combined {path}")
    return path

def slice_with_subtypes(context_path, query_list, subtypes, output_path=None, output_dir="."):
    sliced = generate_slice(context_path, query_list)
    combined = build_combined_context(sliced, subtypes)
    if output_path is None:
        label       = "+".join(subtypes)
        query_label = "_".join(query_list)
        fname       = f"{query_label}_{label}.json"
        output_path = os.path.join(output_dir, fname)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(combined, f, indent=2)
    print(f"  Saved slice+subtype → {output_path}")
    return combined

if __name__ == "__main__":
    import sys

    def get_flag(args, flag, n=1):
        if flag not in args: return None
        idx = args.index(flag)
        return args[idx+1 : idx+1+n] if n > 1 else args[idx+1]

    def get_multi_flag(args, flag):
        if flag not in args: return []
        idx = args.index(flag)
        vals = []
        for a in args[idx+1:]:
            if a.startswith("--"): break
            vals.append(a)
        return vals

    args = sys.argv[1:]
    if not args:
        print("Context Generator - Commands: generate, combine, slice")
        sys.exit(0)

    command = args[0]

    if command == "generate":
        game_name  = args[1]
        zip_path   = args[2]
        output_dir = args[3] if len(args) > 3 and not args[3].startswith("--") else "."
        subtypes   = get_multi_flag(args, "--subtypes") or None
        paths = generate_context(zip_path, game_name, output_dir)
        with open(paths["Context"]) as f:
            full_context = json.load(f)
        generate_subtype_files(full_context, game_name, subtypes, output_dir)

    elif command == "combine":
        game_name    = args[1]
        context_json = args[2]
        subtypes     = get_multi_flag(args, "--subtypes")
        output_dir   = get_flag(args, "--out") or os.path.dirname(context_json) or "."
        with open(context_json) as f:
            full_context = json.load(f)
        generate_combined_file(full_context, game_name, subtypes, output_dir)

    elif command == "slice":
        context_json = args[1]
        queries      = [a for a in args[2:] if not a.startswith("--")]
        subtypes     = get_multi_flag(args, "--subtypes")
        out_path     = get_flag(args, "--out")
        if subtypes:
            slice_with_subtypes(context_json, queries, subtypes, output_path=out_path, output_dir=".")
        else:
            sliced = generate_slice(context_json, queries, out_path)
            if not out_path:
                print(json.dumps(sliced, indent=2)[:2000])