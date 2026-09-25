"""Generate a publication-grade PDF document:
NL-to-SQL Assistant: Full Technical Audit & Architecture Review
File: docs/Full_Technical_Audit.pdf
"""

import sys
from pathlib import Path
from datetime import datetime

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
    HRFlowable,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY


class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas for Page X of Y and running headers/footers."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        page_w, page_h = letter

        # Running header (pages 2+)
        if self._pageNumber > 1:
            self.setFont("Helvetica-Bold", 8)
            self.setFillColor(colors.HexColor("#0F766E"))  # Teal 700
            self.drawString(54, page_h - 36, "NL-TO-SQL ASSISTANT — FULL TECHNICAL AUDIT & ARCHITECTURE REVIEW")
            self.setFont("Helvetica", 8)
            self.setFillColor(colors.HexColor("#64748B"))
            self.drawRightString(page_w - 54, page_h - 36, "CONFIDENTIAL / ENGINEERING AUDIT")

            self.setStrokeColor(colors.HexColor("#CBD5E1"))
            self.setLineWidth(0.75)
            self.line(54, page_h - 42, page_w - 54, page_h - 42)

        # Running footer (all pages)
        self.setStrokeColor(colors.HexColor("#E2E8F0"))
        self.setLineWidth(0.75)
        self.line(54, 46, page_w - 54, 46)

        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#94A3B8"))
        self.drawString(54, 32, "Antigravity Engineering Review | Automated Quality & Architecture Gate")
        self.drawRightString(page_w - 54, 32, f"Page {self._pageNumber} of {page_count}")

        self.restoreState()


