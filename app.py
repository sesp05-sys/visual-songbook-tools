#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VSB/MDB til PDF Sangbok Generator - Web Service
"""

import os
import json
import uuid
import subprocess
import csv
import io
import fcntl
from datetime import datetime
from flask import Flask, request, jsonify, send_file, render_template_string
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 MB max

APP_VERSION = '3.1.0'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
OUTPUT_FOLDER = os.path.join(BASE_DIR, 'output')
STATUS_FILE = os.path.join(BASE_DIR, 'job_status.json')

ALLOWED_EXTENSIONS = {'vsb', 'mdb'}
ALLOWED_CSV_EXTENSIONS = {'csv'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def allowed_csv_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_CSV_EXTENSIONS

def get_status():
    try:
        with open(STATUS_FILE, 'r') as f:
            status = json.load(f)
        # Stale job recovery: if running but started > 10 min ago, consider it dead
        if status.get('running') and status.get('started_at'):
            elapsed = datetime.now().timestamp() - status['started_at']
            if elapsed > 600:
                status['running'] = False
                status['error'] = 'Job timed out (no response for 10 minutes)'
                set_status(status)
        return status
    except (json.JSONDecodeError, IOError):
        return {'running': False, 'progress': 0, 'message': '', 'error': None, 'result': None}

def set_status(status):
    with open(STATUS_FILE, 'w') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        json.dump(status, f)
        f.flush()
        fcntl.flock(f, fcntl.LOCK_UN)

# Ensure directories exist (runs under gunicorn too)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# HTML Template
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="version" content="{{ v }}">
    <title>Visual Songbook Tools</title>
    <style>
        :root {
            --bg: #0f1117; --bg-card: #161b22; --bg-input: #0d1117;
            --border: #21262d; --border-light: #30363d;
            --text: #e1e4e8; --text-secondary: #8b949e; --text-muted: #484f58;
            --accent: #58a6ff; --accent-bg: rgba(56,139,253,0.1);
            --green: #238636; --green-hover: #2ea043; --green-text: #3fb950;
            --blue: #1f6feb; --blue-hover: #388bfd;
            --red: #f85149; --red-bg: rgba(248,81,73,0.1);
            --shadow: rgba(0,0,0,0.4);
        }
        [data-theme="light"] {
            --bg: #e8ecf0; --bg-card: #f0f3f6; --bg-input: #e2e6ea;
            --border: #bbc0c7; --border-light: #c5cad1;
            --text: #1f2328; --text-secondary: #505860; --text-muted: #6e7781;
            --accent: #0550ae; --accent-bg: rgba(5,80,174,0.1);
            --green: #1a7f37; --green-hover: #2da44e; --green-text: #1a7f37;
            --blue: #0550ae; --blue-hover: #0969da;
            --red: #cf222e; --red-bg: rgba(207,34,46,0.1);
            --shadow: rgba(0,0,0,0.12);
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg);
            min-height: 100vh;
            color: var(--text);
        }
        .header {
            border-bottom: 1px solid var(--border);
            padding: 14px 0;
            position: sticky;
            top: 0;
            background: var(--bg);
            z-index: 100;
            margin-bottom: 24px;
        }
        .header-inner {
            max-width: 1200px;
            margin: 0 auto;
            padding: 0 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .header h1 { font-size: 1.2em; font-weight: 600; letter-spacing: -0.02em; }
        .header h1 a { color: var(--text); text-decoration: none; }
        .header h1 a:hover { color: var(--accent); }
        .header-github {
            flex: 1;
            text-align: center;
            color: var(--text-secondary);
            text-decoration: none;
            font-size: 13px;
            transition: color 0.15s;
        }
        .header-github:hover { color: var(--accent); }
        @media (max-width: 720px) { .header-github { display: none; } }
        .header-nav { display: flex; gap: 8px; align-items: center; }
        .header-nav a {
            color: var(--text-secondary);
            text-decoration: none;
            font-size: 13px;
            padding: 6px 12px;
            border-radius: 6px;
            transition: all 0.15s;
        }
        .header-nav a:hover { color: var(--text); background: var(--bg-card); }
        .header-nav a.active { color: var(--accent); background: var(--accent-bg); }
        .theme-toggle {
            background: none; border: none; color: var(--text-secondary);
            cursor: pointer; font-size: 18px; padding: 4px 8px; border-radius: 4px; width: auto;
            box-shadow: none;
        }
        .theme-toggle:hover { color: var(--text); background: var(--accent-bg); }
        .header p {
            color: var(--text-secondary);
            margin-top: 4px;
            font-size: 14px;
        }
        .main {
            max-width: 1200px;
            margin: 0 auto;
            padding: 0 24px 60px;
        }
        .grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }
        @media (max-width: 720px) {
            .grid { grid-template-columns: 1fr; }
        }
        .card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 24px;
            transition: box-shadow 0.3s ease, border-color 0.3s ease;
        }
        .card:hover {
            border-color: var(--border-light);
            box-shadow: 0 4px 20px var(--shadow);
        }
        .card-full { grid-column: 1 / -1; }
        .card h2 {
            font-size: 15px;
            font-weight: 600;
            margin-bottom: 4px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .card h2 .icon { font-size: 18px; }
        .card .desc {
            color: var(--text-secondary);
            font-size: 13px;
            margin-bottom: 16px;
            line-height: 1.5;
        }
        .drop-zone {
            border: 1px dashed var(--border-light);
            border-radius: 8px;
            padding: 28px 16px;
            text-align: center;
            cursor: pointer;
            transition: all 0.2s;
            margin-bottom: 16px;
        }
        .drop-zone:hover, .drop-zone.dragover {
            border-color: var(--accent);
            background: var(--accent-bg);
        }
        .drop-zone.has-file {
            border-color: var(--green-text);
            background: rgba(63,185,80,0.06);
        }
        .drop-zone input[type="file"] { display: none; }
        .drop-zone-text { color: var(--text-secondary); font-size: 13px; }
        .filename {
            color: var(--green-text);
            font-weight: 500;
            margin-top: 8px;
            word-break: break-all;
            font-size: 13px;
        }
        label {
            display: block;
            margin-bottom: 6px;
            color: var(--text-secondary);
            font-size: 13px;
            font-weight: 500;
        }
        input[type="text"] {
            width: 100%;
            padding: 8px 12px;
            border: 1px solid var(--border-light);
            border-radius: 6px;
            background: var(--bg-input);
            color: var(--text);
            font-size: 14px;
            margin-bottom: 12px;
        }
        input[type="text"]:focus {
            outline: none;
            border-color: var(--accent);
            box-shadow: 0 0 0 3px rgba(56,139,253,0.15);
        }
        button {
            width: 100%;
            padding: 10px 16px;
            background: linear-gradient(135deg, var(--green), var(--green-hover));
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.25s ease;
            box-shadow: 0 2px 8px rgba(0,0,0,0.15);
            position: relative;
            overflow: hidden;
        }
        button:hover:not(:disabled) {
            transform: translateY(-1px);
            box-shadow: 0 4px 16px rgba(0,0,0,0.25);
            filter: brightness(1.1);
        }
        button:active:not(:disabled) { transform: translateY(0); box-shadow: 0 1px 4px rgba(0,0,0,0.15); }
        button:disabled {
            background: var(--border);
            color: var(--text-muted);
            cursor: not-allowed;
            box-shadow: none;
            transform: none;
            filter: none;
        }
        .btn-row { display: flex; gap: 8px; }
        .btn-row button { flex: 1; }
        .btn-secondary {
            background: linear-gradient(135deg, var(--bg-card), var(--border));
            color: var(--text);
            border: 1px solid var(--border-light);
            box-shadow: 0 1px 4px rgba(0,0,0,0.1);
        }
        .btn-secondary:hover:not(:disabled) { filter: brightness(1.15); }
        .btn-blue {
            background: linear-gradient(135deg, var(--blue), var(--blue-hover));
        }
        .btn-blue:hover:not(:disabled) { filter: brightness(1.15); }
        .progress-container {
            display: none;
            margin-top: 16px;
        }
        .progress-bar {
            height: 8px;
            background: var(--border);
            border-radius: 4px;
            overflow: hidden;
            margin-bottom: 8px;
        }
        .progress-fill {
            height: 100%;
            background: var(--green-text);
            width: 0%;
            transition: width 0.3s;
            border-radius: 4px;
        }
        .progress-text {
            text-align: center;
            color: var(--text-secondary);
            font-size: 13px;
        }
        .result {
            display: none;
            padding: 12px 16px;
            border-radius: 8px;
            margin-top: 16px;
            font-size: 14px;
            font-weight: 500;
        }
        .result.success {
            color: var(--green-text);
            background: rgba(63,185,80,0.08);
            border: 1px solid rgba(63,185,80,0.3);
        }
        .result.error {
            color: var(--red);
            background: rgba(248,81,73,0.08);
            border: 1px solid rgba(248,81,73,0.3);
        }
        .download-btn {
            display: inline-block;
            padding: 6px 16px;
            background: var(--green-text);
            text-decoration: none;
            border-radius: 6px;
            color: var(--bg);
            font-size: 13px;
            font-weight: 600;
            transition: all 0.2s ease;
        }
        .download-btn:hover { filter: brightness(1.1); transform: translateY(-1px); }
        .format-btn {
            flex: 1;
            padding: 8px;
            background: var(--bg-input);
            border: 1px solid var(--border-light);
            color: var(--text-secondary);
            border-radius: 8px;
            cursor: pointer;
            font-size: 13px;
            transition: all 0.25s ease;
            box-shadow: none;
        }
        .format-btn:hover { border-color: var(--accent); color: var(--text); transform: translateY(-1px); }
        .format-btn.active {
            background: linear-gradient(135deg, var(--accent-bg), rgba(56,139,253,0.18));
            border-color: var(--accent);
            color: var(--accent);
            box-shadow: 0 2px 8px rgba(56,139,253,0.15);
        }
        .merge-list {
            list-style: none;
            padding: 0;
            margin: 0 0 12px 0;
        }
        .merge-item {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 8px 12px;
            margin-bottom: 4px;
            background: var(--bg-input);
            border: 1px solid var(--border);
            border-radius: 6px;
            cursor: grab;
            user-select: none;
            font-size: 13px;
        }
        .merge-item:active { cursor: grabbing; }
        .merge-item.drag-over {
            border-color: var(--accent);
            background: rgba(56,139,253,0.06);
        }
        .merge-item .num {
            background: var(--blue);
            color: #fff;
            width: 22px;
            height: 22px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 11px;
            font-weight: 600;
            flex-shrink: 0;
        }
        .merge-item .name { flex: 1; word-break: break-all; }
        .merge-item .remove-btn {
            background: none;
            border: none;
            color: var(--red);
            cursor: pointer;
            font-size: 16px;
            padding: 0 4px;
            width: auto;
        }
        .merge-item .remove-btn:hover { color: var(--red); }
        .merge-hint { color: var(--text-secondary); font-size: 12px; text-align: center; margin-bottom: 12px; }
        .mapping-row {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 6px;
        }
        .mapping-row .csv-col {
            flex: 1;
            padding: 6px 8px;
            background: var(--bg-input);
            border: 1px solid var(--border);
            border-radius: 4px;
            font-size: 13px;
            color: var(--text);
        }
        .mapping-row .arrow { color: var(--text-muted); flex-shrink: 0; font-size: 12px; }
        .mapping-row select {
            flex: 1;
            padding: 6px 8px;
            background: var(--bg-input);
            border: 1px solid var(--border);
            border-radius: 4px;
            color: var(--text);
            font-size: 13px;
        }
        .mapping-row select option { background: var(--bg-card); }
        .mapping-ok { border-color: var(--green-text) !important; }
        .mapping-missing { border-color: var(--red) !important; }
        .csv-preview-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 12px;
            margin-top: 8px;
        }
        .csv-preview-table th {
            background: rgba(56,139,253,0.08);
            padding: 6px 8px;
            text-align: left;
            border-bottom: 1px solid var(--border);
            color: var(--text-secondary);
            font-weight: 500;
        }
        .csv-preview-table td {
            padding: 4px 8px;
            border-bottom: 1px solid var(--bg-card);
            color: var(--text-secondary);
            max-width: 180px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .tab-bar {
            display: flex;
            gap: 0;
            margin-bottom: 16px;
            border-bottom: 1px solid var(--border);
        }
        .tab {
            flex: 1;
            padding: 8px 12px;
            background: none;
            border: none;
            border-bottom: 2px solid transparent;
            color: var(--text-secondary);
            font-size: 13px;
            font-weight: 500;
            cursor: pointer;
            border-radius: 0;
            transition: all 0.15s;
        }
        .tab:hover { color: var(--text); }
        .tab.active {
            color: var(--accent);
            border-bottom-color: var(--accent);
        }
        .tab:disabled { background: none; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }

        body.modal-open { overflow: hidden; }
        body.modal-open .toolbar,
        body.modal-open .empty-state,
        body.modal-open .card { pointer-events: none; }
        body.modal-open .toolbar-btn,
        body.modal-open button,
        body.modal-open .toolbar-btn *,
        body.modal-open button * { animation: none !important; transition: none !important; }
        body.modal-open .toolbar-btn:hover,
        body.modal-open button:hover { transform: none !important; box-shadow: none !important; filter: none !important; }
        body.modal-open .spinner { display: none !important; }
        /* Busy modal's own spinner must keep rotating */
        body.modal-open .busy-spinner { animation: spin 0.8s linear infinite !important; border-top-color: var(--accent) !important; }

        @keyframes spin { to { transform: rotate(360deg); } }
        .spinner {
            display: inline-block;
            width: 14px;
            height: 14px;
            border: 2px solid rgba(255,255,255,0.3);
            border-top-color: #fff;
            border-radius: 50%;
            animation: spin 0.6s linear infinite;
            vertical-align: middle;
            margin-right: 6px;
        }
        .busy-overlay {
            display: none;
            position: fixed;
            inset: 0;
            background: rgba(0,0,0,0.55);
            z-index: 9999;
            justify-content: center;
            align-items: center;
            backdrop-filter: blur(2px);
        }
        .busy-overlay.show { display: flex; }
        .busy-modal {
            background: var(--bg-card);
            border: 1px solid var(--border-light);
            border-radius: 14px;
            padding: 32px 40px;
            box-shadow: 0 20px 50px rgba(0,0,0,0.5);
            text-align: center;
            min-width: 280px;
        }
        .busy-spinner {
            width: 42px;
            height: 42px;
            border: 3px solid var(--border);
            border-top-color: var(--accent);
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
            margin: 0 auto 16px;
        }
        .busy-title { font-size: 15px; font-weight: 600; color: var(--text); margin-bottom: 4px; }
        .busy-sub { font-size: 13px; color: var(--text-secondary); }
        .divider { border-top: 1px solid var(--border); margin: 20px 0; }
        .footer {
            text-align: center;
            color: var(--text-muted);
            font-size: 12px;
            padding: 32px 0;
        }
        .footer a { color: var(--accent); text-decoration: none; }
    </style>
</head>
<body>
    <div class="busy-overlay" id="busyOverlay">
        <div class="busy-modal">
            <div class="busy-spinner" id="busySpinner"></div>
            <div class="busy-title" id="busyTitle">Working...</div>
            <div class="busy-sub" id="busySub">Patience &mdash; this may take some time!</div>
            <div id="busyProgress" style="display:none;margin-top:18px;">
                <div style="height:8px;background:var(--border);border-radius:4px;overflow:hidden;">
                    <div id="busyProgressFill" style="height:100%;background:var(--accent);width:0%;transition:width 0.3s ease;border-radius:4px;"></div>
                </div>
            </div>
        </div>
    </div>

    <div class="header">
        <div class="header-inner">
            <h1><a href="/">Visual Songbook Tools</a></h1>
            <a href="https://github.com/sesp05-sys/visual-songbook-tools" target="_blank" class="header-github">Source on GitHub</a>
            <div class="header-nav">
                <a href="/" class="active">Convert</a>
                <a href="/editor">Editor</a>
                <button class="theme-toggle" onclick="toggleTheme()" id="themeBtnConv">&#x2600;</button>
            </div>
        </div>
    </div>

    <div class="main">
        <div class="grid">

            <!-- Generate PDF -->
            <div class="card">
                <h2><span class="icon">&#x1F4D6;</span> Generate PDF</h2>
                <div class="desc">Upload a songbook (VSB, CSV or JSON) and generate a print-ready PDF.</div>
                <form id="uploadForm">
                    <div class="drop-zone" id="dropZone">
                        <div class="drop-zone-text" id="dropText">Drop .vsb, .csv or .json file here</div>
                        <div class="filename" id="fileName"></div>
                        <input type="file" id="fileInput" accept=".vsb,.mdb,.csv,.json">
                    </div>
                    <label for="title">Title</label>
                    <input type="text" id="title" name="title" placeholder="e.g. My Church Songbook">
                    <label for="coverSubtitle">Subtitle <span style="color:var(--text-muted);font-weight:400;">(optional)</span></label>
                    <input type="text" id="coverSubtitle" placeholder="e.g. A collection of hymns">
                    <label for="coverFooter">Cover footer <span style="color:var(--text-muted);font-weight:400;">(optional)</span></label>
                    <input type="text" id="coverFooter" placeholder="e.g. 2026 Edition">
                    <label>Page size</label>
                    <div class="btn-row" style="margin-bottom: 12px;">
                        <button type="button" class="format-btn active" data-format="a5" onclick="setFormat('a5')">A5</button>
                        <button type="button" class="format-btn" data-format="halfletter" onclick="setFormat('halfletter')">Half Letter</button>
                    </div>
                    <button type="submit" id="submitBtn" disabled>Generate PDF</button>
                </form>
                <div class="progress-container" id="progressContainer">
                    <div class="progress-bar"><div class="progress-fill" id="progressFill"></div></div>
                    <div class="progress-text" id="progressText"></div>
                </div>
                <div class="result" id="result"></div>
            </div>

            <!-- Convert -->
            <div class="card">
                <h2><span class="icon">&#x1F504;</span> Convert</h2>
                <div class="desc">Drop any songbook file. Automatically detects the format and lets you convert to anything else.</div>
                <div class="drop-zone" id="convDropZone">
                    <div class="drop-zone-text">Drop .vsb, .csv or .json file here</div>
                    <div class="filename" id="convFileName"></div>
                    <input type="file" id="convFileInput" accept=".vsb,.mdb,.csv,.json">
                </div>
                <div id="convFormat" style="display:none;color:var(--text-secondary);font-size:13px;margin-bottom:12px;text-align:center;">
                    Detected: <strong id="convDetected"></strong> &middot; <span id="convSongCount"></span>
                </div>
                <div id="convTargets" style="display:none;">
                    <label style="margin-bottom:8px;">Convert to:</label>
                    <div class="btn-row">
                        <button type="button" class="btn-blue" data-target="vsb" onclick="convertTo('vsb')">VSB</button>
                        <button type="button" class="btn-blue" data-target="csv" onclick="convertTo('csv')">CSV</button>
                        <button type="button" class="btn-blue" data-target="json" onclick="convertTo('json')">JSON</button>
                    </div>
                </div>
            </div>

            <!-- Merge -->
            <div class="card card-full">
                <h2><span class="icon">&#x1F500;</span> Merge Songbooks</h2>
                <div class="desc">Combine multiple VSB files into one. Drag to set the order &mdash; song numbering continues sequentially.</div>
                <div class="drop-zone" id="mergeDropZone">
                    <div class="drop-zone-text" id="mergeDropText">Drop .vsb files here</div>
                    <input type="file" id="mergeFileInput" accept=".vsb,.mdb" multiple>
                </div>
                <div class="merge-hint" id="mergeHint" style="display:none;">Drag to reorder.</div>
                <ul class="merge-list" id="mergeList"></ul>
                <div id="mergeOptions" style="display:none;margin-bottom:12px;padding:12px;background:var(--bg-input);border:1px solid var(--border);border-radius:8px;">
                    <label style="display:flex;align-items:center;gap:8px;font-size:13px;cursor:pointer;margin-bottom:6px;">
                        <input type="checkbox" id="mergeRenumber" onchange="toggleRenumber()">
                        Renumber sequentially
                    </label>
                    <div id="mergeStartRow" style="display:none;align-items:center;gap:8px;font-size:13px;margin-top:8px;">
                        <label for="mergeStartNum">Start at:</label>
                        <input type="number" id="mergeStartNum" value="1" min="1" style="width:80px;padding:4px 8px;border:1px solid var(--border-light);border-radius:4px;background:var(--bg);color:var(--text);">
                    </div>
                    <div id="mergeKeepHint" style="font-size:12px;color:var(--text-secondary);margin-top:4px;">Each book keeps its numbers; later books continue after the previous book's last number.</div>
                </div>
                <button type="button" id="mergeBtn" class="btn-blue" disabled onclick="mergeVsb()">Merge to VSB</button>
            </div>

        </div>
        <div class="footer">
            Supported formats: <strong>.vsb</strong> (Visual Songbook) &middot; <strong>.csv</strong> &middot; <strong>.json</strong>
        </div>
    </div>

    <script>
        // Theme
        function toggleTheme() {
            const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
            document.documentElement.setAttribute('data-theme', isDark ? 'light' : 'dark');
            localStorage.setItem('theme', isDark ? 'light' : 'dark');
            document.getElementById('themeBtnConv').innerHTML = isDark ? '&#x1F319;' : '&#x2600;';
        }
        (function() {
            const saved = localStorage.getItem('theme') || (window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
            if (saved === 'light') document.documentElement.setAttribute('data-theme', 'light');
            document.getElementById('themeBtnConv').innerHTML = saved === 'light' ? '&#x1F319;' : '&#x2600;';
        })();

        // Button loading helpers
        const SPIN = '<span class="spinner"></span>';
        function btnLoading(btn, text) { btn.disabled = true; btn.dataset.origText = btn.textContent; btn.innerHTML = SPIN + text; }
        function btnReset(btn, text) { btn.disabled = false; btn.innerHTML = text; }

        function showBusy(title, sub) {
            document.getElementById('busyTitle').textContent = title || 'Working...';
            document.getElementById('busySub').textContent = sub || 'Patience — this may take some time!';
            document.getElementById('busyOverlay').classList.add('show');
            document.body.classList.add('modal-open');
            document.getElementById('busySpinner').style.display = '';
            document.getElementById('busyProgress').style.display = 'none';
        }
        function setBusyProgress(percent, message) {
            document.getElementById('busySpinner').style.display = 'none';
            document.getElementById('busyProgress').style.display = 'block';
            document.getElementById('busyProgressFill').style.width = (percent || 0) + '%';
            if (message) document.getElementById('busySub').textContent = message;
        }
        function hideBusy() {
            document.getElementById('busyOverlay').classList.remove('show');
            document.body.classList.remove('modal-open');
            document.getElementById('busySpinner').style.display = '';
            document.getElementById('busyProgress').style.display = 'none';
        }

        // Upload with progress tracking
        function uploadWithProgress(url, formData, onProgress) {
            return new Promise((resolve, reject) => {
                const xhr = new XMLHttpRequest();
                xhr.upload.onprogress = (e) => {
                    if (e.lengthComputable && onProgress) {
                        onProgress(Math.round((e.loaded / e.total) * 100));
                    }
                };
                xhr.onload = () => {
                    try {
                        const data = JSON.parse(xhr.responseText);
                        resolve({ ok: xhr.status >= 200 && xhr.status < 300, status: xhr.status, data });
                    } catch (e) {
                        resolve({ ok: false, status: xhr.status, data: { error: 'Invalid response' } });
                    }
                };
                xhr.onerror = () => reject(new Error('Network error'));
                xhr.open('POST', url);
                xhr.send(formData);
            });
        }

        // ====== Generic file converter ======
        let convFile = null;
        let convSongs = null;
        const convDropZone = document.getElementById('convDropZone');
        const convFileInput = document.getElementById('convFileInput');

        convDropZone.addEventListener('click', () => convFileInput.click());
        convDropZone.addEventListener('dragover', e => { e.preventDefault(); convDropZone.classList.add('dragover'); });
        convDropZone.addEventListener('dragleave', () => convDropZone.classList.remove('dragover'));
        convDropZone.addEventListener('drop', e => {
            e.preventDefault();
            convDropZone.classList.remove('dragover');
            if (e.dataTransfer.files[0]) handleConvFile(e.dataTransfer.files[0]);
        });
        convFileInput.addEventListener('change', e => { if (e.target.files[0]) handleConvFile(e.target.files[0]); });

        function detectFormat(name) {
            const ext = name.split('.').pop().toLowerCase();
            if (ext === 'vsb' || ext === 'mdb') return 'vsb';
            if (ext === 'csv') return 'csv';
            if (ext === 'json') return 'json';
            return null;
        }

        async function handleConvFile(file) {
            const fmt = detectFormat(file.name);
            if (!fmt) { alert('Unsupported file type. Use .vsb, .csv or .json'); return; }
            convFile = file;
            convSongs = null;
            document.getElementById('convFileName').textContent = file.name;
            convDropZone.classList.add('has-file');
            document.getElementById('convFormat').style.display = 'block';
            document.getElementById('convDetected').textContent = fmt.toUpperCase();
            document.getElementById('convSongCount').textContent = 'loading...';
            document.getElementById('convTargets').style.display = 'block';

            // Load songs via editor import (universal parser)
            try {
                const fd = new FormData();
                fd.append('file', file);
                const resp = await fetch('/api/editor/import', { method: 'POST', body: fd });
                const data = await resp.json();
                if (data.error) { alert(data.error); return; }
                convSongs = data.songs;
                document.getElementById('convSongCount').textContent = convSongs.length + ' songs';

                // Disable button matching the source format
                document.querySelectorAll('#convTargets button').forEach(b => {
                    b.disabled = (b.dataset.target === fmt);
                });
            } catch (err) {
                alert('Failed to load file: ' + err.message);
            }
        }

        async function convertTo(target) {
            if (!convSongs) return;
            const btn = document.querySelector('#convTargets button[data-target="' + target + '"]');
            const orig = btn.textContent;
            btnLoading(btn, '...');
            showBusy('Converting to ' + target.toUpperCase(), 'Patience — this may take some time!');
            try {
                const resp = await fetch('/api/editor/export/' + target, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ songs: convSongs })
                });
                if (!resp.ok) {
                    const d = await resp.json();
                    alert(d.error || 'Conversion failed');
                    return;
                }
                const blob = await resp.blob();
                const a = document.createElement('a');
                a.href = window.URL.createObjectURL(blob);
                a.download = convFile.name.replace(/\.[^.]+$/, '.' + target);
                document.body.appendChild(a); a.click();
                window.URL.revokeObjectURL(a.href); a.remove();
            } catch (err) {
                alert('Network error: ' + err.message);
            }
            btnReset(btn, orig);
            hideBusy();
        }

        // Merge functionality
        const mergeDropZone = document.getElementById('mergeDropZone');
        const mergeFileInput = document.getElementById('mergeFileInput');
        const mergeList = document.getElementById('mergeList');
        const mergeHint = document.getElementById('mergeHint');
        let mergeFiles = []; // {file, name}

        mergeDropZone.addEventListener('click', () => mergeFileInput.click());
        mergeDropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            mergeDropZone.classList.add('dragover');
        });
        mergeDropZone.addEventListener('dragleave', () => mergeDropZone.classList.remove('dragover'));
        mergeDropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            mergeDropZone.classList.remove('dragover');
            addMergeFiles(e.dataTransfer.files);
        });
        mergeFileInput.addEventListener('change', (e) => {
            addMergeFiles(e.target.files);
            mergeFileInput.value = '';
        });

        function addMergeFiles(files) {
            for (const f of files) {
                if (f.name.match(/\.(vsb|mdb|csv|json)$/i)) {
                    mergeFiles.push({file: f, name: f.name});
                }
            }
            renderMergeList();
        }

        function renderMergeList() {
            mergeList.innerHTML = '';
            mergeHint.style.display = mergeFiles.length > 1 ? 'block' : 'none';
            document.getElementById('mergeOptions').style.display = mergeFiles.length >= 2 ? 'block' : 'none';
            document.getElementById('mergeBtn').disabled = mergeFiles.length < 2;

            mergeFiles.forEach((item, idx) => {
                const li = document.createElement('li');
                li.className = 'merge-item';
                li.draggable = true;
                li.dataset.idx = idx;
                li.innerHTML = `
                    <span class="num">${idx + 1}</span>
                    <span class="name">${item.name}</span>
                    <button class="remove-btn" onclick="removeMergeFile(${idx})">&times;</button>
                `;

                li.addEventListener('dragstart', (e) => {
                    e.dataTransfer.setData('text/plain', idx);
                    li.style.opacity = '0.5';
                });
                li.addEventListener('dragend', () => { li.style.opacity = '1'; });
                li.addEventListener('dragover', (e) => {
                    e.preventDefault();
                    li.classList.add('drag-over');
                });
                li.addEventListener('dragleave', () => li.classList.remove('drag-over'));
                li.addEventListener('drop', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    li.classList.remove('drag-over');
                    const fromIdx = parseInt(e.dataTransfer.getData('text/plain'));
                    const toIdx = idx;
                    if (fromIdx !== toIdx) {
                        const [moved] = mergeFiles.splice(fromIdx, 1);
                        mergeFiles.splice(toIdx, 0, moved);
                        renderMergeList();
                    }
                });

                mergeList.appendChild(li);
            });
        }

        function removeMergeFile(idx) {
            mergeFiles.splice(idx, 1);
            renderMergeList();
        }

        function toggleRenumber() {
            const checked = document.getElementById('mergeRenumber').checked;
            document.getElementById('mergeStartRow').style.display = checked ? 'flex' : 'none';
            document.getElementById('mergeKeepHint').style.display = checked ? 'none' : 'block';
        }

        async function mergeVsb() {
            if (mergeFiles.length < 2) {
                alert('Add at least 2 files');
                return;
            }
            const btn = document.getElementById('mergeBtn');
            btnLoading(btn, 'Merging...');
            showBusy('Merging songbooks', 'Patience — this may take some time!');

            const renumber = document.getElementById('mergeRenumber').checked;
            const startNum = parseInt(document.getElementById('mergeStartNum').value) || 1;

            const formData = new FormData();
            mergeFiles.forEach((item, idx) => {
                formData.append('files', item.file);
            });
            formData.append('renumber', renumber ? '1' : '0');
            formData.append('start_num', String(startNum));

            try {
                const response = await fetch('/api/merge-vsb', {
                    method: 'POST',
                    body: formData
                });
                if (response.ok) {
                    const blob = await response.blob();
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = 'merged_songbook.vsb';
                    document.body.appendChild(a);
                    a.click();
                    window.URL.revokeObjectURL(url);
                    a.remove();
                } else {
                    const data = await response.json();
                    alert(data.error || 'Unknown error');
                }
            } catch (err) {
                alert('Network error: ' + err.message);
            }
            btnReset(btn, 'Merge to VSB');
            hideBusy();
        }

        // ====== Generate PDF card ======
        const dropZone = document.getElementById('dropZone');
        const fileInput = document.getElementById('fileInput');
        const fileName = document.getElementById('fileName');
        const titleInput = document.getElementById('title');
        const submitBtn = document.getElementById('submitBtn');
        const form = document.getElementById('uploadForm');
        const progressContainer = document.getElementById('progressContainer');
        const progressFill = document.getElementById('progressFill');
        const progressText = document.getElementById('progressText');
        const result = document.getElementById('result');
        let selectedFile = null;
        let selectedFormat = 'a5';

        function setFormat(fmt) {
            selectedFormat = fmt;
            document.querySelectorAll('.format-btn[data-format]').forEach(b => {
                b.classList.toggle('active', b.dataset.format === fmt);
            });
        }

        function showError(message) {
            hideBusy();
            progressContainer.style.display = 'none';
            result.className = 'result error';
            result.style.display = 'block';
            result.innerHTML = '<div style="display:flex;align-items:center;gap:10px;justify-content:center;"><span style="font-size:18px;">&#x26A0;</span><span>' + message + '</span></div>';
            btnReset(submitBtn, 'Generate PDF');
        }

        function showSuccess(filename) {
            hideBusy();
            progressContainer.style.display = 'none';
            result.className = 'result success';
            result.style.display = 'block';
            result.innerHTML = '<div style="display:flex;align-items:center;gap:10px;justify-content:center;flex-wrap:wrap;"><span>PDF ready</span><a href="/api/download/' + filename + '" class="download-btn">Download</a></div>';
            btnReset(submitBtn, 'Generate PDF');
        }

        function pollProgress() {
            fetch('/api/progress').then(r => r.json()).then(data => {
                setBusyProgress(data.progress || 0, data.message || 'Working...');
                if (data.error) showError(data.error);
                else if (!data.running && data.result) showSuccess(data.result);
                else if (data.running) setTimeout(pollProgress, 500);
            }).catch(() => setTimeout(pollProgress, 1000));
        }

        // Drag & drop
        dropZone.addEventListener('click', () => fileInput.click());
        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('dragover');
        });
        dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
            const file = e.dataTransfer.files[0];
            if (file && file.name.match(/\.(vsb|mdb|csv|json)$/i)) {
                handleFile(file);
            }
        });

        fileInput.addEventListener('change', (e) => {
            if (e.target.files[0]) handleFile(e.target.files[0]);
        });

        function handleFile(file) {
            selectedFile = file;
            fileName.textContent = file.name;
            dropZone.classList.add('has-file');

            // Auto-fill title from filename
            if (!titleInput.value) {
                const name = file.name.replace(/\.(vsb|mdb|csv|json)$/i, '');
                titleInput.value = name;
            }

            submitBtn.disabled = false;
        }

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            if (!selectedFile) return;

            btnLoading(submitBtn, 'Generating...');
            showBusy('Generating PDF', 'Patience — this may take some time!');
            progressContainer.style.display = 'none';
            result.style.display = 'none';

            const formData = new FormData();
            formData.append('file', selectedFile);
            formData.append('title', titleInput.value || selectedFile.name.replace(/\.(vsb|mdb|csv|json)$/i, ''));
            formData.append('page_format', selectedFormat);
            formData.append('cover_subtitle', document.getElementById('coverSubtitle').value);
            formData.append('cover_footer', document.getElementById('coverFooter').value);

            try {
                const response = await fetch('/api/upload', {
                    method: 'POST',
                    body: formData
                });

                const data = await response.json();

                if (data.started) {
                    pollProgress();
                } else {
                    showError(data.error || t('unknownError'));
                }
            } catch (err) {
                showError(t('networkError') + ': ' + err.message);
            }
        });

    </script>
</body>
</html>
'''

EDITOR_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="version" content="{{ v }}">
    <title>Song Editor - Visual Songbook Tools</title>
    <style>
        :root {
            --bg: #0f1117; --bg-card: #161b22; --bg-input: #0d1117;
            --border: #21262d; --border-light: #30363d;
            --text: #e1e4e8; --text-secondary: #8b949e; --text-muted: #484f58;
            --accent: #58a6ff; --accent-bg: rgba(56,139,253,0.1);
            --green: #238636; --green-hover: #2ea043; --green-text: #3fb950;
            --blue: #1f6feb; --blue-hover: #388bfd;
            --red: #f85149; --red-bg: rgba(248,81,73,0.1);
            --row-hover: rgba(56,139,253,0.04); --row-selected: rgba(56,139,253,0.1);
            --shadow: rgba(0,0,0,0.4);
        }
        [data-theme="light"] {
            --bg: #e8ecf0; --bg-card: #f0f3f6; --bg-input: #e2e6ea;
            --border: #bbc0c7; --border-light: #c5cad1;
            --text: #1f2328; --text-secondary: #505860; --text-muted: #6e7781;
            --accent: #0550ae; --accent-bg: rgba(5,80,174,0.1);
            --green: #1a7f37; --green-hover: #2da44e; --green-text: #1a7f37;
            --blue: #0550ae; --blue-hover: #0969da;
            --red: #cf222e; --red-bg: rgba(207,34,46,0.1);
            --row-hover: rgba(5,80,174,0.06); --row-selected: rgba(5,80,174,0.1);
            --shadow: rgba(0,0,0,0.12);
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg);
            min-height: 100vh;
            color: var(--text);
        }
        .header {
            border-bottom: 1px solid var(--border);
            padding: 14px 0;
            position: sticky;
            top: 0;
            background: var(--bg);
            z-index: 100;
        }
        .header-inner {
            max-width: 1200px;
            margin: 0 auto;
            padding: 0 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .header h1 { font-size: 1.2em; font-weight: 600; letter-spacing: -0.02em; }
        .header h1 a { color: var(--text); text-decoration: none; }
        .header h1 a:hover { color: var(--accent); }
        .header-github {
            flex: 1;
            text-align: center;
            color: var(--text-secondary);
            text-decoration: none;
            font-size: 13px;
            transition: color 0.15s;
        }
        .header-github:hover { color: var(--accent); }
        @media (max-width: 720px) { .header-github { display: none; } }
        .header-nav { display: flex; gap: 8px; align-items: center; }
        .header-nav a {
            color: var(--text-secondary);
            text-decoration: none;
            font-size: 13px;
            padding: 6px 12px;
            border-radius: 6px;
            transition: all 0.15s;
        }
        .header-nav a:hover { color: var(--text); background: var(--bg-card); }
        .header-nav a.active { color: var(--accent); background: var(--accent-bg); }

        .main {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px 24px 60px;
        }

        .toolbar {
            display: flex;
            gap: 8px;
            margin-bottom: 16px;
            flex-wrap: wrap;
            align-items: center;
            position: sticky;
            top: 50px;
            z-index: 90;
            background: var(--bg);
            padding: 12px 0;
        }
        .search-box { flex: 1; min-width: 200px; position: relative; }
        .search-box input {
            width: 100%;
            padding: 8px 12px 8px 34px;
            border: 1px solid var(--border-light);
            border-radius: 6px;
            background: var(--bg-input);
            color: var(--text);
            font-size: 14px;
        }
        .search-box input:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px rgba(56,139,253,0.15); }
        .search-box::before {
            content: '\\1F50D';
            position: absolute; left: 10px; top: 50%; transform: translateY(-50%);
            font-size: 14px; opacity: 0.5;
        }
        .toolbar-btn {
            padding: 8px 14px;
            border: 1px solid var(--border-light);
            border-radius: 8px;
            background: linear-gradient(135deg, var(--bg-card), var(--border));
            color: var(--text);
            font-size: 13px; font-weight: 500;
            cursor: pointer; transition: all 0.25s ease; white-space: nowrap;
            box-shadow: 0 1px 4px rgba(0,0,0,0.1);
        }
        .toolbar-btn:hover { transform: translateY(-1px); box-shadow: 0 3px 12px rgba(0,0,0,0.2); filter: brightness(1.1); }
        .toolbar-btn:active { transform: translateY(0); box-shadow: 0 1px 4px rgba(0,0,0,0.1); }
        .toolbar-btn.primary {
            background: linear-gradient(135deg, var(--green), var(--green-hover));
            border: none; color: #fff;
            box-shadow: 0 2px 8px rgba(0,0,0,0.15);
        }
        .toolbar-btn.primary:hover { box-shadow: 0 4px 16px rgba(35,134,54,0.35); }
        .toolbar-btn.blue {
            background: linear-gradient(135deg, var(--blue), var(--blue-hover));
            border: none; color: #fff;
            box-shadow: 0 2px 8px rgba(0,0,0,0.15);
        }
        .toolbar-btn.blue:hover { box-shadow: 0 4px 16px rgba(31,111,235,0.35); }

        .stats { display: flex; gap: 16px; margin-bottom: 16px; color: var(--text-secondary); font-size: 13px; }
        .stats span { display: flex; align-items: center; gap: 4px; }
        .stats strong { color: var(--text); }

        .song-table-wrap { border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
        .song-table { width: 100%; border-collapse: collapse; font-size: 13px; }
        .song-table th {
            background: var(--bg-card); padding: 10px 12px; text-align: left;
            font-weight: 500; color: var(--text-secondary); border-bottom: 1px solid var(--border);
            cursor: pointer; user-select: none; white-space: nowrap;
        }
        .song-table th:hover { color: var(--text); }
        .song-table th .sort-icon { margin-left: 4px; font-size: 10px; }
        .song-table td { padding: 8px 12px; border-bottom: 1px solid var(--bg-card); vertical-align: top; }
        .song-table tr:hover td { background: var(--row-hover); }
        .song-table tr.selected td { background: var(--row-selected); }
        .song-table tr.selected:hover td { background: var(--row-selected); }
        .song-table .col-num { width: 60px; color: var(--text-secondary); }
        .song-table .col-title { font-weight: 500; }
        .song-table .col-key { width: 60px; color: var(--text-secondary); text-align: center; }
        .song-table .col-author { width: 180px; color: var(--text-secondary); }
        .song-table .col-actions { width: 80px; text-align: right; white-space: nowrap; }
        .song-table .col-preview { color: var(--text-muted); font-size: 12px; max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

        .action-btn {
            background: none; border: none; color: var(--text-secondary); cursor: pointer;
            padding: 4px 8px; border-radius: 6px; font-size: 13px; width: auto;
            transition: all 0.2s ease;
        }
        .action-btn:hover { color: var(--accent); background: var(--accent-bg); transform: scale(1.1); }
        .action-btn.delete:hover { color: var(--red); background: var(--red-bg); }

        .tab-bar { display: flex; gap: 0; border-bottom: 1px solid var(--border); }
        .tab {
            flex: 1; padding: 8px 12px; background: none; border: none;
            border-bottom: 2px solid transparent; color: var(--text-secondary);
            font-size: 13px; font-weight: 500; cursor: pointer; border-radius: 0; transition: all 0.15s;
        }
        .tab:hover { color: var(--text); }
        .tab.active { color: var(--accent); border-bottom-color: var(--accent); }
        .tab:disabled { background: none; }

        .empty-state { text-align: center; padding: 60px 20px; color: var(--text-muted); }
        .empty-state .icon { font-size: 48px; margin-bottom: 12px; }
        .empty-state p { margin-bottom: 16px; }

        .modal-overlay {
            display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.5);
            z-index: 200; justify-content: center; align-items: flex-start;
            padding: 40px 20px; overflow-y: auto;
        }
        .modal-overlay.open { display: flex; }
        body.modal-open { overflow: hidden; }
        body.modal-open .toolbar,
        body.modal-open .empty-state,
        body.modal-open .card { pointer-events: none; }
        body.modal-open .toolbar-btn,
        body.modal-open button,
        body.modal-open .toolbar-btn *,
        body.modal-open button * { animation: none !important; transition: none !important; }
        body.modal-open .toolbar-btn:hover,
        body.modal-open button:hover { transform: none !important; box-shadow: none !important; filter: none !important; }
        body.modal-open .spinner { display: none !important; }
        body.modal-open .busy-spinner { animation: spin 0.8s linear infinite !important; border-top-color: var(--accent) !important; }
        .modal {
            background: var(--bg-card); border: 1px solid var(--border-light);
            border-radius: 14px; width: 100%; max-width: 700px;
            box-shadow: 0 20px 40px var(--shadow);
        }
        .modal-header { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid var(--border); }
        .modal-header h2 { font-size: 16px; font-weight: 600; }
        .modal-close { background: none; border: none; color: var(--text-secondary); font-size: 20px; cursor: pointer; width: auto; padding: 4px 8px; border-radius: 4px; }
        .modal-close:hover { color: var(--text); background: var(--bg-input); }
        .modal-body { padding: 20px; }
        .modal-footer { display: flex; justify-content: flex-end; gap: 8px; padding: 16px 20px; border-top: 1px solid var(--border); }

        .form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 12px; }
        .form-row.full { grid-template-columns: 1fr; }
        .form-group { display: flex; flex-direction: column; }
        .form-group label { font-size: 12px; font-weight: 500; color: var(--text-secondary); margin-bottom: 4px; }
        .form-group input, .form-group textarea {
            padding: 8px 12px; border: 1px solid var(--border-light); border-radius: 6px;
            background: var(--bg-input); color: var(--text); font-size: 14px; font-family: inherit;
        }
        .form-group input:focus, .form-group textarea:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px rgba(56,139,253,0.15); }
        .form-group textarea { font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace; font-size: 13px; line-height: 1.6; resize: vertical; min-height: 250px; }
        .lyrics-hint { font-size: 11px; color: var(--text-muted); margin-top: 4px; }

        .drop-zone {
            border: 2px dashed var(--border-light); border-radius: 10px; padding: 28px 16px;
            text-align: center; cursor: pointer; transition: all 0.3s ease;
        }
        .drop-zone:hover, .drop-zone.dragover {
            border-color: var(--accent); background: var(--accent-bg);
            transform: scale(1.01); box-shadow: 0 4px 16px rgba(56,139,253,0.1);
        }
        .drop-zone.has-file {
            border-color: var(--green-text); background: rgba(63,185,80,0.06);
            border-style: solid;
        }
        .drop-zone input[type="file"] { display: none; }
        .drop-zone-text { color: var(--text-secondary); font-size: 13px; }
        .filename { color: var(--green-text); font-weight: 500; margin-top: 6px; font-size: 13px; word-break: break-all; }

        @keyframes spin { to { transform: rotate(360deg); } }
        .spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid rgba(255,255,255,0.3); border-top-color: #fff; border-radius: 50%; animation: spin 0.6s linear infinite; vertical-align: middle; margin-right: 6px; }

        .busy-overlay {
            display: none;
            position: fixed; inset: 0;
            background: rgba(0,0,0,0.55);
            z-index: 9999;
            justify-content: center; align-items: center;
            backdrop-filter: blur(2px);
        }
        .busy-overlay.show { display: flex; }
        .busy-modal {
            background: var(--bg-card);
            border: 1px solid var(--border-light);
            border-radius: 14px;
            padding: 32px 40px;
            box-shadow: 0 20px 50px rgba(0,0,0,0.5);
            text-align: center;
            min-width: 280px;
        }
        .busy-spinner {
            width: 42px; height: 42px;
            border: 3px solid var(--border);
            border-top-color: var(--accent);
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
            margin: 0 auto 16px;
        }
        .busy-title { font-size: 15px; font-weight: 600; color: var(--text); margin-bottom: 4px; }
        .busy-sub { font-size: 13px; color: var(--text-secondary); }

        .back-to-top {
            position: fixed; bottom: 24px; right: 24px; width: 42px; height: 42px;
            border-radius: 50%;
            background: linear-gradient(135deg, var(--bg-card), var(--border));
            border: 1px solid var(--border-light);
            color: var(--text-secondary); font-size: 18px; cursor: pointer;
            display: none; align-items: center; justify-content: center;
            z-index: 50; transition: all 0.25s ease;
            box-shadow: 0 4px 16px var(--shadow);
        }
        .back-to-top:hover { color: var(--text); transform: translateY(-2px); box-shadow: 0 6px 20px var(--shadow); }
        .back-to-top.visible { display: flex; }

        .theme-toggle {
            background: none; border: none; color: var(--text-secondary);
            cursor: pointer; font-size: 18px; padding: 4px 8px; border-radius: 4px; width: auto;
        }
        .theme-toggle:hover { color: var(--text); background: var(--accent-bg); }

        @media (max-width: 768px) {
            .form-row { grid-template-columns: 1fr; }
            .song-table .col-preview, .song-table .col-author { display: none; }
        }
    </style>
</head>
<body>
    <div class="busy-overlay" id="busyOverlay">
        <div class="busy-modal">
            <div class="busy-spinner" id="busySpinner"></div>
            <div class="busy-title" id="busyTitle">Working...</div>
            <div class="busy-sub" id="busySub">Patience &mdash; this may take some time!</div>
            <div id="busyProgress" style="display:none;margin-top:18px;">
                <div style="height:8px;background:var(--border);border-radius:4px;overflow:hidden;">
                    <div id="busyProgressFill" style="height:100%;background:var(--accent);width:0%;transition:width 0.3s ease;border-radius:4px;"></div>
                </div>
            </div>
        </div>
    </div>

    <div class="header">
        <div class="header-inner">
            <h1><a href="/">Visual Songbook Tools</a></h1>
            <a href="https://github.com/sesp05-sys/visual-songbook-tools" target="_blank" class="header-github">Source on GitHub</a>
            <div class="header-nav">
                <a href="/">Convert</a>
                <a href="/editor" class="active">Editor</a>
                <button class="theme-toggle" onclick="toggleTheme()" title="Toggle light/dark mode" id="themeBtn">&#x2600;</button>
            </div>
        </div>
    </div>

    <div class="main">
        <div class="toolbar">
            <div class="search-box">
                <input type="text" id="searchInput" placeholder="Search songs..." oninput="filterSongs()">
            </div>
            <span id="dirtyIndicator" style="display:none;align-items:center;gap:6px;padding:6px 10px;background:rgba(248,81,73,0.1);border:1px solid rgba(248,81,73,0.3);color:var(--red);border-radius:6px;font-size:12px;font-weight:500;" title="You have changes — export to save them as a file">
                <span style="width:8px;height:8px;border-radius:50%;background:var(--red);"></span>
                Not exported
            </span>
            <button class="toolbar-btn primary" onclick="openAddModal()">+ Add Song</button>
            <button class="toolbar-btn" onclick="openImportModal()">Import</button>
            <button class="toolbar-btn" onclick="exportAs('csv')">Export CSV</button>
            <button class="toolbar-btn" onclick="exportAs('vsb')">Export VSB</button>
            <button class="toolbar-btn" onclick="exportAs('json')">Export JSON</button>
            <button class="toolbar-btn" id="clearAllBtn" onclick="clearAll()" style="display:none;color:var(--red);">Clear All</button>
        </div>

        <div class="stats" id="stats"></div>

        <div class="song-table-wrap">
            <table class="song-table">
                <thead>
                    <tr>
                        <th class="col-num" onclick="sortBy('song_num')"># <span class="sort-icon" id="sort-song_num"></span></th>
                        <th class="col-title" onclick="sortBy('title')">Title <span class="sort-icon" id="sort-title"></span></th>
                        <th class="col-preview">Lyrics</th>
                        <th class="col-author" onclick="sortBy('author')">Author <span class="sort-icon" id="sort-author"></span></th>
                        <th class="col-key" onclick="sortBy('key')">Key <span class="sort-icon" id="sort-key"></span></th>
                        <th class="col-actions"></th>
                    </tr>
                </thead>
                <tbody id="songTableBody"></tbody>
            </table>
        </div>

        <div id="emptyState" class="empty-state" style="display:none;">
            <div class="icon">&#x1F3B5;</div>
            <p>Import a songbook to get started</p>
            <div style="max-width:400px;margin:0 auto;">
                <div class="drop-zone" id="welcomeDropZone">
                    <div class="drop-zone-text">Drop .vsb, .csv or .json file here</div>
                    <div class="filename" id="welcomeFileName"></div>
                    <input type="file" id="welcomeFileInput" accept=".vsb,.mdb,.csv,.json">
                </div>
                <button class="toolbar-btn blue" id="welcomeImportBtn" disabled onclick="doWelcomeImport()" style="margin-top:12px;width:100%;">Import</button>
            </div>
        </div>

    </div>

    <button class="back-to-top" id="backToTop" onclick="window.scrollTo({top:0,behavior:'smooth'});document.getElementById('searchInput').focus();" title="Back to top">&#x2191;</button>

    <!-- Edit/Add Modal -->
    <div class="modal-overlay" id="editModal">
        <div class="modal">
            <div class="modal-header">
                <h2 id="editModalTitle">Edit Song</h2>
                <button class="modal-close" onclick="closeEditModal()">&times;</button>
            </div>
            <div class="modal-body">
                <input type="hidden" id="editId">
                <div class="form-row">
                    <div class="form-group">
                        <label>Song Number</label>
                        <input type="number" id="editNum" min="1">
                    </div>
                    <div class="form-group">
                        <label>Key</label>
                        <input type="text" id="editKey" placeholder="e.g. G, Am, Eb">
                    </div>
                </div>
                <div class="form-row full">
                    <div class="form-group">
                        <label>Title</label>
                        <input type="text" id="editTitle" placeholder="Song title">
                    </div>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label>Author</label>
                        <input type="text" id="editAuthor" placeholder="Author name">
                    </div>
                    <div class="form-group">
                        <label>Copyright</label>
                        <input type="text" id="editCopyright" placeholder="Copyright info">
                    </div>
                </div>
                <div class="form-row full">
                    <div class="form-group">
                        <label>Lyrics</label>
                        <textarea id="editBody" placeholder="Enter lyrics here..."></textarea>
                        <div class="lyrics-hint">Separate verses with a blank line.</div>
                    </div>
                </div>
            </div>
            <div class="modal-footer">
                <button class="toolbar-btn" onclick="closeEditModal()">Cancel</button>
                <button class="toolbar-btn primary" onclick="saveSong()">Save</button>
            </div>
        </div>
    </div>

    <!-- Import Modal -->
    <div class="modal-overlay" id="importModal">
        <div class="modal">
            <div class="modal-header">
                <h2>Import Songs</h2>
                <button class="modal-close" onclick="closeImportModal()">&times;</button>
            </div>
            <div class="modal-body">
                <div class="drop-zone" id="importDropZone">
                    <div class="drop-zone-text">Drop .vsb, .csv or .json file here</div>
                    <div class="filename" id="importFileName"></div>
                    <input type="file" id="importFileInput" accept=".vsb,.mdb,.csv,.json">
                </div>
                <div style="margin-top:12px;">
                    <label style="font-size:13px;color:#8b949e;cursor:pointer;">
                        <input type="checkbox" id="importReplace" style="margin-right:6px;">
                        Replace all existing songs
                    </label>
                </div>
            </div>
            <div class="modal-footer">
                <button class="toolbar-btn" onclick="closeImportModal()">Cancel</button>
                <button class="toolbar-btn blue" id="importBtn" disabled onclick="doImport()">Import</button>
            </div>
        </div>
    </div>

    <script>
        // --- Theme ---
        function toggleTheme() {
            const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
            document.documentElement.setAttribute('data-theme', isDark ? 'light' : 'dark');
            localStorage.setItem('theme', isDark ? 'light' : 'dark');
            document.getElementById('themeBtn').innerHTML = isDark ? '&#x1F319;' : '&#x2600;';
        }
        (function() {
            const saved = localStorage.getItem('theme') || (window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
            if (saved === 'light') document.documentElement.setAttribute('data-theme', 'light');
            document.getElementById('themeBtn').innerHTML = saved === 'light' ? '&#x1F319;' : '&#x2600;';
        })();

        // Busy overlay helpers
        function showBusy(title, sub) {
            document.getElementById('busyTitle').textContent = title || 'Working...';
            document.getElementById('busySub').textContent = sub || 'Patience — this may take some time!';
            document.getElementById('busyOverlay').classList.add('show');
            document.body.classList.add('modal-open');
            // Reset to spinner-only mode
            document.getElementById('busySpinner').style.display = '';
            document.getElementById('busyProgress').style.display = 'none';
        }
        function setBusyProgress(percent, message) {
            // Hide spinner, show progress bar instead
            document.getElementById('busySpinner').style.display = 'none';
            document.getElementById('busyProgress').style.display = 'block';
            document.getElementById('busyProgressFill').style.width = (percent || 0) + '%';
            if (message) document.getElementById('busySub').textContent = message;
        }
        function hideBusy() {
            document.getElementById('busyOverlay').classList.remove('show');
            document.body.classList.remove('modal-open');
            document.getElementById('busySpinner').style.display = '';
            document.getElementById('busyProgress').style.display = 'none';
        }

        // --- State ---
        let songs = [];
        let filteredSongs = [];
        let sortField = 'song_num';
        let sortAsc = true;
        let loadedCount = 0;
        const BATCH = 80;
        let selectedRow = -1; // index in filteredSongs
        let importFile = null;
        let isDirty = false;
        const STORAGE_KEY = 'vsb_editor_songs';
        const DIRTY_KEY = 'vsb_editor_dirty';

        // --- Auto-save to localStorage ---
        function saveToStorage() {
            try {
                localStorage.setItem(STORAGE_KEY, JSON.stringify(songs));
                localStorage.setItem(DIRTY_KEY, isDirty ? '1' : '0');
            } catch (e) {
                console.warn('Could not save to localStorage:', e);
            }
        }

        function loadFromStorage() {
            try {
                const data = localStorage.getItem(STORAGE_KEY);
                if (data) {
                    songs = JSON.parse(data);
                    isDirty = localStorage.getItem(DIRTY_KEY) === '1';
                    return true;
                }
            } catch (e) {
                console.warn('Could not load from localStorage:', e);
            }
            return false;
        }

        function clearStorage() {
            localStorage.removeItem(STORAGE_KEY);
            localStorage.removeItem(DIRTY_KEY);
        }

        function markDirty() {
            isDirty = true;
            saveToStorage();
            updateDirtyIndicator();
        }

        function markClean() {
            isDirty = false;
            saveToStorage();
            updateDirtyIndicator();
        }

        function updateDirtyIndicator() {
            const el = document.getElementById('dirtyIndicator');
            if (el) el.style.display = isDirty ? 'inline-flex' : 'none';
        }

        // Warn before leaving with unsaved changes
        window.addEventListener('beforeunload', (e) => {
            if (isDirty) {
                e.preventDefault();
                e.returnValue = '';
            }
        });

        // --- Render ---
        function render() {
            applySort();
            applyFilter();
            loadedCount = 0;
            renderTable(true);
            renderStats();
        }

        function applySort() {
            songs.sort((a, b) => {
                let va = a[sortField] || '';
                let vb = b[sortField] || '';
                if (sortField === 'song_num') { va = parseInt(va) || 0; vb = parseInt(vb) || 0; }
                else { va = String(va).toLowerCase(); vb = String(vb).toLowerCase(); }
                if (va < vb) return sortAsc ? -1 : 1;
                if (va > vb) return sortAsc ? 1 : -1;
                return 0;
            });
        }

        function applyFilter() {
            const q = document.getElementById('searchInput').value.toLowerCase().trim();
            if (!q) { filteredSongs = [...songs]; }
            else {
                filteredSongs = songs.filter(s =>
                    (s.title || '').toLowerCase().includes(q) ||
                    (s.author || '').toLowerCase().includes(q) ||
                    (s.body || '').toLowerCase().includes(q) ||
                    String(s.song_num).includes(q)
                );
            }
        }

        function renderTable(reset) {
            const tbody = document.getElementById('songTableBody');
            const empty = document.getElementById('emptyState');
            const wrap = document.querySelector('.song-table-wrap');

            if (songs.length === 0) { wrap.style.display = 'none'; empty.style.display = 'block'; return; }
            wrap.style.display = ''; empty.style.display = 'none';

            if (reset) { tbody.innerHTML = ''; loadedCount = 0; selectedRow = -1; }

            const end = Math.min(loadedCount + BATCH, filteredSongs.length);
            const fragment = document.createDocumentFragment();

            for (let i = loadedCount; i < end; i++) {
                const s = filteredSongs[i];
                const idx = songs.indexOf(s);
                const preview = (s.body || '').replace(/\\n/g, ' ').substring(0, 80);
                const tr = document.createElement('tr');
                tr.dataset.fi = i;
                tr.innerHTML = `
                    <td class="col-num">${s.song_num || ''}</td>
                    <td class="col-title">${esc(s.title)}</td>
                    <td class="col-preview">${esc(preview)}</td>
                    <td class="col-author">${esc(s.author || '')}</td>
                    <td class="col-key">${esc(s.key || '')}</td>
                    <td class="col-actions">
                        <button class="action-btn" onclick="event.stopPropagation();openEditModal(${idx})" title="Edit">&#x270E;</button>
                        <button class="action-btn delete" onclick="event.stopPropagation();deleteSong(${idx})" title="Delete">&#x2716;</button>
                    </td>`;
                tr.addEventListener('click', () => selectRow(i));
                tr.addEventListener('dblclick', () => { selectRow(i); viewSelectedSong(); });
                fragment.appendChild(tr);
            }
            tbody.appendChild(fragment);
            loadedCount = end;

            // Sort icons
            document.querySelectorAll('.sort-icon').forEach(el => el.textContent = '');
            const icon = document.getElementById('sort-' + sortField);
            if (icon) icon.textContent = sortAsc ? '\u25B2' : '\u25BC';
        }

        // Lazy load on scroll + back-to-top visibility
        const backToTop = document.getElementById('backToTop');
        window.addEventListener('scroll', () => {
            if (loadedCount < filteredSongs.length && window.innerHeight + window.scrollY >= document.body.scrollHeight - 300) {
                renderTable(false);
            }
            backToTop.classList.toggle('visible', window.scrollY > 400);
        });

        function renderStats() {
            const el = document.getElementById('stats');
            const clearBtn = document.getElementById('clearAllBtn');
            if (clearBtn) clearBtn.style.display = songs.length > 0 ? '' : 'none';
            if (songs.length === 0) { el.innerHTML = ''; return; }
            const showing = filteredSongs.length !== songs.length
                ? `<span>Showing <strong>${filteredSongs.length}</strong> of ${songs.length}</span>`
                : `<span><strong>${songs.length}</strong> songs</span>`;
            el.innerHTML = showing;
        }

        function sortBy(field) {
            if (sortField === field) sortAsc = !sortAsc;
            else { sortField = field; sortAsc = true; }
            render();
        }

        function filterSongs() { render(); }

        function esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

        // --- Row selection & keyboard nav ---
        function selectRow(fi) {
            selectedRow = fi;
            highlightSelected();
        }

        function highlightSelected() {
            document.querySelectorAll('#songTableBody tr').forEach(tr => {
                tr.classList.toggle('selected', parseInt(tr.dataset.fi) === selectedRow);
            });
            // Scroll selected into view
            const sel = document.querySelector('#songTableBody tr.selected');
            if (sel) sel.scrollIntoView({ block: 'nearest' });
        }

        function moveSelection(dir) {
            if (filteredSongs.length === 0) return;
            if (selectedRow < 0) { selectedRow = 0; }
            else { selectedRow = Math.max(0, Math.min(filteredSongs.length - 1, selectedRow + dir)); }
            // Lazy load more if near bottom
            if (selectedRow >= loadedCount - 5 && loadedCount < filteredSongs.length) renderTable(false);
            highlightSelected();
        }

        // --- CRUD ---
        function openAddModal() {
            document.getElementById('editModalTitle').textContent = 'Add Song';
            document.getElementById('editId').value = '-1';
            document.getElementById('editNum').value = songs.length > 0 ? Math.max(...songs.map(s => parseInt(s.song_num) || 0)) + 1 : 1;
            document.getElementById('editTitle').value = '';
            document.getElementById('editBody').value = '';
            document.getElementById('editAuthor').value = '';
            document.getElementById('editCopyright').value = '';
            document.getElementById('editKey').value = '';
            document.getElementById('editModal').classList.add('open');
            document.body.classList.add('modal-open');
            setTimeout(() => document.getElementById('editTitle').focus(), 50);
        }

        function openEditModal(idx) {
            const s = songs[idx];
            document.getElementById('editModalTitle').textContent = 'Edit Song';
            document.getElementById('editId').value = idx;
            document.getElementById('editNum').value = s.song_num || '';
            document.getElementById('editTitle').value = s.title || '';
            document.getElementById('editBody').value = s.body || '';
            document.getElementById('editAuthor').value = s.author || '';
            document.getElementById('editCopyright').value = s.copyright || '';
            document.getElementById('editKey').value = s.key || '';
            document.getElementById('editModal').classList.add('open');
            document.body.classList.add('modal-open');
        }

        function viewSelectedSong() {
            if (selectedRow < 0 || selectedRow >= filteredSongs.length) return;
            const s = filteredSongs[selectedRow];
            const idx = songs.indexOf(s);
            openEditModal(idx);
        }

        function closeEditModal() { document.getElementById('editModal').classList.remove('open'); document.body.classList.remove('modal-open'); }

        function saveSong() {
            const idx = parseInt(document.getElementById('editId').value);
            const song = {
                song_num: document.getElementById('editNum').value,
                title: document.getElementById('editTitle').value.trim(),
                body: document.getElementById('editBody').value,
                author: document.getElementById('editAuthor').value.trim(),
                copyright: document.getElementById('editCopyright').value.trim(),
                key: document.getElementById('editKey').value.trim(),
                category_id: '1'
            };
            if (!song.title) { alert('Title is required'); return; }
            if (idx < 0) songs.push(song);
            else songs[idx] = song;
            markDirty();
            closeEditModal();
            render();
        }

        function deleteSong(idx) {
            if (!confirm('Delete "' + songs[idx].title + '"?')) return;
            songs.splice(idx, 1);
            markDirty();
            render();
        }

        function clearAll() {
            if (songs.length === 0) return;
            const msg = isDirty
                ? 'Discard ' + songs.length + ' songs? You have unsaved changes — they will be lost.'
                : 'Clear all ' + songs.length + ' songs?';
            if (!confirm(msg)) return;
            songs = [];
            clearStorage();
            isDirty = false;
            updateDirtyIndicator();
            render();
        }

        // --- Import ---
        function openImportModal() {
            importFile = null;
            document.getElementById('importFileName').textContent = '';
            document.getElementById('importDropZone').classList.remove('has-file');
            document.getElementById('importBtn').disabled = true;
            document.getElementById('importReplace').checked = songs.length === 0;
            document.getElementById('importModal').classList.add('open');
            document.body.classList.add('modal-open');
        }
        function closeImportModal() { document.getElementById('importModal').classList.remove('open'); document.body.classList.remove('modal-open'); }

        const importDropZone = document.getElementById('importDropZone');
        const importFileInput = document.getElementById('importFileInput');
        importDropZone.addEventListener('click', () => importFileInput.click());
        importDropZone.addEventListener('dragover', e => { e.preventDefault(); importDropZone.classList.add('dragover'); });
        importDropZone.addEventListener('dragleave', () => importDropZone.classList.remove('dragover'));
        importDropZone.addEventListener('drop', e => {
            e.preventDefault(); importDropZone.classList.remove('dragover');
            if (e.dataTransfer.files[0]) handleImportFile(e.dataTransfer.files[0]);
        });
        importFileInput.addEventListener('change', e => { if (e.target.files[0]) handleImportFile(e.target.files[0]); });

        function handleImportFile(file) {
            importFile = file;
            document.getElementById('importFileName').textContent = file.name;
            importDropZone.classList.add('has-file');
            document.getElementById('importBtn').disabled = false;
        }

        async function doImport() {
            if (!importFile) return;
            const btn = document.getElementById('importBtn');
            btn.disabled = true;
            btn.innerHTML = '<span class="spinner"></span>Importing...';
            showBusy('Importing songs', 'Uploading and parsing — patience for large files!');
            try {
                const response = await fetch('/api/editor/import', { method: 'POST', body: (() => { const fd = new FormData(); fd.append('file', importFile); return fd; })() });
                const data = await response.json();
                if (data.error) { alert(data.error); return; }
                if (document.getElementById('importReplace').checked) {
                    songs = data.songs;
                    markClean();
                } else {
                    const maxNum = songs.length > 0 ? Math.max(...songs.map(s => parseInt(s.song_num) || 0)) : 0;
                    data.songs.forEach((s, i) => { s.song_num = String(maxNum + i + 1); });
                    songs = songs.concat(data.songs);
                    markDirty();
                }
                closeImportModal();
                render();
            } catch (err) { alert('Import failed: ' + err.message); }
            finally { btn.disabled = false; btn.innerHTML = 'Import'; hideBusy(); }
        }

        // --- Export ---
        async function exportAs(format) {
            if (songs.length === 0) { alert('No songs to export'); return; }
            const btn = event.target;
            const origText = btn.textContent;
            btn.disabled = true;
            btn.innerHTML = '<span class="spinner"></span>Exporting...';
            showBusy('Exporting to ' + format.toUpperCase(), 'Patience — this may take some time!');
            try {
                const response = await fetch('/api/editor/export/' + format, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ songs })
                });
                if (!response.ok) { const d = await response.json(); alert(d.error || 'Export failed'); return; }
                const blob = await response.blob();
                const a = document.createElement('a');
                a.href = window.URL.createObjectURL(blob);
                a.download = 'songbook.' + format;
                document.body.appendChild(a); a.click();
                window.URL.revokeObjectURL(a.href); a.remove();
                markClean();
            } catch (err) { alert('Export failed: ' + err.message); }
            finally { btn.disabled = false; btn.innerHTML = origText; hideBusy(); }
        }

        // --- Keyboard ---
        function isModalOpen() {
            return document.getElementById('editModal').classList.contains('open') ||
                   document.getElementById('importModal').classList.contains('open');
        }

        document.addEventListener('keydown', e => {
            // Close modals on Escape
            if (e.key === 'Escape') {
                if (isModalOpen()) { closeEditModal(); closeImportModal(); e.preventDefault(); return; }
            }

            // Skip nav keys if typing in an input/textarea or modal is open
            const tag = document.activeElement.tagName;
            if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
            if (isModalOpen()) return;

            if (e.key === 'ArrowDown') { e.preventDefault(); moveSelection(1); }
            else if (e.key === 'ArrowUp') { e.preventDefault(); moveSelection(-1); }
            else if (e.key === 'Enter') { e.preventDefault(); viewSelectedSong(); }
        });

        // --- Welcome drop zone (shown when no songs) ---
        let welcomeFile = null;
        const welcomeDropZone = document.getElementById('welcomeDropZone');
        const welcomeFileInput = document.getElementById('welcomeFileInput');

        welcomeDropZone.addEventListener('click', () => welcomeFileInput.click());
        welcomeDropZone.addEventListener('dragover', e => { e.preventDefault(); welcomeDropZone.classList.add('dragover'); });
        welcomeDropZone.addEventListener('dragleave', () => welcomeDropZone.classList.remove('dragover'));
        welcomeDropZone.addEventListener('drop', e => {
            e.preventDefault(); welcomeDropZone.classList.remove('dragover');
            if (e.dataTransfer.files[0]) handleWelcomeFile(e.dataTransfer.files[0]);
        });
        welcomeFileInput.addEventListener('change', e => { if (e.target.files[0]) handleWelcomeFile(e.target.files[0]); });

        function handleWelcomeFile(file) {
            welcomeFile = file;
            document.getElementById('welcomeFileName').textContent = file.name;
            welcomeDropZone.classList.add('has-file');
            document.getElementById('welcomeImportBtn').disabled = false;
        }

        async function doWelcomeImport() {
            if (!welcomeFile) return;
            const btn = document.getElementById('welcomeImportBtn');
            btn.disabled = true;
            btn.innerHTML = '<span class="spinner"></span>Importing...';
            showBusy('Importing songs', 'Uploading and parsing — patience for large files!');
            try {
                const fd = new FormData();
                fd.append('file', welcomeFile);
                const response = await fetch('/api/editor/import', { method: 'POST', body: fd });
                const data = await response.json();
                if (data.error) { alert(data.error); return; }
                songs = data.songs;
                markClean();
                render();
            } catch (err) { alert('Import failed: ' + err.message); }
            finally { btn.disabled = false; btn.innerHTML = 'Import'; hideBusy(); }
        }

        // Load saved songs from localStorage if any
        if (loadFromStorage()) {
            updateDirtyIndicator();
        }

        // Initial render
        render();
    </script>
</body>
</html>
'''

@app.after_request
def add_cache_headers(response):
    if response.content_type and 'text/html' in response.content_type:
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        response.headers['ETag'] = APP_VERSION
    return response

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, v=APP_VERSION)

@app.route('/editor')
def editor():
    return render_template_string(EDITOR_TEMPLATE, v=APP_VERSION)

# --- Editor API ---

@app.route('/api/editor/import', methods=['POST'])
def editor_import():
    """Import VSB or CSV file, return songs as JSON."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    file = request.files['file']
    if not file.filename:
        return jsonify({'error': 'No file selected'}), 400

    ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
    job_id = str(uuid.uuid4())[:8]

    if ext in ('vsb', 'mdb'):
        # Save VSB, convert to CSV via Jackcess, parse CSV
        vsb_path = os.path.join(UPLOAD_FOLDER, f"{job_id}.vsb")
        csv_path = os.path.join(UPLOAD_FOLDER, f"{job_id}.csv")
        file.save(vsb_path)
        try:
            result = subprocess.run(
                ['java', '-cp', '.:lib/*', 'VsbToCsv', vsb_path, csv_path],
                capture_output=True, text=True, cwd=BASE_DIR, timeout=120
            )
            if result.returncode != 0 or not os.path.exists(csv_path):
                return jsonify({'error': 'Could not read VSB file'}), 400
            songs = parse_csv_to_songs(csv_path)
            return jsonify({'songs': songs})
        finally:
            for p in [vsb_path, csv_path]:
                if os.path.exists(p):
                    os.remove(p)

    elif ext == 'csv':
        csv_path = os.path.join(UPLOAD_FOLDER, f"{job_id}.csv")
        file.save(csv_path)
        try:
            songs = parse_csv_to_songs(csv_path)
            return jsonify({'songs': songs})
        finally:
            if os.path.exists(csv_path):
                os.remove(csv_path)
    elif ext == 'json':
        try:
            content = file.read().decode('utf-8', errors='replace')
            data = json.loads(content)
            songs = parse_json_to_songs(data)
            return jsonify({'songs': songs})
        except json.JSONDecodeError:
            return jsonify({'error': 'Invalid JSON file'}), 400
    else:
        return jsonify({'error': 'Unsupported file type'}), 400

