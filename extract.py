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

if __name__ == "__main__":
    main(*sys.argv[1:4])
