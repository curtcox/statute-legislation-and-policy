dependencies = ["requests>=2.31", "beautifulsoup4", "tqdm"]

"""
download_rsa_docs.py
Download https://rsa.ed.gov/statute-legislation-and-policy/sub-regulatory-guidance
and every referenced document to a local folder (macOS-friendly).

Usage:
    python3 download_rsa_docs.py -o ./rsa_guidance
"""
import argparse, os, sys, time, urllib.parse as up
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

PAGE_URL = "https://rsa.ed.gov/statute-legislation-and-policy/sub-regulatory-guidance"
# add or remove extensions here if you need other file types
DOC_EXTS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".html", ".htm"}

def get_soup(url: str) -> BeautifulSoup:
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")

def sanitize(name: str) -> str:
    name = name.split("?")[0]            # drop query strings
    return "".join(c for c in name if c not in r'\/:*?"<>|').strip()

def download_file(url: str, dest: Path, tries: int = 3):
    for attempt in range(1, tries + 1):
        try:
            with requests.get(url, stream=True, timeout=30) as r:
                r.raise_for_status()
                total = int(r.headers.get("content-length", 0))
                with tqdm(total=total, unit="B", unit_scale=True, desc=dest.name) as bar, \
                        open(dest, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            bar.update(len(chunk))
            return
        except Exception as e:
            if attempt == tries:
                print(f"❌ gave up on {url}: {e}")
            else:
                time.sleep(2)
    # if we drop out, caller continues

def main(out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Fetching main page…")
    soup = get_soup(PAGE_URL)
    (out_dir / "sub-regulatory-guidance.html").write_text(soup.prettify(), encoding="utf-8")

    # extract unique document links
    seen = set()
    doc_links = []
    for tag in soup.find_all("a", href=True):
        href = up.urljoin(PAGE_URL, tag["href"])
        ext = Path(up.urlparse(href).path).suffix.lower()
        if ext in DOC_EXTS and href not in seen:
            seen.add(href)
            doc_links.append(href)

    print(f"Found {len(doc_links)} referenced document(s). Starting download…\n")

    for url in doc_links:
        filename = sanitize(Path(up.urlparse(url).path).name) or f"file{len(seen)}"
        dest = out_dir / filename
        if dest.exists():
            print(f"✔ already have {filename}")
            continue
        download_file(url, dest)

    print("\n✅ All done. Files saved to:", out_dir.resolve())

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download RSA sub-regulatory guidance docs.")
    parser.add_argument("-o", "--out-dir", default="rsa_guidance", type=Path,
                        help="Folder to save the page and its documents.")
    args = parser.parse_args()
    try:
        main(args.out_dir)
    except KeyboardInterrupt:
        sys.exit("\nInterrupted.")
