#!/usr/bin/env python3
"""Extract set.mm's header hierarchy (part > chapter > section > subsection >
subsubsection) with $p/$a counts per node. Writes sections.js (window.SETMM)."""
import json, re, sys
from pathlib import Path

LEVELS = {"#": 1, "#*": 2, "=-": 3, "-.": 4, ".-": 5}
SEP = re.compile(r"^\s*([#*=.\-]{2})\1{9,}[#*=.\-]?\s*$")

def level_of(line):
    m = SEP.match(line)
    if not m: return None
    p = m.group(1)
    return LEVELS.get("#" if p == "##" else p)

def main(src, out, commit, defs_out=None):
    here = Path(__file__).resolve().parent
    mm100 = parse_mm100(Path(src).with_name("mm_100.html"))
    hand = load_hand(here / "mm100-extra.toml")
    highlights = load_hand(here / "highlights.toml")
    wanted = ({l for _, labs in mm100.values() for l in labs} | {h["label"] for h in hand}
              | {h["label"] for h in highlights})
    thms = {}                       # label -> [header line, statement, comment, tag n]
    TAG = re.compile(r"Metamath 100 proof #(\d+)")
    lines = Path(src).read_text(encoding="utf-8").split("\n")
    root = {"name": "set.mm", "level": 0, "children": [], "p": 0, "a": 0, "line": 1}
    stack = [root]
    in_c = False
    defs = {}                       # header line -> list of [label, math, comment]
    comment, last_comment = [], ""
    prev, cur = None, None          # cur: def being collected
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        lv = level_of(line) if in_c else None
        if lv:
            j, title = i + 1, []
            while j < n and level_of(lines[j]) != lv and j - i < 5:
                title.append(lines[j].strip()); j += 1
            if j < n and level_of(lines[j]) == lv and title:
                node = {"name": " ".join(t for t in title if t), "level": lv,
                        "line": i + 1, "children": [], "p": 0, "a": 0}
                while stack[-1]["level"] >= lv: stack.pop()
                stack[-1]["children"].append(node); stack.append(node)
                i = j + 1; continue
        toks = line.split()
        for t in toks:
            if t == "$(":
                in_c, comment = True, []
            elif t == "$)":
                in_c = False
                last_comment = " ".join(comment)
            elif in_c:
                comment.append(t)
            elif cur is not None and cur[0] == "$p":
                if t == "$=":
                    m = TAG.search(last_comment)
                    thms[cur[1]] = [stack[-1]["line"], " ".join(cur[2]), last_comment[:600],
                                    int(m.group(1)) if m else None]
                    cur, last_comment = None, ""
                else:
                    cur[2].append(t)
            elif cur is not None:
                if t == "$.":
                    defs.setdefault(stack[-1]["line"], []).append(
                        [cur[0], " ".join(cur[1]), last_comment[:600]])
                    cur, last_comment = None, ""
                else:
                    cur[1].append(t)
            elif t in ("$p", "$a"):
                stack[-1][t[1]] += 1
                if t == "$a" and prev and prev.startswith("df-"):
                    cur = (prev, [])
                elif t == "$p" and (prev in wanted or TAG.search(last_comment)):
                    cur = ("$p", prev, [])
                else:
                    last_comment = ""
            if not in_c: prev = t
        i += 1

    def tidy(nd):
        for c in nd["children"]: tidy(c)
        if not nd["children"]: del nd["children"]
        elif nd["p"] + nd["a"]:
            # statements before the first child header: keep as a leaf
            nd["children"].insert(0, {"name": "(intro)", "level": nd["level"] + 1,
                                      "line": nd["line"], "p": nd["p"], "a": nd["a"]})
            nd["p"] = nd["a"] = 0
    tidy(root)
    root["commit"] = commit
    Path(out).write_text("window.SETMM = " + json.dumps(root, separators=(",", ":")) + ";\n")
    defs_out = defs_out or str(Path(out).with_name("defs.js"))
    Path(defs_out).write_text("window.SETMM_DEFS = " + json.dumps(defs, separators=(",", ":")) + ";\n")
    sec_codes = {}
    if (here / "msc-map.toml").exists():
        sec_codes, by_label = build_msc(root, defs, here, Path(out).with_name("msc.js"), set(thms))
    else:
        by_label = {}
    build_mm100(mm100, hand, thms, sec_codes, by_label, Path(out).with_name("mm100.js"))
    build_highlights(highlights, thms, sec_codes, by_label, Path(out).with_name("highlights.js"))


