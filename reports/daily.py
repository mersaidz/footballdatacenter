"""
Daily squad status as a document: one landscape A4 page for the morning staff meeting (PDF)
and the same table with raw numbers for analysts (Excel).

Health-data rule for anything printed or forwarded: wellness appears only as the overall level
(total and "below normal"), never the player's answers, sore areas or comments.
"""
from __future__ import annotations

import io
from datetime import date
from pathlib import Path

from django.utils import timezone

from football.services import performance as perf

from .texts import Words

FONTS = Path(__file__).parent / 'fonts'
STATUS_COLOR = {'reduce': '#C93538', 'hold': '#9A6700', 'build': '#2460C4', 'plan': '#1D7F47', 'out': '#697282'}
STATUS_TINT = {'reduce': '#FBE7E7', 'hold': '#FBF1D9', 'build': '#E3ECFA', 'plan': '#E2F3E9', 'out': '#EEF0F3'}
FEEL_COLOR = {'ok': '#1D7F47', 'low': '#9A6700', 'very_low': '#C93538'}
INK, MUTED, LINE, ACCENT = '#14171C', '#5B6472', '#D9DDE3', '#E8590C'
LEVELS = ('reduce', 'hold', 'build', 'plan')


def acwr_color(v):
    if v is None:
        return MUTED
    return '#C93538' if v > 1.5 else '#9A6700' if v > 1.3 else '#2460C4' if v < 0.8 else INK


def build(team, as_of: date | None, lang: str) -> dict:
    """Everything both formats print, already in words."""
    w = Words(lang)
    s = perf.squad_status(team, as_of)
    players = s['players']
    counts = {lvl: sum(1 for p in players if p['level'] == lvl) for lvl in LEVELS + ('out',)}
    lm = s.get('last_match')
    context = ''
    if lm and s.get('days_since_match') is not None:
        name = f"{lm['name']} ({w.day(lm['date'])})"
        context = w('day_after', m=name) if s['days_since_match'] == 1 else w('days_after', n=s['days_since_match'], m=name)
    as_of_d = date.fromisoformat(s['as_of']) if s['as_of'] else timezone.localdate()
    rows = []
    for p in players:
        feel = p.get('wellness')
        av = p.get('availability')
        rows.append({
            **p,
            'status_text': w(f"lvl_{p['level']}"),
            'why': w.reasons(p['reasons']),
            'feel_text': f"{feel['total']}/25 {w('feel_' + feel['level'])}" if feel else w('feel_none'),
            'feel_level': feel['level'] if feel else None,
            'feel_total': feel['total'] if feel else None, 'feel_usual': feel.get('normal') if feel else None,
            'avail_text': w('st_' + av['status']) if av else '', 'return': av['expected_return'] if av else None,
        })
    training = [r for r in rows if r['level'] != 'out']
    md1 = None
    if s.get('days_since_match') == 1:
        by_no = lambda r: (r['shirt_number'] or 99)           # noqa: E731
        md1 = {'recovery': sorted([r for r in training if not r.get('is_gk') and r['last_match_minutes'] >= 60], key=by_no),
               'topup': sorted([r for r in training if not r.get('is_gk') and r['last_match_minutes'] < 60], key=by_no),
               'keepers': sorted([r for r in training if r.get('is_gk')], key=by_no)}
    return {'w': w, 'club': team.club.name, 'team': team.name, 'as_of': as_of_d, 'context': context, 'counts': counts,
            'rows': rows, 'md1': md1, 'wellness': s.get('wellness') or {'answered': 0, 'squad': len(players)},
            'generated': timezone.localtime().strftime('%d.%m.%Y %H:%M')}


# ---------- PDF ----------

def _fonts():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    if 'FDC' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('FDC', str(FONTS / 'DejaVuSansCondensed.ttf')))
        pdfmetrics.registerFont(TTFont('FDC-B', str(FONTS / 'DejaVuSansCondensed-Bold.ttf')))


