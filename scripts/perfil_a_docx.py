#!/usr/bin/env python3
"""Perfil Markdown -> .docx de una columna.
Uso: python scripts/perfil_a_docx.py docs/PERFIL_TECNICO.md docs/PERFIL_TECNICO.docx"""
import re, sys
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH as AL
from docx.shared import Cm
from md_a_docx import par

def main(src, dst):
    doc = Document()
    s = doc.sections[0]
    s.page_width, s.page_height = Cm(21), Cm(29.7)
    s.left_margin = s.right_margin = Cm(1.8)
    s.top_margin = s.bottom_margin = Cm(1.5)
    doc.styles["Normal"].font.name = "Times New Roman"
    for l in open(src, encoding="utf-8").read().split("\n"):
        l = l.rstrip()
        if not l.strip():
            continue
        l = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\1", l)
        if l.startswith("# "):
            par(doc, "**" + l[2:] + "**", 15, AL.CENTER, 0, 3)
        elif l.startswith("## "):
            par(doc, "**" + l[3:] + "**", 11, AL.LEFT, 5, 2)
        elif re.match(r"^\s*- ", l):
            nivel = (len(l) - len(l.lstrip())) // 2
            p = par(doc, "• " + l.strip()[2:], 9.5, AL.JUSTIFY, 0, 1)
            p.paragraph_format.left_indent = Cm(0.6 + 0.5 * nivel)
            p.paragraph_format.first_line_indent = Cm(-0.3)
        else:
            par(doc, l, 9.5, AL.JUSTIFY, 0, 3)
    doc.save(dst)
    print("OK", dst)

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
