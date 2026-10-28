# -*- coding: utf-8 -*-
"""Build the Solace hardware design documentation PDF."""
import csv
import os
import re
import subprocess
import sys

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Frame,
                                KeepTogether, NextPageTemplate, PageBreak,
                                PageTemplate, Paragraph, Spacer, Table, TableStyle)
from reportlab.platypus.flowables import Flowable, HRFlowable
from reportlab.platypus.tableofcontents import TableOfContents

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

OUT = os.path.join("docs", "Solace_Hardware_Design_Documentation_RevB.pdf")
TMP_A = "_build_a.pdf"
TMP_B = "_build_b.pdf"
SCH_PDF = "_schematic.pdf"
SCH_SRC = "main.kicad_sch"

KICAD = r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"

DATE = "2026-10-28"
DOC_ID = "SL-HW-001"
REV = "B"
COMMIT = "527f3d5"

# ---------------------------------------------------------------- palette
NAVY = colors.HexColor("#16324F")
NAVY_D = colors.HexColor("#0E2135")
ACCENT = colors.HexColor("#2F7BB5")
INK = colors.HexColor("#1F2933")
MUTED = colors.HexColor("#66788A")
RULE = colors.HexColor("#C8D4E0")
LIGHT = colors.HexColor("#F3F6F9")
BAND = colors.HexColor("#E8EFF5")

# ---------------------------------------------------------------- fonts
FONT, FONT_B, MONO = "Helvetica", "Helvetica-Bold", "Courier"
UNICODE = False
try:
    fd = r"C:\Windows\Fonts"
    if os.path.exists(os.path.join(fd, "segoeui.ttf")):
        pdfmetrics.registerFont(TTFont("SegoeUI", os.path.join(fd, "segoeui.ttf")))
        pdfmetrics.registerFont(TTFont("SegoeUI-Bold", os.path.join(fd, "segoeuib.ttf")))
        pdfmetrics.registerFont(TTFont("Consolas", os.path.join(fd, "consola.ttf")))
        registerFontFamily("SegoeUI", normal="SegoeUI", bold="SegoeUI-Bold",
                           italic="SegoeUI", boldItalic="SegoeUI-Bold")
        FONT, FONT_B, MONO = "SegoeUI", "SegoeUI-Bold", "Consolas"
        UNICODE = True
except Exception as e:  # pragma: no cover
    print("font fallback:", e)

TRANS = {"\u00b5": "u", "\u03a9": "Ohm", "\u00b0": "deg", "\u2013": "-",
         "\u2014": "-", "\u00b7": "-", "\u2019": "'", "\u201c": '"',
         "\u201d": '"', "\u2192": "->", "\u00d7": "x", "\u2026": "..."}


def tx(s):
    if UNICODE:
        return s
    for k, v in TRANS.items():
        s = s.replace(k, v)
    return s


# ---------------------------------------------------------------- styles
def S(name, **kw):
    base = dict(fontName=FONT, fontSize=9.2, leading=13.2, textColor=INK,
                spaceBefore=0, spaceAfter=0, alignment=TA_LEFT)
    base.update(kw)
    return ParagraphStyle(name, **base)


ST = {
    "body": S("body", spaceAfter=5.5),
    "lead": S("lead", fontSize=10.2, leading=15.4, textColor=colors.HexColor("#3A4A5A"),
              spaceAfter=8),
    "h1": S("H1", fontName=FONT_B, fontSize=14.5, leading=18, textColor=NAVY,
            spaceBefore=2, spaceAfter=2),
    "h1x": S("h1x", fontName=FONT_B, fontSize=14.5, leading=18, textColor=NAVY,
             spaceBefore=2, spaceAfter=2),
    "h2": S("H2", fontName=FONT_B, fontSize=10.4, leading=14, textColor=ACCENT,
            spaceBefore=11, spaceAfter=3),
    "bullet": S("bullet", leftIndent=13, bulletIndent=3, spaceAfter=3.2),
    "cell": S("cell", fontSize=8.1, leading=10.6),
    "cellb": S("cellb", fontName=FONT_B, fontSize=8.1, leading=10.6),
    "th": S("th", fontName=FONT_B, fontSize=7.9, leading=10.4,
            textColor=colors.white),
    "cap": S("cap", fontSize=7.7, leading=10.4, textColor=MUTED, spaceBefore=3),
    "note": S("note", fontSize=8.2, leading=11.6, textColor=colors.HexColor("#40515F")),
}

M = 51.0
PW, PH = A4
CW = PW - 2 * M

TOTAL = 0


# ---------------------------------------------------------------- helpers
def P(text, style="body"):
    return Paragraph(tx(text), ST[style])


def H1(text):
    return KeepTogether([Spacer(1, 12), P(text, "h1"),
                         HRFlowable(width="100%", thickness=0.9, color=NAVY,
                                    spaceBefore=3, spaceAfter=9)])


def H2(text):
    return P(text, "h2")


def BULLETS(items):
    return [Paragraph(tx(i), ST["bullet"], bulletText="\u2022") for i in items]


def TBL(rows, widths, head=True, small=False, align=None, zebra=True):
    data = []
    for r_i, row in enumerate(rows):
        line = []
        for c_i, cellv in enumerate(row):
            if isinstance(cellv, str):
                st = ST["th"] if (head and r_i == 0) else (
                    ST["cellb"] if c_i == 0 and small is False and head else ST["cell"])
                line.append(Paragraph(tx(cellv), st))
            else:
                line.append(cellv)
        data.append(line)
    t = Table(data, colWidths=widths, repeatRows=1 if head else 0, hAlign="LEFT",
              splitByRow=1)
    cmds = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3.6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.6),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
        ("BOX", (0, 0), (-1, -1), 0.6, RULE),
    ]
    if head:
        cmds += [("BACKGROUND", (0, 0), (-1, 0), NAVY),
                 ("TOPPADDING", (0, 0), (-1, 0), 5),
                 ("BOTTOMPADDING", (0, 0), (-1, 0), 5)]
        if zebra:
            for i in range(1, len(rows)):
                if i % 2 == 0:
                    cmds.append(("BACKGROUND", (0, i), (-1, i), LIGHT))
    elif zebra:
        for i in range(0, len(rows)):
            if i % 2 == 1:
                cmds.append(("BACKGROUND", (0, i), (-1, i), LIGHT))
    t.setStyle(TableStyle(cmds))
    return t


