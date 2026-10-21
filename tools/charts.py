"""README charts as static SVG cards (no dependencies), each in a light and a dark version (the README picks one with
<picture>; GitHub shows them as images, so there is no hover: every value is printed).

  donut_card   part-to-whole of a few categories (subjects): categorical slots in fixed order, 2px surface gaps,
               the total in the hole, a legend with hours and share (the light-mode yellow/aqua/pink are under 3:1
               contrast, so the printed legend is required, not decoration)
  bars_card    magnitude across many categories (motion types): one hue on a recessive track, values at the bar ends

Colours: the validated reference palette (dataviz skill, references/palette.md), checked with validate_palette.js.
"""
import html
import math

FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif"
THEMES = {
    'light': dict(card='#ffffff', border='#d1d9e0', ink='#1f2328', ink2='#59636e', ink3='#818b98', track='#eff2f5',
                  bar='#2a78d6', cat=['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300']),
    'dark': dict(card='#0d1117', border='#3d444d', ink='#f0f6fc', ink2='#9198a1', ink3='#6e7681', track='#21262d',
                 bar='#3987e5', cat=['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#008300']),
}
W, H = 560, 360          # one card; two side by side fill a README row


def fmt_h(h):
    return '–' if not h else f'{h:,.0f} h' if h >= 10 else f'{h:.1f} h'


def fmt_pct(x):
    return '' if not x else '<0.1 %' if x < 0.001 else f'{100 * x:.1f} %' if x < 0.1 else f'{100 * x:.0f} %'


def _card(t, title, subtitle, body):
    e = html.escape
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" '
            f'aria-label="{e(title)}" font-family="{FONT}">\n'
            f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" fill="{t["card"]}" stroke="{t["border"]}"/>\n'
            f'<text x="28" y="40" font-size="16" font-weight="600" fill="{t["ink"]}">{e(title)}</text>\n'
            f'<text x="28" y="62" font-size="12.5" fill="{t["ink2"]}">{e(subtitle)}</text>\n' + body + '</svg>\n')


def _arc(cx, cy, r0, r1, a0, a1):
    """an annulus sector from angle a0 to a1 (radians, clockwise from 12 o'clock)"""
    p = lambda r, a: (cx + r * math.sin(a), cy - r * math.cos(a))  # noqa: E731
    large = 1 if a1 - a0 > math.pi else 0
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = p(r1, a0), p(r1, a1), p(r0, a1), p(r0, a0)
    return (f'M{x0:.2f},{y0:.2f} A{r1},{r1} 0 {large} 1 {x1:.2f},{y1:.2f} L{x2:.2f},{y2:.2f} '
            f'A{r0},{r0} 0 {large} 0 {x3:.2f},{y3:.2f} Z')


def donut_card(rows, title, subtitle, total_label, theme='light', slots=None):
    """rows: [(label, value)] in the categorical order; zero / unknown values are listed, not drawn. slots: each row's
    categorical colour, fixed per entity so a new category does not repaint the others (default: the row order)"""
    t, e = THEMES[theme], html.escape
    total = sum(v for _, v in rows) or 1
    col = [t["cat"][k] for k in (slots or range(len(rows)))]
    cx, cy, r1, r0, gap = 142, 210, 104, 70, 2.0               # gap: px of surface between segments
    out, a = [], 0.0
    drawn = [(i, v) for i, (_, v) in enumerate(rows) if v > 0]
    for i, v in drawn:
        span = 2 * math.pi * v / total
        if len(drawn) == 1:                                    # one category: a full ring (an arc cannot close on itself)
            out.append(f'<circle cx="{cx}" cy="{cy}" r="{(r0 + r1) / 2}" fill="none" stroke="{col[i]}" stroke-width="{r1 - r0}"/>')
            break
        trim = min(span / 2 * 0.9, gap / 2 / r0)             # half the gap at each end, measured on the inner edge
        if span - 2 * trim > 1e-4:
            out.append(f'<path d="{_arc(cx, cy, r0, r1, a + trim, a + span - trim)}" fill="{col[i]}"/>')
        a += span
    out.append(f'<text x="{cx}" y="{cy - 2}" text-anchor="middle" font-size="26" font-weight="600" fill="{t["ink"]}">{e(total_label)}</text>')
    out.append(f'<text x="{cx}" y="{cy + 20}" text-anchor="middle" font-size="12" fill="{t["ink2"]}">hours of motion</text>')
    lx, ly, step = 282, 210 - (len(rows) - 1) * 30 / 2, 30     # legend: swatch · name · hours · share, centred on the ring
    for i, (label, v) in enumerate(rows):
        y = round(ly + i * step, 1)
        out.append(f'<rect x="{lx}" y="{y - 6}" width="12" height="12" rx="3" fill="{col[i] if v > 0 else t["track"]}"/>')
        out.append(f'<text x="{lx + 20}" y="{y}" dy="0.35em" font-size="13" fill="{t["ink"]}">{e(label)}</text>')
        out.append(f'<text x="{W - 78}" y="{y}" dy="0.35em" text-anchor="end" font-size="13" font-weight="600" fill="{t["ink"]}">{fmt_h(v)}</text>')
        out.append(f'<text x="{W - 28}" y="{y}" dy="0.35em" text-anchor="end" font-size="12" fill="{t["ink2"]}">{e(fmt_pct(v / total)) if v > 0 else "n/a"}</text>')
    return _card(t, title, subtitle, '\n'.join(out) + '\n')


