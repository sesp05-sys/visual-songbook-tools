#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generates songbook PDF with:
- A5-format, to spalter
- Nøyaktige sidetall i toneartregister
- To-pass generering for å tracke sidetall
- Sangene flyter kontinuerlig etter hverandre
"""

import csv
import re
import sys
from collections import defaultdict
from datetime import datetime
from PyPDF2 import PdfReader
from reportlab.lib.pagesizes import A5, A4, LETTER

# Half Letter: 5.5" x 8.5" (American equivalent to A5)
HALF_LETTER = (5.5 * 72, 8.5 * 72)  # 396pt x 612pt
from reportlab.lib.units import mm, cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, 
    Table, TableStyle, KeepTogether, FrameBreak, Flowable, Image
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfgen import canvas
from reportlab.platypus.frames import Frame
from reportlab.platypus.doctemplate import PageTemplate, BaseDocTemplate, NextPageTemplate

# Global dictionary to store page numbers for each song
song_page_numbers = {}

class PageNumberTracker(Flowable):
    """Invisible flowable that tracks the page number when a song is rendered"""
    
    def __init__(self, song_num):
        Flowable.__init__(self)
        self.song_num = song_num
        self.width = 0
        self.height = 0
    
    def draw(self):
        """Called when flowable is rendered - capture the page number"""
        page_num = self.canv.getPageNumber()
        song_page_numbers[self.song_num] = page_num

class PageTracker(Flowable):
    """Invisible flowable that records its page number into song_page_numbers
    under the given key. Used to detect which page the songs section starts on."""

    def __init__(self, key):
        Flowable.__init__(self)
        self._key = key
        self.width = 0
        self.height = 0

    def draw(self):
        song_page_numbers[self._key] = self.canv.getPageNumber()

class IndexPageTracker(Flowable):
    """Invisible flowable that tracks the page number after the index"""

    def __init__(self):
        Flowable.__init__(self)
        self.width = 0
        self.height = 0

    def draw(self):
        """Called when flowable is rendered - capture the page number"""
        page_num = self.canv.getPageNumber()
        song_page_numbers['_index_end'] = page_num

class SongbookTemplate(BaseDocTemplate):
    """Custom document template med to spalter"""

    def __init__(self, filename, **kwargs):
        self.doc_title = kwargs.get('title', 'Songbook')
        self.page_size = kwargs.get('pagesize', A5)
        BaseDocTemplate.__init__(self, filename, **kwargs)

        page_width = self.page_size[0]
        page_height = self.page_size[1]

        # Scale margins based on page size
        if self.page_size == HALF_LETTER:
            left_margin = 1.1*cm
            right_margin = 1.1*cm
            top_margin = 1.4*cm
            bottom_margin = 1.7*cm
            col_gap = 0.3*cm
        else:  # A5 (default)
            left_margin = 1.2*cm
            right_margin = 1.2*cm
            top_margin = 1.5*cm
            bottom_margin = 1.8*cm
            col_gap = 0.3*cm

        self._left_margin = left_margin

        frame_width = (page_width - left_margin - right_margin - col_gap) / 2
        frame_height = page_height - top_margin - bottom_margin

        # Two-column frames
        left_frame = Frame(
            left_margin, bottom_margin, frame_width, frame_height,
            id='left_col', showBoundary=0
        )
        right_frame = Frame(
            left_margin + frame_width + col_gap, bottom_margin, frame_width, frame_height,
            id='right_col', showBoundary=0
        )

        two_col_template = PageTemplate(
            id='TwoCol', frames=[left_frame, right_frame],
            onPage=self.add_page_decorations
        )

        # Single column frame
        single_frame = Frame(
            left_margin, bottom_margin,
            page_width - left_margin - right_margin, frame_height,
            id='single', showBoundary=0
        )

        single_col_template = PageTemplate(
            id='SingleCol', frames=[single_frame],
            onPage=self.add_page_decorations
        )

        # Blank template for back cover
        blank_template = PageTemplate(
            id='BlankPage', frames=[single_frame],
            onPage=self.add_blank_decorations
        )

        self.addPageTemplates([single_col_template, two_col_template, blank_template])
        
    def add_page_decorations(self, canvas, doc):
        """Legg til header med tittel og footer with page numbers"""
        canvas.saveState()

        page_num = canvas.getPageNumber()
        margin = self._left_margin
        pw = self.page_size[0]
        ph = self.page_size[1]

        # Skip header/footer on title page (page 1)
        if page_num > 1:
            canvas.setFont('Helvetica', 9.2)
            canvas.setStrokeColor(colors.black)
            canvas.setLineWidth(0.8)

            # === HEADER ===
            header_y = ph - 0.9*cm
            canvas.drawCentredString(pw / 2, header_y, self.doc_title)

            header_line_y = ph - 1.1*cm
            canvas.line(margin, header_line_y, pw - margin, header_line_y)

            # === FOOTER ===
            footer_line_y = 1.1*cm
            canvas.line(margin, footer_line_y, pw - margin, footer_line_y)

            canvas.drawCentredString(pw / 2, 0.6*cm, str(page_num))

        canvas.restoreState()
    
    def add_blank_decorations(self, canvas, doc):
        """Blank page - no decorations at all"""
        pass

def create_styles():
    """Lag custom styles"""
    styles = getSampleStyleSheet()
    
    # Title style (11.3pt bold, +5% from previous)
    styles.add(ParagraphStyle(
        name='SongTitle',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=11.3,
        leading=13.3,
        spaceAfter=2,
        spaceBefore=15,
        textColor=colors.black
    ))

    # Key style (toneart, +5%)
    styles.add(ParagraphStyle(
        name='SongKey',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9.2,
        leading=11.3,
        spaceAfter=5,
        textColor=colors.black
    ))

    # Song text line style (10.3pt - with hanging indent for wrapped lines only)
    styles.add(ParagraphStyle(
        name='SongLine',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10.3,
        leading=12.4,
        spaceAfter=0,           # No space between lines
        leftIndent=8,           # Indent for wrapped lines
        firstLineIndent=-8      # First line starts at normal position
    ))

    # Last line in verse - same but with space after
    styles.add(ParagraphStyle(
        name='SongLineEnd',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10.3,
        leading=12.4,
        spaceAfter=5,
        leftIndent=8,
        firstLineIndent=-8
    ))

    # Song text style (for backwards compat)
    styles.add(ParagraphStyle(
        name='SongText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10.3,
        leading=12.4,
        spaceAfter=5,
        leftIndent=8,
        firstLineIndent=-8
    ))

    # Chorus line style (italic - with hanging indent)
    styles.add(ParagraphStyle(
        name='ChorusLine',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=10.3,
        leading=12.4,
        spaceAfter=0,
        leftIndent=8,
        firstLineIndent=-8
    ))

    # Last line in chorus
    styles.add(ParagraphStyle(
        name='ChorusLineEnd',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=10.3,
        leading=12.4,
        spaceBefore=0,
        spaceAfter=11,
        leftIndent=8,
        firstLineIndent=-8
    ))

    # Chorus style (for backwards compat)
    styles.add(ParagraphStyle(
        name='Chorus',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=10.3,
        leading=12.4,
        leftIndent=8,
        firstLineIndent=-8,
        spaceBefore=4,
        spaceAfter=11
    ))

    # Metadata style (+5%)
    styles.add(ParagraphStyle(
        name='Metadata',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.2,
        leading=10.3,
        textColor=colors.HexColor('#666666'),
        spaceAfter=9
    ))
    
    # TOC styles
    styles.add(ParagraphStyle(
        name='TOCHeading',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=16,
        leading=20,
        spaceAfter=15,
        alignment=TA_CENTER
    ))
    
    styles.add(ParagraphStyle(
        name='TOCEntry',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10.3,
        leading=13.3
    ))
    
    # Cover page styles - refined typography
    styles.add(ParagraphStyle(
        name='CoverTitleClassic',
        parent=styles['Normal'],
        fontName='Times-Roman',
        fontSize=32, leading=38,
        alignment=TA_CENTER, textColor=colors.HexColor('#1a1a1a'),
        spaceAfter=8
    ))
    styles.add(ParagraphStyle(
        name='CoverTitleModern',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=26, leading=32,
        alignment=TA_CENTER, textColor=colors.HexColor('#1a1a1a'),
        spaceAfter=8
    ))
    styles.add(ParagraphStyle(
        name='CoverTitleMinimal',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=22, leading=28,
        alignment=TA_CENTER, textColor=colors.HexColor('#222222'),
        spaceAfter=8
    ))
    styles.add(ParagraphStyle(
        name='CoverTitleElegant',
        parent=styles['Normal'],
        fontName='Times-Italic',
        fontSize=28, leading=34,
        alignment=TA_CENTER, textColor=colors.HexColor('#1a1a1a'),
        spaceAfter=8
    ))

    styles.add(ParagraphStyle(
        name='CoverSubtitle',
        parent=styles['Normal'],
        fontName='Times-Italic',
        fontSize=13, leading=18,
        alignment=TA_CENTER, textColor=colors.HexColor('#555555'),
        spaceBefore=4, spaceAfter=6
    ))

    styles.add(ParagraphStyle(
        name='CoverDate',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10, leading=14,
        alignment=TA_CENTER, textColor=colors.HexColor('#777777')
    ))

    styles.add(ParagraphStyle(
        name='CoverFooter',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10, leading=14,
        alignment=TA_CENTER, textColor=colors.HexColor('#666666')
    ))

    # Backwards compat
    styles.add(ParagraphStyle(
        name='CoverTitle', parent=styles['Normal'],
        fontName='Times-Roman', fontSize=32, leading=38,
        alignment=TA_CENTER, textColor=colors.black, spaceAfter=8
    ))

    styles.add(ParagraphStyle(
        name='CoverText',
        parent=styles['Normal'],
        fontName='Helvetica', fontSize=11, leading=14,
        alignment=TA_CENTER, textColor=colors.HexColor('#666666')
    ))

    return styles

def parse_song_structure(body):
    """Parser sangtekst og identifiser vers og refreng"""
    if not body:
        return []
    
    sections = []
    parts = body.split('\n\n')
    
    for part in parts:
        part = part.strip()
        if not part or part == '.':
            continue
        
        # Check if chorus
        if part.lower().startswith('chorus') or part.lower().startswith('kor:') or part.lower().startswith('kor '):
            # Remove chorus prefix
            text = re.sub(r'^(chorus|kor:?)\s*', '', part, flags=re.IGNORECASE)
            # Remove repetition marks
            text = re.sub(r':\/:|\|:\|', '', text).strip()
            if text:
                sections.append(('chorus', text))
        else:
            sections.append(('verse', part))
    
    return sections

def create_section_flowables(text, section_type, styles):
    """Create flowables for a section, one paragraph per line for proper hanging indent"""
    flowables = []
    lines = text.split('\n')

    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue

        # Remove any existing "Kor:" prefix from the line
        if section_type == 'chorus':
            line = re.sub(r'^(kor:?|chorus:?)\s*', '', line, flags=re.IGNORECASE)

        # Escape special XML chars
        line = line.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

        is_last = (i == len(lines) - 1)

        if section_type == 'chorus':
            if i == 0:
                line = f"<i>Kor: {line}</i>"
            else:
                line = f"<i>{line}</i>"
            style = styles['ChorusLineEnd'] if is_last else styles['ChorusLine']
        else:
            style = styles['SongLineEnd'] if is_last else styles['SongLine']

        flowables.append(Paragraph(line, style))

    return flowables

def create_song_flowables(song, styles, track_page=False):
    """Lag flowables for en sang - tittel+key+første seksjon holdes sammen"""
    flowables = []
    
    # Song number and title
    number = song['Nummer']
    title = song['Tittel']
    key = song['Toneart'].strip() if song['Toneart'] else ''
    
    # Add page tracker if needed (for first pass)
    if track_page:
        flowables.append(PageNumberTracker(number))
    
    # Parse song structure first
    sections = parse_song_structure(song['Tekst'])
    
    # Build first block: title + key + first section
    # This ensures title never appears alone at bottom of column
    first_block = []
    
    first_block.append(Paragraph(
        f"<b>{number}. {title}</b>",
        styles['SongTitle']
    ))
    
    # Key (toneart) on separate line if exists
    if key:
        first_block.append(Paragraph(
            f"<b>{key}</b>",
            styles['SongKey']
        ))
    else:
        first_block.append(Spacer(1, 6))
    
    # Add first section (verse or chorus) to the first block
    if sections:
        section_type, text = sections[0]
        section_lines = create_section_flowables(text, section_type, styles)
        first_block.extend(section_lines)

    # Keep the entire first block together
    flowables.append(KeepTogether(first_block))

    # Add remaining sections - each kept together individually
    for i, (section_type, text) in enumerate(sections[1:], 1):
        section_lines = create_section_flowables(text, section_type, styles)
        # Keep each section together
        flowables.append(KeepTogether(section_lines))
    
    # Metadata (author, copyright) if exists
    metadata = []
    if song['Tekstforfatter']:
        metadata.append(f"Tekst: {song['Tekstforfatter']}")
    if song['Copyright']:
        metadata.append(song['Copyright'])
    
    if metadata:
        flowables.append(Paragraph(
            ' | '.join(metadata),
            styles['Metadata']
        ))
    
    # Small space between songs - using paragraph with spaceBefore instead of Spacer
    # This prevents empty lines at top of columns
    
    # Return flowables as list - allows natural flow between songs
    return flowables

def load_songs():
    """Load songs from CSV"""
    songs = []
    with open('songs.csv', 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            songs.append(row)
    
    # Sort by song number
    songs.sort(key=lambda x: int(x['Nummer']) if x['Nummer'].isdigit() else 9999)
    return songs

def create_toc(songs, styles):
    """Lag innholdsfortegnelse"""
    story = []
    
    story.append(Paragraph("Innholdsfortegnelse", styles['TOCHeading']))
    story.append(Spacer(1, 15))
    
    for song in songs:
        number = song['Nummer']
        title = song['Tittel']
        
        # Truncate long titles
        if len(title) > 45:
            title = title[:42] + '...'
        
        toc_text = f"{number}. {title}"
        story.append(Paragraph(toc_text, styles['TOCEntry']))
    
    story.append(PageBreak())
    return story

def create_key_index_table(songs, styles, page_numbers=None):
    """Lag toneartregister som tabell with page numbers"""
    story = []
    
    story.append(PageBreak())
    story.append(Paragraph("Register etter toneart", styles['TOCHeading']))
    story.append(Spacer(1, 15))
    
    # Group songs by key
    by_key = defaultdict(list)
    for song in songs:
        key = song['Toneart'].strip() if song['Toneart'] else 'Ukjent'
        if key:
            by_key[key].append(song)
    
    # Sort keys alphabetically
    for key in sorted(by_key.keys()):
        # Key heading
        story.append(Paragraph(f"<b>{key}</b>", styles['SongTitle']))
        # Line under toneart heading
        story.append(Spacer(1, 2))
        
        # Create a simple horizontal line using a table with bottom border
        line_table = Table([['']], colWidths=[10*cm])
        line_table.setStyle(TableStyle([
            ('LINEBELOW', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        story.append(line_table)
        story.append(Spacer(1, 6))
        
        # Create table data
        table_data = []
        
        for song in sorted(by_key[key], key=lambda x: int(x['Nummer']) if x['Nummer'].isdigit() else 9999):
            number = song['Nummer']
            title = song['Tittel']
            toneart = song['Toneart'] if song['Toneart'] else '-'
            
            # Truncate long titles
            if len(title) > 35:
                title = title[:32] + '...'
            
            # Get page number from tracked data
            if page_numbers and number in page_numbers:
                page_num = str(page_numbers[number])
            else:
                page_num = "..."
            
            table_data.append([number + '.', title, toneart, page_num])
        
        # Create table
        if table_data:
            col_widths = [1.2*cm, 6*cm, 1.5*cm, 1.2*cm]
            
            t = Table(table_data, colWidths=col_widths)
            t.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('ALIGN', (0, 0), (0, -1), 'RIGHT'),   # Number right-aligned
                ('ALIGN', (1, 0), (1, -1), 'LEFT'),    # Title left-aligned
                ('ALIGN', (2, 0), (2, -1), 'CENTER'),  # Key centered
                ('ALIGN', (3, 0), (3, -1), 'RIGHT'),   # Page right-aligned
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                # Ingen linjer - kun spacing
            ]))
            
            story.append(t)
            story.append(Spacer(1, 12))
    
    return story

def create_cover_page(title, filename, date, styles, theme='classic', subtitle=None, footer=None, pagesize=A5):
    """Create cover page with selectable theme using golden ratio.

    Title is positioned at ~1/φ (≈38%) from top — the upper golden section.
    theme: 'classic' | 'modern' | 'minimal' | 'elegant'
    """
    from reportlab.platypus import HRFlowable
    from reportlab.lib.units import cm

    story = []
    page_height = pagesize[1]
    page_width = pagesize[0]

    title_style_map = {
        'classic': 'CoverTitleClassic',
        'modern': 'CoverTitleModern',
        'minimal': 'CoverTitleMinimal',
        'elegant': 'CoverTitleElegant',
    }
    title_style = styles[title_style_map.get(theme, 'CoverTitleClassic')]

    # Golden ratio: title baseline at ~38.2% from top
    # Account for page margins (~1.5cm top)
    top_offset = page_height * 0.382 - 4*cm
    if top_offset < 1*cm:
        top_offset = 1*cm
    story.append(Spacer(1, top_offset))

    # Main title
    story.append(Paragraph(title, title_style))

    # Theme-specific divider beneath title
    rule_width = page_width * 0.18  # short, centered rule
    if theme == 'classic':
        story.append(Spacer(1, 14))
        story.append(HRFlowable(width=rule_width, thickness=0.6,
                                color=colors.HexColor('#999999'),
                                hAlign='CENTER', spaceBefore=0, spaceAfter=0))
        story.append(Spacer(1, 12))
    elif theme == 'elegant':
        story.append(Spacer(1, 12))
        story.append(HRFlowable(width=rule_width * 1.2, thickness=0.4,
                                color=colors.HexColor('#888888'),
                                hAlign='CENTER', spaceBefore=0, spaceAfter=0))
        story.append(Spacer(1, 14))
    elif theme == 'modern':
        story.append(Spacer(1, 10))
        story.append(HRFlowable(width=rule_width * 0.6, thickness=2,
                                color=colors.HexColor('#1a1a1a'),
                                hAlign='CENTER', spaceBefore=0, spaceAfter=0))
        story.append(Spacer(1, 12))
    else:  # minimal — just whitespace
        story.append(Spacer(1, 16))

    # Optional subtitle
    if subtitle:
        story.append(Paragraph(subtitle, styles['CoverSubtitle']))

    # Date — small, positioned at lower golden section
    # Calculate space from current position to ~62% mark
    bottom_section = page_height * 0.618
    # Approximate: push date toward lower third
    story.append(Spacer(1, page_height * 0.18))
    story.append(Paragraph(date, styles['CoverDate']))

    # Footer text — bottom margin area
    if footer:
        story.append(Spacer(1, page_height * 0.06))
        story.append(Paragraph(footer, styles['CoverFooter']))

    story.append(PageBreak())
    return story

def create_blank_page():
    """Lag en blank side"""
    story = []
    story.append(Spacer(1, 1))
    story.append(PageBreak())
    return story

def create_back_cover(image_path, pagesize=A5):
    """Lag bakside med ørn-logo på 70% av siden"""
    import os
    story = []
    
    if not os.path.exists(image_path):
        print(f"⚠️  Advarsel: Finner ikke bilde: {image_path}")
        story.append(Spacer(1, 1))
        story.append(PageBreak())
        return story
    
    page_width = pagesize[0]
    page_height = pagesize[1]
    
    # Use 70% of page for image
    img_width = page_width * 0.70
    img_height = page_height * 0.70
    
    # Load image and maintain aspect ratio
    from PIL import Image as PILImage
    pil_img = PILImage.open(image_path)
    img_aspect = pil_img.width / pil_img.height
    
    # Calculate dimensions maintaining aspect ratio
    if img_aspect > 1:  # Landscape
        final_width = img_width
        final_height = img_width / img_aspect
    else:  # Portrait
        final_height = img_height
        final_width = img_height * img_aspect
    
    # Center vertically - calculate spacer needed
    # Total usable height is approximately page_height - 3.5cm (margins)
    usable_height = page_height - 3.5*cm
    top_space = (usable_height - final_height) / 2
    
    story.append(Spacer(1, top_space))
    
    # Create centered image
    img = Image(image_path, width=final_width, height=final_height)
    img.hAlign = 'CENTER'
    story.append(img)
    
    return story

PAGE_SIZES = {
    'a5': A5,
    'halfletter': HALF_LETTER,
}

def generate_songbook_pdf(output_name=None, page_format='a5', cover_theme='classic', cover_subtitle=None, cover_footer=None):
    """Generate complete songbook PDF with two-pass page numbering"""
    pagesize = PAGE_SIZES.get(page_format, A5)
    format_label = 'Half Letter (5.5x8.5")' if page_format == 'halfletter' else 'A5'
    print("=" * 60)
    print(f"Generating songbook PDF ({format_label} with page numbers)...")
    print("=" * 60)
    
    global song_page_numbers
    
    # Create styles
    styles = create_styles()
    
    # Load songs
    print("\n📖 Loading songs...")
    songs = load_songs()
    print(f"   Loaded {len(songs)} songs")
    
    # Determine output filename
    if output_name:
        filename = f"output/{output_name}.pdf"
        title = output_name.replace('_', ' ').replace('-', ' ')
    else:
        filename = "output/Songbook.pdf"
        title = "Songbook"
    
    # ========== PASS 1: Track page numbers ==========
    print("\n📍 Pass 1: Tracking page numbers...")
    song_page_numbers = {}
    
    doc1 = SongbookTemplate(
        "output/temp_pass1.pdf",
        pagesize=pagesize,
        title=title,
        author=title
    )
    
    story1 = []
    
    # Get date
    today = datetime.now().strftime("%d.%m.%Y")
    
    # Cover page (page 1)
    story1.extend(create_cover_page(title, output_name or "Songbook", today, styles, theme=cover_theme, subtitle=cover_subtitle, footer=cover_footer, pagesize=pagesize))
    
    # Blank page (page 2)
    story1.extend(create_blank_page())
    
    # TOC
    story1.extend(create_toc(songs, styles))
    
    # Songs with page tracking - track which page songs start on
    story1.append(NextPageTemplate('TwoCol'))
    story1.append(PageBreak())
    story1.append(PageTracker('_songs_start'))

    for i, song in enumerate(songs, 1):
        if i % 100 == 0:
            print(f"   Processed {i}/{len(songs)} songs...")
        
        # Create song flowables (now returns a list, not KeepTogether)
        song_flowables = create_song_flowables(song, styles, track_page=True)
        # Add each flowable individually to allow natural flow
        for flowable in song_flowables:
            story1.append(flowable)
    
    # Key index in Pass 1 (without real page numbers yet)
    story1.append(NextPageTemplate('SingleCol'))
    story1.extend(create_key_index_table(songs, styles, page_numbers={}))
    
    # Track page number after index to calculate blank pages needed
    story1.append(IndexPageTracker())
    
    # Add four blank pages before back cover in Pass 1 (maximum possible)
    story1.extend(create_blank_page())
    story1.extend(create_blank_page())
    story1.extend(create_blank_page())
    story1.extend(create_blank_page())
    
    # Switch to blank template for back cover in Pass 1
    story1.append(NextPageTemplate('BlankPage'))
    story1.append(PageBreak())  # Force new page with BlankPage template
    
    # Dummy back cover in Pass 1 (to maintain page count)
    story1.extend(create_blank_page())
    
    # Build first pass
    print("   Building first pass...")
    doc1.build(story1)
    
    print(f"   ✅ Tracked {len(song_page_numbers)} songs with page numbers")
    
    # ========== PASS 2: Build final PDF with page numbers ==========
    print("\n📄 Pass 2: Building final PDF with page numbers...")
    
    # First, build the content WITHOUT covers to check page count
    doc_temp = SongbookTemplate(
        "output/temp_content.pdf",
        pagesize=pagesize,
        title=title,
        author=title
    )
    
    story_content = []
    
    # TOC
    story_content.extend(create_toc(songs, styles))
    
    # Songs - insert blank page if needed to start on odd page
    story_content.append(NextPageTemplate('TwoCol'))
    story_content.append(PageBreak())
    songs_start = song_page_numbers.get('_songs_start', 1)
    if songs_start % 2 == 0:
        story_content.extend(create_blank_page())

    for i, song in enumerate(songs, 1):
        if i % 100 == 0:
            print(f"   Processed {i}/{len(songs)} songs...")
        
        # Create song flowables
        song_flowables = create_song_flowables(song, styles, track_page=False)
        for flowable in song_flowables:
            story_content.append(flowable)
    
    # Key index with real page numbers
    story_content.append(NextPageTemplate('SingleCol'))
    story_content.extend(create_key_index_table(songs, styles, page_numbers=song_page_numbers))
    
    # Build temp PDF to count pages
    print("   Building content to count pages...")
    doc_temp.build(story_content)
    
    # Count pages in temp PDF
    reader = PdfReader("output/temp_content.pdf")
    content_pages = len(reader.pages)
    print(f"   📄 Innmat har {content_pages} sider")
    
    # Calculate blank pages needed
    # We want back cover on even page with some blank pages before it
    # If content is odd: need 2 blanks (odd + 2 + PageBreak = even back cover)
    # If content is even: need 1 blank (even + 1 + PageBreak = even back cover)
    if content_pages % 2 == 0:  # Even - add 1 blank
        blank_pages_needed = 1
        print(f"   ✓ Innmat på partall → legger til {blank_pages_needed} blank side")
    else:  # Odd - add 2 blanks
        blank_pages_needed = 2
        print(f"   ✓ Innmat på oddetall → legger til {blank_pages_needed} blanke sider")
    
    # Now build final PDF with covers
    print("   Building final PDF with covers...")
    doc2 = SongbookTemplate(
        filename,
        pagesize=pagesize,
        title=title,
        author=title
    )
    
    story2 = []
    
    # Cover page (page 1)
    story2.extend(create_cover_page(title, output_name or "Songbook", today, styles, theme=cover_theme, subtitle=cover_subtitle, footer=cover_footer, pagesize=pagesize))
    
    # Blank page (page 2)
    story2.extend(create_blank_page())
    
    # Rebuild all content (can't reuse flowables after they've been built)
    # TOC
    story2.extend(create_toc(songs, styles))
    
    # Songs - insert blank page if needed to start on odd page
    story2.append(NextPageTemplate('TwoCol'))
    story2.append(PageBreak())
    if songs_start % 2 == 0:
        story2.extend(create_blank_page())

    for i, song in enumerate(songs, 1):
        song_flowables = create_song_flowables(song, styles, track_page=False)
        for flowable in song_flowables:
            story2.append(flowable)
    
    # Key index with real page numbers
    story2.append(NextPageTemplate('SingleCol'))
    story2.extend(create_key_index_table(songs, styles, page_numbers=song_page_numbers))
    
    # Add blank page(s) if needed
    if blank_pages_needed > 0:
        # Add all blanks except the last one with normal template
        for i in range(blank_pages_needed - 1):
            story2.extend(create_blank_page())
        
        # Last blank page (nest siste i PDF) without footer
        story2.append(NextPageTemplate('BlankPage'))
        story2.extend(create_blank_page())
    
    # Back cover - already on BlankPage template from above
    # If no blank pages were added, switch to BlankPage template now
    if blank_pages_needed == 0:
        story2.append(NextPageTemplate('BlankPage'))
    
    story2.append(PageBreak())
    
    # Back cover with eagle image (siste side - even numbered)
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    eagle_path = os.path.join(script_dir, 'eagle.png')
    story2.extend(create_back_cover(eagle_path, pagesize=pagesize))
    
    # Build final PDF
    print("   Building final PDF...")
    doc2.build(story2)
    
    print(f"\n✅ PDF generert: {filename}")
    print("=" * 60)
    print(f"\n📊 Statistikk:")
    print(f"   Total songs: {len(songs)}")
    print(f"   Format: {format_label}, to spalter (uten vertikale spaltelinjer)")
    print(f"   Font: Helvetica 10pt/12pt (tekst), 11pt bold (tittel), 9pt (toneart)")
    print(f"   Layout: Sangene flyter naturlig etter hverandre")
    print(f"   Smart sideskift: Tittel+key+første vers holdes sammen")
    print(f"                     Hvert vers/kor holdes sammen individuelt")
    print(f"   Toneartregister: Med nøyaktige sidetall")
    print(f"   Footer: Horisontal linje over")
    print(f"           Filnavn sentrert, sidetall venstre (partall) / høyre (oddetall)")
    print(f"           (ikke på forside eller bakside)")
    print(f"   Cover: Title page, blank p.2, blank second-to-last")
    print(f"           Bakside: Ørn (70%) uten footer")
    print("=" * 60)

if __name__ == '__main__':
    # Check if output name is provided as argument
    output_name = None
    if len(sys.argv) > 1:
        output_name = sys.argv[1]
    
    generate_songbook_pdf(output_name)
