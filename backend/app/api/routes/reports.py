"""
POST /api/reports/export  →  branded PDF (reportlab)
"""
from __future__ import annotations

import datetime
from io import BytesIO
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.security import get_current_user

router = APIRouter()

# ── Request schema ─────────────────────────────────────────────────────────────
class SqlResult(BaseModel):
    label:     Optional[str]        = None
    query_id:  Optional[str]        = None
    rows:      List[Dict[str, Any]] = []
    columns:   List[str]            = []
    row_count: Optional[int]        = None

class ReportRequest(BaseModel):
    title:       Optional[str]          = "DataMind Report"
    prompt:      Optional[str]          = None
    synthesis:   Optional[str]          = None
    sql_results: List[SqlResult]        = []

# ── Endpoint ───────────────────────────────────────────────────────────────────
@router.post("/export")
async def export_report(
    req: ReportRequest,
    current_user=Depends(get_current_user),
):
    buf = BytesIO()
    _build_pdf(buf, req, current_user)
    buf.seek(0)
    ts       = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"datamind_report_{ts}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

# ── PDF builder ────────────────────────────────────────────────────────────────
def _build_pdf(buf: BytesIO, req: ReportRequest, user) -> None:
    from reportlab.lib                      import colors
    from reportlab.lib.enums                import TA_CENTER, TA_RIGHT
    from reportlab.lib.pagesizes            import A4
    from reportlab.lib.styles              import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units               import mm
    from reportlab.platypus                import (
        HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    # ── Brand palette ──────────────────────────────────────────────────────────
    BLUE    = colors.HexColor("#1A4FA0")
    ORANGE  = colors.HexColor("#F47920")
    LIGHT   = colors.HexColor("#eff6ff")
    GRAY    = colors.HexColor("#6b7280")
    DARK    = colors.HexColor("#1e293b")
    BDR     = colors.HexColor("#e2e8f0")

    # ── Styles ─────────────────────────────────────────────────────────────────
    base = getSampleStyleSheet()

    def S(name, **kw):
        return ParagraphStyle(name, parent=base["Normal"], **kw)

    brand_name  = S("BN",  fontSize=22, leading=26, textColor=BLUE,   fontName="Helvetica-Bold")
    brand_sub   = S("BS",  fontSize=9.5, textColor=ORANGE, fontName="Helvetica-Bold")
    hdr_right   = S("HR",  fontSize=8,  textColor=GRAY,   fontName="Helvetica",
                    alignment=TA_RIGHT, leading=13)
    rpt_title   = S("RT",  fontSize=14, leading=18, textColor=DARK,   fontName="Helvetica-Bold",
                    spaceAfter=4)
    lbl         = S("LB",  fontSize=7.5, textColor=GRAY, fontName="Helvetica-Bold",
                    leading=12, spaceBefore=14, spaceAfter=3, wordWrap="CJK")
    body        = S("BD",  fontSize=9.5, textColor=DARK,  fontName="Helvetica", leading=14)
    sec_head    = S("SH",  fontSize=10.5, textColor=BLUE, fontName="Helvetica-Bold",
                    spaceBefore=12, spaceAfter=4)
    note        = S("NT",  fontSize=7.5, textColor=GRAY,  fontName="Helvetica", spaceBefore=2)
    footer      = S("FT",  fontSize=7.5, textColor=GRAY,  fontName="Helvetica",
                    alignment=TA_CENTER)
    th_cell     = S("TH",  fontSize=8,  textColor=colors.white, fontName="Helvetica-Bold")
    td_cell     = S("TD",  fontSize=8,  textColor=DARK,  fontName="Helvetica", leading=11)

    # ── Document ───────────────────────────────────────────────────────────────
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20*mm, rightMargin=20*mm,
        topMargin=22*mm,  bottomMargin=22*mm,
    )

    story = []
    now   = datetime.datetime.now()

    # ── Branded header ─────────────────────────────────────────────────────────
    user_email = getattr(user, "email", "Unknown")
    hdr = Table(
        [[
            Paragraph("DataMind", brand_name),
            Paragraph(
                f"Generated: {now.strftime('%d %b %Y, %H:%M')}<br/>"
                f"By: {user_email}",
                hdr_right,
            ),
        ]],
        colWidths=["60%", "40%"],
    )
    hdr.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(hdr)
    story.append(Paragraph("Decision Minds · AI-Powered Data Intelligence", brand_sub))
    story.append(HRFlowable(width="100%", thickness=2, color=BLUE, spaceAfter=10))

    # Report title
    title = req.title or "DataMind Report"
    story.append(Paragraph(title, rpt_title))
    story.append(HRFlowable(width="100%", thickness=0.5, color=ORANGE, spaceAfter=10))

    # ── Query ──────────────────────────────────────────────────────────────────
    if req.prompt:
        story.append(Paragraph("QUERY", lbl))
        safe_prompt = req.prompt.replace("<", "&lt;").replace(">", "&gt;")
        story.append(Paragraph(safe_prompt, body))

    # ── AI Synthesis ───────────────────────────────────────────────────────────
    if req.synthesis:
        story.append(Paragraph("AI SYNTHESIS", lbl))
        # Strip markdown symbols that reportlab can't parse
        clean = (req.synthesis
                 .replace("**", "")
                 .replace("### ", "")
                 .replace("## ", "")
                 .replace("# ", "")
                 .replace("<", "&lt;")
                 .replace(">", "&gt;"))
        story.append(Paragraph(clean.replace("\n", "<br/>"), body))

    # ── Data tables ────────────────────────────────────────────────────────────
    for sr in req.sql_results:
        if not sr.rows:
            continue

        label = sr.label or sr.query_id or "Results"
        story.append(Paragraph(label.upper(), sec_head))

        cols = sr.columns or (list(sr.rows[0].keys()) if sr.rows else [])
        if not cols:
            continue

        display_rows = sr.rows[:50]

        # Build table data
        header_row = [Paragraph(str(c), th_cell) for c in cols]
        data_rows  = [
            [
                Paragraph(
                    str(row.get(c) if row.get(c) is not None else "—"),
                    td_cell,
                )
                for c in cols
            ]
            for row in display_rows
        ]
        tdata    = [header_row] + data_rows
        avail_w  = 170 * mm
        col_w    = [avail_w / len(cols)] * len(cols)

        t = Table(tdata, colWidths=col_w, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND",     (0, 0), (-1, 0),  BLUE),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
            ("GRID",           (0, 0), (-1, -1), 0.25, BDR),
            ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",     (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING",  (0, 0), (-1, -1), 4),
            ("LEFTPADDING",    (0, 0), (-1, -1), 5),
            ("RIGHTPADDING",   (0, 0), (-1, -1), 5),
        ]))
        story.append(t)

        if len(sr.rows) > 50:
            story.append(Paragraph(
                f"Showing 50 of {len(sr.rows)} rows", note
            ))
        story.append(Spacer(1, 6 * mm))

    # ── Footer ─────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 8 * mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=BDR, spaceAfter=4))
    story.append(Paragraph(
        f"CONFIDENTIAL · Generated by DataMind · Decision Minds · {now.strftime('%d %b %Y')}",
        footer,
    ))

    doc.build(story)