def pdf(data: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    _fonts()
    w = data['w']
    C = colors.HexColor
    base = ParagraphStyle('b', fontName='FDC', fontSize=8.5, leading=10.5, textColor=C(INK))
    small = ParagraphStyle('s', parent=base, fontSize=7.5, leading=9.5, textColor=C(MUTED))
    bold = ParagraphStyle('bb', parent=base, fontName='FDC-B')
    h1 = ParagraphStyle('h1', parent=base, fontName='FDC-B', fontSize=17, leading=20)
    h2 = ParagraphStyle('h2', parent=base, fontName='FDC-B', fontSize=10, leading=13)
    big = ParagraphStyle('big', parent=base, fontName='FDC-B', fontSize=20, leading=22)

    def col(text, color, style=base):
        return Paragraph(f'<font color="{color}">{text}</font>', style)

    page_w, page_h = landscape(A4)
    margin = 12 * mm
    width = page_w - 2 * margin
    story = []

    # header
    d = data['as_of']
    head = Table([[Paragraph(w('title'), h1),
                   Paragraph(f"{data['club']}, {data['team']}<br/>{w.weekday(d)}, {d.strftime('%d.%m.%Y')}", ParagraphStyle('r', parent=base, alignment=2))]],
                 colWidths=[width * 0.6, width * 0.4])
    head.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'BOTTOM'), ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))
    story += [head]
    if data['context']:
        story += [Spacer(1, 2), Paragraph(data['context'], small)]
    story += [Spacer(1, 8)]

    # counts
    cells = []
    for lvl in LEVELS:
        cells.append([col('■ ' + w(f'lvl_{lvl}'), STATUS_COLOR[lvl], bold), Paragraph(str(data['counts'][lvl]), big),
                      Paragraph(w(f'hint_{lvl}'), small)])
    kpi = Table([cells], colWidths=[width / 4] * 4)
    kpi.setStyle(TableStyle([('BOX', (i, 0), (i, 0), 0.6, C(LINE)) for i in range(4)] +
                            [('BACKGROUND', (i, 0), (i, 0), C(STATUS_TINT[lvl])) for i, lvl in enumerate(LEVELS)] +
                            [('VALIGN', (0, 0), (-1, -1), 'TOP'), ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))
    story += [kpi, Spacer(1, 4)]
    extra = [w('answered', a=data['wellness']['answered'], n=data['wellness']['squad'])]
    if data['counts']['out']:
        extra.append(w('not_training', n=data['counts']['out']))
    story += [Paragraph('.   '.join(extra), small), Spacer(1, 8)]

    # MD+1 groups
    if data['md1']:
        names = lambda rs: ', '.join(f"{r['shirt_number'] or ''} {r['name']}".strip() for r in rs) or '—'   # noqa: E731
        groups = Table([[Paragraph(f"{w('recovery')} <font color='{MUTED}'>({w('played60')}, {len(data['md1']['recovery'])})</font>", bold),
                         Paragraph(f"{w('topup')} <font color='{MUTED}'>({w('under60')}, {len(data['md1']['topup'])})</font>", bold)],
                        [Paragraph(names(data['md1']['recovery']), base), Paragraph(names(data['md1']['topup']), base)]],
                       colWidths=[width / 2] * 2)
        groups.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0)]))
        block = [Paragraph(w('md1'), h2), Spacer(1, 3), groups]
        if data['md1']['keepers']:
            block += [Spacer(1, 3), Paragraph(f"<b>{w('keepers')}</b> <font color='{MUTED}'>({w('keepers_hint')})</font>: "
                                              f"{names(data['md1']['keepers'])}", base)]
        story += [KeepTogether(block), Spacer(1, 8)]

    # the table
    header = [w('col_status'), w('col_no'), w('col_player'), w('col_why'), w('col_feel'), w('col_acwr_d'), w('col_acwr_h'), w('col_acwr_a'),
              w('col_week'), w('col_vs_prev'), w('col_last')]
    body = [[Paragraph(h, ParagraphStyle('th', parent=small, fontName='FDC-B')) for h in header]]
    styles = []
    for i, r in enumerate(data['rows'], start=1):
        out = r['level'] == 'out'
        ink = MUTED if out else INK
        acwr_d = f"<font color='{acwr_color(r['acwr_distance'])}'>{w.num(r['acwr_distance'], 2)}</font>"
        if r.get('is_gk'):
            acwr_d += f" <font color='{MUTED}' size='6.5'>{w('gk_pl')}</font>"
        ah = r.get('acwr_dives') if r.get('is_gk') else r['acwr_hsr']
        change = r['week_change_pct']
        body.append([
            col(r['status_text'], STATUS_COLOR[r['level']], bold),
            col(str(r['shirt_number'] or ''), MUTED),
            col(r['name'] + (' (GK)' if r.get('is_gk') else ''), ink, bold),
            col(r['why'], ink),
            col(r['feel_text'], FEEL_COLOR.get(r['feel_level'], MUTED)),
            Paragraph(acwr_d, base),
            col(w.num(ah, 2), acwr_color(ah)),
            col(w.num(r.get('acwr_accdec'), 2), acwr_color(r.get('acwr_accdec'))),
            col(w.num(r['week_distance'] / 1000, 1), ink),
            col('—' if change is None else f"{'+' if change > 0 else ''}{change}%", MUTED),
            col(f"{r['last_match_minutes']}′" if r['last_match_minutes'] else '—', ink),
        ])
        if i % 2 == 0:
            styles.append(('BACKGROUND', (0, i), (-1, i), C('#F6F7F9')))
    cw = [0.11, 0.028, 0.13, 0.26, 0.1, 0.065, 0.06, 0.07, 0.055, 0.06, 0.052]
    table = Table(body, colWidths=[width * x for x in cw], repeatRows=1)
    table.setStyle(TableStyle([
        ('LINEBELOW', (0, 0), (-1, 0), 0.8, C(INK)), ('LINEBELOW', (0, 1), (-1, -1), 0.3, C(LINE)),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 3), ('RIGHTPADDING', (0, 0), (-1, -1), 3),
    ] + styles))
    story += [table, Spacer(1, 8), Paragraph(w('rules'), small)]

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont('FDC', 7)
        canvas.setFillColor(C(MUTED))
        canvas.drawString(margin, 7 * mm, f"Football Data Center.  {w('generated', t=data['generated'])}")
        canvas.drawRightString(page_w - margin, 7 * mm, w('page', n=doc.page))
        canvas.setFillColor(C(ACCENT))
        canvas.rect(margin, page_h - 8 * mm, 18 * mm, 1.2 * mm, stroke=0, fill=1)
        canvas.restoreState()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=margin, rightMargin=margin, topMargin=12 * mm,
                            bottomMargin=13 * mm, title=f"{w('title')} {d.isoformat()}", author='Football Data Center')
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()


