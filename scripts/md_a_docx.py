#!/usr/bin/env python3
"""Informe Markdown -> .docx a dos columnas.
Uso (desde la raiz): python scripts/md_a_docx.py docs/INFORME_IEEE.md docs/INFORME_IEEE.docx"""
import re, sys
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH as AL
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, Cm

FUENTE = "Times New Roman"

def cols(sec, n):
    sp = sec._sectPr
    c = sp.find(qn("w:cols"))
    if c is None:
        c = OxmlElement("w:cols"); sp.append(c)
    c.set(qn("w:num"), str(n)); c.set(qn("w:space"), "425")

def runs(p, texto, tam):
    for t in re.split(r"(\*\*[^*]+\*\*|`[^`]+`)", texto):
        if not t:
            continue
        if t.startswith("**"):
            r = p.add_run(t[2:-2]); r.bold = True; r.font.name = FUENTE
        elif t.startswith("`"):
            r = p.add_run(t[1:-1]); r.font.name = "Courier New"
        else:
            r = p.add_run(t); r.font.name = FUENTE
        r.font.size = Pt(tam)

def par(doc, texto, tam=9.5, al=AL.JUSTIFY, antes=0, despues=4):
    p = doc.add_paragraph(); p.alignment = al
    p.paragraph_format.space_before = Pt(antes)
    p.paragraph_format.space_after = Pt(despues)
    runs(p, texto, tam)
    return p

def tabla(doc, filas):
    filas = [f for f in filas if not re.match(r"^\|[\s:\-|]+\|$", f)]
    datos = [[c.strip() for c in f.strip().strip("|").split("|")] for f in filas]
    t = doc.add_table(rows=len(datos), cols=len(datos[0])); t.style = "Table Grid"
    t.autofit = False
    ancho = Cm(8.2 / len(datos[0]))
    for fila in t.rows:
        for c in fila.cells:
            c.width = ancho
    for i, fila in enumerate(datos):
        for j, txt in enumerate(fila):
            p = t.cell(i, j).paragraphs[0]; p.alignment = AL.CENTER
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.keep_with_next = True
            runs(p, txt, 8)
            if i == 0:
                for r in p.runs:
                    r.bold = True
    par(doc, "", 4, AL.LEFT, 0, 2)

def figura(doc, ruta, cap, ancho):
    if ancho:
        a = doc.add_section(WD_SECTION.CONTINUOUS); cols(a, 1)
    p = doc.add_paragraph(); p.alignment = AL.CENTER
    p.paragraph_format.space_after = Pt(2)
    p.add_run().add_picture(ruta, width=Cm(ancho or 7.5))
    par(doc, cap, 8, AL.CENTER, 0, 6)
    if ancho:
        b = doc.add_section(WD_SECTION.CONTINUOUS); cols(b, 2)

def main(src, dst):
    doc = Document()
    s = doc.sections[0]
    s.page_width, s.page_height = Cm(21), Cm(29.7)
    s.left_margin = s.right_margin = s.top_margin = s.bottom_margin = Cm(1.8)
    doc.styles["Normal"].font.name = FUENTE
    cols(s, 1)
    lineas = open(src, encoding="utf-8").read().split("\n")
    cuerpo, i = False, 0
    while i < len(lineas):
        l = lineas[i].rstrip(); i += 1
        if not l.strip():
            continue
        if l.startswith("# "):
            par(doc, "**" + l[2:] + "**", 16, AL.CENTER, 0, 6); continue
        if l.startswith("## "):
            if not cuerpo:
                n = doc.add_section(WD_SECTION.CONTINUOUS); cols(n, 2); cuerpo = True
            par(doc, "**" + l[3:].upper() + "**", 10, AL.CENTER, 6, 3); continue
        if not cuerpo:
            par(doc, l, 9, AL.CENTER, 0, 8); continue
        if l.startswith("|"):
            bloque = [l]
            while i < len(lineas) and lineas[i].startswith("|"):
                bloque.append(lineas[i].rstrip()); i += 1
            tabla(doc, bloque); continue
        m = re.match(r"^!\[(.*)\]\((.*)\)$", l)
        if m:
            cap, ruta = m.group(1), m.group(2)
            figura(doc, ruta, cap, None if "E39" in ruta else (13 if "fig_cluster" in ruta else 16.5))
            continue
        m = re.match(r"^([A-H]\. [^:]{2,70}:)(.*)$", l)
        if m:
            p = par(doc, "", 9.5)
            r = p.add_run(m.group(1)); r.italic = True; r.font.size = Pt(9.5); r.font.name = FUENTE
            runs(p, m.group(2), 9.5)
        else:
            par(doc, l, 9.5)
    doc.save(dst)
    print("OK", dst)

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