def bars_card(rows, title, subtitle, theme='light'):
    """rows: [(label, value)], largest first; one hue, a full-width track behind each bar, value + share at the end"""
    t, e = THEMES[theme], html.escape
    total = sum(v for _, v in rows) or 1
    vmax = max([v for _, v in rows] + [1e-9])
    x0, label_w, val_w, top = 28, 150, 104, 92
    bx, bw = x0 + label_w, W - x0 - label_w - val_w - 28
    step = min(26.0, (H - top - 20) / max(1, len(rows)))
    bh = 8
    out = []
    for i, (label, v) in enumerate(rows):
        y = round(top + i * step, 1)
        out.append(f'<text x="{x0}" y="{y}" dy="0.35em" font-size="13" fill="{t["ink"]}">{e(label)}</text>')
        out.append(f'<rect x="{bx}" y="{y - bh / 2}" width="{bw}" height="{bh}" rx="{bh / 2}" fill="{t["track"]}"/>')
        w = 0 if v <= 0 else max(bh, bw * v / vmax)
        if w:
            out.append(f'<rect x="{bx}" y="{y - bh / 2}" width="{w:.2f}" height="{bh}" rx="{bh / 2}" fill="{t["bar"]}"/>')
        out.append(f'<text x="{W - 28 - 52}" y="{y}" dy="0.35em" text-anchor="end" font-size="13" font-weight="600" fill="{t["ink"]}">{fmt_h(v)}</text>')
        out.append(f'<text x="{W - 28}" y="{y}" dy="0.35em" text-anchor="end" font-size="12" fill="{t["ink2"]}">{e(fmt_pct(v / total))}</text>')
    return _card(t, title, subtitle, '\n'.join(out) + '\n')


# ---------------------------------------------------------------------------------------------------------------- quality
# severity tiers of a red flag (value / threshold): the palette's fixed status steps, never themed; every cell prints its
# value and the legend names the tiers, so colour never carries the meaning alone
SEVERITY = [(1.0, '#fab219', '#1f2328', '25–50 % of windows'), (2.0, '#ec835a', '#1f2328', '50–75 %'), (3.0, '#d03b3b', '#ffffff', 'over 75 %')]
NEUTRAL = {'light': '#f0efec', 'dark': '#383835'}


