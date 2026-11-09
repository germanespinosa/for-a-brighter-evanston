#!/usr/bin/env python3
"""Build the team help PDF after reviewing its Markdown; --check detects drift.

Requires reportlab>=4,<5 for building. --check uses only the standard library.
Do not regenerate merely to silence a freshness failure: review the help text first.
"""
import argparse
import hashlib
import html
import json
from pathlib import Path
import re

SOURCE = 'docs/help/team-help.md'
PDF = 'docs/help/team-help.pdf'
MANIFEST = 'docs/help/reviewed-sources.json'
TRACKED = (
    SOURCE, 'docs/agents/fabian-news.md', 'docs/agents/fabian-website.md',
    'scripts/news_tool.py', 'scripts/sandbox_check.py', 'scripts/sandbox_screens.py',
    'scripts/mockup_check.py',
    '.github/workflows/pages.yml', '.github/workflows/sandbox-trigger.yml',
    'scripts/build_help_pdf.py',
    'scripts/build_site_icons.py', 'assets/img/brand-icon.png', '_layouts/default.html',
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stale(root):
    path = root / MANIFEST
    if not path.exists():
        return [MANIFEST]
    baseline = json.loads(path.read_text(encoding='utf-8'))
    return [name for name in (*TRACKED, PDF)
            if not (root / name).exists() or baseline.get(name) != digest(root / name)]


def build(root):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

    fonts = Path('/usr/share/fonts/truetype/dejavu')
    pdfmetrics.registerFont(TTFont('HelpSans', str(fonts / 'DejaVuSans.ttf')))
    pdfmetrics.registerFont(TTFont('HelpSansBold', str(fonts / 'DejaVuSans-Bold.ttf')))
    pdfmetrics.registerFontFamily('HelpSans', normal='HelpSans', bold='HelpSansBold')
    styles = getSampleStyleSheet()
    body = ParagraphStyle('HelpBody', fontName='HelpSans', fontSize=9.5,
                          leading=14, spaceAfter=7, alignment=TA_LEFT)
    h1 = ParagraphStyle('HelpH1', parent=body, fontName='HelpSansBold', fontSize=16,
                        leading=21, textColor=colors.HexColor('#13224F'), spaceBefore=16,
                        spaceAfter=10, keepWithNext=True)
    h2 = ParagraphStyle('HelpH2', parent=h1, fontSize=12, leading=17, spaceBefore=10)
    bullet = ParagraphStyle('HelpBullet', parent=body, leftIndent=12, firstLineIndent=-9)
    example = ParagraphStyle('HelpExample', parent=body, leftIndent=14,
                             textColor=colors.HexColor('#30567D'), borderPadding=6,
                             backColor=colors.HexColor('#F0F4FA'))
    source_style = ParagraphStyle('HelpSource', parent=body, fontSize=7.5, leading=11,
                                  wordWrap='CJK')
    replacements = {'✅': '✓', '❌': '✗', '👀': '[Eyes]', '⏳': '[Hourglass]', '⚠️': '[Warning]'}
    def markup(text):
        for old, new in replacements.items():
            text = text.replace(old, new)
        text = html.escape(text)
        text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
        return re.sub(r'(https?://[^\s]+)', r'<link href="\1" color="#30567D">\1</link>', text)
    story = []
    for line in (root / SOURCE).read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        if line.startswith('# '):
            style, text = h1, line[2:]
        elif line.startswith('## '):
            style, text = h2, line[3:]
        elif line.startswith('- '):
            style, text = bullet, '• ' + line[2:]
        elif line.startswith('> '):
            style, text = example, line[2:]
        elif re.match(r'^\[\d+\] https', line):
            style, text = source_style, line
        else:
            style, text = body, line
        story.append(Paragraph(markup(text), style))
    output = root / PDF
    output.parent.mkdir(parents=True, exist_ok=True)
    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont('HelpSans', 8)
        canvas.setFillColor(colors.HexColor('#586174'))
        canvas.drawString(43, 27, 'For a Brighter Evanston | Working with Fabian')
        canvas.drawRightString(letter[0] - 43, 27, f'Page {doc.page}')
        canvas.restoreState()
    SimpleDocTemplate(str(output), pagesize=letter, rightMargin=43, leftMargin=43,
                      topMargin=36, bottomMargin=43, title='Working with Fabian',
                      author='For a Brighter Evanston').build(story, onFirstPage=footer, onLaterPages=footer)
    hashes = {name: digest(root / name) for name in (*TRACKED, PDF)}
    (root / MANIFEST).write_text(json.dumps(hashes, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(f'Built {PDF}; recorded reviewed source hashes')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    if args.check:
        changed = stale(root)
        if changed:
            print('HELP REVIEW REQUIRED: ' + ', '.join(changed))
            print('Update docs/help/team-help.md to match functionality, rebuild the PDF, and commit all outputs.')
            return 1
        print('Help source, PDF and reviewed functionality fingerprints are current.')
        return 0
    build(root)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
