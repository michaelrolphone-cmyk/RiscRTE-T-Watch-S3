#!/usr/bin/env python3
"""Normalize the supplied HTML's SVG at 10:42:18.250, animation phase 15s.

Inkscape needs CSS class fonts/rotations expanded and pathLength dash units
converted. This is a reference-render preparation step, not firmware code.
"""
from pathlib import Path
import math,re
ROOT=Path(__file__).resolve().parent
source=(ROOT/'NOVA-7-original.html').read_text()
svg=re.search(r'<svg.*?</svg>',source,re.S).group(0).replace('viewBox=','width="240" height="240" viewBox=',1)
ticks=[]
for i in range(60):
    a=(i*6-90)*math.pi/180;q=i%15==0;m=i%5==0;r=101 if q else 105 if m else 110
    ticks.append(f'<line x1="{120+116*math.cos(a)}" y1="{120+116*math.sin(a)}" x2="{120+r*math.cos(a)}" y2="{120+r*math.sin(a)}" stroke="'+('#fff' if q else '#19e3ff' if m else '#0e4f5c')+f'" stroke-width="{3 if q else 2 if m else 1}"'+(' stroke-linecap="round"' if q else '')+'/>')
svg=svg.replace('<g id="ticks"></g>','<rect width="240" height="240" fill="black"/><g id="ticks">'+''.join(ticks)+'</g>')
svg=svg.replace('class="o"','font-family="Orbitron"').replace('class="r"','font-family="Rajdhani"')
svg=svg.replace('class="spin"','transform="rotate(60 120 120)"').replace('class="spin2"','transform="rotate(-135 120 120)"')
svg=svg.replace('pathLength="60" stroke-dasharray="0 60"',f'stroke-dasharray="{18.25/60*math.tau*98} {math.tau*98}"')
a=(18.25*6-90)*math.pi/180
svg=svg.replace('<circle id="dot"',f'<circle cx="{120+98*math.cos(a)}" cy="{120+98*math.sin(a)}" id="dot"').replace('>00</text>','>18</text>')
(ROOT/'reference-104218.svg').write_text(svg)