def parse_json_to_songs(data):
    """Parse JSON data into list of song dicts. Accepts array of objects or {songs: [...]}."""
    import re
    if isinstance(data, dict):
        if 'songs' in data: data = data['songs']
        elif 'items' in data: data = data['items']
        elif 'data' in data: data = data['data']
    if not isinstance(data, list):
        return []

    # Field aliases (lowercase normalized)
    aliases = {
        'number': ['number', 'num', 'songnum', 'song_num', 'nr', 'no', '#'],
        'title': ['title', 'name', 'song', 'tittel', 'sang'],
        'body': ['body', 'lyrics', 'text', 'words', 'tekst', 'sangtekst'],
        'author': ['author', 'writer', 'artist', 'forfatter', 'tekstforfatter'],
        'copyright': ['copyright', 'rights'],
        'key': ['key', 'tone', 'toneart'],
        'category': ['category', 'cat', 'type', 'genre', 'kategori', 'category_id', 'categoryid'],
    }

    def find(obj, field):
        if not isinstance(obj, dict): return ''
        # Build lowercase keys map
        lc = {re.sub(r'[^a-z0-9#]', '', k.lower()): k for k in obj.keys()}
        for alias in aliases[field]:
            normalized = re.sub(r'[^a-z0-9#]', '', alias)
            if normalized in lc:
                v = obj[lc[normalized]]
                return str(v) if v is not None else ''
        return ''

    songs = []
    for item in data:
        title = find(item, 'title').strip()
        if not title: continue
        songs.append({
            'song_num': find(item, 'number'),
            'title': title,
            'body': find(item, 'body'),
            'author': find(item, 'author').strip(),
            'copyright': find(item, 'copyright').strip(),
            'key': find(item, 'key').strip(),
            'category_id': find(item, 'category') or '1',
        })
    return songs

