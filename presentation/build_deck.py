"""Builds the AgileAgent abstract-seminar deck.

The department fixes the slide order, the content of each slide, and an 8-10
minute limit. That makes the deck a data problem, not a design problem: every
slide is described in `SLIDES` below and rendered by one of four layout
functions, so all twelve share a single visual system instead of being
positioned twelve separate times.

Edit the text in `SLIDES`. Leave the layout functions alone unless something
overflows.

    python build_deck.py

Requires python-pptx. Speaker notes are written into each slide's notes pane
and are budgeted to land the whole deck at roughly nine minutes.
"""

from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

OUTPUT = Path(__file__).with_name("AgileAgent_Abstract_Seminar.pptx")

# --- theme ------------------------------------------------------------------
# One accent colour, used only for headings, arrows and emphasis. A second
# accent is the fastest way to make an academic deck look unserious.
BACKGROUND = RGBColor(0x0F, 0x17, 0x2A)
SURFACE = RGBColor(0x1E, 0x29, 0x3B)
SURFACE_ALT = RGBColor(0x17, 0x21, 0x33)
ACCENT = RGBColor(0x38, 0xBD, 0xF8)
ACCENT_DEEP = RGBColor(0x0E, 0x74, 0x90)
TEXT = RGBColor(0xE2, 0xE8, 0xF0)
MUTED = RGBColor(0x94, 0xA3, 0xB8)
DANGER = RGBColor(0xF8, 0x71, 0x71)
SUCCESS = RGBColor(0x4A, 0xDE, 0x80)
FONT = "Segoe UI"

SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)
MARGIN = Inches(0.62)
CONTENT_W = SLIDE_W - MARGIN * 2
BODY_TOP = Inches(1.42)


# --- primitives -------------------------------------------------------------


