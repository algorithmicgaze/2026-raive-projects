#!/usr/bin/env python3
"""Check the public source tree for private artifacts and common disclosures.

This is a guardrail, not a replacement for reviewing identities in prose.
Uses only Python's standard library. Does not print matched secret values.
"""
from pathlib import Path
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_EXTENSIONS = set('jpg jpeg png gif webp mp4 mov webm wav m4a mp3 onnx pth pt ckpt safetensors pkl npy npz bin task u8 zip tar gz pyc'.split())
PRIVATE_DIRS = {'.venv', 'node_modules', '__pycache__', 'media', 'datasets', 'diary', 'models', 'dist', 'build', 'deps', 'externals', '.cache'}
EMAIL = re.compile(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}')
SECRET = re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----)')
issues = []
checked = 0
for p in sorted(ROOT.rglob('*')):
    rel = p.relative_to(ROOT)
    if '.git' in rel.parts:
        continue
    if p.is_symlink():
        if not p.resolve().is_relative_to(ROOT):
            issues.append((rel, 'symlink leaves source tree'))
        continue
    if not p.is_file():
        continue
    checked += 1
    if p.suffix.lower().lstrip('.') in PRIVATE_EXTENSIONS or any(part in PRIVATE_DIRS or part.startswith('output-') for part in rel.parts):
        issues.append((rel, 'private/generated artifact'))
    if p.name == '.env' or (p.name.startswith('.env.') and p.name not in {'.env.example', '.env.template'}):
        issues.append((rel, 'local credentials file'))
    try:
        text = p.read_text(encoding='utf-8')
    except (UnicodeError, OSError):
        issues.append((rel, 'non-text file'))
        continue
    if '\x00' in text:
        issues.append((rel, 'binary content'))
    if p == Path(__file__).resolve():
        continue
    if SECRET.search(text):
        issues.append((rel, 'credential pattern'))
    if any(m.group().split('@')[1] not in {'example.com', 'example.org', 'example.invalid'} for m in EMAIL.finditer(text)):
        issues.append((rel, 'non-example email address'))
    if re.search(r'/(?:Users|home)/[^\s/"\\]+', text):
        issues.append((rel, 'personal home directory'))
    if re.search(r'data:(?:image|video|audio)/', text):
        issues.append((rel, 'embedded media'))
    if p.suffix in {'.json', '.fgmt', '.maxpat', '.maxhelp', '.ipynb'}:
        try:
            data = json.loads(text)
            if p.suffix == '.ipynb':
                for cell in data.get('cells', []):
                    if cell.get('outputs') or cell.get('attachments') or cell.get('execution_count') is not None:
                        issues.append((rel, 'notebook outputs or attachments'))
                        break
        except json.JSONDecodeError:
            issues.append((rel, 'invalid JSON'))
for rel, reason in issues:
    print(f'{rel}: {reason}')
print(f'Checked {checked} source files; {len(issues)} issue(s).')
sys.exit(bool(issues))