def CALLOUT(text, colour=ACCENT):
    t = Table([[Paragraph(tx(text), ST["note"])]], colWidths=[CW], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F0F6FB")),
        ("LINEBEFORE", (0, 0), (0, -1), 2.4, colour),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return t


# ---------------------------------------------------------------- diagram
class BlockDiagram(Flowable):
    W = CW
    H = 372

    def __init__(self):
        Flowable.__init__(self)
        self.width = self.W
        self.height = self.H

    def _box(self, x, y, w, h, title, sub="", fill=LIGHT, stroke=RULE,
             tcol=NAVY, scol=MUTED, bold=True):
        c = self.canv
        Y = self.H - y - h
        c.setFillColor(fill)
        c.setStrokeColor(stroke)
        c.setLineWidth(0.7)
        c.roundRect(x, Y, w, h, 3.2, stroke=1, fill=1)
        c.setFillColor(tcol)
        c.setFont(FONT_B if bold else FONT, 7.4)
        if sub:
            c.drawCentredString(x + w / 2.0, Y + h - 12.5, title)
            c.setFillColor(scol)
            c.setFont(FONT, 5.9)
            c.drawCentredString(x + w / 2.0, Y + h - 22.0, sub)
        else:
            c.drawCentredString(x + w / 2.0, Y + h / 2.0 - 2.6, title)

    def _arrow(self, x1, y1, x2, y2, head=True):
        c = self.canv
        c.setStrokeColor(colors.HexColor("#5A7186"))
        c.setFillColor(colors.HexColor("#5A7186"))
        c.setLineWidth(0.65)
        c.line(x1, self.H - y1, x2, self.H - y2)
        if head:
            import math
            ang = math.atan2(-(y2 - y1), (x2 - x1))
            L, Wd = 4.6, 2.3
            px, py = x2, self.H - y2
            c.setLineWidth(0)
            p = c.beginPath()
            p.moveTo(px, py)
            p.lineTo(px - L * math.cos(ang) + Wd * math.sin(ang),
                     py - L * math.sin(ang) - Wd * math.cos(ang))
            p.lineTo(px - L * math.cos(ang) - Wd * math.sin(ang),
                     py - L * math.sin(ang) + Wd * math.cos(ang))
            p.close()
            c.drawPath(p, stroke=0, fill=1)

    def _lbl(self, x, y, text, anchor="l"):
        c = self.canv
        c.setFillColor(MUTED)
        c.setFont(FONT, 5.6)
        if anchor == "c":
            c.drawCentredString(x, self.H - y, text)
        elif anchor == "r":
            c.drawRightString(x, self.H - y, text)
        else:
            c.drawString(x, self.H - y, text)

    def draw(self):
        # row geometry
        r1, r2, r3, r4, r5, r6 = 4, 62, 120, 180, 240, 316
        hh = 36
        self._box(20, r1, 210, hh, "USB-C receptacle", "5 V - CC sink - ESD - 1.1 A fuse")
        self._box(263, r1, 210, hh, "Li-ion cell", "JST-PH connector - 3.0 to 4.2 V")
        self._box(20, r2, 210, hh, "TP4056 charger", "500 mA - CHRG# / STDBY# to MCU")
        self._box(263, r2, 210, hh, "DW01A + FS8205A", "cell protection, BAT- path")
        self._box(20, r3, 453, 34, "Power path  -  D1 Schottky (USB)  +  Q4 PMOS (cell)  ->  VSYS",
                  "", fill=BAND, stroke=colors.HexColor("#A9BED3"))
        self._box(20, r4, 218, hh, "AP2112K-3.3", "600 mA  ->  +3V3")
        self._box(255, r4, 218, hh, "TPS7A2033", "300 mA low-noise  ->  AUDIO_3V3")
        self._box(20, r5, 453, 44, "RP2350B",
                  "QFN-80 - dual Cortex-M33 - QSPI / SPI / I2S / I2C / SDIO / GPIO",
                  fill=NAVY, stroke=NAVY_D, tcol=colors.white, scol=colors.HexColor("#B9CDE0"))

        # peripherals
        pw, gap = 46, 6
        xs = [20 + i * (pw + gap) for i in range(9)]
        per = [("QSPI flash", "16 MB"), ("PSRAM", "8 MB"), ("microSD", "TF-01A"),
               ("TFT", "200x648"), ("DAC + amp", "-> jack"), ("Haptics", "DRV2605L"),
               ("Sensors", "IMU/enc"), ("RTC", "PCF8563"), ("Mic", "I2S MEMS")]
        for x, (t, s) in zip(xs, per):
            self._box(x, r6, pw, 44, t, s)

        # power flow
        self._arrow(125, r1 + hh, 125, r2)
        self._lbl(129, r2 - 6, "5 V")
        self._arrow(368, r1 + hh, 368, r2)
        self._lbl(372, r2 - 6, "BAT-")
        self._arrow(125, r2 + hh, 125, r3)
        self._lbl(129, r3 - 6, "BAT+")
        self._arrow(368, r2 + hh, 368, r3)
        # power path -> LDOs
        ymid = r3 + 34 + 8
        self._arrow(246, r3 + 34, 246, ymid, head=False)
        self._arrow(129, ymid, 364, ymid, head=False)
        self._arrow(129, ymid, 129, r4)
        self._arrow(364, ymid, 364, r4)
        self._lbl(251, ymid - 5, "VSYS")
        # LDOs -> MCU
        ymid2 = r4 + hh + 8
        self._arrow(129, r4 + hh, 129, ymid2, head=False)
        self._arrow(364, r4 + hh, 364, ymid2, head=False)
        self._arrow(129, ymid2, 364, ymid2, head=False)
        self._arrow(246, ymid2, 246, r5)
        # MCU -> peripheral bus
        bus = r5 + 44 + 16
        self._arrow(246, r5 + 44, 246, bus, head=False)
        self._arrow(xs[0] + pw / 2, bus, xs[-1] + pw / 2, bus, head=False)
        for x in xs:
            self._arrow(x + pw / 2, bus, x + pw / 2, r6)


# ---------------------------------------------------------------- cover
def draw_cover(c, doc):
    c.saveState()
    c.setFillColor(colors.white)
    c.rect(0, 0, PW, PH, stroke=0, fill=1)

    # top band
    c.setFillColor(NAVY)
    c.rect(0, PH - 150, PW, 150, stroke=0, fill=1)
    c.setFillColor(ACCENT)
    c.rect(0, PH - 153, PW, 3, stroke=0, fill=1)

    c.setFillColor(colors.white)
    c.setFont(FONT_B, 25)
    c.drawString(M, PH - 78, "SOLACE")
    c.setFont(FONT, 7.6)
    c.setFillColor(colors.HexColor("#9FBBD4"))
    c.drawString(M, PH - 95, "P O R T A B L E   H I - F I   M U S I C   P L A Y E R")

    c.setFont(FONT, 7.6)
    c.setFillColor(colors.HexColor("#9FBBD4"))
    c.drawRightString(PW - M, PH - 78, "HARDWARE DESIGN DOCUMENTATION")
    c.setFont(FONT_B, 7.6)
    c.setFillColor(colors.white)
    c.drawRightString(PW - M, PH - 95, "%s   -   REV %s" % (DOC_ID, REV))

    # title block
    c.setFillColor(NAVY)
    c.setFont(FONT_B, 30)
    c.drawString(M, PH - 235, "Hardware Design")
    c.setFillColor(ACCENT)
    c.drawString(M, PH - 270, "Documentation")

    c.setFillColor(RULE)
    c.setLineWidth(0.8)
    c.line(M, PH - 292, PW - M, PH - 292)

    c.setFillColor(MUTED)
    c.setFont(FONT, 9.4)
    c.drawString(M, PH - 312, "Architecture, electrical specification, interfaces and design rationale")

    # at a glance
    top = PH - 350
    c.setStrokeColor(RULE)
    c.setLineWidth(0.8)
    c.line(M, top, PW - M, top)
    stats = [("16 MB", "QSPI flash"), ("8 MB", "PSRAM"),
             ("2.83 in", "200x648 TFT"), ("500 mA", "USB-C charge")]
    cwid = (PW - 2 * M) / 4.0
    for i, (big, small) in enumerate(stats):
        x = M + i * cwid
        c.setFillColor(NAVY)
        c.setFont(FONT_B, 14)
        c.drawString(x, top - 26, big)
        c.setFillColor(MUTED)
        c.setFont(FONT, 6.9)
        c.drawString(x, top - 38, small.upper())

    # metadata
    rows = [("Document", DOC_ID), ("Revision", REV), ("Date", DATE),
            ("Status", "Schematic complete - PCB pending"),
            ("Baseline", COMMIT), ("EDA", "KiCad 10.0")]
    y = PH - 500
    for k, v in rows:
        c.setFillColor(MUTED)
        c.setFont(FONT, 8.0)
        c.drawString(M, y, k.upper())
        c.setFillColor(INK)
        c.setFont(FONT_B, 8.6)
        c.drawString(M + 96, y, v)
        c.setStrokeColor(colors.HexColor("#E2E9F0"))
        c.setLineWidth(0.5)
        c.line(M, y - 7, M + 330, y - 7)
        y -= 26

    # footer strip
    c.setFillColor(NAVY)
    c.rect(0, 0, PW, 34, stroke=0, fill=1)
    c.setFillColor(colors.HexColor("#9FBBD4"))
    c.setFont(FONT, 7.0)
    c.drawString(M, 13, "RP2350B  -  2.83 in 200x648 TFT  -  PCM5102A + TPA6132A2  -  microSD  -  RTC  -  MEMS mic  -  USB-C")
    c.setFillColor(colors.white)
    c.setFont(FONT_B, 7.0)
    c.drawRightString(PW - M, 13, "%s Rev %s" % (DOC_ID, REV))
    c.restoreState()


def draw_body(c, doc):
    p = c.getPageNumber()
    c.saveState()
    c.setStrokeColor(RULE)
    c.setLineWidth(0.6)
    c.line(M, PH - M + 16, PW - M, PH - M + 16)
    c.setFont(FONT, 7.3)
    c.setFillColor(MUTED)
    c.drawString(M, PH - M + 21, "Solace  -  Hardware Design Documentation")
    c.drawRightString(PW - M, PH - M + 21, "%s  -  Rev %s" % (DOC_ID, REV))

    c.line(M, M - 16, PW - M, M - 16)
    c.drawString(M, M - 28, DATE)
    c.drawRightString(PW - M, M - 28, "Page %d of %d" % (p, TOTAL))
    c.restoreState()


# ---------------------------------------------------------------- document
class Doc(BaseDocTemplate):
    def __init__(self, fn):
        BaseDocTemplate.__init__(self, fn, pagesize=A4, title="Solace - Hardware Design Documentation",
                                 author="Solace hardware project", subject="Hardware architecture and specification",
                                 creator="KiCad 10.0 + reportlab", leftMargin=M, rightMargin=M,
                                 topMargin=M, bottomMargin=M)
        f_cover = Frame(0, 0, PW, PH, id="cover", leftPadding=0, rightPadding=0,
                        topPadding=0, bottomPadding=0)
        f_body = Frame(M, 68, CW, 698, id="body", leftPadding=0, rightPadding=0,
                       topPadding=0, bottomPadding=0)
        self.addPageTemplates([
            PageTemplate(id="cover", frames=[f_cover], onPage=draw_cover),
            PageTemplate(id="body", frames=[f_body], onPage=draw_body),
        ])

    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph):
            nm = flowable.style.name
            if nm in ("H1", "H2"):
                txt = flowable.getPlainText()
                lvl = 0 if nm == "H1" else 1
                key = self.seq.nextf("sec")
                self.canv.bookmarkPage(key)
                self.canv.addOutlineEntry(txt, key, level=lvl, closed=False)
                self.notify("TOCEntry", (lvl, txt, self.page, key))


