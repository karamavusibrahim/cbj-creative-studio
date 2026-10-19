#!/usr/bin/env python3
"""Validate .claude/skills/*/SKILL.md against the Agent Skills spec and this repo's seven-section standard.

    python .claude/skills/scripts/validate_skills.py [--strict]     # --strict turns warnings into failures
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECTIONS = ["## 1. Purpose", "## 2. Source of truth", "## 3. Facts", "## 4. Procedure",
            "## 5. Not possible here", "## 6. Evidence", "## 7. Change rules"]
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
XML_RE = re.compile(r"<[a-zA-Z/][^>]*>")
LINK_RE = re.compile(r"\]\(([^)#]+)(?:#[^)]*)?\)")


def frontmatter(text: str):
    if not text.startswith("---"):
        return None, text
    end = text.find("\n---", 3)
    if end < 0:
        return None, text
    raw, body = text[3:end].strip(), text[end + 4:]
    f, key = {}, None
    for line in raw.splitlines():
        m = re.match(r"^([a-zA-Z0-9_-]+):\s*(.*)$", line)
        if m and not line.startswith(" "):
            key = m.group(1)
            f[key] = m.group(2).strip()
        elif key and line.startswith(" "):
            m2 = re.match(r"^\s+([a-zA-Z0-9_-]+):\s*(.*)$", line)
            if m2 and key == "metadata":
                f[f"metadata.{m2.group(1)}"] = m2.group(2).strip().strip('"')
            else:
                f[key] += " " + line.strip()
    return f, body


def main() -> int:
    strict = "--strict" in sys.argv
    errors, warnings = [], []
    dirs = sorted(d for d in ROOT.iterdir() if d.is_dir() and d.name != "scripts")
    for d in dirs:
        p = d / "SKILL.md"
        if not p.is_file():
            errors.append(f"{d.name}: no SKILL.md")
            continue
        text = p.read_text()
        f, body = frontmatter(text)
        if f is None:
            errors.append(f"{d.name}: missing frontmatter")
            continue
        name, desc = f.get("name", ""), f.get("description", "")
        if not name:
            errors.append(f"{d.name}: missing name")
        else:
            if len(name) > 64:
                errors.append(f"{d.name}: name > 64 chars")
            if not NAME_RE.match(name):
                errors.append(f"{d.name}: name must be lowercase alnum + single hyphens")
            if name != d.name:
                errors.append(f"{d.name}: name {name!r} != directory")
        if not desc:
            errors.append(f"{d.name}: missing description")
        else:
            if len(desc) > 1024:
                errors.append(f"{d.name}: description {len(desc)} chars (max 1024)")
            if XML_RE.search(desc):
                errors.append(f"{d.name}: description contains XML tags")
            if not re.search(r"use when", desc, re.I):
                warnings.append(f"{d.name}: description has no 'Use when' trigger")
            if len(desc) < 200:
                warnings.append(f"{d.name}: description only {len(desc)} chars")
        for key in ("metadata.spec-version", "metadata.last-verified"):
            if key not in f:
                errors.append(f"{d.name}: missing {key}")
        lines = body.strip().splitlines()
        if len(lines) > 500:
            warnings.append(f"{d.name}: body {len(lines)} lines (>500): move detail to references/")
        pos = [body.find(s) for s in SECTIONS]
        missing = [s for s, i in zip(SECTIONS, pos) if i < 0]
        if missing:
            errors.append(f"{d.name}: missing sections {missing}")
        elif pos != sorted(pos):
            errors.append(f"{d.name}: sections out of order")
        for link in LINK_RE.findall(body):
            if link.startswith(("http://", "https://")):
                continue
            if not (d / link).exists() and not (ROOT / link).exists():
                errors.append(f"{d.name}: broken link {link}")
    for w in warnings:
        print("warning:", w)
    for e in errors:
        print("error:", e)
    bad = errors + (warnings if strict else [])
    print(f"{len(dirs)} skills, {len(errors)} errors, {len(warnings)} warnings")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
