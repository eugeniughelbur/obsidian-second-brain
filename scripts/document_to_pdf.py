#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Eugeniu Ghelbur and contributors
# SPDX-License-Identifier: MIT
# Author: Eugeniu Ghelbur (AI Automation Engineer, AI Tooling Engineer, AI Educator), https://github.com/eugeniughelbur/obsidian-second-brain
# Questions or consulting: e.ghelbur@gmail.com | https://www.linkedin.com/in/eugeniu-ghelbur/ | More: https://theaioperator.io | https://x.com/eugeniu_ghelbur
"""Convert a text document to a temporary PDF with LibreOffice 26.2+.
Print the PDF path; the caller uses normal PDF ingestion and removes its parent folder.
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# https://github.com/LibreOffice/core/commit/625fc73a5784fc5dec06df579a9951908f52a783
PDF_FILTER = "pdf:writer_pdf_Export:" + json.dumps({
    name: {"type": "boolean", "value": str(value).lower()}
    for name, value in {
        "ExportTrackedChanges": False,
        "ExportNotes": False,
        "ExportNotesInMargin": False,
        "UseTaggedPDF": True,
        "UseLosslessCompression": True,
        "ReduceImageResolution": False,
    }.items()
}, separators=(",", ":"))
# A damaged or hostile document can stall LibreOffice; never let it hang the agent.
CONVERT_TIMEOUT = 300


def convert_document(source: Path, soffice: str | None = None) -> Path:
    source = source.expanduser().resolve()
    executable = (
        soffice or shutil.which("soffice.com") or shutil.which("soffice")
        or shutil.which("libreoffice") or "soffice"
    )

    with tempfile.TemporaryDirectory(prefix="obsidian-convert-") as work_dir:
        work = Path(work_dir)
        staged = work / source.name
        shutil.copyfile(source, staged)
        # A private profile keeps conversion independent of desktop sessions.
        subprocess.run(
            [
                executable,
                f"-env:UserInstallation={(work / 'profile').as_uri()}",
                "--headless", "--norestore",
                "--convert-to", PDF_FILTER,
                "--outdir", str(work), str(staged),
            ],
            check=True, stdout=sys.stderr, timeout=CONVERT_TIMEOUT,
        )
        pdf = staged.with_suffix(".pdf")
        destination = Path(tempfile.mkdtemp(prefix="obsidian-ingest-")) / pdf.name
        shutil.move(str(pdf), str(destination))
        return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Selected .docx, .doc, or .odt document")
    parser.add_argument("--soffice", help="LibreOffice executable path (26.2+)")
    args = parser.parse_args()
    try:
        result = convert_document(args.source, args.soffice)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        print(error, file=sys.stderr)
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
