#!/usr/bin/env python3
"""
PDF to Markdown and HTML Converter

This script processes all PDF files in a directory and converts them to:
1. Markdown (.md) files
2. HTML (.html) files

Requirements:
    pip install pymupdf markdown beautifulsoup4

Usage:
    python pdf_converter.py [input_directory] [output_directory]

    If no arguments provided, uses current directory for input and creates 'converted' subfolder for output.
"""

import os
import sys
import argparse
from pathlib import Path
import fitz  # PyMuPDF
import markdown
from bs4 import BeautifulSoup
import re
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class PDFConverter:
    def __init__(self, input_dir, output_dir):
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)

        # Create output directories
        self.markdown_dir = self.output_dir / 'markdown'
        self.html_dir = self.output_dir / 'html'

        self.markdown_dir.mkdir(parents=True, exist_ok=True)
        self.html_dir.mkdir(parents=True, exist_ok=True)

    def clean_text(self, text):
        """Clean and normalize extracted text"""
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        # Remove weird characters that sometimes appear in PDFs
        text = re.sub(r'[^\w\s\.,;:!?\'"()\-\[\]{}/@#$%^&*+=<>|`~]', '', text)
        # Fix line breaks and paragraphs
        text = re.sub(r'\n\s*\n', '\n\n', text)
        return text.strip()

    def extract_text_from_pdf(self, pdf_path):
        """Extract text content from PDF file"""
        try:
            doc = fitz.open(pdf_path)
            full_text = ""

            for page_num in range(doc.page_count):
                page = doc.load_page(page_num)
                text = page.get_text()

                if text.strip():  # Only add non-empty pages
                    full_text += f"\n\n## Page {page_num + 1}\n\n"
                    full_text += self.clean_text(text)

            doc.close()
            return full_text

        except Exception as e:
            logger.error(f"Error extracting text from {pdf_path}: {str(e)}")
            return None

    def create_markdown(self, text, title):
        """Create properly formatted Markdown content"""
        markdown_content = f"# {title}\n\n"
        markdown_content += text
        return markdown_content

    def create_html(self, markdown_content, title):
        """Convert Markdown to HTML with proper formatting"""
        # Convert markdown to HTML
        html_content = markdown.markdown(markdown_content, extensions=['extra', 'codehilite'])

        # Create full HTML document
        full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            color: #333;
        }}
        h1, h2, h3, h4, h5, h6 {{
            color: #2c3e50;
            margin-top: 1.5em;
            margin-bottom: 0.5em;
        }}
        h1 {{
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }}
        h2 {{
            border-bottom: 1px solid #bdc3c7;
            padding-bottom: 5px;
        }}
        p {{
            margin-bottom: 1em;
            text-align: justify;
        }}
        code {{
            background-color: #f8f9fa;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
        }}
        pre {{
            background-color: #f8f9fa;
            padding: 15px;
            border-radius: 5px;
            overflow-x: auto;
            border-left: 4px solid #3498db;
        }}
    </style>
</head>
<body>
    {html_content}
</body>
</html>"""
        return full_html

    def convert_pdf(self, pdf_path):
        """Convert a single PDF to Markdown and HTML"""
        pdf_name = pdf_path.stem
        logger.info(f"Processing: {pdf_path.name}")

        # Extract text from PDF
        text = self.extract_text_from_pdf(pdf_path)
        if not text:
            logger.warning(f"No text extracted from {pdf_path.name}")
            return False

        # Create Markdown version
        markdown_content = self.create_markdown(text, pdf_name)
        markdown_file = self.markdown_dir / f"{pdf_name}.md"

        try:
            with open(markdown_file, 'w', encoding='utf-8') as f:
                f.write(markdown_content)
            logger.info(f"Created: {markdown_file}")
        except Exception as e:
            logger.error(f"Error writing Markdown file {markdown_file}: {str(e)}")
            return False

        # Create HTML version
        html_content = self.create_html(markdown_content, pdf_name)
        html_file = self.html_dir / f"{pdf_name}.html"

        try:
            with open(html_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
            logger.info(f"Created: {html_file}")
        except Exception as e:
            logger.error(f"Error writing HTML file {html_file}: {str(e)}")
            return False

        return True

    def convert_all_pdfs(self):
        """Convert all PDF files in the input directory"""
        pdf_files = list(self.input_dir.glob("*.pdf"))

        if not pdf_files:
            logger.warning(f"No PDF files found in {self.input_dir}")
            return

        logger.info(f"Found {len(pdf_files)} PDF files to convert")
        successful_conversions = 0

        for pdf_file in pdf_files:
            if self.convert_pdf(pdf_file):
                successful_conversions += 1

        logger.info(f"Successfully converted {successful_conversions}/{len(pdf_files)} PDF files")
        logger.info(f"Markdown files saved to: {self.markdown_dir}")
        logger.info(f"HTML files saved to: {self.html_dir}")

def main():
    parser = argparse.ArgumentParser(description='Convert PDF files to Markdown and HTML')
    parser.add_argument('input_dir', nargs='?', default='.',
                       help='Input directory containing PDF files (default: current directory)')
    parser.add_argument('output_dir', nargs='?', default='./converted',
                       help='Output directory for converted files (default: ./converted)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Validate input directory
    input_path = Path(args.input_dir)
    if not input_path.exists():
        logger.error(f"Input directory does not exist: {input_path}")
        sys.exit(1)

    if not input_path.is_dir():
        logger.error(f"Input path is not a directory: {input_path}")
        sys.exit(1)

    # Create converter and process files
    converter = PDFConverter(args.input_dir, args.output_dir)
    converter.convert_all_pdfs()

if __name__ == "__main__":
    main()