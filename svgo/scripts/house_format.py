#!/usr/bin/env python3
"""Re-indent an SVG to the house style: two spaces, one element per line.

  python3 house_format.py in.svg > out.svg
  python3 house_format.py --in-place a.svg b.svg ...

The files are read and hand-edited by people, so a 4KB single line is worse than
a slightly larger file somebody can scan. A parent holding exactly one child stays
on one line when that fits in `--width` (default 200) -- a <filter> wrapping one
<feGaussianBlur> reads better whole than split across three lines -- and <defs>
holding one element always collapses, since the wrapper is pure plumbing.
"""
import sys, re
from xml.dom import minidom

WIDTH = 200
INLINE_ALWAYS = {'defs'}

def esc(v):
    return v.replace('&', '&amp;').replace('<', '&lt;').replace('"', '&quot;')

def render(node, indent=0, width=WIDTH):
    pad = '  ' * indent
    kids = [c for c in node.childNodes if c.nodeType == c.ELEMENT_NODE]
    text = ''.join(c.data for c in node.childNodes if c.nodeType == c.TEXT_NODE).strip()
    attrs = ''.join(f' {k}="{esc(v)}"' for k, v in node.attributes.items())
    open_tag = f'<{node.tagName}{attrs}>'
    if not kids and not text:
        return f'{pad}<{node.tagName}{attrs}/>'
    if not kids:
        return f'{pad}{open_tag}{esc(text)}</{node.tagName}>'
    flat = open_tag + ''.join(render(k, 0, 10**9).strip() for k in kids) + f'</{node.tagName}>'
    if len(kids) == 1 and (node.tagName in INLINE_ALWAYS or len(pad) + len(flat) <= width):
        return pad + flat
    body = '\n'.join(render(k, indent + 1, width) for k in kids)
    return f'{pad}{open_tag}\n{body}\n{pad}</{node.tagName}>'

def format_svg(src):
    doc = minidom.parseString(re.sub(r'>\s+<', '><', src.strip()))
    return render(doc.documentElement) + '\n'

if __name__ == '__main__':
    args = sys.argv[1:]
    inplace = '--in-place' in args
    files = [a for a in args if not a.startswith('--')]
    for f in files:
        out = format_svg(open(f, encoding='utf8').read())
        if inplace: open(f, 'w', encoding='utf8').write(out)
        else: sys.stdout.write(out)
