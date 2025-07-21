#!/usr/bin/env python3
"""
Advanced PDF to Markdown/HTML/Text Converter focused on readability preservation

This script offers multiple conversion strategies:
1. pdfplumber - Superior text extraction and layout analysis
2. pymupdf4llm - AI-optimized extraction for better structure
3. marker-pdf - Advanced layout understanding (if available)
4. Hybrid approach combining multiple methods

Requirements:
    pip install pdfplumber pymupdf4llm markdown beautifulsoup4 pandas

Optional (for best results):
    pip install marker-pdf  # Advanced layout analysis
    pip install unstructured[pdf]  # Alternative parser

Usage:
    python pdf_converter.py [input_directory] [output_directory] --method [pdfplumber|pymupdf4llm|hybrid|marker]

Output Structure:
```
output_directory/
├── markdown/
│   ├── document1.md
│   ├── document2.md
│   └── ...
├── html/
│   ├── document1.html
│   ├── document2.html
│   └── ...
└── text/
    ├── document1.txt
    ├── document2.txt
    └── ...
```
"""

import os
import sys
import argparse
from pathlib import Path
import logging
import re
from typing import List, Dict, Any, Optional
import markdown
import json

# Core libraries
import pdfplumber
import pandas as pd

# Optional advanced libraries
try:
    import pymupdf4llm
    HAS_PYMUPDF4LLM = True
except ImportError:
    HAS_PYMUPDF4LLM = False
    print("pymupdf4llm not available. Install with: pip install pymupdf4llm")

try:
    from marker.convert import convert_single_pdf
    from marker.models import load_all_models
    HAS_MARKER = True
except ImportError:
    HAS_MARKER = False
    print("marker-pdf not available. Install with: pip install marker-pdf")

try:
    from unstructured.partition.pdf import partition_pdf
    HAS_UNSTRUCTURED = True