# ---------- Excel ----------

def xlsx(data: dict) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    w = data['w']
    wb = Workbook()
    ws = wb.active
    ws.title = w('sheet')
    d = data['as_of']
    ws['A1'] = f"{w('title')}: {data['club']}, {data['team']}"
    ws['A1'].font = Font(bold=True, size=14)
    ws['A2'] = f"{w('col_date')}: {d.strftime('%d.%m.%Y')}" + (f".  {data['context']}" if data['context'] else '')
    ws['A3'] = '   '.join(f"{w('lvl_' + lvl)}: {data['counts'][lvl]}" for lvl in LEVELS + ('out',))
    header = [w('col_status'), w('col_no'), w('col_player'), w('col_pos'), w('col_why'), w('col_feel_total'), w('col_feel_usual'),
              w('col_feel'), w('col_acwr_d'), w('col_acwr_h'), w('col_acwr_a'), w('col_week'), w('col_vs_prev'), w('col_last'), w('col_avail'),
              w('col_return')]
    top = 5
    for c, h in enumerate(header, start=1):
        cell = ws.cell(row=top, column=c, value=h)
        cell.font = Font(bold=True)
        cell.alignment = Alignment(wrap_text=True, vertical='center')
    for i, r in enumerate(data['rows'], start=top + 1):
        values = [r['status_text'], r['shirt_number'], r['name'], 'GK' if r.get('is_gk') else r['position'], r['why'],
                  r['feel_total'], r['feel_usual'], w('feel_' + r['feel_level']) if r['feel_level'] else w('feel_none'),
                  r['acwr_distance'], r.get('acwr_dives') if r.get('is_gk') else r['acwr_hsr'], r.get('acwr_accdec'), round(r['week_distance'] / 1000, 1),
                  (r['week_change_pct'] / 100) if r['week_change_pct'] is not None else None, r['last_match_minutes'] or None,
                  r['avail_text'], date.fromisoformat(r['return']) if r['return'] else None]
        for c, v in enumerate(values, start=1):
            ws.cell(row=i, column=c, value=v)
        ws.cell(row=i, column=1).fill = PatternFill('solid', fgColor=STATUS_TINT[r['level']][1:])
        ws.cell(row=i, column=1).font = Font(bold=True, color=STATUS_COLOR[r['level']][1:])
        for c in (9, 10, 11):
            ws.cell(row=i, column=c).number_format = '0.00'
        ws.cell(row=i, column=13).number_format = '+0%;-0%;0%'
        ws.cell(row=i, column=16).number_format = 'DD.MM.YYYY'
        ws.cell(row=i, column=5).alignment = Alignment(wrap_text=True, vertical='top')
    widths = [18, 5, 22, 8, 48, 12, 9, 14, 10, 10, 12, 10, 12, 10, 14, 11]
    for c, wdt in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(c)].width = wdt
    ws.freeze_panes = ws.cell(row=top + 1, column=4)
    ws.auto_filter.ref = f'A{top}:{get_column_letter(len(header))}{top + len(data["rows"])}'
    ws.cell(row=top + len(data['rows']) + 2, column=1, value=w('rules')).font = Font(italic=True, color='5B6472')
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
