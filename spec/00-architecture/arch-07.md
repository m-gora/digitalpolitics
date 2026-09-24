# Design
Here are the design instructions from the party portal.

These tokens are hard-coded for a single party by design; see adr-02 (single-tenant model).

## Colors

Farbwelt
Dunkelblau - die Tiefe unserer Vision. Gelb - die Wärme unserer Leidenschaft. Hellblau - ein Signal von Hoffnung.

Gelb
HEX #FFE000
RGB 255 / 224 / 0
CMYK 0 / 8 / 100 / 0
RAL Classic 1018
Pantone 107C
Primärfarbe Gelb

Dunkelblau
HEX #032D67
RGB 3 / 45 / 103
CMYK 100 / 75 / 0 / 40
RAL Design 270 30 30
Pantone 7687C
Primärfarbe Blau

Cyan
HEX #00A7E7
RGB 0 / 167 / 231
CMYK 90 / 0 / 0 / 0
RAL Classic 5012
Pantone 2995C
Sekundärfarbe Hellblau

Schwarz
HEX #000000
RGB 0 / 0 / 0
CMYK 0 / 0 / 0 / 100
RAL 9005
Pantone Black C
Tertiärfarbe Schwarz

Weiß
HEX #FFFFFF
RGB 255 / 255 / 255
CMYK 0 / 0 / 0 / 0
RAL 9003
Pantone -
Tertiärfarbe Weiß

## Typography

Unsere Typografie wird zur Stimme, die nicht zaudert. Geradlinig, direkt, prägnant - eine Schriftfamilie, die spricht, ohne umschweifig zu werden.

Die Schriftfamilie Public Sans (alle Schnitte) steht hier zum Download bereit

Corporate-Schrift und Einsatz

Auf gelbem Hintergrund
Public Sans Black
Public Sans Black
Einsatz: Headlines
Laufweite: −30
Zeilenabstand: 80-100 %

Auf blauem Hintergrund
Public Sans Extrabold
Public Sans Extrabold
Einsatz: Headlines
Laufweite: −30
Zeilenabstand: 80-100 %

Auf allen Farbhintergründen
Public Sans Bold
Einsatz: Subheadlines
Laufweite: −10 bis −30
Zeilenabstand: 100 %

Public Sans Medium
Public Sans Regular
Einsatz: Fließtexte
Laufweite: 0
Zeilenabstand: 110-130 %

Corporate-Schrift
Die Public Sans ist ein vielseitig ausgebauter Open-Source Google-(Web-)Font, kostenlos für die kommerzielle Nutzung, entwickelt für hohe Lesbarkeit, mit kommunikativer, sachlicher Anmutung.

Anwendung
Auf blauem Hintergrund wird bei Headlines der Extrabold-Schnitt verwendet - so entsteht ein optischer Ausgleich (Buchstaben laufen optisch nicht zu). Textausrichtung generell linksbündig. Je nach Größe, Materialität und Medium: Regular oder Medium für Fließtexte.

Zeilenabstand
Sofern sich Buchstaben mit Unterlängen (z. B. g, p, q) nicht mit der darunterstehenden Zeile überschneiden, kann der Zeilenabstand auf bis zu 80 % reduziert werden.

# Logo

Complete FDP logo SVG (also used as `app/src/dpp/static/img/fdp-logo.svg`):

```svg
<svg id="Ebene_1" xmlns="http://www.w3.org/2000/svg" version="1.1" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 178.08 69.73" style="width:120px;height:auto;display:block">
  <defs>
    <style>
      .st0-gelb { fill: #FFE000; }
      .st1-gelb { fill: none; }
      .st2-gelb { clip-path: url(#clippath-gelb-1); }
      .st3-gelb { clip-path: url(#clippath-gelb-2); }
      .st4-gelb { clip-path: url(#clippath-gelb); }
    </style>
    <clipPath id="clippath-gelb">
      <rect class="st1-gelb" width="51.89" height="69.73"></rect>
    </clipPath>
    <clipPath id="clippath-gelb-1">
      <rect class="st1-gelb" x="53.47" width="64.32" height="69.73"></rect>
    </clipPath>
    <clipPath id="clippath-gelb-2">
      <rect class="st1-gelb" x="119.45" width="58.63" height="69.73"></rect>
    </clipPath>
  </defs>
  <g class="st4-gelb">
    <polygon class="st0-gelb" points="50.89 1 50.89 15.13 18.64 15.13 18.64 28.98 46.53 28.98 46.53 42.64 18.64 42.64 18.64 68.73 1 68.73 1 1 50.89 1"></polygon>
  </g>
  <g class="st2-gelb">
    <path class="st0-gelb" d="M79.01,54.59h-6.9V15.13h7.7c11.92,0,19.33,5.91,19.33,19.43,0,14.92-6.51,20.03-20.13,20.03ZM83.68,1h-29.22v67.73h29.59c19.92,0,32.72-11.95,32.72-34.15S103.98,1,83.68,1Z"></path>
  </g>
  <g class="st3-gelb">
    <path class="st0-gelb" d="M150.24,32.49c5.6,0,9.2-2.56,9.2-8.44s-3.7-8.92-9.2-8.92h-12.14v17.36h12.14ZM152.8,1c14.32,0,24.28,7.3,24.28,21.91,0,15.37-7.97,23.24-24.47,23.24h-14.51v22.58h-17.64V1h32.35Z"></path>
  </g>
</svg>
```
