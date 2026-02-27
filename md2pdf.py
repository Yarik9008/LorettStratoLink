import markdown
import subprocess
import os
import re
import base64
import urllib.request
import urllib.parse

MD_PATH = "lorett_stratolink_tx_notes.md"
HTML_PATH = os.path.abspath("_tmp_render.html")
PDF_PATH = os.path.abspath("lorett_stratolink_tx_notes.pdf")
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

CSS = """
@page {
    size: A4;
    margin: 18mm 16mm 20mm 16mm;
}

body {
    font-family: "Segoe UI", "Noto Sans", Arial, sans-serif;
    font-size: 10.5pt;
    line-height: 1.5;
    color: #1a1a1a;
    max-width: 100%;
}

h1 {
    font-size: 18pt;
    border-bottom: 2.5px solid #2c3e50;
    padding-bottom: 6px;
    margin-top: 0;
    color: #2c3e50;
}
h2 {
    font-size: 13.5pt;
    color: #2c3e50;
    border-bottom: 1px solid #bdc3c7;
    padding-bottom: 4px;
    margin-top: 20px;
    page-break-after: avoid;
}
h3 {
    font-size: 11.5pt;
    color: #34495e;
    margin-top: 16px;
    page-break-after: avoid;
}
h4 {
    font-size: 10.5pt;
    color: #34495e;
    margin-top: 12px;
    margin-bottom: 4px;
    page-break-after: avoid;
}

p { margin: 6px 0; }

ul, ol {
    margin: 4px 0 4px 6px;
    padding-left: 20px;
}
li { margin-bottom: 3px; }

blockquote {
    border-left: 3px solid #3498db;
    margin: 10px 0;
    padding: 8px 16px;
    background: #eaf2f8;
    color: #2c3e50;
    border-radius: 0 4px 4px 0;
}
blockquote p { margin: 4px 0; }

code {
    font-family: "Cascadia Code", "Consolas", "Courier New", monospace;
    font-size: 9.5pt;
    background: #f0f0f0;
    padding: 1px 5px;
    border-radius: 3px;
}

table {
    border-collapse: collapse;
    width: 100%;
    margin: 8px 0 12px 0;
    font-size: 10pt;
    page-break-inside: avoid;
}
th, td {
    border: 1px solid #bdc3c7;
    padding: 5px 10px;
    text-align: left;
}
th {
    background: #2c3e50;
    color: #ffffff;
    font-weight: 600;
}
tr:nth-child(even) { background: #f7f9fa; }

hr {
    border: none;
    border-top: 1px solid #dce1e4;
    margin: 18px 0;
}

strong { color: #2c3e50; }

.mermaid-diagram {
    text-align: center;
    margin: 12px 0;
    page-break-inside: avoid;
}
.mermaid-diagram img {
    max-width: 100%;
    height: auto;
}
"""


def render_mermaid_to_img_tag(mermaid_code: str) -> str:
    """Render mermaid code to an <img> tag via mermaid.ink API."""
    payload = '{"code":' + __import__("json").dumps(mermaid_code) + ',"mermaid":{"theme":"default"}}'
    encoded = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")
    url = f"https://mermaid.ink/img/{encoded}"
    return f'<div class="mermaid-diagram"><img src="{url}" alt="Структурная схема"></div>'


def replace_mermaid_blocks(md_text: str) -> str:
    """Find ```mermaid ... ``` blocks and replace with image references."""
    pattern = r"```mermaid\s*\n(.*?)```"
    parts = []
    last_end = 0
    for m in re.finditer(pattern, md_text, re.DOTALL):
        parts.append(md_text[last_end:m.start()])
        mermaid_code = m.group(1).strip()
        parts.append(f'\n<MERMAID_PLACEHOLDER:{base64.b64encode(mermaid_code.encode()).decode()}>\n')
        last_end = m.end()
    parts.append(md_text[last_end:])
    return "".join(parts)


def restore_mermaid_in_html(html: str) -> str:
    """Replace MERMAID_PLACEHOLDER with rendered <img> tags."""
    pattern = r"<MERMAID_PLACEHOLDER:(.*?)>"
    def repl(m):
        code = base64.b64decode(m.group(1).encode()).decode()
        return render_mermaid_to_img_tag(code)
    return re.sub(pattern, repl, html)


with open(MD_PATH, encoding="utf-8") as f:
    md_text = f.read()

md_text = replace_mermaid_blocks(md_text)

html_body = markdown.markdown(
    md_text,
    extensions=["tables", "fenced_code", "sane_lists"],
    output_format="html5",
)

html_body = restore_mermaid_in_html(html_body)

html_doc = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<style>{CSS}</style>
</head>
<body>
{html_body}
</body>
</html>"""

with open(HTML_PATH, "w", encoding="utf-8") as f:
    f.write(html_doc)

result = subprocess.run(
    [
        EDGE,
        "--headless",
        "--disable-gpu",
        "--no-pdf-header-footer",
        f"--print-to-pdf={PDF_PATH}",
        HTML_PATH,
    ],
    capture_output=True,
    text=True,
    timeout=30,
)

os.remove(HTML_PATH)

if os.path.isfile(PDF_PATH) and os.path.getsize(PDF_PATH) > 1000:
    size_kb = os.path.getsize(PDF_PATH) / 1024
    print(f"OK: {PDF_PATH} ({size_kb:.0f} KB)")
else:
    print("FAIL")
    print(result.stdout)
    print(result.stderr)