def quality_card(rows, cols, title, subtitle, theme='light'):
    """heatmap of red flags. rows: [(dataset name, [(text, severity or None)] per column)], cols: [(name, threshold text)];
    severity = value / threshold (< 1 is below the flag, None = not measured)"""
    t, e = THEMES[theme], html.escape
    lw, cw, rh, top = 196, 64, 20, 128
    w = 28 + lw + cw * len(cols) + 28
    h = top + rh * len(rows) + 64
    out = []
    for k, (name, thr) in enumerate(cols):                       # column heads: metric and its threshold
        x = 28 + lw + cw * k + cw / 2
        out.append(f'<text x="{x}" y="{top - 26}" text-anchor="middle" font-size="12" font-weight="600" fill="{t["ink"]}">{e(name)}</text>')
        out.append(f'<text x="{x}" y="{top - 10}" text-anchor="middle" font-size="11" fill="{t["ink3"]}">{e(thr)}</text>')
    for i, (name, cells) in enumerate(rows):
        y = top + rh * i
        short = name if len(name) <= 27 else name[:25].rstrip() + '…'
        out.append(f'<text x="{28 + lw - 10}" y="{y + rh / 2}" dy="0.35em" text-anchor="end" font-size="12" fill="{t["ink"]}">{e(short)}</text>')
        for k, (text, sev) in enumerate(cells):
            x = 28 + lw + cw * k
            flagged = sev is not None and sev > 1                    # strictly over, as tools/quality.py flags
            if sev is None:                                          # not measured: an outline, so it never reads as "fine"
                out.append(f'<rect x="{x + 1.5}" y="{y + 1.5}" width="{cw - 3}" height="{rh - 3}" rx="3" fill="none" stroke="{t["border"]}"/>')
                ink = t['ink3']
            else:
                fill, ink = (NEUTRAL[theme], t['ink2']) if not flagged else [(c, k) for lo, c, k, _ in SEVERITY if sev > lo][-1]
                out.append(f'<rect x="{x + 1}" y="{y + 1}" width="{cw - 2}" height="{rh - 2}" rx="3" fill="{fill}"/>')   # 2px surface gaps
            out.append(f'<text x="{x + cw / 2}" y="{y + rh / 2}" dy="0.35em" text-anchor="middle" font-size="11" '
                       f'font-weight="{600 if flagged else 400}" fill="{ink}">{e(text)}</text>')
    ly = top + rh * len(rows) + 30                               # legend
    items = [(NEUTRAL[theme], 'up to 25 % of windows')] + [(c, lab) for _, c, _, lab in SEVERITY] + [(None, 'not measured')]
    x = 28 + lw
    for c, lab in items:
        out.append(f'<rect x="{x}" y="{ly - 6}" width="12" height="12" rx="3" ' + (f'fill="{c}"/>' if c else f'fill="none" stroke="{t["border"]}"/>'))
        out.append(f'<text x="{x + 18}" y="{ly}" dy="0.35em" font-size="12" fill="{t["ink2"]}">{e(lab)}</text>')
        x += 34 + 6.6 * len(lab)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" '
            f'aria-label="{e(title)}" font-family="{FONT}">\n'
            f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" fill="{t["card"]}" stroke="{t["border"]}"/>\n'
            f'<text x="28" y="40" font-size="16" font-weight="600" fill="{t["ink"]}">{e(title)}</text>\n'
            f'<text x="28" y="62" font-size="12.5" fill="{t["ink2"]}">{e(subtitle)}</text>\n' + '\n'.join(out) + '\n</svg>\n')


