#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Visual Songbook Tools - Background PDF Generation
"""

import os
import sys
import json
import csv
import io
import subprocess
import traceback
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATUS_FILE = os.path.join(BASE_DIR, 'job_status.json')
OUTPUT_FOLDER = os.path.join(BASE_DIR, 'output')

def set_status(running, progress, message, error=None, result=None):
    import fcntl
    status = {
        'running': running,
        'progress': progress,
        'message': message,
        'error': error,
        'result': result,
        'started_at': datetime.now().timestamp() if running else None
    }
    with open(STATUS_FILE, 'w') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        json.dump(status, f)
        f.flush()
        fcntl.flock(f, fcntl.LOCK_UN)

def convert_mdb_to_csv(mdb_path, csv_path):
    """Convert MDB/VSB file to CSV"""
    result = subprocess.run(
        ['mdb-export', mdb_path, 'Songs'],
        capture_output=True,
        text=True,
        check=True
    )

    reader = csv.DictReader(io.StringIO(result.stdout))
    songs_raw = list(reader)

    # Filter dummy songs
    real_songs = [s for s in songs_raw
                 if s.get('Title') and not s['Title'].startswith('_')]

    # Write CSV in correct format
    with open(csv_path, 'w', encoding='utf-8', newline='') as f:
        fieldnames = ['Nummer', 'Tittel', 'Tekst', 'Tekstforfatter',
                     'Copyright', 'Toneart', 'Kategori']
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=';')
        writer.writeheader()

        for song in real_songs:
            writer.writerow({
                'Nummer': song.get('SongNum', ''),
                'Tittel': song.get('Title', '').strip(),
                'Tekst': song.get('Body', '').strip(),
                'Tekstforfatter': song.get('Author', '').strip(),
                'Copyright': song.get('Copyright', '').strip(),
                'Toneart': song.get('Key', '').strip(),
                'Kategori': song.get('CategoryId', '1')
            })

    return len(real_songs)

def generate_pdf(csv_path, output_name, title):
    """Generate PDF using the existing generator"""
    # Import the generator module
    sys.path.insert(0, BASE_DIR)

    # We need to modify generate_pdf.py to accept parameters
    # For now, copy the CSV to the expected location and run the generator

    # Copy CSV to expected location
    expected_csv = os.path.join(BASE_DIR, 'songs.csv')
    if csv_path != expected_csv:
        import shutil
        shutil.copy(csv_path, expected_csv)

    # Import and run the generator
    from generate_pdf import generate_songbook_pdf

    # The generator writes to output/ folder
    generate_songbook_pdf(output_name)

    return f"{output_name}.pdf"

def run_worker(input_path, title, job_id, page_format='a5', cover_theme='classic', cover_subtitle=None, cover_footer=None):
    """Main worker function"""
    try:
        set_status(True, 0, 'Starting...')

        # Create safe output name from title
        output_name = "".join(c if c.isalnum() or c in ' -_' else '' for c in title)
        output_name = output_name.replace(' ', '_')
        if not output_name:
            output_name = f"songbook_{job_id}"

        # Step 1: Get CSV (either from VSB conversion or direct CSV input)
        csv_path = os.path.join(BASE_DIR, f'temp_{job_id}.csv')
        ext = input_path.rsplit('.', 1)[1].lower() if '.' in input_path else ''

        if ext == 'csv':
            set_status(True, 10, 'Reading CSV...')
            import shutil
            shutil.copy(input_path, csv_path)
            with open(csv_path, 'r', encoding='utf-8') as f:
                song_count = max(0, sum(1 for _ in f) - 1)
        else:
            set_status(True, 10, 'Reading database...')
            song_count = convert_mdb_to_csv(input_path, csv_path)

        set_status(True, 30, f'Found {song_count} songs. Generating PDF...')

        # Step 2: Generate PDF
        set_status(True, 40, 'Building table of contents...')

        # Copy to expected location for generator
        expected_csv = os.path.join(BASE_DIR, 'songs.csv')
        import shutil
        shutil.copy(csv_path, expected_csv)

        set_status(True, 50, 'Pass 1: Calculating page numbers...')

        # Run the generator
        sys.path.insert(0, BASE_DIR)
        from generate_pdf import generate_songbook_pdf

        generate_songbook_pdf(output_name, page_format=page_format,
                              cover_theme=cover_theme,
                              cover_subtitle=cover_subtitle,
                              cover_footer=cover_footer)

        set_status(True, 90, 'Finalizing PDF...')

        # Verify output exists
        output_pdf = os.path.join(OUTPUT_FOLDER, f"{output_name}.pdf")
        if not os.path.exists(output_pdf):
            raise Exception(f"PDF was not generated: {output_pdf}")

        # Cleanup
        set_status(True, 95, 'Cleaning up...')

        # Remove temp files
        if os.path.exists(csv_path):
            os.remove(csv_path)
        if os.path.exists(input_path):
            os.remove(input_path)

        # Remove temp PDFs
        for temp_file in ['temp_pass1.pdf', 'temp_content.pdf']:
            temp_path = os.path.join(OUTPUT_FOLDER, temp_file)
            if os.path.exists(temp_path):
                os.remove(temp_path)

        # Done!
        pdf_filename = f"{output_name}.pdf"
        set_status(False, 100, 'Done!', result=pdf_filename)

    except Exception as e:
        error_msg = f"Error: {str(e)}"
        set_status(False, 0, '', error=error_msg)
        traceback.print_exc()

        # Cleanup temp files on failure
        for path in [
            os.path.join(BASE_DIR, f'temp_{job_id}.csv'),
            input_path,
            os.path.join(BASE_DIR, 'songs.csv'),
        ]:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass
        for temp_file in ['temp_pass1.pdf', 'temp_content.pdf']:
            try:
                temp_path = os.path.join(OUTPUT_FOLDER, temp_file)
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except OSError:
                pass

if __name__ == '__main__':
    if len(sys.argv) < 4:
        print("Usage: worker.py <input_path> <title> <job_id>")
        sys.exit(1)

    input_path = sys.argv[1]
    title = sys.argv[2]
    job_id = sys.argv[3]
    page_format = sys.argv[4] if len(sys.argv) > 4 else 'a5'
    cover_theme = sys.argv[5] if len(sys.argv) > 5 else 'classic'
    cover_subtitle = sys.argv[6] if len(sys.argv) > 6 and sys.argv[6] else None
    cover_footer = sys.argv[7] if len(sys.argv) > 7 and sys.argv[7] else None

    run_worker(input_path, title, job_id, page_format=page_format,
               cover_theme=cover_theme,
               cover_subtitle=cover_subtitle,
               cover_footer=cover_footer)