# ---------------------------------------------------------------- data
def read_bom():
    rows = []
    with open("main.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            fp = r["Footprint"]
            fp = fp.split(":")[-1] if ":" in fp else fp
            rows.append((r["Reference"], r["Qty"], r["Value"], fp))
    return rows


def netlist_stats():
    s = open("main.txt", encoding="utf-8").read().replace("\r\n", "\n")
    comps = set(re.findall(r'\(comp\s*\n\s*\(ref "([^"]+)"\)', s))
    nets = re.findall(r'^\t\t\(net$', s, re.M)
    return len(comps), len(nets)


# ---------------------------------------------------------------- story
def build_story():
    st = []
    st += [NextPageTemplate("body"), PageBreak()]

    # ---- document control
    st.append(H1("Document control"))
    st.append(P("This document is the controlled hardware description for the Solace portable music "
                "player. It defines the architecture, the electrical specification, the interface "
                "assignment and the design rationale, and records the outstanding work required before "
                "prototype build.", "lead"))
    st.append(Spacer(1, 4))
    st.append(TBL([["Field", "Value"],
                   ["Document identifier", DOC_ID],
                   ["Revision", REV],
                   ["Date", DATE],
                   ["Status", "Schematic complete and netlist-verified. No PCB layout."],
                   ["Source baseline", "main.kicad_sch, working tree at " + DATE + " (HEAD " + COMMIT + " plus review edits)"],
                   ["EDA tool", "KiCad 10.0"],
                   ["Revision history", "Rev B - see revision history below."]],
                  [130, CW - 130]))
    st.append(Spacer(1, 10))
    st.append(P("Revision history", "h2"))
    st.append(TBL([["Rev", "Date", "Description", "By"],
                   ["B", DATE, "Adds the PCF8563TS real-time clock with CR1220 backup and an I2S MEMS "
                    "microphone. Haptic pads replaced by connector J4. Verification figures refreshed. "
                    "Review pass adds mic / button pull-ups, haptic-trigger and LCD-control bias, and "
                    "reduces C14 to 1 uF.", "-"],
                   ["A", "2026-10-27", "Initial issue. Schematic complete: 14-pin display, load sharing, "
                    "firmware charger control, external thermistor.", "-"]],
                  [34, 62, CW - 96 - 34 - 62 + 96 - 96, 96]))

    # ---- contents
    st.append(PageBreak())
    st.append(P("Contents", "h1x"))
    st.append(HRFlowable(width="100%", thickness=0.9, color=NAVY, spaceBefore=3, spaceAfter=10))
    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle("toc1", fontName=FONT_B, fontSize=8.9, leading=15.5, textColor=NAVY,
                       spaceBefore=1.5),
        ParagraphStyle("toc2", fontName=FONT, fontSize=8.2, leading=12.6, textColor=MUTED,
                       leftIndent=16),
    ]
    st.append(toc)
    st.append(Spacer(1, 6))
    st.append(P("Appendices are listed at the end: A - Bill of materials, B - Schematic (A2 fold-out).",
                "cap"))

    # ================================================== 1 introduction
    st.append(PageBreak())
    st.append(H1("1  Introduction"))
    st.append(P("Solace is a pocket-sized, battery-powered music player built around the Raspberry Pi "
                "RP2350B microcontroller. Audio files reside on a microSD card, are decoded on the MCU "
                "and are played out through a PCM5102A digital-to-analogue converter and a TPA6132A2 "
                "capless headphone amplifier to a 3.5 mm jack. A 2.83 inch 200x648 SPI TFT carries the "
                "user interface, a DRV2605L provides haptic feedback, and an IMU, a magnetic rotary "
                "encoder and six buttons provide input. A PCF8563TS real-time clock with a coin-cell "
                "backup keeps time across battery changes, and an I2S MEMS microphone supports "
                "voice-driven mini-games.", "lead"))

    st.append(H2("1.1  Purpose of this document"))
    st.append(P("To record the electrical design in a form that can be reviewed independently of the "
                "schematic, to fix the interface contract between hardware and firmware, and to make "
                "the known limitations explicit before a PCB is committed."))

    st.append(H2("1.2  Scope of this revision"))
    st.append(TBL([["Work item", "State"],
                   ["Schematic capture", "Complete - netlist verified, ERC reviewed"],
                   ["Component selection and BOM", "Complete - LCSC part numbers recorded"],
                   ["PCB layout", "Outline drafted - no placement or routing"],
                   ["Enclosure / mechanical", "Not started"],
                   ["Firmware", "Not part of this repository"],
                   ["Prototype build and validation", "Pending"]],
                  [CW * 0.42, CW * 0.58]))

    st.append(H2("1.3  Reference documents"))
    st.append(P("The following are held in the project repository and were used to derive this design."))
    st.append(TBL([["Reference", "Location"],
                   ["RP2350 datasheet", "docs/datasheets/rp2350/rp2350-datasheet-3.pdf"],
                   ["Hardware design with RP2350", "docs/datasheets/rp2350/RP-008280-DS-2-hardware-design-with-rp2350.pdf"],
                   ["TFT panel specification, C14 (14-pin FPC)", "docs/datasheets/panels/SPEC ZJY283-2064KIWPG03-C14 VER A.pdf"],
                   ["TFT panel specification, H12 (12-pin FPC, alternative)", "docs/datasheets/panels/SPEC ZJY283-2064KIWPG02-H12 VER A.pdf"],
                   ["TFT panel specification, CON8 (8-pin, legacy)", "docs/datasheets/panels/ZJY283S0800TG01.pdf"],
                   ["Component datasheets", "Datasheet URL on each symbol; see Appendix A"]],
                  [CW * 0.55, CW * 0.45]))

    st.append(H2("1.4  Conventions"))
    st.append(P("Net names and component designators are quoted verbatim from the schematic. Voltages "
                "are DC unless stated. Current figures for the backlight and audio chain are design "
                "estimates derived from the datasheets, not measured values, and are marked as such "
                "where they appear."))

    # ================================================== 2 architecture
    st.append(H1("2  System architecture"))
    st.append(P("The design divides into a power subsystem that produces two regulated rails, a compute "
                "core with external QSPI memory and removable storage, and a set of peripherals on SPI, "
                "I2S, I2C and SDIO.", "lead"))
    st.append(Spacer(1, 2))
    st.append(BlockDiagram())
    st.append(P("Figure 1 - System block diagram. The power path selects between USB input and cell, so the "
                "cell is isolated from the load whenever USB is present.", "cap"))
    st.append(Spacer(1, 8))

    st.append(H2("2.1  Subsystem summary"))
    st.append(TBL([["Subsystem", "Principal devices", "Interface", "Section"],
                   ["Power", "TP4056, DW01A, FS8205A, AP2112K-3.3, TPS7A2033", "analogue", "4"],
                   ["Compute", "RP2350B, W25Q128JV, APS6404L", "QSPI, USB", "5"],
                   ["Display", "ZJY283-2064KIWPG03-C14, GC9B72", "SPI1 + GPIO", "6"],
                   ["Audio", "PCM5102A, TPA6132A2, PJ-342", "I2S + analogue", "7"],
                   ["Haptics", "DRV2605L", "I2C + GPIO", "8"],
                   ["Sensing", "LSM6DSO, AS5600, TCA9554", "I2C", "9"],
                   ["Input", "6x EVQP1Y05M tactile switches", "I2C expander", "9"],
                   ["Timing", "PCF8563TS, 32.768 kHz crystal, CR1220 backup", "I2C", "9.3"],
                   ["Audio input", "I2S MEMS microphone", "I2S (PIO)", "9.4"],
                   ["Storage", "TF-01A microSD socket", "SDIO (4-bit)", "10"]],
                  [62, CW * 0.46, 92, 44]))

    # ================================================== 3 electrical spec
    st.append(H1("3  Electrical specification"))
    st.append(H2("3.1  Supply rails"))
    st.append(TBL([["Rail", "Source", "Nominal", "Load", "Notes"],
                   ["VSYS", "D1 or Q4 (power path)", "3.0 - 4.65 V", "system", "USB 5 V less Schottky drop, or cell"],
                   ["+3V3", "AP2112K-3.3 (U4)", "3.30 V", "600 mA max", "digital domains and backlight"],
                   ["AUDIO_3V3", "TPS7A2033 (U5)", "3.30 V", "300 mA max", "low noise; ferrite-split per DAC domain"],
                   ["+1V1", "RP2350 internal buck", "1.10 V", "core", "external 3.3 uH inductor L10"]],
                  [58, 108, 66, 62, CW - 294]))

    st.append(H2("3.2  Power budget (estimated)"))
    st.append(TBL([["Load", "Current at +3V3", "Basis"],
                   ["RP2350B + QSPI flash + PSRAM", "35 mA", "estimate at 150 MHz"],
                   ["Display logic (GC9B72)", "10 mA", "datasheet IDD 8-10 mA"],
                   ["Backlight (R35 = 3.3 ohm)", "95 mA", "derived, see 6.3"],
                   ["PCM5102A", "20 mA", "datasheet typical"],
                   ["TPA6132A2 (playing)", "25 mA", "datasheet typical"],
                   ["AS5600 + IMU + expander + SD idle", "7 mA", "datasheet typical"],
                   ["RTC + MEMS microphone", "1 mA", "datasheet typical"],
                   ["Regulator quiescent", "1 mA", "two LDOs"],
                   ["Total, screen on", "194 mA", ""],
                   ["Total, screen off", "99 mA", ""],
                   ["Average at 40 % screen duty", "137 mA", "planning figure"]],
                  [CW * 0.5, 90, CW - 90 - CW * 0.5]))

    st.append(H2("3.3  Battery life"))
    st.append(P("Runtime from the 136 mA planning figure, after allowing roughly 15 % of nameplate "
                "capacity to be unusable because the LDO drops out near the end of discharge (see 4.7)."))
    st.append(TBL([["Cell capacity", "Usable", "Runtime (estimate)"],
                   ["1000 mAh", "850 mAh", "6.2 h"],
                   ["1500 mAh", "1275 mAh", "9.3 h"],
                   ["2000 mAh", "1700 mAh", "12.4 h"]],
                  [110, 110, CW - 220]))
    st.append(P("A 4 to 6 hour target needs roughly 550 to 850 mAh of usable capacity, so a 1500 mAh cell "
                "(about 1275 mAh usable) gives more than 9 hours. The backlight is approximately 70 % of "
                "the budget, so it remains the effective runtime control.", "cap"))

    st.append(H2("3.4  Margins and limits"))
    st.append(TBL([["Parameter", "Value", "Assessment"],
                   ["Panel VDD", "3.3 V", "Equal to the panel maximum recommended value; absolute max 4.6 V. Safe, no margin - do not raise."],
                   ["Backlight LED current", "50 - 95 mA", "Rated 100/120/145 mA. Below nominal by design; see 6.3."],
                   ["Charge current", "500 mA", "R5 = 2.4k. Requires a cell of at least about 1000 mAh."],
                   ["LDO dropout", "approx 3.45 V input", "Sets the practical end-of-discharge point; see 4.7."],
                   ["RP2350 core rail", "1.10 V from internal buck", "Matches the reference design exactly."]],
                  [130, 82, CW - 212]))

    # ================================================== 4 power
    st.append(H1("4  Power subsystem"))
    st.append(H2("4.1  Topology"))
    st.append(P("The charging and system rails are deliberately separated. The cell connects to BAT+ and "
                "nothing else on the load side; the system runs from VSYS, which is fed either by the USB "
                "input through a Schottky diode or by the cell through a P-channel MOSFET."))
    st.append(CALLOUT("Load sharing is not cosmetic. If the load hangs on BAT+, the TP4056 never sees the "
                      "current fall to its termination threshold, so it holds the cell at 4.2 V for as long as "
                      "the device is on and connected. Separating the rails restores correct charge "
                      "termination and removes that standing stress."))

    st.append(H2("4.2  Charger"))
    st.append(TBL([["Parameter", "Value", "Reference"],
                   ["Charger IC", "TP4056, ESOP-8", "U2"],
                   ["Programmed current", "500 mA (R5 = 2.4 kohm, I = 1200 / R)", "R5"],
                   ["Status outputs", "CHRG# to GPIO18, STDBY# to GPIO22", "both active low, open drain"],
                   ["Status pull-ups", "10 kohm to +3V3", "R13, R49"],
                   ["Enable", "CHARGE_EN (see 4.5)", "Q5, R47, R48"],
                   ["Temperature sense", "TEMP tied to GND - internal cut-out disabled", "see 4.6"]],
                  [104, CW * 0.52, CW - 104 - CW * 0.52]))

    st.append(H2("4.3  Load sharing"))
    st.append(TBL([["Ref", "Part", "Function"],
                   ["D1", "B5819WS (SOD-323)", "USB to VSYS; blocks battery back-feed to the port"],
                   ["Q4", "AO3401A P-MOSFET", "Cell to VSYS; source on VSYS, drain on BAT+"],
                   ["R44", "100 ohm", "Gate pull-up to USB_5V"],
                   ["R45", "100 kohm", "Gate pull-down"],
                   ["C66", "22 uF", "VSYS bulk"],
                   ["C67", "10 uF", "BAT+ / charger output"]],
                  [40, 150, CW - 190]))
    st.append(Spacer(1, 6))
    st.append(TBL([["USB present", "Gate", "Q4", "Cell to load", "System source"],
                   ["Yes", "approx 5.0 V", "off", "disconnected", "USB via D1, about 4.65 V"],
                   ["No", "0 V", "on", "connected", "cell via Q4, about 3.0-4.2 V"]],
                  [80, 82, 40, 100, CW - 302]))
    st.append(P("The MOSFET is oriented source-to-load so that its body diode conducts cell to load and is "
                "reverse-biased when USB is present. Reversing the part would allow USB to charge the cell "
                "around the charger - this orientation is a safety requirement, not a preference.", "cap"))

    st.append(H2("4.4  Regulators"))
    st.append(P("A separate low-noise regulator feeds the audio chain so that the MCU's switching core "
                "supply and the backlight do not modulate the analogue rail. AUDIO_3V3 is then split per "
                "domain through ferrites L5 to L8 into the DAC's AVDD, CPVDD and DVDD and the amplifier's "
                "VDD."))

    st.append(H2("4.5  Charger control from firmware"))
    st.append(P("CE is not tied to USB. It is pulled up to USB_5V by R47, so charging is enabled by default, "
                "and an N-channel MOSFET Q5 can pull it low to stop charging. The MCU drives only Q5's gate; "
                "5 V never reaches an RP2350 pin."))
    st.append(TBL([["Condition", "CHARGE_CTL (GPIO21)", "Q5", "CE", "Charging"],
                   ["MCU off, power switch open", "floating", "off (R48)", "5 V", "enabled"],
                   ["Boot, before firmware init", "high impedance", "off", "5 V", "enabled"],
                   ["Firmware allows", "driven low", "off", "5 V", "enabled"],
                   ["Firmware cuts", "driven high", "on", "0 V", "disabled"]],
                  [140, 118, 62, 40, CW - 360]))
    st.append(P("Charging is fail-safe: a dead MCU, a hung boot or an open power switch can never leave the "
                "device unable to charge. Cutting charge does not stop the system - it continues to run "
                "from USB or from the cell.", "cap"))

    st.append(H2("4.6  Battery monitoring"))
    st.append(TBL([["Quantity", "Network", "Conversion"],
                   ["Pack voltage", "R24 220 k / R28 100 k, C25 100 nF to GPIO40 (ADC0)",
                    "VBAT = 3.2 x V_ADC; full scale 4.2 V reads 1.31 V"],
                   ["Cell temperature", "J2 external NTC with R46 10 k to +3V3, C68 100 nF, to GPIO44 (ADC4)",
                    "R_NTC = 10 k x V / (3.3 - V); B = 3950, 10 k at 25 degC"]],
                  [92, CW * 0.5, CW - 92 - CW * 0.5]))
    st.append(Spacer(1, 6))
    st.append(P("The thermistor divider is referenced to the regulated +3V3 rail rather than to USB_5V, so "
                "the reading is valid whether or not USB is connected. The NTC is off-board on J2 because "
                "the board is single-sided: an on-board sensor would measure the PCB, not the cell."))
    st.append(CALLOUT("The TP4056 TEMP pin is tied to GND, which disables the charger's own thermal window "
                      "comparator. That comparator is ratiometric to VCC, so it cannot share the 3.3 V-referenced "
                      "sense node. The consequence is that over-temperature protection is entirely a firmware "
                      "responsibility: read ADC4, and drive CHARGE_CTL high when the cell is too hot."))

    st.append(H2("4.7  End of discharge and brownout"))
    st.append(P("The AP2112K stops regulating at roughly 3.45 V input, whereas the DW01A protection trips only "
                "near 2.5 V. Without intervention the device will therefore brown out and reset-loop as the "
                "cell empties. Firmware must monitor ADC0 and shut down gracefully at about 3.5 V, warning at "
                "3.6 V. Removing this limit would require a buck-boost converter, which is not fitted."))

    # ================================================== 5 compute
    st.append(H1("5  Compute and memory"))
    st.append(TBL([["Ref", "Device", "Function", "Notes"],
                   ["U16", "RP2350B, QFN-80", "Host MCU", "Dual Cortex-M33, external QSPI boot"],
                   ["U17", "W25Q128JVSIQ", "Program and asset storage", "128 Mbit = 16 MB, QSPI, chip select 0"],
                   ["U1", "APS6404L-3SQR-SN", "PSRAM", "64 Mbit = 8 MB, QSPI, chip select 1 on GPIO0"],
                   ["U18", "ABM8-272-T3", "12 MHz main crystal", "15 pF load caps C61/C62, 1 k series R23"],
                   ["L10", "AOTA-B201610S3R3-101-T", "Core buck inductor", "3.3 uH, polarised - observe the dot"]],
                  [36, 130, 118, CW - 284]))
    st.append(Spacer(1, 6))
    st.append(P("16 MB is the maximum bootable flash window: the QMI provides two 16 MB apertures, and the "
                "RP2350 bootrom requires a bootable partition to lie wholly within the first one. The PSRAM "
                "therefore occupies the second aperture rather than extending the flash. The core-rail "
                "network - the Abracon inductor and the 33 ohm / 4.7 uF filter on VREG_AVDD - is copied "
                "directly from the reference design and should not be substituted."))
    st.append(P("Debug access is a 3-pin SWD header (J3) plus RUN (SW11) and BOOTSEL (SW12) switches."))

    # ================================================== 6 display
    st.append(H1("6  Display"))
    st.append(H2("6.1  Panel and connector"))
    st.append(TBL([["Parameter", "Value"],
                   ["Panel", "ZJY283-2064KIWPG03-C14, 2.83 inch, 200 x 648, normally black"],
                   ["Driver IC", "GC9B72"],
                   ["Interface", "4-wire SPI, write only (no SDO and no TE on this variant)"],
                   ["Connector", "KH-FG0.5-H2.0-14P-SMT, 14-pin 0.5 mm FPC, H = 2.0 mm (U9)"],
                   ["FPC", "0.5 mm pitch, PI + FPC = 0.3 +/- 0.03 mm"],
                   ["Decoupling", "C63 1 uF at the panel VDD pin"]],
                  [110, CW - 110]))

    st.append(H2("6.2  Signal assignment"))
    st.append(TBL([["Panel pin", "Signal", "MCU", "Note"],
                   ["1", "GND", "-", ""],
                   ["2", "RESET", "GPIO7", "active low"],
                   ["3", "SCL", "GPIO10", "SPI1 SCK"],
                   ["4", "D/C", "GPIO8", "command / data"],
                   ["5", "CS", "GPIO9", "SPI1 CSn, active low"],
                   ["6", "SDA", "GPIO11", "SPI1 TX, latched on SCL rising edge"],
                   ["7", "NC", "-", ""],
                   ["8", "GND", "-", ""],
                   ["9", "VDD", "+3V3", "panel maximum"],
                   ["10", "LEDK", "Q2 drain", "via R35 3.3 ohm"],
                   ["11, 12", "GND", "-", ""],
                   ["13, 14", "NC", "-", ""]],
                  [62, 60, 78, CW - 200]))
    st.append(P("SPI mode 0 or 3. All three of clock, data and chip select run on hardware SPI1.", "cap"))

    st.append(H2("6.3  Backlight and brightness control"))
    st.append(P("The C14 variant exposes only the LED cathode. The LED anodes are tied internally to the "
                "panel's VDD, so the string is powered from +3V3 and the current is set by R35 in series "
                "with the low-side switch Q2. Brightness is set by PWM on the gate: GPIO6's alternate "
                "function 4 is PWM3 A, so a hardware PWM slice drives Q2 directly at a recommended 10 to "
                "20 kHz."))
    st.append(TBL([["Duty", "Average LED current", "Approximate luminance", "Note"],
                   ["100 %", "50 - 95 mA", "120 - 275 cd/m2", "panel rated 120 mA, 350 cd/m2"],
                   ["50 %", "25 - 48 mA", "60 - 140 cd/m2", ""],
                   ["0 %", "0 mA", "off", "matches the R36 default-off"]],
                  [52, 118, 118, CW - 288]))
    st.append(CALLOUT("Rated backlight brightness is not reachable on this panel variant. With VDD = 3.3 V and "
                      "a forward voltage of about 3.0 to 3.2 V there is only 0.1 to 0.3 V of headroom, so no "
                      "series resistor can regulate 120 mA. Achieved output is roughly one third to three "
                      "quarters of nominal, and it varies between panels. Reaching full brightness would need "
                      "the H12 12-pin variant, which exposes LEDA and permits a constant-current boost driver.",
                      colors.HexColor("#C46A2E")))

    # ================================================== 7 audio
    st.append(H1("7  Audio"))
    st.append(TBL([["Ref", "Device", "Function", "Notes"],
                   ["U6", "PCM5102A", "I2S DAC, 2.1 Vrms line output", "SCK tied low; clock derived from BCK"],
                   ["U11", "TPA6132A2", "Capless headphone amplifier", "Integrated charge pump, gain straps to -6 dB"],
                   ["CN1", "PJ-342", "3.5 mm TRS jack", "Switch contacts unused"],
                   ["L8", "Ferrite", "AUDIO_3V3 to amplifier VDD", ""]],
                  [36, 96, 128, CW - 260]))
    st.append(Spacer(1, 6))
    st.append(P("Signal path: RP2350 I2S (BCK GPIO3, DIN GPIO2, LRCK GPIO4) into the DAC; DAC outputs are "
                "AC-coupled through 1 uF into the amplifier's differential inputs; amplifier outputs drive "
                "the jack directly. XSMT (GPIO42) and the amplifier enable (GPIO43) both carry 10 kohm "
                "pull-downs, so the chain starts muted and the amplifier starts off."))
    st.append(H2("7.1  Jack wiring"))
    st.append(TBL([["Connector pin", "Function", "Evidence"],
                   ["CN1.2, CN1.5", "Ground (sleeve tabs)", "pad geometry, rear pair"],
                   ["CN1.3", "Right channel", "TPA6132_OUT_R"],
                   ["CN1.6", "Left channel", "TPA6132_OUT_L"],
                   ["CN1.4, CN1.7", "Switch contacts, unused", "front pair, no net"]],
                  [104, 150, CW - 254]))
    st.append(CALLOUT("The PJ-342 symbol carries generic pin names, so the tip / ring assignment has not been "
                      "proven from a datasheet. Before production, confirm with a continuity test on a real part "
                      "that CN1.3 and CN1.6 are tip and ring and that the sleeve is ground. A left / right swap "
                      "is the plausible error, and would be corrected with a two-pad rework or in firmware. "
                      "There is also no ESD protection on the jack lines; a TVS array and 33 to 68 ohm series "
                      "resistors are advisable for a consumer product."))

    st.append(H2("7.2  Loudness"))
    st.append(P("Loudness is adequate for standard earbuds and headphones. The limiting case is not the "
                "amplifier's output but the gain structure."))
    st.append(TBL([["Transducer", "Sensitivity", "Power at approx 0.6 Vrms", "Resulting level"],
                   ["16 ohm earbuds", "105 dB/mW", "25 mW", "about 119 dB SPL"],
                   ["32 ohm headphones", "100 dB/mW", "12 mW", "about 111 dB SPL"],
                   ["300 ohm headphones", "98 dB/mW", "1.3 mW", "about 99 dB SPL"]],
                  [110, 90, 130, CW - 330]))
    st.append(P("The DAC delivers 2.1 Vrms. With the gain straps (G0/G1 to ground) the TPA6132A2 runs at "
                "its lowest setting, -6 dB, so the output is about 1.05 Vrms - close to its maximum swing on a "
                "3.3 V rail. Digital volume should still be capped a few dB to avoid clipping into 16 to 32 ohm "
                "loads. Per the gain table, G0 high with G1 low selects 0 dB.", "cap"))

    # ================================================== 8 haptics
    st.append(H1("8  Haptics"))
    st.append(TBL([["Parameter", "Value"],
                   ["Driver", "DRV2605L, I2C, powered from +3V3"],
                   ["Actuator", "J4 2-pin header, nets HAPTIC_A / HAPTIC_B"],
                   ["Control", "EN on GPIO1, IN/TRIG on GPIO5"],
                   ["Local bulk", "C64 22 uF at the driver supply"],
                   ["Enable default", "R43 100 kohms pull-down on EN - driver off until firmware configures it"],
                   ["Trigger default", "R53 100 kohms pull-down on IN/TRIG - no trigger while GPIO5 floats"]],
                  [110, CW - 110]))
    st.append(P("Drive voltage equals +3V3, so the actuator must be a 2 to 3 V LRA or ERM. A 5 V ERM would "
                "require a boost converter that is not fitted."))

    # ================================================== 9 sensors
    st.append(H1("9  Sensors and user input"))
    st.append(H2("9.1  I2C bus"))
    st.append(P("A single I2C0 bus on GPIO16 (SDA) and GPIO17 (SCL) with 4.7 kohm pull-ups carries every "
                "peripheral plus the J1 expansion header."))
    st.append(TBL([["Device", "Ref", "Address", "Notes"],
                   ["LSM6DSO IMU", "U8", "0x6A", "SDO/SA0 tied low; INT1 to GPIO19"],
                   ["AS5600 magnetic encoder", "U12", "0x36", "DIR tied low; OUT and PGO unused"],
                   ["TCA9554 expander", "U14", "0x20", "A0-A2 tied low; INT to GPIO20"],
                   ["DRV2605L haptics", "U7", "0x5A", "REG cap C49 1 uF"],
                   ["PCF8563TS real-time clock", "U13", "0x51", "32.768 kHz crystal, coin-cell backup"],
                   ["J1 expansion header", "J1", "-", "4-pin: GND, +3V3, SCL, SDA"]],
                  [130, 40, 58, CW - 228]))

    st.append(H2("9.2  Buttons"))
    st.append(P("Six tactile switches connect to the expander with the common side to ground; the expander's "
                "open-drain interrupt reports changes on GPIO20, so no MCU pin is consumed per button."))
    st.append(TBL([["Button", "Switch", "Expander pin", "Net"],
                   ["Up", "SW3", "P0", "BTN_UP"],
                   ["Down", "SW4", "P1", "BTN_DOWN"],
                   ["Left", "SW6", "P2", "BTN_LEFT"],
                   ["Right", "SW7", "P3", "BTN_RIGHT"],
                   ["A", "SW8", "P4", "BTN_A"],
                   ["B", "SW10", "P5", "BTN_B"]],
                  [80, 70, 100, CW - 250]))
    st.append(P("The power switch SW5 is a slide switch in the regulator enable path, not a load switch: the "
                "regulator inputs remain at VSYS and only their enable pins are switched, with R10 holding "
                "them off. Reset is SW11 to the RP2350 RUN pin; BOOTSEL is SW12 via R42.", "cap"))

    st.append(H2("9.3  Real-time clock"))
    st.append(P("A PCF8563TS keeps wall-clock time across power cycles. It is a small I2C device on the "
                "shared bus at address 0x51, clocked by a 32.768 kHz crystal (Y2) with two 15 pF load "
                "capacitors. INT and CLKOUT are left unconnected, so time is read by polling the "
                "registers rather than through an interrupt."))
    st.append(TBL([["Parameter", "Value"],
                   ["Device", "PCF8563TS, TSSOP-8, I2C address 0x51 (U13)"],
                   ["Timebase", "Y2, 32.768 kHz, load caps C69 / C70 15 pF"],
                   ["Supply", "RTC_VDD, diode-OR of +3V3 and the backup cell"],
                   ["Backup", "U19 KH-CR1220-2 (C5365933) via D3 BAT54C; C71 100 nF"],
                   ["Unused outputs", "INT and CLKOUT left open"]],
                  [110, CW - 110]))
    st.append(P("D3 is a dual common-cathode Schottky wired as a diode-OR: anode 1 to +3V3, anode 2 to "
                "the cell, cathode to RTC_VDD. The clock therefore runs from the regulated rail whenever "
                "the device is on, and from the coin cell when it is off, with no switch-over logic and "
                "no firmware involvement.", "cap"))
    st.append(P("The cell is a CR1220 in an SMT holder on the component side, so the board stays "
                "single-sided. Note that the diode drops roughly 0.2 to 0.3 V; the PCF8563 therefore sees "
                "about 3.0 V on backup, well inside its 1.0 to 5.5 V range. The backup cell is only "
                "loaded by the RTC, so its shelf life dominates.", "cap"))

    st.append(H2("9.4  Microphone"))
    st.append(TBL([["Parameter", "Value"],
                   ["Device", "ICS-43434 I2S MEMS microphone (U15)"],
                   ["Data path", "MIC_BCLK GPIO23, MIC_WS GPIO24, MIC_DATA GPIO25"],
                   ["Channel select", "LR tied to GND (left channel)"],
                   ["Decoupling", "C72 100 nF and C73 1 uF at the supply pin"],
                   ["Data line", "R50 100 kohms pull-down on MIC_DATA (line discharge)"]],
                  [110, CW - 110]))
    st.append(P("The microphone is given its own I2S pins rather than sharing the DAC's bus. That spends "
                "three GPIOs that were otherwise free, but it keeps capture and playback independent, so "
                "the two can run at the same time without reconfiguring a shared PIO state machine."))
    st.append(P("As with the DAC, the I2S clocks come from a PIO program - the RP2350 has no dedicated "
                "I2S peripheral. The microphone's acoustic port must line up with an opening or gasket in "
                "the enclosure, because the MEMS element senses through the port, not at the board "
                "surface.", "cap"))

    # ================================================== 10 storage
    st.append(H1("10  Storage"))
    st.append(P("The microSD socket (TF-01A) is wired for 4-bit SDIO on freely assigned GPIOs, which suits a "
                "PIO-based SDIO host or a bit-banged implementation. Card detect is not connected."))
    st.append(TBL([["SD signal", "MCU pin", "Note"],
                   ["DAT0", "GPIO12", ""],
                   ["DAT1", "GPIO13", ""],
                   ["DAT2", "GPIO14", ""],
                   ["DAT3 / CS", "GPIO15", ""],
                   ["CMD", "GPIO39", ""],
                   ["CLK", "GPIO41", "shares an ADC pin, unused as analogue"]],
                  [100, 90, CW - 190]))

    # ================================================== 11 interfaces
    st.append(H1("11  Interface assignment"))
    st.append(P("Complete assignment of RP2350B general-purpose pins. Dedicated pins (QSPI, USB, crystal, "
                "SWD, RUN, regulator) are omitted."))
    gpio = [
        ("0", "77", "PSRAM chip select", "XIP_CS1n"),
        ("1", "78", "Haptic enable", "DRV2605L EN"),
        ("2", "79", "I2S data (DIN)", "PCM5102A DIN"),
        ("3", "80", "I2S bit clock (BCK)", "PCM5102A BCK"),
        ("4", "1", "I2S word clock", "PCM5102A LRCK"),
        ("5", "2", "Haptic trigger", "DRV2605L IN/TRIG"),
        ("6", "3", "LCD backlight PWM", "PWM3 A"),
        ("7", "4", "LCD reset", "active low"),
        ("8", "6", "LCD D/C", ""),
        ("9", "7", "LCD chip select", "SPI1 CSn"),
        ("10", "8", "LCD clock", "SPI1 SCK"),
        ("11", "9", "LCD data", "SPI1 TX"),
        ("12", "11", "SD DAT0", ""),
        ("13", "12", "SD DAT1", ""),
        ("14", "13", "SD DAT2", ""),
        ("15", "14", "SD DAT3", ""),
        ("16", "16", "I2C0 SDA", "shared bus"),
        ("17", "17", "I2C0 SCL", "shared bus"),
        ("18", "18", "Charger CHRG#", "low = charging"),
        ("19", "19", "IMU interrupt", "INT1"),
        ("20", "20", "Button interrupt", "expander INT"),
        ("21", "21", "Charger enable", "high = stop charging"),
        ("22", "22", "Charger STDBY#", "low = charge complete"),
        ("23", "23", "Mic bit clock", "MIC_BCLK"),
        ("24", "25", "Mic word clock", "MIC_WS"),
        ("25", "26", "Mic data", "MIC_DATA"),
        ("26-38", "-", "Free", "13 pins"),
        ("39", "48", "SD CMD", ""),
        ("40", "49", "Battery voltage", "ADC0"),
        ("41", "52", "SD clock", ""),
        ("42", "53", "DAC soft mute", "XSMT"),
        ("43", "54", "Headphone amp enable", ""),
        ("44", "55", "Cell temperature", "ADC4"),
        ("45-47", "-", "Free", "3 ADC-capable pins"),
    ]
    rows = [["GPIO", "Pin", "Function", "Note"]] + [list(g) for g in gpio]
    st.append(TBL(rows, [56, 40, 150, CW - 246]))

    # ================================================== 12 net naming
    st.append(H1("12  Net naming"))
    st.append(TBL([["Net", "Meaning"],
                   ["RP2354_GPIO<n>", "Direct MCU GPIO connection. The prefix says 2354 although the fitted part is an RP2350B."],
                   ["VSYS", "Post-power-path system rail: USB or cell"],
                   ["BAT+ / BAT-", "Cell terminals; BAT- is downstream of the protection FETs"],
                   ["+3V3, AUDIO_3V3, +1V1, GND", "Supply rails"],
                   ["USB_5V", "Fused USB input, ahead of the power path"],
                   ["LCD_LEDK, TEMP_SENSE", "Display backlight cathode, thermistor sense node"],
                   ["RTC_VDD, VBAT_CELL", "RTC supply after the diode-OR, and the backup cell terminal"],
                   ["MIC_BCLK, MIC_WS, MIC_DATA", "Microphone I2S bus"],
                   ["HAPTIC_A, HAPTIC_B", "Actuator drive from the haptic driver"],
                   ["CHARGE_EN, CHARGE_CTL, CHARGE_STAT", "Charger enable node, firmware control, charge-complete status"],
                   ["BTN_*", "Button nets between switch and expander"],
                   ["Net-(<ref>-<pin>)", "Auto-generated unnamed net"]],
                  [150, CW - 150]))
    st.append(P("Connectivity is label-based almost everywhere: most symbols carry global labels at their pin "
                "ends rather than drawn wires, so net identity comes from the label name. Renaming a label is "
                "therefore a rewire, and moving one silently relocates every pin on that label.", "cap"))

    # ================================================== 13 decisions
    st.append(H1("13  Design decisions"))
    dec = [
        ("Load sharing was added", "With the load on BAT+, the charger never terminates and holds the cell "
         "at 4.2 V while the device is used on USB. VSYS separates the two."),
        ("Q4 orientation", "Source on the load side makes the body diode block USB to cell conduction. This "
         "is a safety property; the part must not be reversed."),
        ("Charger control is open drain", "A direct GPIO would either leave charging disabled when the MCU is "
         "off, or inject 5 V into an unpowered pin. The MOSFET plus pull-up avoids both."),
        ("Temperature is referenced to +3V3", "So the reading is valid without USB. This is precisely why the "
         "TP4056 TEMP comparator, which is ratiometric to VCC, cannot share the node."),
        ("The thermistor is off-board", "The board is single-sided, so an on-board sensor would measure the "
         "PCB rather than the cell."),
        ("Display moved from 8 to 14 pins", "The C14 panel replaced the earlier 8-pin FPC; connector U13 was "
         "removed and U9 wired to the C14 pin table."),
        ("SPI moved to hardware SPI1", "The earlier pin choice could not be served by a single SPI "
         "peripheral, since GPIO6 belongs to SPI0 and GPIO8 to SPI1."),
        ("Separate audio regulator", "Keeps the analogue rail away from the MCU's switching core supply and "
         "the PWM backlight."),
        ("RTC backup is a diode-OR", "A BAT54C from +3V3 and the coin cell needs no switch-over logic and "
         "keeps the clock alive whether or not the pack is fitted."),
        ("The microphone has its own I2S pins", "Sharing the DAC's PIO I2S bus would force capture and "
         "playback to take turns. Three spare GPIOs were available, so they were spent on independence."),
    ]
    st.append(TBL([["#", "Decision", "Rationale"]] +
                  [[str(i + 1), d[0], d[1]] for i, d in enumerate(dec)],
                  [22, 128, CW - 150]))

    # ================================================== 14 limitations
    st.append(H1("14  Limitations and open items"))
    st.append(P("The following are known as of revision B. The first four affect behaviour and must be "
                "understood before the first prototype.", "lead"))
    st.append(TBL([["#", "Item", "Impact", "Status"],
                   ["1", "Backlight cannot reach rated brightness", "Output about one third to three quarters of nominal, panel to panel variation", "Accepted - see 6.3"],
                   ["2", "Brownout at end of discharge", "Reset loop below about 3.45 V unless firmware shuts down at 3.5 V", "Firmware requirement"],
                   ["3", "No hardware over-temperature cut-out", "Cell has no thermal protection unless firmware implements it", "Firmware requirement"],
                   ["4", "Charger control is fail-safe to enabled", "A hung MCU cannot stop charging", "By design"],
                   ["5", "PCB outline only", "main.kicad_pcb holds the 100 x 64 mm outline; no placement or routing", "In progress"],
                   ["6", "FPC contact side unverified", "U9 is bottom-contact; wrong side would be unassemblable", "Verify with sample"],
                   ["7", "Jack tip/ring unverified", "Possible left / right swap", "Verify by continuity"],
                   ["8", "No SD card detect", "Insertion must be inferred in software", "Accepted"],
                   ["9", "No jack ESD protection", "Consumer-product robustness", "Consider"],
                   ["10", "Fixed 500 mA charge current", "Requires a cell of at least about 1000 mAh; system load can exceed a 500 mA USB-C source", "Accepted"],
                   ["11", "ERC reports 35 findings", "Unconnected NC pins, power-flag and pin-type annotations; no electrical errors", "Reviewed, accepted"],
                   ["12", "No LCSC part number for Y2", "Sourcing must be completed before an order can be placed", "User to select"]],
                  [20, 118, CW - 20 - 118 - 86, 86]))

    st.append(H2("14.1  Required before prototype"))
    st.extend(BULLETS([
        "Assign an LCSC part number for Y2 (32.768 kHz crystal).",
        "Lay out the PCB, observing the checklist in section 16.",
        "Implement the low-voltage shutdown at 3.5 V and the over-temperature charge cut in firmware.",
        "Confirm the FPC contact side and the jack tip / ring assignment.",
    ]))

    # ================================================== 15 verification
    ncomp, nnets = netlist_stats()
    st.append(H1("15  Verification"))
    st.append(P("The schematic is checked mechanically rather than by inspection: the netlist is regenerated "
                "from source and compared against the previous baseline, then the component set is compared "
                "against the BOM."))
    nbom = sum(int(q) for _, q, _, _ in read_bom())
    st.append(TBL([["Check", "Result"],
                   ["Netlist components", str(ncomp)],
                   ["BOM references", str(nbom)],
                   ["Nets", str(nnets)],
                   ["Pins appearing in more than one net", "0"],
                   ["ERC findings", "35 (unconnected NC pins, power-flag and pin-type annotations) - all reviewed as benign"],
                   ["Netlist / BOM consistency", "Exact match: the same %d references in both" % nbom]],
                  [170, CW - 170]))
    st.append(Spacer(1, 8))
    st.append(P("Method. After every schematic edit the netlist is exported and compared net by net with the "
                "previous revision; only intended differences are accepted. The BOM reference set is then "
                "compared with the netlist, because a silently dropped symbol is easy to miss and is invisible "
                "in a net-level diff."))
    st.append(P("Tooling", "h2"))
    st.append(P('kicad-cli sch export netlist --format kicadsexpr --output main.txt main.kicad_sch', "body"))
    st.append(P('kicad-cli sch erc --severity-error --output erc.rpt main.kicad_sch', "body"))
    st.append(CALLOUT("KiCad holds a lock file while the schematic is open. If the file is edited externally, "
                      "reload before saving or the in-memory copy will overwrite the change."))

    # ================================================== 16 layout
    st.append(H1("16  Layout guidelines"))
    st.extend(BULLETS([
        "100 nF at every RP2350 power pin: eight IOVDD, ADC_AVDD, VREG_VIN, USB_OTP_VDD and QSPI_IOVDD. A dedicated 100 nF (C65) sits at ADC_AVDD, pin 59.",
        "Keep the regulator loop tight: input capacitor at VREG_VIN, output capacitor at the inductor, and VREG_PGND returning directly to its pin.",
        "Observe the polarity dot on the 3.3 uH core inductor (L10). Orientation affects regulator stability.",
        "Cluster D1, Q4, C66 and C67 at the battery and charger area and keep the VSYS loop short.",
        "Place C64 (22 uF) directly at the DRV2605 supply pins.",
        "Place J2, R46 and C68 near the battery connector, with the NTC bonded to the cell rather than the board.",
        "Place C63 (1 uF) at the display connector VDD pin.",
        "Place Y2 and its 15 pF load capacitors directly at PCF8563 pins 1 and 2; keep those traces short and clear of the SDIO clock and QSPI bus.",
        "Keep D3, C71 and U19 together at the RTC supply pin, and keep the coin-cell holder away from the board edge.",
        "Mount the MEMS microphone so its acoustic port aligns with an enclosure opening; keep C72 and C73 within a few millimetres of the supply pin and do not route signals beneath the port.",
        "The ICS-43434 is a bottom-port microphone: the acoustic path is through the 0.4 mm hole in the land pattern, so the enclosure aperture must open onto the underside of the board or a gasket must bridge it.",
        "Keep the AUDIO_3V3 ferrites close to the DAC and amplifier pins.",
        "Single-sided build: confirm the FPC connector, USB-C receptacle and SD socket are all reachable from the back face.",
    ]))

    # ================================================== 17 approval
    st.append(PageBreak())
    st.append(H1("17  Approval"))
    st.append(P("This revision is released for review. Signature records acceptance of the design as "
                "described; it does not imply that prototype validation has been completed."))
    st.append(Spacer(1, 10))
    appr = TBL([["Role", "Name", "Signature", "Date"],
                ["Prepared by", "", "", ""],
                ["Reviewed by", "", "", ""],
                ["Approved by", "", "", ""]],
               [104, CW * 0.28, CW - 104 - CW * 0.28 - 92, 92])
    appr.setStyle(TableStyle([("TOPPADDING", (0, 1), (-1, -1), 12),
                              ("BOTTOMPADDING", (0, 1), (-1, -1), 12)]))
    st.append(KeepTogether([appr, Spacer(1, 8),
                            P("Uncontrolled when printed. The electronic copy in the project repository is the "
                              "controlled version.", "cap")]))

    # ================================================== appendix A
    st.append(PageBreak())
    st.append(H1("Appendix A  Bill of materials"))
    st.append(P("Generated from main.csv. Footprints are shown without their library prefix. J4 is the "
                "actuator connector and J2 the external thermistor connector; either may be fitted as a "
                "header or used as solder pads."))
    bom = read_bom()
    rows = [["Reference", "Qty", "Value", "Footprint"]]
    for ref, qty, val, fp in bom:
        rows.append([ref, qty, val, fp])
    st.append(TBL(rows, [CW * 0.30, 32, CW * 0.22, CW * 0.48 - 32], small=True))

    # ================================================== appendix B
    st.append(PageBreak())
    st.append(H1("Appendix B  Schematic"))
    st.append(P("The complete schematic follows at its native sheet size (A2, landscape). It is a single flat "
                "sheet; connectivity is carried by global labels."))
    st.append(Spacer(1, 10))
    st.append(TBL([["Sheet", "Source", "Size"],
                   ["1 of 1", "main.kicad_sch", "A2 landscape"]],
                  [80, CW - 190, 110]))
    return st


