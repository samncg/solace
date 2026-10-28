#!/usr/bin/env python3
"""Temporary audit helper: parse a KiCad kicadsexpr netlist and dump pin->net maps."""
import re
import sys
from collections import defaultdict


def tokenize(s):
    tok = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c in '()':
            tok.append(c)
            i += 1
        elif c == '"':
            j = i + 1
            buf = []
            while j < n:
                if s[j] == '\\' and j + 1 < n:
                    buf.append(s[j + 1])
                    j += 2
                elif s[j] == '"':
                    break
                else:
                    buf.append(s[j])
                    j += 1
            tok.append(('STR', ''.join(buf)))
            i = j + 1
        elif c.isspace():
            i += 1
        else:
            j = i
            while j < n and not s[j].isspace() and s[j] not in '()':
                j += 1
            tok.append(('SYM', s[i:j]))
            i = j
    return tok


def parse(tok):
    pos = 0

    def walk():
        nonlocal pos
        assert tok[pos] == '('
        pos += 1
        out = []
        while tok[pos] != ')':
            t = tok[pos]
            if t == '(':
                out.append(walk())
            else:
                out.append(t)
                pos += 1
        pos += 1
        return out

    return walk()


def name(node):
    if node and isinstance(node[0], tuple):
        return node[0][1]
    return None


def val(x):
    if isinstance(x, tuple):
        return x[1]
    return x


def children(node, key):
    return [c for c in node if isinstance(c, list) and name(c) == key]


def child(node, key):
    c = children(node, key)
    return c[0] if c else None


def main(path):
    s = open(path, encoding='utf-8').read()
    root = parse(tokenize(s))
    comps_node = child(root, 'components')
    nets_node = child(root, 'nets')

    comps = {}
    for c in children(comps_node, 'comp'):
        ref = val(child(c, 'ref')[1])
        value = val(child(c, 'value')[1]) if child(c, 'value') else ''
        fp = val(child(c, 'footprint')[1]) if child(c, 'footprint') else ''
        pins = []
        units = child(c, 'units')
        if units:
            for u in children(units, 'unit'):
                pn = child(u, 'pins')
                if pn:
                    for p in children(pn, 'pin'):
                        pins.append(val(child(p, 'num')[1]))
        comps[ref] = dict(value=value, fp=fp, pins=pins, nets={})

    nets = []
    for nt in children(nets_node, 'net'):
        code = val(child(nt, 'code')[1])
        nm = val(child(nt, 'name')[1])
        nodes = []
        for nd in children(nt, 'node'):
            ref = val(child(nd, 'ref')[1])
            pin = val(child(nd, 'pin')[1])
            pf = child(nd, 'pinfunction')
            pfn = val(pf[1]) if pf and len(pf) > 1 else ''
            nodes.append((ref, pin, pfn))
            if ref in comps:
                comps[ref]['nets'][pin] = (nm, pfn)
        nets.append((code, nm, nodes))

    if len(sys.argv) > 1 and sys.argv[1] == 'comps':
        for ref in sorted(comps, key=lambda r: (re.sub(r'\d+', '', r), int(re.sub(r'\D', '', r) or 0))):
            c = comps[ref]
            print(f"=== {ref}  [{c['value']}]  {c['fp']}")
            if not c['nets']:
                print("    <NO NETS>")
            for pin in sorted(c['nets'], key=lambda p: (int(p) if p.isdigit() else 9999, p)):
                nm, pfn = c['nets'][pin]
                print(f"  {pin:>3} {pfn:<18} {nm}")
    elif len(sys.argv) > 1 and sys.argv[1] == 'nets':
        for code, nm, nodes in sorted(nets, key=lambda x: x[1].lower()):
            print(f"=== [{nm}] ({len(nodes)})")
            for ref, pin, pfn in nodes:
                print(f"  {ref}.{pin:<3} {pfn}")
    else:
        print(f"components={len(comps)} nets={len(nets)}")
        unconnected = [n for n in nets if len(n[2]) == 1]
        print(f"single-node nets={len(unconnected)}")
        for code, nm, nodes in unconnected:
            print(f"  {nm} -> {nodes}")
        # pins listed in more than one net
        seen = defaultdict(list)
        for code, nm, nodes in nets:
            for ref, pin, pfn in nodes:
                seen[(ref, pin)].append(nm)
        dup = {k: v for k, v in seen.items() if len(v) > 1}
        print(f"pins on >1 net={len(dup)}")
        for k, v in dup.items():
            print(f"  {k}: {v}")
        # components with pins not on any net
        for ref, c in sorted(comps.items()):
            missing = [p for p in c['pins'] if p not in c['nets']]
            if missing:
                print(f"  {ref} pins on no net: {missing}")
        # summary of net names
        print("--- all nets ---")
        for code, nm, nodes in sorted(nets, key=lambda x: x[1].lower()):
            print(f"{nm} ({len(nodes)})")


if __name__ == '__main__':
    main(sys.argv[2] if len(sys.argv) > 2 else 'main.txt')