# ---------------------------------------------------------- Metamath 100 theorems
def parse_mm100(path):
    """n -> (title, [labels]) from set.mm's mm_100.html (labels in link order)."""
    if not path.exists(): return {}
    h = path.read_text(encoding="utf-8", errors="replace")
    parts = re.split(r'<li><a name="(\d+)">\d+</a>\.', h)
    out = {}
    for k in range(1, len(parts), 2):
        body = re.split(r"</li>|<li>|</ol>", parts[k + 1], flags=re.I)[0]
        title = re.sub(r"<[^>]+>", "", re.split(r"\(<a", body, flags=re.I)[0])
        labs = re.findall(r'href="(?:https://us\.metamath\.org/)?mpeuni/([^"#]+)\.html"', body, re.I)
        import html
        out[int(parts[k])] = (html.unescape(" ".join(title.split()).rstrip(" .(")), list(dict.fromkeys(labs)))
    return out

def load_hand(path):
    if not path.exists(): return []
    import tomllib
    return tomllib.loads(path.read_text(encoding="utf-8")).get("theorem", [])

def build_highlights(entries, thms, sec_codes, by_label, out):
    res = []
    for h in entries:
        lbl = h["label"]
        if lbl not in thms:
            print(f"warning: highlight {lbl}: not found as $p", file=sys.stderr); continue
        line, stmt, cm, _ = thms[lbl]
        res.append({"n": None, "title": h.get("title", lbl), "label": lbl, "also": [],
                    "note": h.get("note", ""), "line": line, "stmt": stmt, "comment": cm,
                    "msc": by_label.get(lbl, sec_codes.get(line, []))})
    Path(out).write_text("window.SETMM_HIGHLIGHTS = " + json.dumps(
        {"theorems": res}, separators=(",", ":")) + ";\n")
    print(f"highlights: {len(res)} theorems", file=sys.stderr)

def build_mm100(mm100, hand, thms, sec_codes, by_label, out):
    items = {}                      # n -> {n, title, labels}
    for n, (title, labs) in mm100.items():
        items[n] = {"n": n, "title": title, "labels": list(labs), "note": ""}
    for lbl, (_, _, _, n) in thms.items():          # comment tags
        if n is None: continue
        it = items.setdefault(n, {"n": n, "title": f"Metamath 100 #{n}", "labels": [], "note": ""})
        if lbl not in it["labels"]: it["labels"].append(lbl)
    extra = []
    for h in hand:
        n = h.get("n")
        if n is not None and n in items:
            it = items[n]
            if h["label"] not in it["labels"]: it["labels"].insert(0, h["label"])
            it["note"] = h.get("note", it["note"])
            if h.get("title"): it["title"] = h["title"]
        else:
            extra.append({"n": n, "title": h.get("title", h["label"]), "labels": [h["label"]],
                          "note": h.get("note", "")})
    res, missing = [], []
    for it in sorted(items.values(), key=lambda x: x["n"]) + extra:
        labs = [l for l in it["labels"] if l in thms]
        gone = [l for l in it["labels"] if l not in thms]
        if gone: print(f"warning: Metamath 100 #{it['n']}: label(s) not found as $p: {gone}", file=sys.stderr)
        if not labs:
            if it["n"] is not None: missing.append([it["n"], it["title"]])
            continue
        main = labs[0]
        line, stmt, cm, _ = thms[main]
        res.append({"n": it["n"], "title": it["title"], "label": main, "also": labs[1:],
                    "note": it["note"], "line": line, "stmt": stmt, "comment": cm,
                    "msc": by_label.get(main, sec_codes.get(line, []))})
    Path(out).write_text("window.SETMM_MM100 = " + json.dumps(
        {"theorems": res, "missing": missing}, separators=(",", ":")) + ";\n")
    print(f"mm100: {len(res)} theorems ({sum(r['n'] is not None for r in res)} from the 100 list), "
          f"{len(missing)} of the 100 not in set.mm", file=sys.stderr)


# ---------------------------------------------------------------- MSC view
def load_concepts(d):
    """label -> msc codes from prove4mm concept cards (frontmatter lists)."""
    out = {}
    for f in sorted(Path(d).glob("*.md")) if Path(d).is_dir() else []:
        fm = f.read_text(encoding="utf-8").split("---")[1]
        get = lambda k: re.findall(r'[\w.-]+', (re.search(rf"^{k}:\s*\[(.*)\]", fm, re.M) or [None, ""])[1])
        for lbl in get("labels"):
            out.setdefault(lbl, [])
            out[lbl] += [c for c in get("msc") if c not in out[lbl]]
    return out