# ---------------------------------------------------------------- build
def _heading_level(fl):
    """1 for a top-level heading, 2 for a sub-heading, 0 otherwise."""
    if isinstance(fl, Paragraph):
        return 1 if fl.style.name == "H1" else (2 if fl.style.name == "H2" else 0)
    if isinstance(fl, KeepTogether):
        for item in getattr(fl, "_content", []):
            lv = _heading_level(item)
            if lv:
                return lv
    return 0


def guard_headings(story):
    """Insert a conditional frame break before each heading so a title is never
    stranded at the foot of a page, without forcing a break when it already fits."""
    out = []
    for fl in story:
        lv = _heading_level(fl)
        if lv == 1:
            out.append(CondPageBreak(140))
        elif lv == 2:
            out.append(CondPageBreak(110))
        out.append(fl)
    return out


def build(target):
    doc = Doc(target)
    doc.multiBuild(guard_headings(build_story()))
    return doc


def count_pages(path):
    import pymupdf
    d = pymupdf.open(path)
    n = len(d)
    d.close()
    return n


def main():
    global TOTAL

    # 1. vector schematic for the appendix
    if os.path.exists(KICAD):
        subprocess.run([KICAD, "sch", "export", "pdf", "-o", SCH_PDF, SCH_SRC],
                       check=True, capture_output=True)
        print("schematic exported")
    else:
        print("kicad-cli not found; skipping schematic appendix")

    # 2. first pass to learn the page count
    build(TMP_A)
    n_a = count_pages(TMP_A)
    n_sch = count_pages(SCH_PDF) if os.path.exists(SCH_PDF) else 0
    TOTAL = n_a + n_sch
    print("body pages:", n_a, "schematic pages:", n_sch, "total:", TOTAL)

    # 3. final build with the correct total
    build(TMP_B)
    n_b = count_pages(TMP_B)
    assert n_b == n_a, (n_a, n_b)

    # 4. merge
    import pymupdf
    out = pymupdf.open()
    body = pymupdf.open(TMP_B)
    toc = body.get_toc(simple=True)
    out.insert_pdf(body)
    body.close()
    if os.path.exists(SCH_PDF):
        sch = pymupdf.open(SCH_PDF)
        out.insert_pdf(sch)
        sch.close()
    if toc:
        out.set_toc(toc)
    out.set_metadata({"title": "Solace - Hardware Design Documentation",
                      "author": "Solace hardware project",
                      "subject": "Architecture, electrical specification and design rationale",
                      "keywords": "RP2350B, PCM5102A, TPA6132A2, TP4056, GC9B72, KiCad",
                      "creator": "KiCad 10.0 / reportlab"})
    out.save(OUT, garbage=4, deflate=True)
    out.close()

    for f in (TMP_A, TMP_B, SCH_PDF):
        if os.path.exists(f):
            os.remove(f)
    print("written", OUT, os.path.getsize(OUT), "bytes")


if __name__ == "__main__":
    main()