def parse_csv_to_songs(csv_path):
    """Parse a CSV file (semicolon-delimited, Norwegian headers) into a list of song dicts."""
    import re
    songs_list = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        content = f.read()

    lines = content.split('\n')
    if not lines:
        return songs_list

    header_line = lines[0].strip()
    delim = ';' if ';' in header_line else ','

    reader = csv.reader([header_line], delimiter=delim)
    columns = [c.strip().lower() for c in next(reader)]

    # Map columns to canonical names
    col_map = {}
    for i, col in enumerate(columns):
        normalized = re.sub(r'[^a-z0-9#]', '', col)
        canonical = COLUMN_ALIASES.get(normalized)
        if canonical and canonical not in col_map:
            col_map[canonical] = i

    data_text = '\n'.join(lines[1:])
    reader = csv.reader(io.StringIO(data_text), delimiter=delim)

    for row in reader:
        if not any(cell.strip() for cell in row):
            continue
        def g(key):
            idx = col_map.get(key)
            if idx is not None and idx < len(row):
                return row[idx].strip()
            return ''
        title = g('title')
        if not title:
            continue
        songs_list.append({
            'song_num': g('number'),
            'title': title,
            'body': g('body'),
            'author': g('author'),
            'copyright': g('copyright'),
            'key': g('key'),
            'category_id': g('category') or '1'
        })
    return songs_list