def build_msc(root, defs, here, out, theorems=frozenset()):
    import tomllib
    cfg = tomllib.loads((here / "msc-map.toml").read_text(encoding="utf-8"))
    rules = {tuple(s.strip() for s in k.split(" > ")): v for k, v in cfg.get("sections", {}).items()}
    names = {}
    for ln in (here / "msc-codes.tsv").read_text(encoding="utf-8").splitlines():
        if ln and not ln.startswith("#"):
            c, n = ln.split("\t", 1); names[c] = n
    by_label = load_concepts(here.parent / "prove4mm" / "design-space" / "concepts")
    by_label.update(cfg.get("labels", {}))
    used = set()

    def codes_for(path):           # path: header titles, root excluded
        for i in range(len(path), 0, -1):       # deepest header first
            hits = [k for k in rules if len(k) <= i and tuple(path[i - len(k):i]) == k]
            if hits:
                return rules[max(hits, key=len)]  # longest key wins a tie
        return []

    assign = {}                     # label -> codes
    where = {}                      # label -> [line, idx]
    counts = []                     # (section codes, p, a) per leaf section
    sec_by_line = {}                # leaf header line -> section codes
    def walk(nd, path):
        here_path = path + ([nd["name"]] if nd is not root else [])
        for k in rules:
            if len(k) <= len(here_path) and tuple(here_path[-len(k):]) == k: used.add(k)
        if "children" in nd:
            for c in nd["children"]:
                walk(c, path + ([nd["name"]] if nd is not root else []))
            return
        full = path + ([nd["name"]] if nd["name"] != "(intro)" else [])
        sec = codes_for(full)
        sec_by_line[nd["line"]] = sec
        if nd["p"] + nd["a"]: counts.append((sec, nd["p"], nd["a"]))
        for i, (lbl, _, _) in enumerate(defs.get(nd["line"], [])):
            assign[lbl] = by_label.get(lbl, sec)
            where[lbl] = [nd["line"], i]
    walk(root, [])

    unknown = sorted({c for v in assign.values() for c in v if c not in names})
    if unknown: print("warning: codes missing from msc-codes.tsv:", unknown, file=sys.stderr)
    for key in rules:
        if key not in used: print("warning: section rule matches no header:", " > ".join(key), file=sys.stderr)
    for lbl in cfg.get("labels", {}):
        if lbl not in assign and lbl not in theorems:
            print("warning: label rule for unknown definition/theorem:", lbl, file=sys.stderr)

    # Tree: 2-char class > 3-char > 5-char. Defs sit on the node of their code.
    tree = {"name": "MSC 2020", "code": "", "children": {}}
    def node(code):
        chain = [code[:2]] + ([code[:3]] if len(code) >= 3 else []) + ([code] if len(code) == 5 else [])
        t = tree
        for c in chain:
            t = t["children"].setdefault(c, {"name": f"{c} {names.get(c, '?')}", "code": c,
                                             "children": {}, "refs": [], "p": 0, "a": 0})
        return t
    unc = {"name": "Unclassified", "code": "?", "children": {}, "refs": [], "p": 0, "a": 0}
    for lbl, cs in assign.items():
        for c in cs or [None]:
            (node(c) if c else unc)["refs"].append(where[lbl])
    # Theorems/axioms: each section's counts go to every code of that section.
    for cs, np_, na in counts:
        for c in cs or [None]:
            t = node(c) if c else unc
            t["p"] += np_; t["a"] += na
    unc_p = unc["p"]
    if unc["refs"] or unc["p"] + unc["a"]: tree["children"]["~"] = unc

    def finish(t):
        kids = [finish(t["children"][k]) for k in sorted(t["children"])]
        refs = sorted(t.pop("refs", []))
        np_, na = t.pop("p", 0), t.pop("a", 0)
        if kids and (refs or np_ + na):
            kids.insert(0, {"name": "(general)", "code": t["code"], "refs": refs, "p": np_, "a": na})
        elif not kids:
            t.update(refs=refs, p=np_, a=na)
        if kids: t["children"] = kids
        else: t.pop("children")
        return t
    finish(tree)
    data = {"tree": tree, "byLabel": assign,
            "names": {c: n for c, n in names.items() if any(c in v for v in assign.values())}}
    Path(out).write_text("window.SETMM_MSC = " + json.dumps(data, separators=(",", ":")) + ";\n")
    n_multi = sum(len(v) > 1 for v in assign.values())
    print(f"msc: {len(assign)} definitions, {sum(not v for v in assign.values())} unclassified, "
          f"{n_multi} with more than one code; $p in unclassified sections: {unc_p} "
          f"of {sum(x[1] for x in counts)}", file=sys.stderr)
    return sec_by_line, by_label

if __name__ == "__main__":
    main(*sys.argv[1:4])
