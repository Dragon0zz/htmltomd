#!/usr/bin/env python3
"""
confluence_html_to_md.py

Chuyen doi file HTML export tu Confluence sang Markdown, phuc vu cho agent doc.
CHI dung thu vien chuan (standard library) cua Python: html.parser, re, pathlib.
KHONG can pip install / uvx / bat ky package ngoai nao.

Cach dung:
    python confluence_html_to_md.py input.html output.md
    python confluence_html_to_md.py input_dir/ output_dir/      # convert hang loat *.html/*.htm

Ghi chu:
- Phu hop voi HTML export "chuan" cua Confluence (Space Export > HTML), noi cac macro
  (code, panel, table, ...) da duoc render thanh the HTML thong thuong.
- Neu input la XML storage format (co the ac:*, ri:* namespace tags), script van chay
  duoc (khong crash) nhung se bo qua thuoc tinh macro, chi lay text ben trong.
- Bang (table) khong ho tro rowspan/colspan (se render phang thanh o rieng).
"""

import sys
import re
import html
from pathlib import Path
from html.parser import HTMLParser


class MarkdownHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.output = []
        self.list_stack = []          # stack cua ['ul'|'ol', counter]
        self.in_pre = False
        self.skip_stack = []          # dang trong script/style thi bo qua
        self.in_table = False
        self.table_rows = []
        self.current_row = []
        self.in_cell = False
        self.cell_is_header = False
        self.current_cell = []
        self.in_link = False
        self.link_href = None
        self.link_text = []

    # ---------- helpers ----------
    def _newline(self):
        if self.output and not self.output[-1].endswith('\n'):
            self.output.append('\n')

    def _flush_table(self):
        if not self.table_rows:
            return
        self._newline()
        header = self.table_rows[0]
        cols = len(header)
        header_line = '| ' + ' | '.join(c.replace('|', '\\|') for c in header) + ' |'
        sep_line = '| ' + ' | '.join('---' for _ in range(cols)) + ' |'
        self.output.append(header_line + '\n' + sep_line + '\n')
        for row in self.table_rows[1:]:
            cells = [c.replace('|', '\\|') for c in row]
            while len(cells) < cols:
                cells.append('')
            self.output.append('| ' + ' | '.join(cells[:cols]) + ' |\n')
        self.output.append('\n')
        self.table_rows = []

    # ---------- HTMLParser overrides ----------
    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag in ('script', 'style'):
            self.skip_stack.append(tag)
            return
        if self.skip_stack:
            return

        if tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            level = int(tag[1])
            self._newline()
            self.output.append('#' * level + ' ')
        elif tag == 'p':
            self._newline()
        elif tag == 'br':
            self.output.append('  \n')
        elif tag in ('strong', 'b'):
            self.output.append('**')
        elif tag in ('em', 'i'):
            self.output.append('*')
        elif tag == 'pre':
            self.in_pre = True
            self._newline()
            self.output.append('```\n')
        elif tag == 'code' and not self.in_pre:
            self.output.append('`')
        elif tag == 'a':
            self.in_link = True
            self.link_href = attrs_dict.get('href', '')
            self.link_text = []
        elif tag == 'img':
            src = attrs_dict.get('src', '')
            alt = attrs_dict.get('alt', 'image')
            self.output.append(f'![{alt}]({src})')
        elif tag in ('ul', 'ol'):
            self.list_stack.append([tag, 0])
            self._newline()
        elif tag == 'li':
            self._newline()
            indent = '  ' * max(0, len(self.list_stack) - 1)
            if self.list_stack and self.list_stack[-1][0] == 'ol':
                self.list_stack[-1][1] += 1
                marker = f'{self.list_stack[-1][1]}.'
            else:
                marker = '-'
            self.output.append(f'{indent}{marker} ')
        elif tag == 'blockquote':
            self._newline()
            self.output.append('> ')
        elif tag == 'hr':
            self._newline()
            self.output.append('---\n')
        elif tag == 'table':
            self.in_table = True
            self.table_rows = []
        elif tag == 'tr':
            self.current_row = []
        elif tag in ('td', 'th'):
            self.in_cell = True
            self.cell_is_header = (tag == 'th')
            self.current_cell = []
        # cac the khac (div, span, ac:*, ri:*, ...) khong xu ly rieng -> fallthrough,
        # text ben trong van duoc lay qua handle_data.

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            if self.skip_stack and self.skip_stack[-1] == tag:
                self.skip_stack.pop()
            return
        if self.skip_stack:
            return

        if tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            self.output.append('\n\n')
        elif tag == 'p':
            self.output.append('\n\n')
        elif tag in ('strong', 'b'):
            self.output.append('**')
        elif tag in ('em', 'i'):
            self.output.append('*')
        elif tag == 'pre':
            self.in_pre = False
            self._newline()
            self.output.append('```\n\n')
        elif tag == 'code' and not self.in_pre:
            self.output.append('`')
        elif tag == 'a':
            text = ''.join(self.link_text).strip()
            if self.link_href and text:
                self.output.append(f'[{text}]({self.link_href})')
            elif text:
                self.output.append(text)
            self.in_link = False
            self.link_href = None
            self.link_text = []
        elif tag in ('ul', 'ol'):
            if self.list_stack:
                self.list_stack.pop()
            self.output.append('\n')
        elif tag == 'li':
            self.output.append('\n')
        elif tag == 'blockquote':
            self.output.append('\n\n')
        elif tag in ('td', 'th'):
            self.in_cell = False
            self.current_row.append(''.join(self.current_cell).strip())
        elif tag == 'tr':
            if self.current_row:
                self.table_rows.append(self.current_row)
        elif tag == 'table':
            self._flush_table()
            self.in_table = False

    def handle_data(self, data):
        if self.skip_stack:
            return
        if self.in_link:
            self.link_text.append(data)
            return
        if self.in_cell:
            self.current_cell.append(data)
            return
        if self.in_pre:
            self.output.append(data)
            return
        if not data.strip():
            # Text node chi chua whitespace (vd: xuong dong/thut le giua cac the
            # block trong HTML goc). Neu dang o dau dong/block moi thi bo qua
            # hoan toan; neu dang giua noi dung inline thi giu lai 1 khoang trang.
            if self.output and not self.output[-1].endswith(('\n', ' ')):
                self.output.append(' ')
            return
        text = re.sub(r'\s+', ' ', data)
        self.output.append(text)

    def get_markdown(self):
        text = ''.join(self.output)
        text = html.unescape(text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        lines = [l.rstrip() if not l.endswith('  ') else l for l in text.split('\n')]
        text = '\n'.join(lines)
        return text.strip() + '\n'


def convert_html_to_md(html_text: str) -> str:
    parser = MarkdownHTMLParser()
    parser.feed(html_text)
    parser.close()
    return parser.get_markdown()


def convert_file(src: Path, dst: Path):
    html_text = src.read_text(encoding='utf-8', errors='ignore')
    md_text = convert_html_to_md(html_text)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(md_text, encoding='utf-8')
    print(f'  {src.name} -> {dst}')


def main():
    if len(sys.argv) != 3:
        print('Cach dung:')
        print('  python confluence_html_to_md.py input.html output.md')
        print('  python confluence_html_to_md.py input_dir/ output_dir/')
        sys.exit(1)

    src_path = Path(sys.argv[1])
    dst_path = Path(sys.argv[2])

    if src_path.is_dir():
        html_files = sorted(src_path.rglob('*.html')) + sorted(src_path.rglob('*.htm'))
        if not html_files:
            print(f'Khong tim thay file .html/.htm nao trong {src_path}')
            sys.exit(1)
        print(f'Tim thay {len(html_files)} file HTML, dang chuyen doi...')
        for f in html_files:
            rel = f.relative_to(src_path)
            out_file = dst_path / rel.with_suffix('.md')
            convert_file(f, out_file)
        print(f'\nHoan tat. Output tai: {dst_path}')
    else:
        convert_file(src_path, dst_path)
        print('Hoan tat.')


if __name__ == '__main__':
    main()
