#!/usr/bin/env python3
"""Test two geometric claims about an SVG's paths, instead of eyeballing them.

  python3 fit_shapes.py file.svg              # is each path secretly an ellipse?
  python3 fit_shapes.py --symmetry file.svg   # is any path a rigid copy of another?

Pure Python (needs numpy). It flattens the path itself rather than driving a
browser, so it runs anywhere.

Reading the output: `residual` is the largest distance, in user units, between a
sampled point and the fitted shape. Compare it to the viewBox -- under ~0.5% of the
width means the export wrote a primitive as Beziers and you can substitute the
primitive. For --symmetry, a `scale` of 1.000 with a tiny residual means one path
is genuinely the same artwork transformed; anything else is two different shapes
that merely rhyme.
"""
import sys, re, math, cmath
import numpy as np

# ---------------------------------------------------------------- path parsing
NUM = re.compile(r'[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?')
CMD = re.compile(r'([MmZzLlHhVvCcSsQqTtAa])')

def _tok(d):
    out = []
    for part in CMD.split(d):
        part = part.strip()
        if not part: continue
        if len(part) == 1 and part.isalpha(): out.append(part)
        else: out.extend(float(x) for x in NUM.findall(part))
    return out

def _arc(p0, rx, ry, phi, large, sweep, p1, n=24):
    """Endpoint-parameterised arc -> polyline (SVG implementation notes F.6.5)."""
    if p0 == p1: return []
    rx, ry = abs(rx), abs(ry)
    if rx == 0 or ry == 0: return [p1]
    phi = math.radians(phi)
    dx2, dy2 = (p0.real - p1.real) / 2, (p0.imag - p1.imag) / 2
    x1 = math.cos(phi) * dx2 + math.sin(phi) * dy2
    y1 = -math.sin(phi) * dx2 + math.cos(phi) * dy2
    lam = x1 * x1 / (rx * rx) + y1 * y1 / (ry * ry)
    if lam > 1: rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
    num = rx * rx * ry * ry - rx * rx * y1 * y1 - ry * ry * x1 * x1
    den = rx * rx * y1 * y1 + ry * ry * x1 * x1
    c = math.sqrt(max(0.0, num / den)) * (-1 if large == sweep else 1)
    cx1, cy1 = c * rx * y1 / ry, -c * ry * x1 / rx
    cx = math.cos(phi) * cx1 - math.sin(phi) * cy1 + (p0.real + p1.real) / 2
    cy = math.sin(phi) * cx1 + math.cos(phi) * cy1 + (p0.imag + p1.imag) / 2
    ang = lambda ux, uy, vx, vy: (
        (1 if ux * vy - uy * vx >= 0 else -1) *
        math.acos(max(-1, min(1, (ux * vx + uy * vy) /
                              (math.hypot(ux, uy) * math.hypot(vx, vy))))))
    t1 = ang(1, 0, (x1 - cx1) / rx, (y1 - cy1) / ry)
    dt = ang((x1 - cx1) / rx, (y1 - cy1) / ry, (-x1 - cx1) / rx, (-y1 - cy1) / ry)
    if not sweep and dt > 0: dt -= 2 * math.pi
    elif sweep and dt < 0: dt += 2 * math.pi
    pts = []
    for i in range(1, n + 1):
        t = t1 + dt * i / n
        x, y = rx * math.cos(t), ry * math.sin(t)
        pts.append(complex(math.cos(phi) * x - math.sin(phi) * y + cx,
                           math.sin(phi) * x + math.cos(phi) * y + cy))
    return pts

def _bez(p, n=24):
    """Cubic (4 ctrl pts) or quadratic (3) -> polyline."""
    out = []
    for i in range(1, n + 1):
        t = i / n; u = 1 - t
        if len(p) == 4:
            out.append(u**3*p[0] + 3*u*u*t*p[1] + 3*u*t*t*p[2] + t**3*p[3])
        else:
            out.append(u*u*p[0] + 2*u*t*p[1] + t*t*p[2])
    return out