def _blank(prs: Presentation):
    """A slide with the theme background and nothing else."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    background = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, SLIDE_W, SLIDE_H)
    background.fill.solid()
    background.fill.fore_color.rgb = BACKGROUND
    background.line.fill.background()
    background.shadow.inherit = False
    return slide


def _textbox(slide, left, top, width, height):
    box = slide.shapes.add_textbox(left, top, width, height)
    frame = box.text_frame
    frame.word_wrap = True
    frame.margin_left = frame.margin_right = Emu(0)
    frame.margin_top = frame.margin_bottom = Emu(0)
    return frame


def _write(frame, text, *, size, bold=False, color=TEXT, align=PP_ALIGN.LEFT, space_after=0):
    """Append a paragraph, reusing the empty first one."""
    paragraph = frame.paragraphs[0] if not frame.paragraphs[0].runs else frame.add_paragraph()
    paragraph.alignment = align
    paragraph.space_after = Pt(space_after)
    run = paragraph.add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = FONT
    return paragraph


def _box(slide, left, top, width, height, *, fill=SURFACE, line=None, radius=True):
    shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE
    shape = slide.shapes.add_shape(shape_type, left, top, width, height)
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    if line is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = line
        shape.line.width = Pt(1.25)
    shape.shadow.inherit = False
    shape.text_frame.word_wrap = True
    shape.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE
    shape.text_frame.margin_left = shape.text_frame.margin_right = Inches(0.09)
    shape.text_frame.margin_top = shape.text_frame.margin_bottom = Inches(0.04)
    return shape


def _label(shape, lines, *, size=12, bold_first=True):
    """Fill a shape with one or more centred lines."""
    frame = shape.text_frame
    for index, line in enumerate(lines):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        paragraph.alignment = PP_ALIGN.CENTER
        paragraph.space_after = Pt(0)
        run = paragraph.add_run()
        run.text = line
        run.font.size = Pt(size if index == 0 else size - 2)
        run.font.bold = bold_first and index == 0
        run.font.color.rgb = TEXT if index == 0 else MUTED
        run.font.name = FONT


def _arrow(slide, left, top, width, height, *, color=ACCENT):
    shape = slide.shapes.add_shape(MSO_SHAPE.DOWN_ARROW, left, top, width, height)
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()
    shape.shadow.inherit = False
    return shape


def _chrome(slide, number, title, subtitle=""):
    """Title band and footer — identical on every content slide."""
    _box(slide, MARGIN, Inches(0.46), Inches(0.09), Inches(0.52), fill=ACCENT, radius=False)

    frame = _textbox(slide, MARGIN + Inches(0.24), Inches(0.42), CONTENT_W - Inches(1.2), Inches(0.6))
    _write(frame, title, size=29, bold=True)
    if subtitle:
        _write(frame, subtitle, size=13, color=MUTED)

    footer = _textbox(slide, MARGIN, Inches(6.94), CONTENT_W, Inches(0.3))
    _write(footer, "AgileAgent  ·  Abstract Seminar  ·  Dept. of CSE, MVSREC (A)", size=10, color=MUTED)

    page = _textbox(slide, SLIDE_W - MARGIN - Inches(1.0), Inches(6.94), Inches(1.0), Inches(0.3))
    _write(page, f"{number} / 12", size=10, color=MUTED, align=PP_ALIGN.RIGHT)


def _notes(slide, text):
    slide.notes_slide.notes_text_frame.text = text


# --- layouts ----------------------------------------------------------------


def title_slide(prs, spec):
    slide = _blank(prs)

    _box(slide, 0, 0, SLIDE_W, Inches(0.14), fill=ACCENT, radius=False)

    frame = _textbox(slide, MARGIN, Inches(0.95), CONTENT_W, Inches(1.6))
    _write(frame, "AgileAgent", size=58, bold=True, color=ACCENT, align=PP_ALIGN.CENTER)
    _write(
        frame,
        "Multi-Agent AI Software Engineering Platform",
        size=23,
        align=PP_ALIGN.CENTER,
        space_after=2,
    )
    _write(
        frame,
        "for Autonomous Software Development",
        size=23,
        align=PP_ALIGN.CENTER,
    )

    _box(slide, Inches(5.17), Inches(2.92), Inches(3.0), Inches(0.03), fill=ACCENT_DEEP, radius=False)

    members = _box(slide, Inches(3.3), Inches(3.22), Inches(6.73), Inches(1.62), fill=SURFACE)
    frame = members.text_frame
    frame.vertical_anchor = MSO_ANCHOR.MIDDLE
    _write(frame, "TEAM MEMBERS", size=11, bold=True, color=ACCENT, align=PP_ALIGN.CENTER, space_after=6)
    for name, roll in spec["members"]:
        paragraph = frame.add_paragraph()
        paragraph.alignment = PP_ALIGN.CENTER
        paragraph.space_after = Pt(2)
        run = paragraph.add_run()
        run.text = f"{name}    —    {roll}"
        run.font.size = Pt(15)
        run.font.color.rgb = TEXT
        run.font.name = FONT

    frame = _textbox(slide, MARGIN, Inches(5.06), CONTENT_W, Inches(1.6))
    _write(frame, "Project Guide:  V. Swarna", size=17, bold=True, align=PP_ALIGN.CENTER, space_after=12)
    _write(
        frame,
        "Department of Computer Science & Engineering",
        size=15,
        color=MUTED,
        align=PP_ALIGN.CENTER,
        space_after=2,
    )
    _write(
        frame,
        "M V S R Engineering College (A)",
        size=15,
        color=MUTED,
        align=PP_ALIGN.CENTER,
        space_after=2,
    )
    _write(frame, "Academic Year 2026 – 27", size=15, color=MUTED, align=PP_ALIGN.CENTER)

    _box(slide, 0, SLIDE_H - Inches(0.14), SLIDE_W, Inches(0.14), fill=ACCENT, radius=False)
    _notes(slide, spec["notes"])


def bullet_slide(prs, spec):
    """Bulleted content, optionally with a highlighted closing strip."""
    slide = _blank(prs)
    _chrome(slide, spec["number"], spec["title"], spec.get("subtitle", ""))

    strip = spec.get("strip")
    height = Inches(4.55) if strip else Inches(5.3)
    frame = _textbox(slide, MARGIN, BODY_TOP, CONTENT_W, height)

    for item in spec["bullets"]:
        lead, rest = (item if isinstance(item, tuple) else (None, item))
        paragraph = frame.paragraphs[0] if not frame.paragraphs[0].runs else frame.add_paragraph()
        paragraph.space_after = Pt(15)
        marker = paragraph.add_run()
        marker.text = "▸  "
        marker.font.size = Pt(19)
        marker.font.color.rgb = ACCENT
        marker.font.name = FONT
        if lead:
            run = paragraph.add_run()
            run.text = f"{lead}  "
            run.font.size = Pt(19)
            run.font.bold = True
            run.font.color.rgb = TEXT
            run.font.name = FONT
        run = paragraph.add_run()
        run.text = rest
        run.font.size = Pt(19)
        run.font.color.rgb = TEXT if not lead else MUTED
        run.font.name = FONT

    if strip:
        shape = _box(slide, MARGIN, Inches(6.02), CONTENT_W, Inches(0.72), fill=ACCENT_DEEP)
        _label(shape, [strip], size=16)

    _notes(slide, spec["notes"])


def table_slide(prs, spec):
    """A comparison or survey table, optionally with a block beneath it."""
    slide = _blank(prs)
    _chrome(slide, spec["number"], spec["title"], spec.get("subtitle", ""))

    rows = spec["rows"]
    widths = spec["widths"]
    block = spec.get("block")
    table_h = Inches(spec.get("table_height", 4.0))

    shape = slide.shapes.add_table(len(rows), len(widths), MARGIN, BODY_TOP, CONTENT_W, table_h)
    table = shape.table
    table.first_row = True

    for index, width in enumerate(widths):
        table.columns[index].width = Inches(width)

    body_size = spec.get("font_size", 12)
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            cell = table.cell(r, c)
            cell.fill.solid()
            if r == 0:
                cell.fill.fore_color.rgb = ACCENT_DEEP
            else:
                cell.fill.fore_color.rgb = SURFACE if r % 2 else SURFACE_ALT
            cell.margin_left = cell.margin_right = Inches(0.09)
            cell.margin_top = cell.margin_bottom = Inches(0.05)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE

            frame = cell.text_frame
            frame.word_wrap = True
            paragraph = frame.paragraphs[0]
            run = paragraph.add_run()
            run.text = value
            run.font.size = Pt(body_size + 1 if r == 0 else body_size)
            run.font.bold = r == 0 or c == 0
            run.font.name = FONT
            if r == 0:
                run.font.color.rgb = TEXT
            elif c == len(widths) - 1 and spec.get("last_column_danger"):
                run.font.color.rgb = DANGER
            else:
                run.font.color.rgb = TEXT if c == 0 else MUTED

    if block:
        top = Inches(spec.get("block_top", 5.6))
        shape = _box(slide, MARGIN, top, CONTENT_W, Inches(spec.get("block_height", 1.2)), fill=SURFACE, line=ACCENT)
        frame = shape.text_frame
        frame.vertical_anchor = MSO_ANCHOR.MIDDLE
        _write(frame, block["heading"], size=15, bold=True, color=ACCENT, space_after=4)
        _write(frame, block["body"], size=13, color=TEXT)

    _notes(slide, spec["notes"])


def mapping_slide(prs, spec):
    """Two columns joined by arrows: limitation on the left, mechanism on the right."""
    slide = _blank(prs)
    _chrome(slide, spec["number"], spec["title"], spec.get("subtitle", ""))

    banner = _box(slide, MARGIN, BODY_TOP, CONTENT_W, Inches(0.62), fill=ACCENT_DEEP)
    _label(banner, [spec["definition"]], size=14)

    left_w = Inches(4.55)
    right_w = Inches(6.15)
    arrow_w = Inches(0.55)
    left_x = MARGIN
    arrow_x = left_x + left_w + Inches(0.32)
    right_x = arrow_x + arrow_w + Inches(0.32)

    header_y = Inches(2.28)
    for x, width, text, color in (
        (left_x, left_w, "LIMITATION OF EXISTING WORK", DANGER),
        (right_x, right_w, "AGILEAGENT MECHANISM", SUCCESS),
    ):
        frame = _textbox(slide, x, header_y, width, Inches(0.28))
        _write(frame, text, size=11, bold=True, color=color)

    row_y = Inches(2.66)
    row_h = Inches(0.66)
    gap = Inches(0.11)

    for limitation, mechanism in spec["pairs"]:
        shape = _box(slide, left_x, row_y, left_w, row_h, fill=SURFACE_ALT)
        frame = shape.text_frame
        paragraph = frame.paragraphs[0]
        paragraph.alignment = PP_ALIGN.LEFT
        run = paragraph.add_run()
        run.text = limitation
        run.font.size = Pt(13)
        run.font.color.rgb = MUTED
        run.font.name = FONT

        arrow = slide.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, arrow_x, row_y + Inches(0.24), arrow_w, Inches(0.24))
        arrow.fill.solid()
        arrow.fill.fore_color.rgb = ACCENT
        arrow.line.fill.background()
        arrow.shadow.inherit = False

        shape = _box(slide, right_x, row_y, right_w, row_h, fill=SURFACE)
        frame = shape.text_frame
        paragraph = frame.paragraphs[0]
        paragraph.alignment = PP_ALIGN.LEFT
        run = paragraph.add_run()
        run.text = mechanism
        run.font.size = Pt(13)
        run.font.bold = True
        run.font.color.rgb = TEXT
        run.font.name = FONT

        row_y += row_h + gap

    _notes(slide, spec["notes"])


def flow_slide(prs, spec):
    """Numbered methodology steps in two columns."""
    slide = _blank(prs)
    _chrome(slide, spec["number"], spec["title"], spec.get("subtitle", ""))

    steps = spec["steps"]
    half = (len(steps) + 1) // 2
    columns = (steps[:half], steps[half:])
    col_w = Inches(6.05)
    step_h = Inches(0.82)
    gap = Inches(0.11)

    for column_index, column in enumerate(columns):
        x = MARGIN + column_index * (col_w + Inches(0.4))
        y = BODY_TOP
        for number, heading, detail, deterministic in column:
            shape = _box(
                slide,
                x,
                y,
                col_w,
                step_h,
                fill=SURFACE_ALT if not deterministic else SURFACE,
                line=SUCCESS if deterministic else None,
            )
            frame = shape.text_frame
            frame.vertical_anchor = MSO_ANCHOR.MIDDLE

            paragraph = frame.paragraphs[0]
            marker = paragraph.add_run()
            marker.text = f"{number}   "
            marker.font.size = Pt(15)
            marker.font.bold = True
            marker.font.color.rgb = SUCCESS if deterministic else ACCENT
            marker.font.name = FONT
            run = paragraph.add_run()
            run.text = heading
            run.font.size = Pt(14)
            run.font.bold = True
            run.font.color.rgb = TEXT
            run.font.name = FONT

            paragraph = frame.add_paragraph()
            run = paragraph.add_run()
            run.text = f"      {detail}"
            run.font.size = Pt(11)
            run.font.color.rgb = MUTED
            run.font.name = FONT

            y += step_h + gap

    legend = _box(slide, MARGIN, Inches(6.10), CONTENT_W, Inches(0.56), fill=SURFACE, line=SUCCESS)
    _label(legend, [spec["legend"]], size=13, bold_first=False)

    _notes(slide, spec["notes"])


def architecture_slide(prs, spec):
    """The block diagram. Native shapes only — no bullets on this slide."""
    slide = _blank(prs)
    _chrome(slide, spec["number"], spec["title"], spec.get("subtitle", ""))

    centre = SLIDE_W / 2

    # Band 1 — client
    client = _box(slide, centre - Inches(2.5), Inches(1.34), Inches(5.0), Inches(0.5), fill=SURFACE, line=ACCENT)
    _label(client, ["React 18 + TypeScript Web Client"], size=13)

    _arrow(slide, centre - Inches(0.12), Inches(1.90), Inches(0.24), Inches(0.22))
    frame = _textbox(slide, centre + Inches(0.22), Inches(1.92), Inches(3.4), Inches(0.22))
    _write(frame, "REST  +  Server-Sent Events", size=10, color=ACCENT)

    # Band 2 — API layer
    api_boxes = ["API Routes", "Services", "Repositories", "PostgreSQL 16"]
    width = Inches(2.86)
    gap = Inches(0.24)
    total = width * len(api_boxes) + gap * (len(api_boxes) - 1)
    x = centre - total / 2
    for index, name in enumerate(api_boxes):
        shape = _box(slide, x, Inches(2.20), width, Inches(0.52), fill=SURFACE_ALT)
        _label(shape, [name], size=12)
        if index < len(api_boxes) - 1:
            arrow = slide.shapes.add_shape(
                MSO_SHAPE.RIGHT_ARROW, x + width + Inches(0.03), Inches(2.36), Inches(0.18), Inches(0.20)
            )
            arrow.fill.solid()
            arrow.fill.fore_color.rgb = ACCENT
            arrow.line.fill.background()
            arrow.shadow.inherit = False
        x += width + gap

    frame = _textbox(slide, MARGIN, Inches(2.78), CONTENT_W, Inches(0.22))
    _write(frame, "strict one-way dependency — a service never imports the web framework", size=10, color=MUTED, align=PP_ALIGN.CENTER)

    # Band 3 — core subsystems over shared memory
    cores = [
        ("Agent Registry", "11 specialised agents"),
        ("Workflow Engine", "planner · executor · events"),
        ("Adapter Registry", "9 technology plugins"),
        ("Packaging", "workspace · archive · report"),
    ]
    x = centre - total / 2
    for name, detail in cores:
        shape = _box(slide, x, Inches(3.10), width, Inches(0.72), fill=SURFACE, line=ACCENT_DEEP)
        _label(shape, [name, detail], size=12)
        x += width + gap

    memory = _box(slide, centre - total / 2, Inches(3.94), total, Inches(0.46), fill=ACCENT_DEEP)
    _label(memory, ["Shared Project Memory  —  one typed state read and written by every agent"], size=12)

    _arrow(slide, centre - Inches(0.12), Inches(4.50), Inches(0.24), Inches(0.20))

    # Band 4 — provider manager and providers
    manager = _box(slide, centre - total / 2, Inches(4.78), total, Inches(0.64), fill=SURFACE, line=ACCENT)
    _label(
        manager,
        ["Provider Manager", "Cache  →  Route  →  Retry  →  Fail over  →  Record"],
        size=13,
    )

    providers = ["Gemini", "Groq", "NVIDIA NIM", "Ollama", "OpenAI", "Anthropic"]
    p_width = Inches(1.86)
    p_gap = Inches(0.18)
    p_total = p_width * len(providers) + p_gap * (len(providers) - 1)
    x = centre - p_total / 2
    for name in providers:
        shape = _box(slide, x, Inches(5.60), p_width, Inches(0.46), fill=SURFACE_ALT)
        _label(shape, [name], size=11)
        x += p_width + p_gap

    caption = _box(slide, MARGIN, Inches(6.24), CONTENT_W, Inches(0.5), fill=SURFACE_ALT)
    _label(
        caption,
        ["No agent addresses a provider directly — every model call passes through one manager, which is what makes failover automatic."],
        size=12,
        bold_first=False,
    )

    _notes(slide, spec["notes"])


def tech_slide(prs, spec):
    """Technology columns plus the dataset/evaluation block."""
    slide = _blank(prs)
    _chrome(slide, spec["number"], spec["title"], spec.get("subtitle", ""))

    groups = spec["groups"]
    col_w = Inches(3.87)
    gap = Inches(0.26)
    x = MARGIN
    for index, (heading, items) in enumerate(groups):
        if index == 3:
            x = MARGIN
        top = BODY_TOP if index < 3 else BODY_TOP + Inches(1.86)
        shape = _box(slide, x, top, col_w, Inches(1.70), fill=SURFACE)
        frame = shape.text_frame
        frame.vertical_anchor = MSO_ANCHOR.TOP
        frame.margin_top = Inches(0.11)
        _write(frame, heading.upper(), size=11, bold=True, color=ACCENT, space_after=5)
        for item in items:
            _write(frame, f"·  {item}", size=12, color=TEXT, space_after=1)
        x += col_w + gap

    block = _box(slide, MARGIN, Inches(5.28), CONTENT_W, Inches(1.46), fill=SURFACE_ALT, line=ACCENT)
    frame = block.text_frame
    frame.vertical_anchor = MSO_ANCHOR.MIDDLE
    _write(frame, "DATASET & EVALUATION", size=12, bold=True, color=ACCENT, space_after=4)
    _write(
        frame,
        "AgileAgent trains no model — it orchestrates pre-trained language models, so there is no dataset, "
        "no preprocessing stage and no train/test split.",
        size=13,
        space_after=4,
    )
    _write(
        frame,
        "Evaluation is system-level:  artifact completeness  ·  structural validity of generated code  ·  "
        "build success rate  ·  per-agent success rate  ·  failover recovery rate  ·  generation latency  ·  token cost",
        size=12,
        color=MUTED,
    )

    _notes(slide, spec["notes"])


def outcomes_slide(prs, spec):
    """Deliverables checklist beside application tiles."""
    slide = _blank(prs)
    _chrome(slide, spec["number"], spec["title"], spec.get("subtitle", ""))

    left_w = Inches(6.9)
    right_w = CONTENT_W - left_w - Inches(0.35)
    right_x = MARGIN + left_w + Inches(0.35)

    frame = _textbox(slide, MARGIN, BODY_TOP, left_w, Inches(0.3))
    _write(frame, "EXPECTED OUTCOMES", size=12, bold=True, color=ACCENT)

    y = BODY_TOP + Inches(0.42)
    for item in spec["outcomes"]:
        shape = _box(slide, MARGIN, y, left_w, Inches(0.66), fill=SURFACE_ALT)
        inner = shape.text_frame
        paragraph = inner.paragraphs[0]
        tick = paragraph.add_run()
        tick.text = "✓   "
        tick.font.size = Pt(13)
        tick.font.bold = True
        tick.font.color.rgb = SUCCESS
        tick.font.name = FONT
        run = paragraph.add_run()
        run.text = item
        run.font.size = Pt(12)
        run.font.color.rgb = TEXT
        run.font.name = FONT
        y += Inches(0.76)

    frame = _textbox(slide, right_x, BODY_TOP, right_w, Inches(0.3))
    _write(frame, "APPLICATIONS", size=12, bold=True, color=ACCENT)

    tile_w = (right_w - Inches(0.18)) / 2
    y = BODY_TOP + Inches(0.42)
    for index in range(0, len(spec["applications"]), 2):
        for column, application in enumerate(spec["applications"][index : index + 2]):
            shape = _box(
                slide,
                right_x + column * (tile_w + Inches(0.18)),
                y,
                tile_w,
                Inches(0.66),
                fill=SURFACE,
            )
            _label(shape, [application], size=11, bold_first=False)
        y += Inches(0.76)

    strip = _box(slide, MARGIN, Inches(6.02), CONTENT_W, Inches(0.72), fill=ACCENT_DEEP)
    _label(strip, [spec["significance"]], size=14)

    _notes(slide, spec["notes"])


def workplan_slide(prs, spec):
    """Phase timeline, responsibilities and references."""
    slide = _blank(prs)
    _chrome(slide, spec["number"], spec["title"], spec.get("subtitle", ""))

    phases = spec["phases"]
    width = (CONTENT_W - Inches(0.14) * (len(phases) - 1)) / len(phases)
    x = MARGIN
    for number, period, work in phases:
        shape = _box(slide, x, BODY_TOP, width, Inches(1.28), fill=SURFACE, line=ACCENT_DEEP)
        frame = shape.text_frame
        frame.vertical_anchor = MSO_ANCHOR.TOP
        frame.margin_top = Inches(0.08)
        _write(frame, number, size=13, bold=True, color=ACCENT, align=PP_ALIGN.CENTER, space_after=2)
        _write(frame, period, size=10, color=TEXT, align=PP_ALIGN.CENTER, space_after=4)
        _write(frame, work, size=9, color=MUTED, align=PP_ALIGN.CENTER)
        x += width + Inches(0.14)

    frame = _textbox(slide, MARGIN, Inches(2.92), CONTENT_W, Inches(0.26))
    _write(frame, "TEAM RESPONSIBILITIES", size=11, bold=True, color=ACCENT)

    resp_w = (CONTENT_W - Inches(0.24) * 2) / 3
    x = MARGIN
    for name, roll, work in spec["responsibilities"]:
        shape = _box(slide, x, Inches(3.24), resp_w, Inches(0.94), fill=SURFACE_ALT)
        frame = shape.text_frame
        frame.vertical_anchor = MSO_ANCHOR.MIDDLE
        _write(frame, name, size=12, bold=True, align=PP_ALIGN.CENTER, space_after=1)
        _write(frame, roll, size=9, color=MUTED, align=PP_ALIGN.CENTER, space_after=3)
        _write(frame, work, size=10, color=ACCENT, align=PP_ALIGN.CENTER)
        x += resp_w + Inches(0.24)

    frame = _textbox(slide, MARGIN, Inches(4.42), CONTENT_W, Inches(0.26))
    _write(frame, "REFERENCES", size=11, bold=True, color=ACCENT)

    # 9 pt, because six IEEE references at 10 pt wrap into the footer.
    frame = _textbox(slide, MARGIN, Inches(4.70), CONTENT_W, Inches(2.2))
    for reference in spec["references"]:
        _write(frame, reference, size=9, color=MUTED, space_after=3)

    _notes(slide, spec["notes"])


# --- content ----------------------------------------------------------------

SLIDES = [
    {
        "layout": title_slide,
        "number": 1,
        "members": [
            ("Mohammed Abdul Akif Ahmed", "245123733173"),
            ("Mohammed Aslam Uddin", "245123733182"),
            ("Puneeth Reddy", "245123733186"),
        ],
        "notes": (
            "[AKIF — 20 seconds]\n\n"
            "Good morning. We are presenting AgileAgent, a multi-agent AI software engineering "
            "platform for autonomous software development, under the guidance of V. Swarna. "
            "I am Akif; with me are Aslam Uddin and Puneeth Reddy."
        ),
    },
    {
        "layout": bullet_slide,
        "number": 2,
        "title": "Introduction",
        "subtitle": "Domain — AI-assisted software engineering and autonomous multi-agent systems",
        "bullets": [
            ("Software development is a chain of decisions —", "requirements, design, code, testing, documentation."),
            ("Language models now write correct code,", "but assist at the scale of a function or a single file."),
            ("The developer remains the integrator,", "manually carrying context between every prompt."),
            ("Multi-agent systems are the emerging answer —", "several specialised agents, each with a defined role."),
            ("AgileAgent applies that idea", "to the complete software development lifecycle."),
        ],
        "strip": "AI today accelerates typing. It does not yet perform engineering.",
        "notes": (
            "[AKIF — 35 seconds]\n\n"
            "Our domain is AI-assisted software engineering. Building software is not one task — it is a "
            "chain of dependent decisions from requirements through to documentation. Language models are "
            "genuinely good at writing code, but they work at the level of a function. Everything around "
            "that code — deciding what to build, how to structure it, whether it is correct — still falls "
            "to the developer. Multi-agent systems, where several specialised agents each own a role, are "
            "the emerging response. AgileAgent applies that idea across the entire lifecycle."
        ),
    },
    {
        "layout": bullet_slide,
        "number": 3,
        "title": "Problem Statement",
        "subtitle": "Four defects that prevent current AI tools from delivering complete software",
        "bullets": [
            ("No shared context.", "Every prompt starts blind; the developer carries decisions between them."),
            ("No traceability.", "Nothing links a generated file back to the requirement that justified it."),
            ("Single-model dependency.", "One quota, rate limit or outage aborts a long generation entirely."),
            ("Unverified output.", "Code arrives without review, structural validation or tests."),
        ],
        "strip": "Result: the integration burden is not removed — it is simply moved onto the developer.",
        "notes": (
            "[AKIF — 40 seconds]\n\n"
            "The problem breaks into four specific defects. First, no shared context — each prompt starts "
            "blind, so the developer manually carries decisions forward. Second, no traceability; nothing "
            "connects a generated file to the requirement that justified writing it. Third, single-model "
            "dependency — one rate limit or outage during a long generation, and the whole thing is lost. "
            "Fourth, the output is unverified: no review, no structural validation, no tests. The net "
            "effect is that AI speeds up typing but the integration work simply moves onto the developer."
        ),
    },
    {
        "layout": table_slide,
        "number": 4,
        "title": "Existing System",
        "subtitle": "Current approaches and where each one stops",
        "widths": [2.65, 4.45, 4.99],
        "font_size": 12,
        "table_height": 3.9,
        "last_column_danger": True,
        "rows": [
            ["Approach", "How it works", "Limitation"],
            [
                "GitHub Copilot,\nCursor",
                "Inline completion inside the editor",
                "Snippet scope; produces no requirements, design or documentation",
            ],
            [
                "ChatGPT /\nClaude chat",
                "Whole application requested in one conversation",
                "Long completions truncate; files import modules that were never written",
            ],
            [
                "MetaGPT, ChatDev,\nAutoGen",
                "Multi-agent research frameworks with role play",
                "Fixed pipeline for every input; single LLM backend; build files LLM-generated",
            ],
            [
                "Low-code\nplatforms",
                "Template assembly through a visual builder",
                "Fixed templates; no real source ownership or architectural control",
            ],
        ],
        "block": {
            "heading": "COMMON GAP",
            "body": "No shared project state, no resilience when a provider fails, and no verification of what was produced.",
        },
        "block_top": 5.62,
        "block_height": 1.1,
        "notes": (
            "[AKIF — 45 seconds]\n\n"
            "Looking at what exists today. Copilot and Cursor complete code inline, but they produce no "
            "requirements, no design, no documentation. Asking ChatGPT or Claude for a whole application "
            "in one conversation truncates — you get files importing modules the model never wrote. The "
            "research frameworks, MetaGPT, ChatDev and AutoGen, do use multiple agents, but they run the "
            "same fixed pipeline no matter what you ask for, depend on one model backend, and let the "
            "model generate build configuration. Low-code platforms just assemble templates. The common "
            "gap across all four is the same: no shared state, no resilience, no verification. "
            "Aslam will now present what we propose."
        ),
    },
    {
        "layout": mapping_slide,
        "number": 5,
        "title": "Proposed System",
        "subtitle": "AgileAgent — eleven specialised AI engineering agents under a deterministic workflow engine",
        "definition": "A plain-language idea becomes a complete, reviewed, downloadable software project.",
        "pairs": [
            ("No shared context between prompts", "One typed Shared Project Memory threaded through every agent"),
            ("Fixed pipeline regardless of the project", "Capability-driven workflow — every skip shown with its reason"),
            ("Single-model dependency", "Provider-agnostic layer: routing, retry, failover, caching"),
            ("Build files written by a language model", "Deterministic scaffolding — build tooling never AI-generated"),
            ("Output returned unverified", "Automated review and improvement pass, plus generated tests"),
        ],
        "notes": (
            "[ASLAM — 70 seconds]\n\n"
            "This is the core of our proposal. AgileAgent is a platform where eleven specialised AI "
            "engineering agents collaborate under a deterministic workflow engine to turn a plain-language "
            "idea into a complete, reviewed, downloadable project.\n\n"
            "Each mechanism on the right removes a specific limitation on the left. No shared context is "
            "solved by one typed shared project memory that every agent reads and writes — so the backend "
            "engineer sees the schema the database engineer designed. The fixed pipeline is replaced by "
            "capability-driven assignment: a portfolio site gets no database engineer, and the interface "
            "shows the reason it was skipped. Single-model dependency is solved by a provider-agnostic "
            "layer with automatic failover. Build files are emitted deterministically by hand-verified "
            "code, never by a model, because a subtly wrong build file breaks a project in ways a reader "
            "cannot diagnose. And the output goes through a review and improvement pass before packaging."
        ),
    },
    {
        "layout": bullet_slide,
        "number": 6,
        "title": "Objectives & Scope",
        "subtitle": "Five measurable objectives",
        "bullets": [
            ("1.", "Design a multi-agent architecture of eleven roles over a single typed project state."),
            ("2.", "Build a capability-driven workflow engine that states a reason for every skipped agent."),
            ("3.", "Implement provider-agnostic orchestration — routing, retry, failover, caching — across six providers."),
            ("4.", "Guarantee structure via deterministic build tooling and two-phase plan-then-generate code output."),
            ("5.", "Deliver a packaged, reviewed, documented project with an auditable engineering report."),
        ],
        "strip": "Out of scope: cloud deployment · CI/CD generation · GitHub push · vector memory · multi-tenant SaaS",
        "notes": (
            "[ASLAM — 40 seconds]\n\n"
            "Five objectives, each measurable. One, an eleven-role multi-agent architecture over a single "
            "typed project state. Two, a workflow engine that selects agents by capability and gives a "
            "reason for every skip. Three, a provider-agnostic orchestration layer across six model "
            "providers. Four, structural correctness — build tooling emitted deterministically, and code "
            "generated in two phases: first a file manifest, then contents in ordered batches. Five, a "
            "packaged and documented project with an auditable report.\n\n"
            "We have deliberately scoped out cloud deployment, CI/CD generation, GitHub push automation, "
            "vector memory and multi-tenant isolation — the architecture accommodates them later, but "
            "they are not version one."
        ),
    },
    {
        "layout": table_slide,
        "number": 7,
        "title": "Literature Survey & Research Gap",
        "widths": [2.62, 3.15, 3.10, 3.22],
        "font_size": 10,
        "table_height": 3.55,
        "last_column_danger": True,
        "rows": [
            ["Author, Year", "Method / Technique", "Findings", "Limitation"],
            [
                "Chen et al., 2021\n(Codex)",
                "LLM trained on public code; HumanEval benchmark",
                "28.8% pass@1;\n~70% pass@100",
                "Isolated functions only; no multi-file project structure",
            ],
            [
                "Yao et al., 2022\n(ReAct)",
                "Interleaves reasoning traces with tool actions",
                "Less hallucination than chain-of-thought alone",
                "Single agent; no role specialisation or persistent artifacts",
            ],
            [
                "Hong et al., 2023\n(MetaGPT)",
                "Standard operating procedures encoded into agent roles",
                "Outperforms single-agent baselines on software tasks",
                "Fixed waterfall for every input; one LLM backend",
            ],
            [
                "Qian et al., 2023\n(ChatDev)",
                "Chat-chain 'virtual software company' of paired roles",
                "Completes small software in minutes, at low cost",
                "Toy scale; build config LLM-written; correctness unverified",
            ],
            [
                "Wu et al., 2023\n(AutoGen)",
                "Generic framework of conversable, composable agents",
                "Flexible orchestration across many domains",
                "Developer must design the loop; no SDLC artifacts or packaging",
            ],
        ],
        "block": {
            "heading": "RESEARCH GAP",
            "body": (
                "Existing multi-agent frameworks share four unaddressed weaknesses:  (a) a fixed pipeline is executed "
                "regardless of what the project requires,  (b) they depend on a single model provider, so one quota "
                "aborts a long run,  (c) the language model writes build configuration — where silent breakage "
                "originates, and  (d) code is returned with no review pass and no traceable artifact set.  "
                "AgileAgent is designed to address all four."
            ),
        },
        "block_top": 5.18,
        "block_height": 1.54,
        "notes": (
            "[ASLAM — 55 seconds]\n\n"
            "Five papers frame our work. Codex, in 2021, showed LLMs can write correct code — but it "
            "evaluates isolated functions, not projects. ReAct improved reliability by interleaving "
            "reasoning with actions, but it is a single agent. MetaGPT and ChatDev, both 2023, are the "
            "closest work: they use specialised roles and do outperform single agents. But MetaGPT runs "
            "the same waterfall for every input, and ChatDev produces toy-scale output with build "
            "configuration written by the model itself. AutoGen is flexible but leaves the developer to "
            "design the loop, with no SDLC artifacts.\n\n"
            "So the research gap is fourfold: fixed pipelines, single-provider dependency, LLM-written "
            "build configuration, and no review or traceability. Those four gaps are exactly what "
            "AgileAgent targets."
        ),
    },
    {
        "layout": flow_slide,
        "number": 8,
        "title": "Proposed Methodology",
        "subtitle": "End-to-end working procedure",
        "steps": [
            ("1", "Idea intake", "the user describes the software in plain language", False),
            ("2", "Requirement analysis", "SRS produced; five capability questions answered", False),
            ("3", "Technology recommendation", "stacks scored against requirements, each ranking explained", False),
            ("4", "Stack review", "the user may override any layer before execution", False),
            ("5", "Workflow planning", "order derived by topological sort of agent dependencies", False),
            ("6", "Deterministic scaffolding", "build tooling emitted by code — no model involvement", True),
            ("7", "Dynamic agent execution", "only required agents run, over the shared memory", False),
            ("8", "Two-phase code generation", "file manifest first, then contents in ordered batches", True),
            ("9", "Review & improvement", "file-specific issues found, then applied", False),
            ("10", "Packaging", "documentation, containers, manifest, report, archive", False),
        ],
        "legend": "Steps 6 and 8 are deterministic — the two places where ordinary code, not a language model, guarantees the result.",
        "notes": (
            "[ASLAM — 55 seconds]\n\n"
            "The working procedure runs in ten steps. The user describes an idea. The Business Analyst "
            "agent produces an SRS and answers five capability questions — does anything persist? do "
            "different people see different data? is there a user interface? Those answers decide which "
            "agents run. Technology options are scored and explained, and the user can override any "
            "layer. The workflow engine then derives execution order by topological sort over each "
            "agent's declared dependencies.\n\n"
            "Two steps are highlighted because they are deliberately not AI. Step six emits build tooling "
            "from hand-verified code. Step eight generates code in two phases — a file manifest first, "
            "then contents in ordered batches that can see what already exists — because a single "
            "completion for a whole application reliably truncates. Review, improvement and packaging "
            "close the pipeline. Puneeth will take the architecture."
        ),
    },
    {
        "layout": architecture_slide,
        "number": 9,
        "title": "System Architecture",
        "subtitle": "Four bands, strict one-way dependency, one gateway to every model provider",
        "notes": (
            "[PUNEETH — 70 seconds]\n\n"
            "The architecture has four bands. At the top, a React client that talks to the API over REST "
            "and receives live progress over Server-Sent Events — a client that reconnects replays from "
            "its last sequence number, so nothing is lost.\n\n"
            "The second band is a strictly layered API: routes handle HTTP only, services hold business "
            "logic and never import the web framework, repositories own all SQL, and PostgreSQL persists "
            "it. The dependency direction is one-way and enforced.\n\n"
            "The third band is where the capability lives — the agent registry with eleven agents, the "
            "workflow engine, nine technology adapters, and packaging. All four sit on the Shared Project "
            "Memory, which is the single typed state every agent reads and writes.\n\n"
            "The fourth band is the provider manager. Every model call passes through it: cache, route, "
            "retry, fail over, record. No agent ever addresses a provider directly — and that single "
            "constraint is what makes failover across these six providers automatic rather than "
            "something each agent has to handle."
        ),
    },
    {
        "layout": tech_slide,
        "number": 10,
        "title": "Technologies & Requirements",
        "groups": [
            (
                "Backend",
                ["Python 3.11+, FastAPI", "SQLAlchemy 2.0 (async)", "Pydantic v2, Alembic", "JWT auth, httpx, pytest"],
            ),
            (
                "Frontend",
                ["React 18, TypeScript (strict)", "Vite, Tailwind CSS", "SSE over fetch / ReadableStream", "Vitest"],
            ),
            (
                "Data & Infrastructure",
                ["PostgreSQL 16 (SQLite in dev)", "Docker, Docker Compose", "Non-root containers", "8 GB development machine"],
            ),
            (
                "Model providers",
                ["Google Gemini, Groq", "NVIDIA NIM, Ollama (local)", "OpenAI, Anthropic", "One provider-agnostic interface"],
            ),
            (
                "Stacks the platform generates",
                ["React 18 · Next.js 15 · Angular 18", "FastAPI · Express.js · Spring Boot 3.4", "PostgreSQL 16 · MySQL 8.4 · SQLite 3"],
            ),
            (
                "External requirements",
                ["Hosted provider API keys, or", "a local GPU for offline inference", "Internet access for hosted models"],
            ),
        ],
        "notes": (
            "[PUNEETH — 40 seconds]\n\n"
            "The backend is Python with FastAPI and async SQLAlchemy; the frontend is React with strict "
            "TypeScript; PostgreSQL in production, SQLite locally; everything containerised. Six model "
            "providers sit behind one provider-agnostic interface, and the platform can generate projects "
            "on nine different technology stacks.\n\n"
            "One point I want to make directly, because it is usually the first question. AgileAgent "
            "trains no model. It is an orchestration system built on pre-trained language models, so "
            "there is no dataset, no preprocessing and no train/test split — accuracy, precision and "
            "recall do not apply. Our evaluation is system-level instead: artifact completeness, "
            "structural validity of generated code, build success rate, per-agent success rate, failover "
            "recovery rate, generation latency and token cost per project."
        ),
    },
    {
        "layout": outcomes_slide,
        "number": 11,
        "title": "Expected Outcomes & Applications",
        "outcomes": [
            "A complete starter project: requirements, architecture, schema with executable DDL, API specification",
            "Frontend and backend source, unit tests, documentation and container definitions",
            "Runs that survive a provider failing mid-generation by continuing on another",
            "Every skipped agent reported with the reason it was not required",
            "A downloadable archive plus an auditable AI Engineering Report",
        ],
        "applications": [
            "Startup prototyping",
            "Academic project bootstrapping",
            "Developer onboarding",
            "Reference architectures",
            "Hackathon scaffolding",
            "Teaching the SDLC",
        ],
        "significance": "Significance: AI moves from a snippet-level assistant to an accountable engineering team.",
        "notes": (
            "[PUNEETH — 40 seconds]\n\n"
            "What we expect to deliver: a complete starter project — requirements, architecture, a database "
            "schema with executable DDL, an API specification, frontend and backend source, tests, "
            "documentation and container definitions. Runs that survive a provider failing halfway "
            "through. Every skipped agent reported with its reason, so the system's decisions are legible "
            "rather than mysterious. And a downloadable archive with an auditable engineering report.\n\n"
            "Applications range from startup prototyping and academic project bootstrapping to developer "
            "onboarding and teaching the lifecycle itself. The significance is the shift: AI stops being "
            "a snippet-level assistant and becomes an accountable engineering team — one that records "
            "why each decision was taken."
        ),
    },
    {
        "layout": workplan_slide,
        "number": 12,
        "title": "Work Plan & References",
        "phases": [
            ("Phase 1", "Aug – Sep 2026", "Literature survey, requirement analysis, architecture design"),
            ("Phase 2", "Oct 2026", "Core platform: API layer, authentication, database schema"),
            ("Phase 3", "Nov 2026", "Agents, shared project memory, workflow engine"),
            ("Phase 4", "Dec 26 – Jan 27", "LLM orchestration: routing, failover, caching; adapters"),
            ("Phase 5", "Feb 2027", "Web client, live event streaming, dashboards"),
            ("Phase 6", "Mar 2027", "Packaging, testing, evaluation against metrics"),
            ("Phase 7", "Apr 2027", "Documentation, final report, demonstration"),
        ],
        "responsibilities": [
            ("Mohammed Abdul Akif Ahmed", "245123733173", "LLM orchestration · provider integration · backend core"),
            ("Mohammed Aslam Uddin", "245123733182", "Agent implementation · workflow engine · shared memory"),
            ("Puneeth Reddy", "245123733186", "Web client · event streaming · packaging · testing"),
        ],
        "references": [
            "[1]  M. Chen et al., “Evaluating Large Language Models Trained on Code,” arXiv preprint arXiv:2107.03374, 2021.",
            "[2]  S. Yao et al., “ReAct: Synergizing Reasoning and Acting in Language Models,” in Proc. ICLR, 2023.",
            "[3]  S. Hong et al., “MetaGPT: Meta Programming for a Multi-Agent Collaborative Framework,” in Proc. ICLR, 2024.",
            "[4]  C. Qian et al., “ChatDev: Communicative Agents for Software Development,” in Proc. ACL, 2024.",
            "[5]  Q. Wu et al., “AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation,” arXiv preprint arXiv:2308.08155, 2023.",
            "[6]  C. E. Jimenez et al., “SWE-bench: Can Language Models Resolve Real-World GitHub Issues?,” in Proc. ICLR, 2024.",
        ],
        "notes": (
            "[PUNEETH — 35 seconds]\n\n"
            "Our work plan runs across seven phases from August 2026 to April 2027: survey and design "
            "first, then the core platform, then the agents and workflow engine, then LLM orchestration "
            "and the technology adapters, the web client, packaging and evaluation, and finally "
            "documentation and the demonstration.\n\n"
            "Responsibilities are split three ways — I have the web client, streaming, packaging and "
            "testing; Aslam has the agents, workflow engine and shared memory; Akif has the LLM "
            "orchestration layer and backend core. Our references are listed below. Thank you — we are "
            "happy to take questions."
        ),
    },
]


def build() -> Path:
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H

    for spec in SLIDES:
        spec["layout"](prs, spec)

    prs.save(OUTPUT)
    return OUTPUT


if __name__ == "__main__":
    path = build()
    print(f"wrote {path}  ({len(SLIDES)} slides)")