def build_pdf(output_path: Path):
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54,
    )

    base_styles = getSampleStyleSheet()
    pw = letter[0] - 108  # Printable width = 504 pt

    # Custom styles
    title_style = ParagraphStyle(
        "DocTitle",
        parent=base_styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=22,
        leading=26,
        textColor=colors.HexColor("#0F172A"),
        alignment=TA_LEFT,
        spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "DocSubtitle",
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#475569"),
        alignment=TA_LEFT,
        spaceAfter=14,
    )
    h1_style = ParagraphStyle(
        "Heading1_Custom",
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=17,
        textColor=colors.HexColor("#0F766E"),
        spaceBefore=14,
        spaceAfter=6,
        keepWithNext=True,
    )
    h2_style = ParagraphStyle(
        "Heading2_Custom",
        fontName="Helvetica-Bold",
        fontSize=10.5,
        leading=14,
        textColor=colors.HexColor("#1E293B"),
        spaceBefore=10,
        spaceAfter=4,
        keepWithNext=True,
    )
    body_style = ParagraphStyle(
        "Body_Custom",
        fontName="Helvetica",
        fontSize=8.5,
        leading=12.5,
        textColor=colors.HexColor("#334155"),
        spaceAfter=6,
    )
    body_bold = ParagraphStyle(
        "Body_Bold",
        parent=body_style,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#0F172A"),
    )
    table_cell = ParagraphStyle(
        "TableCell",
        fontName="Helvetica",
        fontSize=7.5,
        leading=10.5,
        textColor=colors.HexColor("#1E293B"),
    )
    table_cell_bold = ParagraphStyle(
        "TableCellBold",
        parent=table_cell,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#0F172A"),
    )
    table_cell_code = ParagraphStyle(
        "TableCellCode",
        parent=table_cell,
        fontName="Courier",
        fontSize=7.0,
        leading=9.5,
        textColor=colors.HexColor("#0F766E"),
    )

    story = []

    # Title & Metadata Banner
    story.append(Paragraph("Full Technical Audit & Architecture Review", title_style))
    story.append(Paragraph(
        "Line-by-Line Code Quality Audit, Dead Code Identification, and Honest System Architecture Status<br/>"
        f"<b>Target Codebase:</b> NL-to-SQL Assistant (FastAPI + React) &nbsp;|&nbsp; <b>Date:</b> {datetime.now().strftime('%B %d, %Y')} &nbsp;|&nbsp; <b>Status:</b> Safe Audit (No Unconfirmed Deletions)",
        subtitle_style,
    ))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#0F766E"), spaceBefore=0, spaceAfter=10))

    # Executive Summary Card
    summary_text = (
        "<b>Executive Summary & Safety Protocol:</b><br/>"
        "This audit provides a comprehensive, file-by-file inspection across all backend modules in <code>app/</code>, "
        "test scripts in <code>scripts/</code>, and dependencies in <code>requirements.txt</code>. In accordance with strict "
        "safety protocols, <b>zero code deletions or destructive modifications have been applied</b>. All findings are "
        "cataloged by file, line number, and severity level (Critical, Minor, Cosmetic, Cleanup-Candidate). Part 2 delivers "
        "an honest architectural status across 14 operational dimensions, clearly framing hackathon design decisions versus "
        "future production evolutionary paths."
    )
    summary_table = Table([[Paragraph(summary_text, body_style)]], colWidths=[pw])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#CBD5E1")),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 10))

    # PART 1: Code Quality Audit
    story.append(Paragraph("PART 1: Code Quality Audit (File-by-File Findings)", h1_style))
    story.append(Paragraph(
        "A rigorous line-by-line inspection of backend services, routers, models, and utility scripts identified 24 distinct findings "
        "categorized into dead code, duplicate logic, exception risks, pattern inconsistencies, hardcoded magic numbers, leftover debug code, "
        "and obsolete artifacts.",
        body_style,
    ))

    # Audit Findings Table
    audit_headers = ["ID", "Location & File", "Issue Description", "Category", "Severity"]
    audit_data = [
        [
            Paragraph(f"<b>{h}</b>", table_cell_bold) for h in audit_headers
        ],
        [
            Paragraph("F-01", table_cell_bold),
            Paragraph("<code>app/models/meta_db.py</code><br/>Lines 61-69", table_cell_code),
            Paragraph("<code>AuditLogModel</code> defined and exported in <code>__init__.py</code>, but never imported, written to, or queried anywhere in backend services or routers.", table_cell),
            Paragraph("Dead Code", table_cell),
            Paragraph("<font color='#D97706'><b>Cleanup-Candidate</b></font>", table_cell),
        ],
        [
            Paragraph("F-02", table_cell_bold),
            Paragraph("<code>app/models/__init__.py</code><br/>Lines 7, 18", table_cell_code),
            Paragraph("<code>AuditLogModel</code> exported in <code>__all__</code> despite being completely unused across the entire application runtime.", table_cell),
            Paragraph("Dead Code", table_cell),
            Paragraph("<font color='#64748B'>Cosmetic</font>", table_cell),
        ],
        [
            Paragraph("F-03", table_cell_bold),
            Paragraph("<code>app/services/session_store.py</code><br/>Line 19", table_cell_code),
            Paragraph("<code>from sqlalchemy import create_engine, inspect</code> imported inside <code>get_session()</code>, but neither symbol is ever invoked in that scope.", table_cell),
            Paragraph("Dead Code", table_cell),
            Paragraph("<font color='#64748B'>Cosmetic</font>", table_cell),
        ],
        [
            Paragraph("F-04", table_cell_bold),
            Paragraph("<code>app/services/session_store.py</code><br/>Lines 77-84", table_cell_code),
            Paragraph("<code>remove_session()</code> defined to pop session metadata and FAISS index, but is never called anywhere (no disconnect or session teardown endpoint exists).", table_cell),
            Paragraph("Dead Code", table_cell),
            Paragraph("<font color='#D97706'><b>Cleanup-Candidate</b></font>", table_cell),
        ],
        [
            Paragraph("F-05", table_cell_bold),
            Paragraph("<code>app/routers/connect_db.py</code><br/>Line 8", table_cell_code),
            Paragraph("<code>Literal</code> imported from standard library <code>typing</code> but never utilized in any type annotation.", table_cell),
            Paragraph("Dead Code", table_cell),
            Paragraph("<font color='#64748B'>Cosmetic</font>", table_cell),
        ],
        [
            Paragraph("F-06", table_cell_bold),
            Paragraph("<code>app/routers/conversations.py</code><br/>Line 11", table_cell_code),
            Paragraph("<code>from app.services.session_store import get_session</code> imported at file top level but never called anywhere in the router.", table_cell),
            Paragraph("Dead Code", table_cell),
            Paragraph("<font color='#64748B'>Cosmetic</font>", table_cell),
        ],
        [
            Paragraph("F-07", table_cell_bold),
            Paragraph("<code>app/services/rag_service.py</code><br/>Lines 229-231", table_cell_code),
            Paragraph("<code>is_session_indexed()</code> defined to check FAISS index existence, but is never imported or called in any router or test.", table_cell),
            Paragraph("Dead Code", table_cell),
            Paragraph("<font color='#D97706'><b>Cleanup-Candidate</b></font>", table_cell),
        ],
        [
            Paragraph("F-08", table_cell_bold),
            Paragraph("<code>app/main.py</code><br/>Lines 92-93", table_cell_code),
            Paragraph("Production origin <code>https://project-final-nl-2-sql.vercel.app</code> appears twice consecutively in the development CORS origin array.", table_cell),
            Paragraph("Duplicate Logic", table_cell),
            Paragraph("<font color='#64748B'>Cosmetic</font>", table_cell),
        ],
        [
            Paragraph("F-09", table_cell_bold),
            Paragraph("<code>app/services/sql_validator.py</code><br/>Lines 17-23, 70-76", table_cell_code),
            Paragraph("Guard 1 strips comments to count semicolons, but Guard 2 immediately follows and unconditionally rejects any query containing <code>--</code> or <code>/*</code>, making comment stripping in Guard 1 redundant.", table_cell),
            Paragraph("Duplicate Logic", table_cell),
            Paragraph("<font color='#64748B'>Minor</font>", table_cell),
        ],
        [
            Paragraph("F-10", table_cell_bold),
            Paragraph("<code>app/main.py</code><br/>Lines 145-146", table_cell_code),
            Paragraph("Leftover stdout prints (<code>print(f'[DEBUG SPA FALLBACK] ...')</code>) fire on every non-API asset request, polluting standard output in production.", table_cell),
            Paragraph("Leftover Debug", table_cell),
            Paragraph("<font color='#D97706'><b>Minor</b></font>", table_cell),
        ],
        [
            Paragraph("F-11", table_cell_bold),
            Paragraph("<code>app/routers/connect_db.py</code><br/>Lines 33-35", table_cell_code),
            Paragraph("<code>connection_string: Optional[str]</code> field in <code>ConnectDBRequest</code> is accepted by Pydantic but never read or processed by <code>connect_database()</code>.", table_cell),
            Paragraph("Placeholder Code", table_cell),
            Paragraph("<font color='#D97706'><b>Cleanup-Candidate</b></font>", table_cell),
        ],
        [
            Paragraph("F-12", table_cell_bold),
            Paragraph("<code>app/services/execution_engine.py</code><br/>Line 37", table_cell_code),
            Paragraph("Heuristic <code>'data' in err_msg</code> prematurely masks legitimate SQLite errors containing 'datatype mismatch' or tables named 'data_*' into generic error strings, hindering Gemini self-correction.", table_cell),
            Paragraph("Unhandled Edge Case", table_cell),
            Paragraph("<font color='#DC2626'><b>Minor</b></font>", table_cell),
        ],
        [
            Paragraph("F-13", table_cell_bold),
            Paragraph("<code>app/services/execution_engine.py</code><br/>Lines 27-32", table_cell_code),
            Paragraph("SQLite execution lacks a timeout or progress handler; a catastrophic query (e.g. Cartesian product) could block the worker thread indefinitely.", table_cell),
            Paragraph("Execution Safety", table_cell),
            Paragraph("<font color='#DC2626'><b>Minor</b></font>", table_cell),
        ],
        [
            Paragraph("F-14", table_cell_bold),
            Paragraph("<code>app/routers/query.py</code><br/>Line 33", table_cell_code),
            Paragraph("<code>_QUERY_TIMESTAMPS</code> dictionary keys (session IDs) are never evicted when empty; creates an unbounded memory leak over long server uptimes.", table_cell),
            Paragraph("Memory Leak", table_cell),
            Paragraph("<font color='#D97706'><b>Minor</b></font>", table_cell),
        ],
        [
            Paragraph("F-15", table_cell_bold),
            Paragraph("<code>app/services/rag_service.py</code><br/>Line 25", table_cell_code),
            Paragraph("<code>_SESSION_RAG_STORE</code> keeps FAISS indexes in memory without TTL or maximum capacity eviction; sessions accumulate indefinitely.", table_cell),
            Paragraph("Memory Leak", table_cell),
            Paragraph("<font color='#D97706'><b>Minor</b></font>", table_cell),
        ],
        [
            Paragraph("F-16", table_cell_bold),
            Paragraph("<code>app/routers/conversations.py</code><br/>Lines 160-174", table_cell_code),
            Paragraph("<code>DELETE /api/conversations/{id}</code> returns 200 <code>{'status': 'deleted'}</code> even if ID does not exist, whereas GET messages raises 404.", table_cell),
            Paragraph("Pattern Inconsistency", table_cell),
            Paragraph("<font color='#64748B'>Cosmetic</font>", table_cell),
        ],
        [
            Paragraph("F-17", table_cell_bold),
            Paragraph("<code>app/routers/query.py</code><br/>Lines 160-180", table_cell_code),
            Paragraph("Legacy <code>GET /api/history</code> returns flat non-conversational list of 20 items; superseded by conversational endpoints and never used by frontend.", table_cell),
            Paragraph("Superseded Endpoint", table_cell),
            Paragraph("<font color='#D97706'><b>Cleanup-Candidate</b></font>", table_cell),
        ],
        [
            Paragraph("F-18", table_cell_bold),
            Paragraph("<code>requirements.txt</code><br/>Line 9", table_cell_code),
            Paragraph("<code>requests</code> listed in dependencies but never imported anywhere in <code>app/</code> (FastAPI uses httpx in tests; Gemini uses google-generativeai REST transport).", table_cell),
            Paragraph("Unused Dependency", table_cell),
            Paragraph("<font color='#D97706'><b>Cleanup-Candidate</b></font>", table_cell),
        ],
        [
            Paragraph("F-19", table_cell_bold),
            Paragraph("<code>app/routers/connect_db.py</code><br/>Line 240", table_cell_code),
            Paragraph("<code>_MAX_UPLOAD_BYTES = 5 * 1024 * 1024</code> hardcoded in router file rather than centrally managed in <code>app/config.py</code>.", table_cell),
            Paragraph("Hardcoded Config", table_cell),
            Paragraph("<font color='#64748B'>Cosmetic</font>", table_cell),
        ],
        [
            Paragraph("F-20", table_cell_bold),
            Paragraph("<code>app/routers/query.py</code><br/>Lines 35-37, 359", table_cell_code),
            Paragraph("Rate limits (20/min session, 100/min global) and retry max (2) hardcoded as constants in router rather than exported from <code>app/config.py</code>.", table_cell),
            Paragraph("Hardcoded Config", table_cell),
            Paragraph("<font color='#64748B'>Cosmetic</font>", table_cell),
        ],
        [
            Paragraph("F-21", table_cell_bold),
            Paragraph("<code>app/services/sql_generator.py</code><br/>Lines 39, 413, 733", table_cell_code),
            Paragraph("<code>CACHE_TTL_SECONDS = 600.0</code>, max tokens (800), and temperature (0.0) hardcoded in service rather than config.", table_cell),
            Paragraph("Hardcoded Config", table_cell),
            Paragraph("<font color='#64748B'>Cosmetic</font>", table_cell),
        ],
        [
            Paragraph("F-22", table_cell_bold),
            Paragraph("<code>app/services/sql_generator.py</code><br/>Line 115", table_cell_code),
            Paragraph("<code>clear_query_cache(session_id)</code> accepts an unused <code>session_id</code> parameter while clearing the entire global cache.", table_cell),
            Paragraph("Dead Parameter", table_cell),
            Paragraph("<font color='#64748B'>Cosmetic</font>", table_cell),
        ],
        [
            Paragraph("F-23", table_cell_bold),
            Paragraph("<code>app/services/sql_validator.py</code><br/>Line 71", table_cell_code),
            Paragraph("Strict rejection of <code>--</code> in raw SQL input flags queries where double hyphens appear legitimately inside string literals (e.g. <code>WHERE code = '--'</code>).", table_cell),
            Paragraph("False Positive Risk", table_cell),
            Paragraph("<font color='#64748B'>Minor</font>", table_cell),
        ],
        [
            Paragraph("F-24", table_cell_bold),
            Paragraph("<code>scripts/</code><br/>(12 Test Scripts)", table_cell_code),
            Paragraph("12 manual test scripts (<code>test_phase*.py</code>, <code>test_clarification.py</code>, etc.) require live servers and duplicate the automated 155-test pytest suite.", table_cell),
            Paragraph("Superseded Scripts", table_cell),
            Paragraph("<font color='#D97706'><b>Cleanup-Candidate</b></font>", table_cell),
        ],
    ]

    findings_table = Table(audit_data, colWidths=[28, 110, 220, 76, 70])
    findings_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F766E")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(findings_table)
    story.append(Spacer(1, 14))

    # Point 7: Unnecessary / Unused Items Breakdown
    story.append(Paragraph("Point 7: Detailed Unnecessary / Unused Items Breakdown", h1_style))
    story.append(Paragraph(
        "Below is the explicit assessment of items flagged as candidates for removal, annotated with exact rationale and confidence levels:",
        body_style,
    ))

    p7_headers = ["Item Name & Reference", "Why It Appears Unnecessary", "Confidence Level"]
    p7_data = [
        [Paragraph(f"<b>{h}</b>", table_cell_bold) for h in p7_headers],
        [
            Paragraph("<b>AuditLogModel</b><br/><code>app/models/meta_db.py:61-69</code><br/><code>app/models/__init__.py:7,18</code>", table_cell),
            Paragraph("Partially scaffolded for enterprise compliance logging; never written to or queried anywhere in backend routes. Audit telemetry is currently satisfied via standard Python logging.", table_cell),
            Paragraph("<font color='#0F766E'><b>Certain</b></font>", table_cell_bold),
        ],
        [
            Paragraph("<b>GET /api/history</b><br/><code>app/routers/query.py:160-180</code>", table_cell),
            Paragraph("Legacy Phase 2 endpoint returning a flat limit(20) array. Completely superseded by conversational threads (<code>/api/conversations/*</code>). Uncalled by frontend components.", table_cell),
            Paragraph("<font color='#0F766E'><b>Certain</b></font>", table_cell_bold),
        ],
        [
            Paragraph("<b>'requests' Dependency</b><br/><code>requirements.txt:9</code>", table_cell),
            Paragraph("Unused by runtime backend (FastAPI uses Starlette/Pydantic; Gemini uses google-generativeai; tests use httpx). Only retained by manual verification scripts in <code>scripts/</code>.", table_cell),
            Paragraph("<font color='#0F766E'><b>Certain</b></font>", table_cell_bold),
        ],
        [
            Paragraph("<b>remove_session()</b><br/><code>app/services/session_store.py:77-84</code>", table_cell),
            Paragraph("Defined for session eviction but no router endpoint or lifecycle event ever invokes it. Sessions remain in memory until process termination.", table_cell),
            Paragraph("<font color='#0F766E'><b>Certain</b></font>", table_cell_bold),
        ],
        [
            Paragraph("<b>is_session_indexed()</b><br/><code>app/services/rag_service.py:229-231</code>", table_cell),
            Paragraph("Utility helper that is neither imported nor called across the entire codebase.", table_cell),
            Paragraph("<font color='#0F766E'><b>Certain</b></font>", table_cell_bold),
        ],
        [
            Paragraph("<b>connection_string Field</b><br/><code>app/routers/connect_db.py:33-35</code>", table_cell),
            Paragraph("Present in Pydantic request model but ignored by database connector; leftover from proposed remote database URI support.", table_cell),
            Paragraph("<font color='#0F766E'><b>Certain</b></font>", table_cell_bold),
        ],
        [
            Paragraph("<b>Unused Imports (Literal, get_session)</b><br/><code>connect_db.py:8</code>, <code>conversations.py:11</code>", table_cell),
            Paragraph("Symbols imported at module level but never referenced in subsequent logic.", table_cell),
            Paragraph("<font color='#0F766E'><b>Certain</b></font>", table_cell_bold),
        ],
        [
            Paragraph("<b>12 Manual Test Scripts in scripts/</b><br/><code>scripts/test_*.py</code>", table_cell),
            Paragraph("Superseded by the 155-test automated pytest suite in <code>tests/</code> which runs in CI without needing an external live server. Retained currently as non-breaking reference.", table_cell),
            Paragraph("<font color='#D97706'><b>Probably</b></font>", table_cell_bold),
        ],
        [
            Paragraph("<b>clear_query_cache(session_id) Arg</b><br/><code>app/services/sql_generator.py:115</code>", table_cell),
            Paragraph("The <code>session_id</code> parameter is ignored; clearing is always global.", table_cell),
            Paragraph("<font color='#D97706'><b>Probably</b></font>", table_cell_bold),
        ],
    ]

    p7_table = Table(p7_data, colWidths=[130, 290, 84])
    p7_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E293B")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(p7_table)
    story.append(Spacer(1, 16))

    # PART 2: Architecture Documentation
    story.append(Paragraph("PART 2: Architecture Documentation (14 Dimensions)", h1_style))
    story.append(Paragraph(
        "This section documents the current architectural implementation across 14 operational dimensions. Each category provides "
        "file references for active components, an honest appraisal of hackathon demo scope, and the concrete production evolution path.",
        body_style,
    ))

    arch_sections = [
        (
            "1. System Design & Architecture",
            "The system employs a decoupled 3-tier architecture: a React Vite frontend, a FastAPI Python backend (<code>app/main.py</code>), and Google Gemini AI via REST. Queries route through intent detection, a SentenceTransformers/FAISS schema retriever (<code>app/services/rag_service.py</code>), and a multi-model fallback LLM orchestrator (<code>app/services/sql_generator.py</code>) executing against isolated SQLite databases.<br/>"
            "<b>Hackathon Demo Scope vs. Production:</b> Distributed microservices and message queues were intentionally avoided to ensure zero network hops and instant, deterministic responsiveness during live jury evaluation; production evolution would introduce an API gateway and asynchronous Celery/RabbitMQ job queues for heavy analytical workloads."
        ),
        (
            "2. APIs & Backend Logic",
            "Ten REST endpoints are exposed under <code>/api</code> covering database connection, CSV/SQL upload, conversational sessions, query translation, and system health. Request validation and error handling are uniformly enforced via Pydantic models with strict typing.<br/>"
            "<b>Hackathon Demo Scope vs. Production:</b> GraphQL or gRPC interfaces were intentionally bypassed in favor of transparent REST/JSON endpoints to facilitate frictionless browser inspection and zero-config client integration."
        ),
        (
            "3. Databases & Storage",
            "Metadata is persisted in <code>data/meta.db</code> via SQLAlchemy models (<code>app/models/meta_db.py</code>), while uploaded and demo datasets exist as isolated SQLite files in <code>data/</code>. Session schemas and FAISS indexes are cached in memory in <code>app/services/session_store.py</code>.<br/>"
            "<b>Hackathon Demo Scope vs. Production:</b> File-based SQLite provides zero-dependency, self-contained portability essential for rock-solid local and single-instance demos; production migration requires managed PostgreSQL for multi-writer concurrency and Redis for distributed session and RAG index caching."
        ),
        (
            "4. Auth & Permissions",
            "No authentication tokens, passwords, or user accounts are implemented; clients are tracked via client-generated UUID session tokens stored in browser localStorage and validated in memory.<br/>"
            "<b>Hackathon Demo Scope vs. Production:</b> Omitting OAuth2 and user login flows was a deliberate decision to eliminate jury onboarding friction; production deployment would implement Auth0/Clerk with JWT bearer tokens and tenant-level database row security."
        ),
        (
            "5. Hosting & Cloud",
            "The primary application is configured to run on localhost (FastAPI on port 8000, React Vite on port 5173), with an integrated single-service static asset hosting mode implemented in <code>app/main.py</code>. Render and Vercel cloud manifests were tested and documented.<br/>"
            "<b>Hackathon Demo Scope vs. Production:</b> Localhost demonstration was chosen by design to guarantee immunity from cloud cold starts, rate quota throttling, or venue Wi-Fi drops; production hosting would leverage AWS ECS or GCP Cloud Run with managed load balancing."
        ),
        (
            "6. CI/CD",
            "Automated continuous integration is established via GitHub Actions (<code>.github/workflows/test.yml</code>), running full frontend builds and the 155-test backend pytest suite on every push. Continuous delivery is supported via Render's native Git push-to-deploy webhook.<br/>"
            "<b>Hackathon Demo Scope vs. Production:</b> Multi-environment staging and canary pipelines were skipped in favor of a lean, free GitHub Actions workflow tailored for immediate feedback; production would introduce automated migration rollbacks and synthetic smoke tests."
        ),
        (
            "7. Version Control",
            "The codebase is managed in a monorepo containing <code>frontend/</code>, <code>nl2sql-backend/</code>, <code>docs/</code>, and <code>.github/</code> on branch <code>main</code>. Commits follow conventional, modular milestones documenting discrete enhancements.<br/>"
            "<b>Hackathon Demo Scope vs. Production:</b> Direct commits on <code>main</code> accelerated rapid hackathon development; production workflows would enforce branch protection, semantic release tagging, and mandatory multi-approver pull request reviews."
        ),
        (
            "8. Security & Hardening",
            "Security includes environment isolation (<code>.env</code> never committed), environment-aware CORS (<code>app/main.py</code>), HTTP security headers (CSP, X-Frame-Options, X-Content-Type-Options), and AST SQL validation (<code>app/services/sql_validator.py</code>) blocking stacked queries, comment bypasses, and mutating operations (INSERT, UPDATE, DROP).<br/>"
            "<b>Hackathon Demo Scope vs. Production:</b> Request signing, mTLS, and data-at-rest encryption were omitted as disproportionate overhead for a public-sample demo; production enterprise environments would mandate KMS encryption and audit-trail logging."
        ),
        (
            "9. Rate Limiting",
            "Enforced via an in-memory two-tier sliding window algorithm in <code>app/routers/query.py</code>: Tier 1 restricts individual sessions to 20 queries/minute, while Tier 2 restricts global traffic to 100 queries/minute to safeguard Gemini free-tier quotas.<br/>"
            "<b>Hackathon Demo Scope vs. Production:</b> Sliding-window memory dictionaries reset upon process restart, which is acceptable for single-instance demos; production multi-instance scale requires Redis token buckets backed by Cloudflare edge rate limiting."
        ),
        (
            "10. Caching & CDN",
            "Features a deterministic SHA-256 in-memory query response cache in <code>app/services/sql_generator.py</code> (10-minute TTL, evict-on-read) to eliminate repeated Gemini LLM latency, paired with HTTP <code>Cache-Control</code> immutable headers for Vite static assets.<br/>"
            "<b>Hackathon Demo Scope vs. Production:</b> Edge CDNs are unnecessary for local or small-scale jury testing; production scale would introduce an external Redis cluster for query caching and Cloudflare CDN for global static asset distribution."
        ),
        (
            "11. Error Tracking & Logs",
            "Standard Python <code>logging</code> captures diagnostic events and Gemini retry attempts to console and Uvicorn stdout streams with sanitized error messages to prevent filesystem path exposure.<br/>"
            "<b>Hackathon Demo Scope vs. Production:</b> External APM and crash tracking services (Sentry, Datadog) were avoided to prevent external dependency bloat; production deployment would integrate OpenTelemetry distributed tracing and automated alert notifications."
        ),
        (
            "12. Monitoring & Alerts",
            "Basic service liveness is monitored via the <code>GET /health</code> endpoint without synthetic probes or background metric collectors.<br/>"
            "<b>Hackathon Demo Scope vs. Production:</b> PagerDuty alerts and metric collectors (Prometheus/Grafana) are out of scope for a self-contained hackathon evaluation; production systems would track p95 latency, model token consumption, and error budgets."
        ),
        (
            "13. Testing & Verification",
            "Quality is assured by a 155-test pytest suite in <code>tests/</code> achieving 77% code coverage across routers, AST validators, execution engine, language detectors, and the self-correction engine, supplemented by legacy diagnostic scripts in <code>scripts/</code>.<br/>"
            "<b>Hackathon Demo Scope vs. Production:</b> End-to-end browser automation (Playwright/Cypress) was omitted to keep CI runs fast (<10 seconds); production testing would incorporate headless browser test suites and database load testing."
        ),
        (
            "14. Scaling & Performance",
            "The current single-instance Uvicorn server comfortably serves 5-10 concurrent users with sub-second execution overhead on free-tier compute.<br/>"
            "<b>Hackathon Demo Scope vs. Production:</b> Vertical scaling and in-memory stores are adequate for hackathon jury traffic; scaling to enterprise multi-user concurrency (1,000+ users) requires stateless FastAPI worker nodes, Celery/RabbitMQ job queues, Redis for session and rate-limit persistence, and a read-replica PostgreSQL cluster."
        ),
    ]

    for title, text in arch_sections:
        story.append(Paragraph(title, h2_style))
        story.append(Paragraph(text, body_style))
        story.append(Spacer(1, 4))

    # Backend API Endpoints Table
    story.append(Spacer(1, 8))
    story.append(Paragraph("Complete Backend API Endpoint Reference", h2_style))
    api_headers = ["Method", "Endpoint Path", "Handler Function", "Operational Purpose"]
    api_rows = [
        [Paragraph(f"<b>{h}</b>", table_cell_bold) for h in api_headers],
        [
            Paragraph("<b>GET</b>", table_cell),
            Paragraph("<code>/health</code>", table_cell_code),
            Paragraph("<code>health_check()</code>", table_cell),
            Paragraph("Service liveness probe returning API operational status and uptime.", table_cell),
        ],
        [
            Paragraph("<b>POST</b>", table_cell),
            Paragraph("<code>/api/connect-db</code>", table_cell_code),
            Paragraph("<code>connect_database()</code>", table_cell),
            Paragraph("Connects to demo SQLite database (hospital or ecommerce) and caches schema.", table_cell),
        ],
        [
            Paragraph("<b>POST</b>", table_cell),
            Paragraph("<code>/api/upload-db</code>", table_cell_code),
            Paragraph("<code>upload_database()</code>", table_cell),
            Paragraph("Uploads .csv/.sql file, sanitizes table/column names, and loads into session SQLite.", table_cell),
        ],
        [
            Paragraph("<b>GET</b>", table_cell),
            Paragraph("<code>/api/session-status</code>", table_cell_code),
            Paragraph("<code>get_session_status()</code>", table_cell),
            Paragraph("Checks whether a session ID is active in memory or restorable from disk.", table_cell),
        ],
        [
            Paragraph("<b>POST</b>", table_cell),
            Paragraph("<code>/api/query</code>", table_cell_code),
            Paragraph("<code>handle_query()</code>", table_cell),
            Paragraph("Translates natural language to SQL, validates AST, executes query, records history.", table_cell),
        ],
        [
            Paragraph("<b>GET</b>", table_cell),
            Paragraph("<code>/api/conversations</code>", table_cell_code),
            Paragraph("<code>list_conversations()</code>", table_cell),
            Paragraph("Lists all active conversation sessions for a session ID ordered by recency.", table_cell),
        ],
        [
            Paragraph("<b>POST</b>", table_cell),
            Paragraph("<code>/api/conversations/new</code>", table_cell_code),
            Paragraph("<code>create_conversation()</code>", table_cell),
            Paragraph("Spawns a new conversational thread with an initial default title.", table_cell),
        ],
        [
            Paragraph("<b>GET</b>", table_cell),
            Paragraph("<code>/api/conversations/{id}/messages</code>", table_cell_code),
            Paragraph("<code>get_conversation_messages()</code>", table_cell),
            Paragraph("Retrieves chronologically ordered messages, SQL, explanations, and results.", table_cell),
        ],
        [
            Paragraph("<b>DELETE</b>", table_cell),
            Paragraph("<code>/api/conversations/{id}</code>", table_cell_code),
            Paragraph("<code>delete_conversation()</code>", table_cell),
            Paragraph("Permanently deletes conversation and cascades through query history records.", table_cell),
        ],
        [
            Paragraph("<b>GET</b>", table_cell),
            Paragraph("<code>/api/history</code>", table_cell_code),
            Paragraph("<code>get_history()</code>", table_cell),
            Paragraph("<i>(Legacy Phase 2)</i> Retrieves flat query list up to 20 items across sessions.", table_cell),
        ],
    ]

    api_table = Table(api_rows, colWidths=[45, 150, 115, 194])
    api_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F766E")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(api_table)

    # Build the document
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"[SUCCESS] Audit PDF generated successfully at: {output_path}")


if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parent.parent.parent
    docs_dir = base_dir / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    target_pdf = docs_dir / "Full_Technical_Audit.pdf"
    build_pdf(target_pdf)