def sample(d):
    """Flatten path data to a list of subpaths, each a list of complex points."""
    t = _tok(d); i = 0; cur = start = 0j; subs = []; pts = []; cmd = None; prev_c = prev_q = None
    def flush():
        nonlocal pts
        if len(pts) > 2: subs.append(pts)
        pts = []
    while i < len(t):
        if isinstance(t[i], str): cmd = t[i]; i += 1
        elif cmd in 'Mm': cmd = 'L' if cmd == 'M' else 'l'
        rel = cmd.islower(); C = cmd.upper()
        if C == 'Z':
            if pts and abs(pts[-1] - start) > 1e-12: pts.append(start)
            cur = start; flush(); continue
        if C == 'M':
            x, y = t[i], t[i+1]; i += 2
            cur = (cur + complex(x, y)) if rel else complex(x, y)
            flush(); start = cur; pts = [cur]; prev_c = prev_q = None; continue
        if C in 'LT':
            x, y = t[i], t[i+1]; i += 2
            p = (cur + complex(x, y)) if rel else complex(x, y)
            if C == 'T':
                c1 = 2*cur - prev_q if prev_q else cur
                pts += _bez([cur, c1, p]); prev_q = c1
            else: pts.append(p)
            cur = p; prev_c = None if C == 'L' else prev_c
        elif C in 'HV':
            v = t[i]; i += 1
            p = (cur + (complex(v, 0) if C == 'H' else complex(0, v))) if rel else (
                complex(v, cur.imag) if C == 'H' else complex(cur.real, v))
            pts.append(p); cur = p; prev_c = prev_q = None
        elif C in 'CS':
            if C == 'C':
                c1 = complex(t[i], t[i+1]); c2 = complex(t[i+2], t[i+3]); p = complex(t[i+4], t[i+5]); i += 6
                if rel: c1, c2, p = cur + c1, cur + c2, cur + p
            else:
                c2 = complex(t[i], t[i+1]); p = complex(t[i+2], t[i+3]); i += 4
                if rel: c2, p = cur + c2, cur + p
                c1 = 2*cur - prev_c if prev_c else cur
            pts += _bez([cur, c1, c2, p]); prev_c = c2; prev_q = None; cur = p
        elif C == 'Q':
            c1 = complex(t[i], t[i+1]); p = complex(t[i+2], t[i+3]); i += 4
            if rel: c1, p = cur + c1, cur + p
            pts += _bez([cur, c1, p]); prev_q = c1; prev_c = None; cur = p
        elif C == 'A':
            rx, ry, rot, la, sw = t[i], t[i+1], t[i+2], int(t[i+3]), int(t[i+4])
            p = complex(t[i+5], t[i+6]); i += 7
            if rel: p = cur + p
            pts += _arc(cur, rx, ry, rot, la, sw, p); prev_c = prev_q = None; cur = p
        else:
            i += 1
    flush()
    return subs

def paths_of(svg):
    out = []
    for m in re.finditer(r'<path\b[^>]*?\sd="([^"]+)"', svg):
        tag = m.group(0)
        ident = re.search(r'\sid="([^"]+)"', tag)
        fill = re.search(r'\sfill="([^"]+)"', tag)
        out.append({'d': m.group(1), 'id': ident.group(1) if ident else None,
                    'fill': fill.group(1) if fill else None})
    return out

# ------------------------------------------------------------------ ellipse fit
def fit_ellipse(P):
    x, y = P[:, 0], P[:, 1]
    mx, my = x.mean(), y.mean(); sc = max(x.std(), y.std()) or 1
    X, Y = (x - mx) / sc, (y - my) / sc
    A = np.c_[X*X, X*Y, Y*Y, X, Y, np.ones_like(X)]
    a, b, c, d, e, f = np.linalg.svd(A)[2][-1]
    M = np.array([[a, b/2], [b/2, c]])
    if np.linalg.det(M) <= 0: return None            # hyperbola/parabola: not an ellipse
    cen = np.linalg.solve(2*M, [-d, -e])
    val = a*cen[0]**2 + b*cen[0]*cen[1] + c*cen[1]**2 + d*cen[0] + e*cen[1] + f
    ev, evec = np.linalg.eigh(M)
    if np.any(-val/ev <= 0): return None
    ax = np.sqrt(-val/ev)
    th = math.degrees(math.atan2(evec[1, 0], evec[0, 0]))
    cen = cen*sc + [mx, my]; rx, ry = ax*sc
    cand = [((((th + 90*k + 180) % 360) - 180),) + ((rx, ry) if k % 2 == 0 else (ry, rx))
            for k in range(4)]
    best = min(cand, key=lambda z: abs(z[0]))
    t, r1, r2 = best
    ct, st = math.cos(math.radians(t)), math.sin(math.radians(t))
    u = (x-cen[0])*ct + (y-cen[1])*st; v = -(x-cen[0])*st + (y-cen[1])*ct
    k = np.hypot(u/r1, v/r2); r = np.hypot(u, v)
    res = float(np.max(np.abs(r - r/np.maximum(k, 1e-12))))
    rad = math.radians(-t)
    px = cen[0]*math.cos(rad) - cen[1]*math.sin(rad)
    py = cen[0]*math.sin(rad) + cen[1]*math.cos(rad)
    return dict(cx=cen[0], cy=cen[1], rx=r1, ry=r2, rot=t, res=res, rcx=px, rcy=py)

