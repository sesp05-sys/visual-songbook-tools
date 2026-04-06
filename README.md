# Visual Songbook Tools

A web-based toolkit for working with Visual Songbook (.vsb) files. Convert, edit, merge, and generate PDF songbooks.

## Features

- **Convert** &mdash; Drop any .vsb, .csv, or .json file and convert to any other format. Auto-detects source format and column mappings.
- **Generate PDF** &mdash; Upload a songbook (VSB, CSV, or JSON) and produce a print-ready PDF (A5 or Half Letter).
- **Song Editor** &mdash; Browse, search, edit, add, and delete songs in the browser. Lazy-loading table, keyboard navigation, import from any format, export to .vsb / .csv / .json.
- **Merge** &mdash; Combine multiple .vsb files into one. Drag to reorder. By default each book keeps its own numbering and later books continue after the previous one&apos;s last number; optional sequential renumbering with custom start number.
- **Light / dark mode** &mdash; Theme stored in `localStorage`, respects system preference.

## Tech Stack

- **Backend**: Python / Flask
- **Frontend**: Vanilla HTML / CSS / JS (no build step)
- **VSB handling**: Java with [Jackcess](https://jackcess.sourceforge.net/) for reading and writing JET4 (Microsoft Access) databases.
- **PDF generation**: ReportLab with a two-pass renderer that tracks song page numbers and ensures songs always start on a recto page.

## Setup

### Requirements

- Python 3.10+
- Java 17+

### Install

```bash
git clone https://github.com/sesp05-sys/visual-songbook-tools.git
cd visual-songbook-tools

# Python dependencies
python3 -m venv venv
source venv/bin/activate
pip install flask reportlab PyPDF2 gunicorn Pillow

# Compile Java tools
javac -cp "lib/*" CsvToVsb.java MergeVsb.java VsbToCsv.java

# Run
python app.py
```

Open http://localhost:5003

### VSB template (optional)

If you place a `.vsb` file in the project root, it will be used as a template when creating new VSB files (preserves the JET4 database structure). Without a template, `CsvToVsb` creates a fresh JET4 database from scratch.

## File Overview

| File | Description |
|------|-------------|
| `app.py` | Flask web app &mdash; routes, HTML templates, all API endpoints |
| `worker.py` | Background PDF generation worker |
| `generate_pdf.py` | PDF layout engine (ReportLab, two-column A5 / Half Letter) |
| `CsvToVsb.java` | Converts CSV to VSB using Jackcess |
| `VsbToCsv.java` | Exports VSB to CSV (sorted, ignores ghost rows) |
| `MergeVsb.java` | Merges multiple VSB files with offset or sequential numbering |
| `lib/` | Jackcess JARs (jackcess, commons-lang3, commons-logging) |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Converter page (PDF, convert, merge) |
| `/editor` | GET | Song editor page |
| `/api/upload` | POST | Generate PDF from VSB / CSV / JSON |
| `/api/progress` | GET | Job progress polling |
| `/api/download/<file>` | GET | Download generated PDF |
| `/api/export-csv` | POST | VSB &rarr; CSV |
| `/api/import-csv` | POST | CSV &rarr; VSB (with column mapping) |
| `/api/validate-csv` | POST | Validate CSV columns and preview |
| `/api/merge-vsb` | POST | Merge multiple VSB files |
| `/api/editor/import` | POST | Universal import (VSB / CSV / JSON) returning JSON |
| `/api/editor/export/<fmt>` | POST | Export song list as CSV / VSB / JSON |

## License

MIT