# ---------------------------------------------------------------------------------------------------------------- trend
def trend_card(points, notes, title, subtitle, start, theme='light', w=1136, h=380):
    """cumulative hours over time, stepping up at each release month (months are not labelled, years are). points:
    [(t, cumulative hours)] with t in fractional years, the first one at `start` holding everything released before it;
    notes: {t: (label, hours added)} for direct labels on the biggest steps"""
    t, e = THEMES[theme], html.escape
    x0, x1, y0, y1 = 84, w - 40, h - 52, 96                     # plot box: left, right, bottom (baseline), top
    ta, tb = start, math.floor(points[-1][0]) + 1                 # x from `start` to the end of the last year
    top = max(p[1] for p in points)
    step = next(s for s in (50, 100, 200, 250, 500, 1000, 2000) if top / s <= 5)
    ymax = step * math.ceil(top / step)
    X = lambda tt: x0 + (tt - ta) / (tb - ta) * (x1 - x0)         # noqa: E731
    Y = lambda v: y0 - v / ymax * (y0 - y1)                       # noqa: E731
    out = []
    for k in range(0, int(ymax / step) + 1):                     # recessive grid + y labels
        v = k * step; yy = Y(v)
        out.append(f'<line x1="{x0}" y1="{yy:.1f}" x2="{x1}" y2="{yy:.1f}" stroke="{t["track"]}" stroke-width="1"/>')
        out.append(f'<text x="{x0 - 10}" y="{yy:.1f}" dy="0.35em" text-anchor="end" font-size="11.5" fill="{t["ink3"]}">{v:,} h</text>')
    for yr in range(int(ta), int(tb) + 1):                        # year ticks; the first reads "before <year>"
        xx = X(yr)
        out.append(f'<line x1="{xx:.1f}" y1="{y0}" x2="{xx:.1f}" y2="{y0 + 5}" stroke="{t["border"]}"/>')
        if yr < tb:
            lab = f'before {yr}' if yr == ta else str(yr)
            out.append(f'<text x="{xx:.1f}" y="{y0 + 22}" text-anchor="{"start" if yr == ta else "middle"}" font-size="11.5" fill="{t["ink3"]}">{lab}</text>')
    path = [(X(points[0][0]), Y(points[0][1]))]                   # flat until the next release month, then up
    for (_, va), (tb_, vb) in zip(points, points[1:]):
        path += [(X(tb_), Y(va)), (X(tb_), Y(vb))]
    path.append((X(tb), Y(points[-1][1])))
    line = ' '.join(f'{"M" if i == 0 else "L"}{px:.1f},{py:.1f}' for i, (px, py) in enumerate(path))
    area = f'M{x0},{y0} L{x0},{path[0][1]:.1f} ' + ' '.join(f'L{px:.1f},{py:.1f}' for px, py in path) + f' L{X(tb):.1f},{y0} Z'
    out.append(f'<path d="{area}" fill="{t["bar"]}" fill-opacity="0.12"/>')
    out.append(f'<path d="{line}" fill="none" stroke="{t["bar"]}" stroke-width="2" stroke-linejoin="round"/>')
    for tt, v in points[1:]:                                      # a small mark at each release month
        out.append(f'<circle cx="{X(tt):.1f}" cy="{Y(v):.1f}" r="3" fill="{t["bar"]}" stroke="{t["card"]}" stroke-width="1.5"/>')
    # direct labels, one line each, biggest steps first: the first candidate spot (up-left of the step, below-right on
    # its flat run, left of its rise) that hits neither the line nor a placed label; none fits -> no label
    segs = [(min(p[0], q[0]), max(p[0], q[0]), min(p[1], q[1]), max(p[1], q[1])) for p, q in zip(path, path[1:])]
    hit = lambda r: any(r[0] < s1 + 2 and s0 - 2 < r[1] and r[2] < s3 + 2 and s2 - 2 < r[3] for s0, s1, s2, s3 in segs)   # noqa: E731
    placed, cum, prev = [], dict(points), {b_: a_ for a_, b_ in zip([p[0] for p in points], [p[0] for p in points][1:])}
    for tt, (name, add) in sorted(notes.items(), key=lambda kv: -kv[1][1]):
        px, py = X(tt), Y(cum[tt]); txt = f'+{add:,.0f} h'
        wd = 6.6 * len(name) + 7 * len(txt) + 6
        lo = Y(cum[prev[tt]]) if tt in prev else py                  # where the rise starts
        cands = [(px - 6 - wd, px - 6, py - 19, py - 5),             # up-left
                 (px + 6, px + 6 + wd, py + 5, py + 19),             # below-right, under its flat run
                 (px - 6 - wd, px - 6, (py + lo) / 2 - 7, (py + lo) / 2 + 7)]   # left of its rise
        cands += [(px - 70 - wd, px - 70, y1 - 14 + 18 * k, y1 + 18 * k) for k in range(8)]   # callouts in the empty top, with a leader
        for n_, r in enumerate(cands):
            if n_ >= 3 and math.hypot(px - r[1], py - (r[2] + r[3]) / 2) > 110:   # leaders stay short
                continue
            if r[0] >= x0 and r[1] <= x1 + 30 and r[2] >= y1 - 30 and r[3] <= y0 - 2 and not hit(r) and \
                    not any(r[0] < q1 and q0 < r[1] and r[2] < q3 and q2 < r[3] for q0, q1, q2, q3 in placed):
                placed.append((r[0] - 4, r[1] + 4, r[2] - 3, r[3] + 3))
                if n_ >= 3:
                    out.append(f'<path d="M{r[1] + 4:.1f},{(r[2] + r[3]) / 2:.1f} L{px - 5:.1f},{py - 3:.1f}" stroke="{t["ink3"]}" stroke-width="1" fill="none"/>')
                out.append(f'<text x="{r[0]:.1f}" y="{r[3] - 3:.1f}" font-size="12" fill="{t["ink"]}">'
                           f'<tspan font-weight="600">{e(name)}</tspan> <tspan fill="{t["ink2"]}">{e(txt)}</tspan></text>')
                break
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" '
            f'aria-label="{e(title)}" font-family="{FONT}">\n'
            f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" fill="{t["card"]}" stroke="{t["border"]}"/>\n'
            f'<text x="28" y="40" font-size="16" font-weight="600" fill="{t["ink"]}">{e(title)}</text>\n'
            f'<text x="28" y="62" font-size="12.5" fill="{t["ink2"]}">{e(subtitle)}</text>\n' + '\n'.join(out) + '\n</svg>\n')