# ------------------------------------------------------------------- symmetry
def procrustes(A, B):
    """Best rotation+uniform-scale+translation taking A onto B (vectorised)."""
    ca, cb = A.mean(0), B.mean(0)
    A0, B0 = A - ca, B - cb
    Sxx = float((A0*B0).sum()); Sxy = float((A0[:, 0]*B0[:, 1] - A0[:, 1]*B0[:, 0]).sum())
    na = float((A0*A0).sum()) or 1e-12
    s = math.hypot(Sxx, Sxy)/na; th = math.atan2(Sxy, Sxx)
    co, si = math.cos(th)*s, math.sin(th)*s
    R = np.c_[co*A0[:, 0] - si*A0[:, 1], si*A0[:, 0] + co*A0[:, 1]]
    res = float(np.max(np.hypot(*(R - B0).T)))
    tx = cb[0] - (co*ca[0] - si*ca[1]); ty = cb[1] - (si*ca[0] + co*ca[1])
    return math.degrees(th), s, res, tx, ty

def resample(subs, n=360):
    """Longest subpath, resampled at even ARC LENGTH -- index-based resampling
    puts the two outlines out of step wherever their segment density differs,
    which fakes a large residual between shapes that actually match."""
    pts = np.array([[p.real, p.imag] for p in max(subs, key=len)])
    seg = np.r_[0, np.cumsum(np.hypot(*np.diff(pts, axis=0).T))]
    if seg[-1] == 0: return np.repeat(pts[:1], n, 0)
    t = np.linspace(0, seg[-1], n, endpoint=False)
    return np.c_[np.interp(t, seg, pts[:, 0]), np.interp(t, seg, pts[:, 1])]

def best_match(A, B):
    """Try every cyclic alignment and both traversal directions; keep the best.
    Two outlines of the same shape can start at different points and wind
    opposite ways, and either mismatch alone hides a perfect fit."""
    out = None
    for cand in (B, B[::-1]):
        for sh in range(len(cand)):
            r = procrustes(A, np.roll(cand, sh, axis=0))
            if out is None or r[2] < out[2]: out = r
    return out

# ------------------------------------------------------------------------ main
def main():
    argv = [a for a in sys.argv[1:] if not a.startswith('--')]
    sym = '--symmetry' in sys.argv
    svg = open(argv[0], encoding='utf8').read()
    vb = re.search(r'viewBox="([-\d.eE\s,]+)"', svg)
    W = float(vb.group(1).split()[2]) if vb else 100.0
    ps = paths_of(svg)
    print(f'{len(ps)} path(s), viewBox width {W:g}  (0.5% = {W*0.005:.3f} units)\n')
    if sym:
        S = [resample(sample(p['d'])) for p in ps]
        for i in range(len(S)):
            for j in range(i+1, len(S)):
                th, s, res, tx, ty = best_match(S[i], S[j])
                tag = 'RIGID COPY' if res < W*0.005 and abs(s-1) < 0.01 else 'different'
                print(f'path[{i}] -> path[{j}]: angle={th:7.2f}  scale={s:.4f}  '
                      f'residual={res:.4f}  {tag}')
                if tag == 'RIGID COPY':
                    print(f'    transform="matrix({math.cos(math.radians(th)):.6g} '
                          f'{math.sin(math.radians(th)):.6g} {-math.sin(math.radians(th)):.6g} '
                          f'{math.cos(math.radians(th)):.6g} {tx:.6g} {ty:.6g})"')
        return
    for i, p in enumerate(ps):
        subs = sample(p['d'])
        label = f'path[{i}]' + (f' #{p["id"]}' if p['id'] else '') + (f' {p["fill"]}' if p['fill'] else '')
        if len(subs) != 1:
            print(f'{label}: {len(subs)} subpaths - fit each separately if needed'); continue
        P = np.array([[q.real, q.imag] for q in subs[0]])
        f = fit_ellipse(P)
        if not f: print(f'{label}: not a conic'); continue
        ok = f['res'] < W*0.005
        print(f'{label}: residual={f["res"]:.4f} {"ELLIPSE" if ok else "(not an ellipse)"}')
        if ok:
            if abs(f['rot']) < 0.3:
                same = abs(f['rx']-f['ry']) < W*0.002
                tag = 'circle' if same else 'ellipse'
                print(f'    <{tag} cx="{f["cx"]:.2f}" cy="{f["cy"]:.2f}" '
                      + (f'r="{f["rx"]:.2f}"' if same else f'rx="{f["rx"]:.2f}" ry="{f["ry"]:.2f}"') + '/>')
            else:
                print(f'    <ellipse cx="{f["rcx"]:.2f}" cy="{f["rcy"]:.2f}" rx="{f["rx"]:.2f}" '
                      f'ry="{f["ry"]:.2f}" transform="rotate({f["rot"]:.2f})"/>')

if __name__ == '__main__':
    main()