except ImportError:
    HAS_UNSTRUCTURED = False
    print("unstructured not available. Install with: pip install unstructured[pdf]")

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AdvancedPDFConverter:
    def __init__(self, input_dir, output_dir, method='pdfplumber'):
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.method = method

        # Create output directories
        self.markdown_dir = self.output_dir / 'markdown'
        self.html_dir = self.output_dir / 'html'
        self.text_dir = self.output_dir / 'text'

        self.markdown_dir.mkdir(parents=True, exist_ok=True)
        self.html_dir.mkdir(parents=True, exist_ok=True)
        self.text_dir.mkdir(parents=True, exist_ok=True)

        # Initialize marker models if using marker method
        if method == 'marker' and HAS_MARKER:
            logger.info("Loading marker models (this may take a while on first run)...")
            try:
                self.marker_models = load_all_models()
                logger.info("Marker models loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load marker models: {e}")
                self.marker_models = None
        else:
            self.marker_models = None

    def extract_with_pdfplumber(self, pdf_path: Path) -> str:
        """Extract text using pdfplumber - excellent for layout preservation"""
        logger.info(f"Using pdfplumber extraction for {pdf_path.name}")

        markdown_content = []

        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    if page_num > 1:
                        markdown_content.append(f"\n\n---\n## Page {page_num}\n")

                    # Extract text with layout information
                    text = page.extract_text(layout=True, x_tolerance=3, y_tolerance=3)

                    if text:
                        # Process the text to improve formatting
                        processed_text = self.process_pdfplumber_text(text, page)
                        markdown_content.append(processed_text)

                    # Extract tables separately
                    tables = page.extract_tables()
                    for table in tables:
                        if table and any(any(cell for cell in row if cell) for row in table):
                            table_md = self.table_to_markdown(table)
                            markdown_content.append(f"\n\n{table_md}\n")

            return '\n'.join(markdown_content)

        except Exception as e:
            logger.error(f"Error with pdfplumber extraction: {e}")
            return None

    def process_pdfplumber_text(self, text: str, page) -> str:
        """Process pdfplumber extracted text for better formatting"""
        if not text:
            return ""

        lines = text.split('\n')
        processed_lines = []

        # Get page dimensions for layout analysis
        page_width = page.width
        page_height = page.height

        # Analyze text objects for formatting hints
        chars = page.chars
        line_heights = {}
        line_fonts = {}

        # Group characters by approximate line
        for char in chars:
            y_pos = round(char['y0'], 1)
            if y_pos not in line_heights:
                line_heights[y_pos] = []
                line_fonts[y_pos] = []
            line_heights[y_pos].append(char['size'])
            line_fonts[y_pos].append(char.get('fontname', ''))

        # Calculate average font sizes per line
        avg_font_sizes = {}
        for y_pos, sizes in line_heights.items():
            avg_font_sizes[y_pos] = sum(sizes) / len(sizes) if sizes else 12

        # Find the most common font size (body text)
        all_sizes = [size for sizes in line_heights.values() for size in sizes]
        body_font_size = max(set(all_sizes), key=all_sizes.count) if all_sizes else 12

        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                processed_lines.append("")
                continue

            # Detect headers based on font size, position, and content
            is_header = self.detect_header_pdfplumber(line, avg_font_sizes, body_font_size, page_width)

            # Detect lists
            is_list = self.detect_list_item_simple(line)

            if is_header:
                # Determine header level
                level = min(is_header, 6)
                processed_lines.append(f"{'#' * level} {line}")
            elif is_list:
                processed_lines.append(f"- {line}")
            else:
                # Regular paragraph text
                processed_lines.append(line)

        return '\n'.join(processed_lines)

    def detect_header_pdfplumber(self, line: str, font_sizes: dict, body_size: float, page_width: float) -> int:
        """Detect if a line is a header and return its level"""
        line = line.strip()

        # Common header patterns
        header_patterns = [
            r'^[A-Z][A-Z\s]{10,}$',  # ALL CAPS headers
            r'^\d+\.?\s+[A-Z]',       # Numbered sections
            r'^[A-Z][a-z]+.*:$',      # Title case ending with colon
            r'^(Chapter|Section|Part)\s+\d+',  # Chapter/Section headers
        ]

        # Check patterns
        for pattern in header_patterns:
            if re.match(pattern, line):
                return self.estimate_header_level(line)

        # Check if line is short and could be a header
        if len(line) < 80 and len(line.split()) <= 10:
            # Check if it's title case or sentence case
            words = line.split()
            if words and (words[0][0].isupper() or line.isupper()):
                return self.estimate_header_level(line)

        return 0

    def estimate_header_level(self, line: str) -> int:
        """Estimate header level based on content"""
        line = line.strip()

        # Level 1: Very short, all caps, or contains "chapter"
        if len(line) < 30 and (line.isupper() or 'chapter' in line.lower()):
            return 1

        # Level 2: Numbered sections
        if re.match(r'^\d+\.?\s+', line):
            return 2

        # Level 3: Subsections
        if re.match(r'^\d+\.\d+', line):
            return 3

        # Default to level 2 for detected headers
        return 2

    def detect_list_item_simple(self, line: str) -> bool:
        """Simple list item detection"""
        line = line.strip()
        patterns = [
            r'^[•·▪▫‣⁃]\s+',
            r'^\d+\.\s+',
            r'^[a-zA-Z]\.\s+',
            r'^[-*]\s+',
            r'^\([a-zA-Z0-9]+\)\s+',
        ]

        return any(re.match(pattern, line) for pattern in patterns)

    def extract_with_pymupdf4llm(self, pdf_path: Path) -> str:
        """Extract using pymupdf4llm - optimized for LLM processing"""
        if not HAS_PYMUPDF4LLM:
            logger.error("pymupdf4llm not available")
            return None

        logger.info(f"Using pymupdf4llm extraction for {pdf_path.name}")

        try:
            # pymupdf4llm returns well-formatted markdown directly
            markdown_text = pymupdf4llm.to_markdown(str(pdf_path))
            return markdown_text
        except Exception as e:
            logger.error(f"Error with pymupdf4llm extraction: {e}")
            return None

    def extract_with_marker(self, pdf_path: Path) -> str:
        """Extract using marker - advanced layout understanding"""
        if not HAS_MARKER or not self.marker_models:
            logger.error("Marker not available or models not loaded")
            return None

        logger.info(f"Using marker extraction for {pdf_path.name}")

        try:
            full_text, images, out_meta = convert_single_pdf(
                str(pdf_path),
                self.marker_models,
                max_pages=None,
                langs=None
            )
            return full_text
        except Exception as e:
            logger.error(f"Error with marker extraction: {e}")
            return None

    def extract_with_unstructured(self, pdf_path: Path) -> str:
        """Extract using unstructured library"""
        if not HAS_UNSTRUCTURED:
            logger.error("unstructured library not available")
            return None

        logger.info(f"Using unstructured extraction for {pdf_path.name}")

        try:
            elements = partition_pdf(str(pdf_path))

            markdown_content = []
            for element in elements:
                element_type = str(type(element).__name__)
                text = str(element)

                if 'Title' in element_type:
                    markdown_content.append(f"# {text}")
                elif 'Header' in element_type:
                    markdown_content.append(f"## {text}")
                elif 'ListItem' in element_type:
                    markdown_content.append(f"- {text}")
                elif 'Table' in element_type:
                    markdown_content.append(f"\n{text}\n")
                else:
                    markdown_content.append(text)

            return '\n\n'.join(markdown_content)
        except Exception as e:
            logger.error(f"Error with unstructured extraction: {e}")
            return None

    def extract_hybrid(self, pdf_path: Path) -> str:
        """Hybrid approach - try multiple methods and use the best result"""
        logger.info(f"Using hybrid extraction for {pdf_path.name}")

        results = {}

        # Try each available method
        if HAS_PYMUPDF4LLM:
            results['pymupdf4llm'] = self.extract_with_pymupdf4llm(pdf_path)

        results['pdfplumber'] = self.extract_with_pdfplumber(pdf_path)

        if HAS_MARKER and self.marker_models:
            results['marker'] = self.extract_with_marker(pdf_path)

        if HAS_UNSTRUCTURED:
            results['unstructured'] = self.extract_with_unstructured(pdf_path)

        # Filter out None results
        valid_results = {k: v for k, v in results.items() if v}

        if not valid_results:
            logger.error("All extraction methods failed")
            return None

        # Choose the best result based on length and structure
        best_method = max(valid_results.keys(),
                         key=lambda k: self.score_extraction(valid_results[k]))

        logger.info(f"Best extraction method for {pdf_path.name}: {best_method}")
        return valid_results[best_method]

    def score_extraction(self, text: str) -> float:
        """Score extraction quality based on structure and content"""
        if not text:
            return 0

        score = 0

        # Length bonus (more content is usually better)
        score += min(len(text) / 1000, 10)

        # Header structure bonus
        header_count = len(re.findall(r'^#+\s+', text, re.MULTILINE))
        score += min(header_count * 2, 10)

        # List structure bonus
        list_count = len(re.findall(r'^[-*]\s+', text, re.MULTILINE))
        score += min(list_count * 0.5, 5)

        # Table structure bonus
        table_count = text.count('|')
        score += min(table_count * 0.1, 3)

        # Penalize excessive whitespace
        whitespace_ratio = (text.count('\n') + text.count(' ')) / len(text)
        if whitespace_ratio > 0.3:
            score -= 5

        return score

    def table_to_markdown(self, table: List[List[str]]) -> str:
        """Convert table data to markdown format"""
        if not table or not any(table):
            return ""

        # Clean the table data
        cleaned_table = []
        for row in table:
            cleaned_row = [str(cell).strip() if cell else "" for cell in row]
            cleaned_table.append(cleaned_row)

        if not cleaned_table:
            return ""

        # Create markdown table
        markdown_lines = []

        # Header row
        header = cleaned_table[0]
        markdown_lines.append("| " + " | ".join(header) + " |")

        # Separator row
        separator = "| " + " | ".join(["---"] * len(header)) + " |"
        markdown_lines.append(separator)

        # Data rows
        for row in cleaned_table[1:]:
            # Pad row to match header length
            while len(row) < len(header):
                row.append("")
            markdown_lines.append("| " + " | ".join(row[:len(header)]) + " |")

        return "\n".join(markdown_lines)

    def markdown_to_text(self, markdown_content: str) -> str:
        """Convert markdown to clean plain text"""
        if not markdown_content:
            return ""

        # Remove markdown syntax while preserving structure
        text = markdown_content

        # Convert headers to plain text with spacing
        text = re.sub(r'^#{1,6}\s+(.+)$', r'\1', text, flags=re.MULTILINE)

        # Convert lists to plain text
        text = re.sub(r'^[-*+]\s+(.+)$', r'• \1', text, flags=re.MULTILINE)
        text = re.sub(r'^\d+\.\s+(.+)$', r'\1', text, flags=re.MULTILINE)

        # Remove bold and italic formatting
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)  # Bold
        text = re.sub(r'\*([^*]+)\*', r'\1', text)      # Italic
        text = re.sub(r'__([^_]+)__', r'\1', text)      # Bold alternative
        text = re.sub(r'_([^_]+)_', r'\1', text)        # Italic alternative

        # Convert tables to plain text
        lines = text.split('\n')
        cleaned_lines = []

        for line in lines:
            # Skip table separator lines
            if re.match(r'^\|[\s\-\|]+\|$', line.strip()):
                continue

            # Convert table rows to plain text
            if line.strip().startswith('|') and line.strip().endswith('|'):
                # Remove table markup and clean up spacing
                cells = [cell.strip() for cell in line.split('|')[1:-1]]
                if cells and any(cell for cell in cells):
                    cleaned_lines.append('  '.join(cell for cell in cells if cell))
                continue

            # Remove other markdown syntax
            line = re.sub(r'^\>\s+', '', line)  # Blockquotes
            line = re.sub(r'`([^`]+)`', r'\1', line)  # Inline code
            line = re.sub(r'```[\s\S]*?```', '', line)  # Code blocks
            line = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', line)  # Links

            cleaned_lines.append(line)

        # Join lines and clean up excessive whitespace
        text = '\n'.join(cleaned_lines)

        # Normalize whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)  # Max 2 consecutive newlines
        text = re.sub(r'[ \t]+', ' ', text)     # Multiple spaces to single space
        text = text.strip()

        return text

    def create_html_from_markdown(self, markdown_content: str, title: str) -> str:
        """Convert markdown to well-styled HTML"""
        html_content = markdown.markdown(
            markdown_content,
            extensions=['extra', 'codehilite', 'toc', 'tables', 'fenced_code']
        )

        css = """
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
            line-height: 1.6;
            max-width: 800px;
            margin: 0 auto;
            padding: 2rem;
            color: #333;
        }
        h1, h2, h3, h4, h5, h6 {
            margin-top: 2rem;
            margin-bottom: 1rem;
            font-weight: 600;
            line-height: 1.25;
        }
        h1 { font-size: 2rem; border-bottom: 2px solid #eee; padding-bottom: 0.5rem; }
        h2 { font-size: 1.5rem; }
        h3 { font-size: 1.25rem; }
        p { margin-bottom: 1rem; }
        ul, ol { margin-bottom: 1rem; padding-left: 2rem; }
        li { margin-bottom: 0.25rem; }
        table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
        th, td { border: 1px solid #ddd; padding: 0.5rem; text-align: left; }
        th { background: #f5f5f5; font-weight: 600; }
        code { background: #f5f5f5; padding: 0.2rem 0.4rem; border-radius: 3px; }
        pre { background: #f5f5f5; padding: 1rem; border-radius: 5px; overflow-x: auto; }
        blockquote { border-left: 4px solid #ddd; margin: 1rem 0; padding: 0 1rem; }
        hr { border: none; border-top: 1px solid #eee; margin: 2rem 0; }
        """

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>{css}</style>
</head>
<body>
    {html_content}