@app.route('/api/editor/export/<fmt>', methods=['POST'])
def editor_export(fmt):
    """Export songs (sent as JSON) to CSV, VSB, or JSON."""
    data = request.get_json()
    if not data or 'songs' not in data:
        return jsonify({'error': 'No songs provided'}), 400

    songs_data = data['songs']
    job_id = str(uuid.uuid4())[:8]

    if fmt == 'json':
        export = [{
            'number': s.get('song_num', ''),
            'title': s.get('title', ''),
            'lyrics': s.get('body', ''),
            'author': s.get('author', ''),
            'copyright': s.get('copyright', ''),
            'key': s.get('key', ''),
            'category': s.get('category_id', '1'),
        } for s in songs_data]
        return send_file(
            io.BytesIO(json.dumps(export, indent=2, ensure_ascii=False).encode('utf-8')),
            mimetype='application/json',
            as_attachment=True,
            download_name='songbook.json'
        )

    csv_path = os.path.join(UPLOAD_FOLDER, f"{job_id}_export.csv")

    # Write songs to CSV
    with open(csv_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow(['Nummer', 'Tittel', 'Tekst', 'Tekstforfatter', 'Copyright', 'Toneart', 'Kategori'])
        for s in songs_data:
            writer.writerow([
                s.get('song_num', ''),
                s.get('title', ''),
                s.get('body', ''),
                s.get('author', ''),
                s.get('copyright', ''),
                s.get('key', ''),
                s.get('category_id', '1')
            ])

    if fmt == 'csv':
        response = send_file(csv_path, mimetype='text/csv', as_attachment=True, download_name='songbook.csv')
        @response.call_on_close
        def cleanup():
            if os.path.exists(csv_path):
                os.remove(csv_path)
        return response

    elif fmt == 'vsb':
        vsb_path = os.path.join(OUTPUT_FOLDER, f"{job_id}_export.vsb")
        try:
            template = None
            for name in ['template.vsb']:
                path = os.path.join(BASE_DIR, name)
                if os.path.exists(path):
                    template = path
                    break
            if not template:
                return jsonify({'error': 'No template VSB file on server'}), 500

            result = subprocess.run(
                ['java', '-cp', '.:lib/*', 'CsvToVsb', csv_path, vsb_path, '--template', template],
                capture_output=True, text=True, cwd=BASE_DIR, timeout=120
            )
            if result.returncode != 0 or not os.path.exists(vsb_path):
                return jsonify({'error': 'VSB export failed'}), 500

            response = send_file(vsb_path, as_attachment=True, download_name='songbook.vsb')
            @response.call_on_close
            def cleanup_vsb():
                for p in [csv_path, vsb_path]:
                    if os.path.exists(p):
                        os.remove(p)
            return response
        except Exception:
            for p in [csv_path, vsb_path]:
                if os.path.exists(p):
                    os.remove(p)
            return jsonify({'error': 'Export failed'}), 500
    else:
        os.remove(csv_path)
        return jsonify({'error': 'Unknown format'}), 400

@app.route('/api/upload', methods=['POST'])
def upload():
    status = get_status()
    if status.get('running'):
        return jsonify({'error': 'A job is already running. Please wait.'}), 400

    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
    if ext not in ('vsb', 'mdb', 'csv', 'json'):
        return jsonify({'error': 'Invalid file type. Use .vsb, .csv or .json'}), 400

    title = request.form.get('title', '').strip()
    if not title:
        title = secure_filename(file.filename).rsplit('.', 1)[0]

    page_format = request.form.get('page_format', 'a5')
    if page_format not in ('a5', 'halfletter'):
        page_format = 'a5'

    cover_theme = request.form.get('cover_theme', 'classic')
    if cover_theme not in ('classic', 'modern', 'minimal', 'elegant'):
        cover_theme = 'classic'
    cover_subtitle = request.form.get('cover_subtitle', '').strip()[:200]
    cover_footer = request.form.get('cover_footer', '').strip()[:200]

    # Save uploaded file
    job_id = str(uuid.uuid4())[:8]
    input_path = os.path.join(UPLOAD_FOLDER, f"{job_id}.{ext}")
    file.save(input_path)

    # If CSV/JSON, convert to a normalized CSV that the worker can read directly as VSB-equivalent
    # We do this by writing a "fake VSB" path - actually we need worker to handle CSV/JSON too
    # Simplest: parse here, write a normalized CSV, pass that to worker via a new arg
    if ext in ('csv', 'json'):
        try:
            if ext == 'csv':
                songs = parse_csv_to_songs(input_path)
            else:
                with open(input_path, 'r', encoding='utf-8') as f:
                    songs = parse_json_to_songs(json.load(f))
            if not songs:
                os.remove(input_path)
                return jsonify({'error': 'No valid songs found in file (need at least a Title field)'}), 400

            # Write a normalized CSV with the same format as VSB->CSV produces
            normalized_path = os.path.join(UPLOAD_FOLDER, f"{job_id}.csv")
            with open(normalized_path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f, delimiter=';')
                writer.writerow(['Nummer', 'Tittel', 'Tekst', 'Tekstforfatter', 'Copyright', 'Toneart', 'Kategori'])
                for s in songs:
                    writer.writerow([
                        s.get('song_num', ''), s.get('title', ''), s.get('body', ''),
                        s.get('author', ''), s.get('copyright', ''),
                        s.get('key', ''), s.get('category_id', '1')
                    ])
            # Remove original, replace with normalized
            if input_path != normalized_path and os.path.exists(input_path):
                os.remove(input_path)
            input_path = normalized_path
        except Exception as e:
            if os.path.exists(input_path):
                os.remove(input_path)
            return jsonify({'error': f'Could not parse file: {str(e)}'}), 400

    # Start worker process
    cmd = [
        os.path.join(BASE_DIR, 'venv', 'bin', 'python3'),
        os.path.join(BASE_DIR, 'worker.py'),
        input_path,
        title,
        job_id,
        page_format,
        cover_theme,
        cover_subtitle,
        cover_footer
    ]

    set_status({'running': True, 'progress': 0, 'message': 'Starting...', 'error': None, 'result': None, 'started_at': datetime.now().timestamp()})
    subprocess.Popen(cmd, start_new_session=True)

    return jsonify({'started': True, 'job_id': job_id})

@app.route('/api/progress')
def progress():
    return jsonify(get_status())

@app.route('/api/download/<filename>')
def download(filename):
    # Sanitize filename
    filename = secure_filename(filename)
    filepath = os.path.join(OUTPUT_FOLDER, filename)

    if not os.path.exists(filepath):
        return jsonify({'error': 'File not found'}), 404

    return send_file(filepath, as_attachment=True, download_name=filename)

@app.route('/api/export-csv', methods=['POST'])
def export_csv():
    """Export VSB/MDB to CSV directly"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file type. Only .vsb supported.'}), 400

    # Save uploaded file temporarily
    job_id = str(uuid.uuid4())[:8]
    original_ext = file.filename.rsplit('.', 1)[1].lower()
    input_filename = f"{job_id}.{original_ext}"
    input_path = os.path.join(UPLOAD_FOLDER, input_filename)
    file.save(input_path)

    csv_path = os.path.join(UPLOAD_FOLDER, f"{job_id}.csv")

    try:
        # Use Jackcess (VsbToCsv) - reads only active rows, sorted by SongNum
        result = subprocess.run(
            ['java', '-cp', '.:lib/*', 'VsbToCsv', input_path, csv_path],
            capture_output=True, text=True, cwd=BASE_DIR, timeout=120
        )

        if result.returncode != 0 or not os.path.exists(csv_path):
            return jsonify({'error': 'Could not read database'}), 400

        original_name = file.filename.rsplit('.', 1)[0]
        csv_filename = f"{original_name}.csv"

        response = send_file(csv_path, mimetype='text/csv',
                             as_attachment=True, download_name=csv_filename)

        @response.call_on_close
        def cleanup():
            for p in [input_path, csv_path]:
                if os.path.exists(p):
                    os.remove(p)

        return response

    except Exception:
        for p in [input_path, csv_path]:
            if os.path.exists(p):
                os.remove(p)
        return jsonify({'error': 'An unexpected error occurred'}), 500

COLUMN_ALIASES = {
    'nummer': 'number', 'number': 'number', 'num': 'number', 'songnum': 'number',
    'nr': 'number', '#': 'number', 'no': 'number',
    'tittel': 'title', 'title': 'title', 'name': 'title', 'sang': 'title', 'song': 'title',
    'tekst': 'body', 'text': 'body', 'body': 'body', 'lyrics': 'body',
    'words': 'body', 'sangtekst': 'body',
    'tekstforfatter': 'author', 'author': 'author', 'forfatter': 'author',
    'writer': 'author', 'artist': 'author',
    'copyright': 'copyright', 'rettigheter': 'copyright',
    'toneart': 'key', 'key': 'key', 'tone': 'key',
    'kategori': 'category', 'category': 'category', 'cat': 'category',
    'type': 'category', 'genre': 'category',
}

def parse_csv_header(file_content):
    """Parse CSV and return header info, auto-mapping, and preview rows."""
    import re
    lines = file_content.split('\n')
    if not lines:
        return None

    header_line = lines[0].strip()
    delim = ';' if ';' in header_line else ','

    # Parse header
    reader = csv.reader([header_line], delimiter=delim)
    columns = next(reader)
    columns = [c.strip() for c in columns]

    # Auto-map columns
    mapping = {}  # index -> canonical name
    used = set()
    for i, col in enumerate(columns):
        normalized = re.sub(r'[^a-z0-9#]', '', col.lower())
        canonical = COLUMN_ALIASES.get(normalized)
        if canonical and canonical not in used:
            mapping[i] = canonical
            used.add(canonical)

    # Parse preview rows (first 3 data rows)
    preview = []
    data_text = '\n'.join(lines[1:])
    if data_text.strip():
        reader = csv.reader(io.StringIO(data_text), delimiter=delim)
        for j, row in enumerate(reader):
            if j >= 3:
                break
            preview.append(row)

    # Count total rows
    reader = csv.reader(io.StringIO(data_text), delimiter=delim)
    total = sum(1 for row in reader if any(cell.strip() for cell in row))

    return {
        'csv_columns': columns,
        'mapping': mapping,
        'preview': preview,
        'total_rows': total,
        'delimiter': delim
    }

@app.route('/api/validate-csv', methods=['POST'])
def validate_csv():
    """Validate CSV and return column mapping for user confirmation."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['file']
    if not file.filename or not allowed_csv_file(file.filename):
        return jsonify({'error': 'Invalid file type. Only .csv supported.'}), 400

    content = file.read().decode('utf-8', errors='replace')
    result = parse_csv_header(content)
    if not result:
        return jsonify({'error': 'Could not parse CSV file'}), 400

    return jsonify(result)

@app.route('/api/import-csv', methods=['POST'])
def import_csv():
    """Convert CSV to VSB using user-confirmed column mapping."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['file']
    if not file.filename or not allowed_csv_file(file.filename):
        return jsonify({'error': 'Invalid file type. Only .csv supported.'}), 400

    # Get user mapping: {canonical_name: column_index}
    user_mapping = {}
    mapping_json = request.form.get('mapping', '{}')
    try:
        user_mapping = json.loads(mapping_json)
    except:
        pass

    if 'title' not in user_mapping:
        return jsonify({'error': 'Title column is required'}), 400

    job_id = str(uuid.uuid4())[:8]

    # Read and remap the CSV according to user mapping
    content = file.read().decode('utf-8', errors='replace')
    lines = content.split('\n')
    header_line = lines[0].strip()
    delim = ';' if ';' in header_line else ','

    # Write a normalized CSV with standard headers for CsvToVsb
    csv_path = os.path.join(UPLOAD_FOLDER, f"{job_id}.csv")
    vsb_path = os.path.join(OUTPUT_FOLDER, f"{job_id}.vsb")

    FIELDS = ['number', 'title', 'body', 'author', 'copyright', 'key', 'category']
    HEADERS = ['Nummer', 'Tittel', 'Tekst', 'Tekstforfatter', 'Copyright', 'Toneart', 'Kategori']

    data_text = '\n'.join(lines[1:])
    reader = csv.reader(io.StringIO(data_text), delimiter=delim)

    with open(csv_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f, delimiter=';')
        writer.writerow(HEADERS)
        for row in reader:
            if not any(cell.strip() for cell in row):
                continue
            out_row = []
            for field in FIELDS:
                idx = user_mapping.get(field)
                if idx is not None:
                    idx = int(idx)
                    out_row.append(row[idx].strip() if idx < len(row) else '')
                else:
                    out_row.append('')
            writer.writerow(out_row)

    try:
        template = None
        for name in ['template.vsb']:
            path = os.path.join(BASE_DIR, name)
            if os.path.exists(path):
                template = path
                break

        if not template:
            return jsonify({'error': 'No template VSB file found on server.'}), 500

        result = subprocess.run(
            ['java', '-cp', '.:lib/*', 'CsvToVsb', csv_path, vsb_path, '--template', template],
            capture_output=True, text=True, cwd=BASE_DIR, timeout=120
        )

        if result.returncode != 0:
            error_msg = result.stderr.strip() or result.stdout.strip() or 'Unknown error'
            return jsonify({'error': f'Conversion failed: {error_msg}'}), 500

        if not os.path.exists(vsb_path):
            return jsonify({'error': 'VSB file was not created'}), 500

        original_name = file.filename.rsplit('.', 1)[0]
        vsb_filename = f"{original_name}.vsb"

        response = send_file(vsb_path, as_attachment=True, download_name=vsb_filename)

        @response.call_on_close
        def cleanup():
            for p in [csv_path, vsb_path]:
                if os.path.exists(p):
                    os.remove(p)

        return response

    except subprocess.TimeoutExpired:
        for p in [csv_path, vsb_path]:
            if os.path.exists(p):
                os.remove(p)
        return jsonify({'error': 'Conversion timed out'}), 500
    except Exception as e:
        for p in [csv_path, vsb_path]:
            if os.path.exists(p):
                os.remove(p)
        return jsonify({'error': str(e)}), 500

@app.route('/api/merge-vsb', methods=['POST'])
def merge_vsb():
    """Merge multiple VSB files into one with sequential numbering"""
    files = request.files.getlist('files')
    if len(files) < 2:
        return jsonify({'error': 'At least 2 files required'}), 400

    job_id = str(uuid.uuid4())[:8]
    saved_paths = []

    try:
        # Save all uploaded files in order
        for i, file in enumerate(files):
            if not file.filename or not allowed_file(file.filename):
                return jsonify({'error': f'Invalid file: {file.filename}'}), 400
            ext = file.filename.rsplit('.', 1)[1].lower()
            path = os.path.join(UPLOAD_FOLDER, f"{job_id}_{i}.{ext}")
            file.save(path)
            saved_paths.append(path)

        output_path = os.path.join(OUTPUT_FOLDER, f"{job_id}_merged.vsb")

        renumber = request.form.get('renumber', '1') == '1'
        try:
            start_num = max(1, int(request.form.get('start_num', '1')))
        except ValueError:
            start_num = 1

        cmd = ['java', '-cp', '.:lib/*', 'MergeVsb', output_path]
        if renumber:
            cmd += ['--start', str(start_num)]
        else:
            cmd += ['--keep-numbers']
        cmd += saved_paths
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=BASE_DIR, timeout=120
        )

        if result.returncode != 0:
            return jsonify({'error': 'Merge failed'}), 500

        if not os.path.exists(output_path):
            return jsonify({'error': 'VSB file was not created'}), 500

        response = send_file(output_path, as_attachment=True, download_name='merged_songbook.vsb')

        @response.call_on_close
        def cleanup():
            for p in saved_paths:
                if os.path.exists(p):
                    os.remove(p)
            if os.path.exists(output_path):
                os.remove(output_path)

        return response

    except subprocess.TimeoutExpired:
        for p in saved_paths:
            if os.path.exists(p):
                os.remove(p)
        return jsonify({'error': 'Merge timed out'}), 500
    except Exception:
        for p in saved_paths:
            if os.path.exists(p):
                os.remove(p)
        return jsonify({'error': 'An unexpected error occurred'}), 500

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5003)