</body>
</html>"""

    def convert_pdf(self, pdf_path: Path) -> bool:
        """Convert a single PDF using the specified method"""
        pdf_name = pdf_path.stem
        logger.info(f"Converting {pdf_path.name} using {self.method} method")

        # Choose extraction method
        if self.method == 'pdfplumber':
            content = self.extract_with_pdfplumber(pdf_path)
        elif self.method == 'pymupdf4llm':
            content = self.extract_with_pymupdf4llm(pdf_path)
        elif self.method == 'marker':
            content = self.extract_with_marker(pdf_path)
        elif self.method == 'unstructured':
            content = self.extract_with_unstructured(pdf_path)
        elif self.method == 'hybrid':
            content = self.extract_hybrid(pdf_path)
        else:
            logger.error(f"Unknown method: {self.method}")
            return False

        if not content:
            logger.error(f"Failed to extract content from {pdf_path.name}")
            return False

        # Ensure content starts with document title
        if not content.startswith('#'):
            content = f"# {pdf_name}\n\n{content}"

        # Save Markdown
        markdown_file = self.markdown_dir / f"{pdf_name}.md"
        try:
            with open(markdown_file, 'w', encoding='utf-8') as f:
                f.write(content)
            logger.info(f"Created: {markdown_file}")
        except Exception as e:
            logger.error(f"Error writing Markdown: {e}")
            return False

        # Save Plain Text
        text_content = self.markdown_to_text(content)
        text_file = self.text_dir / f"{pdf_name}.txt"
        try:
            with open(text_file, 'w', encoding='utf-8') as f:
                f.write(text_content)
            logger.info(f"Created: {text_file}")
        except Exception as e:
            logger.error(f"Error writing plain text: {e}")
            return False

        # Save HTML
        html_content = self.create_html_from_markdown(content, pdf_name)
        html_file = self.html_dir / f"{pdf_name}.html"
        try:
            with open(html_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
            logger.info(f"Created: {html_file}")
        except Exception as e:
            logger.error(f"Error writing HTML: {e}")
            return False

        return True

    def convert_all_pdfs(self):
        """Convert all PDFs in the input directory"""
        pdf_files = list(self.input_dir.glob("*.pdf"))

        if not pdf_files:
            logger.warning(f"No PDF files found in {self.input_dir}")
            return

        logger.info(f"Found {len(pdf_files)} PDF files")
        logger.info(f"Using method: {self.method}")

        successful = 0
        for pdf_file in pdf_files:
            if self.convert_pdf(pdf_file):
                successful += 1

        logger.info(f"Successfully converted {successful}/{len(pdf_files)} files")

def main():
    parser = argparse.ArgumentParser(description='Advanced PDF to Markdown/HTML/Text converter')
    parser.add_argument('input_dir', nargs='?', default='.',
                       help='Input directory (default: current directory)')
    parser.add_argument('output_dir', nargs='?', default='./converted',
                       help='Output directory (default: ./converted)')
    parser.add_argument('--method', '-m',
                       choices=['pdfplumber', 'pymupdf4llm', 'marker', 'unstructured', 'hybrid'],
                       default='hybrid',
                       help='Extraction method (default: hybrid)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Verbose logging')

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Validate input
    input_path = Path(args.input_dir)
    if not input_path.exists():
        logger.error(f"Input directory does not exist: {input_path}")
        sys.exit(1)

    # Show available methods
    available_methods = ['pdfplumber']
    if HAS_PYMUPDF4LLM:
        available_methods.append('pymupdf4llm')
    if HAS_MARKER:
        available_methods.append('marker')
    if HAS_UNSTRUCTURED:
        available_methods.append('unstructured')

    logger.info(f"Available methods: {', '.join(available_methods)}")

    if args.method not in available_methods and args.method != 'hybrid':
        logger.error(f"Method {args.method} not available. Install required dependencies.")
        sys.exit(1)

    # Convert PDFs
    converter = AdvancedPDFConverter(args.input_dir, args.output_dir, args.method)
    converter.convert_all_pdfs()

if __name__ == "__main__":
    main()