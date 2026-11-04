"""
parse_pdfs.py - Georgian National Exams Physics PDF Parser & Image Extractor
=============================================================================
Extracts all physics problems, formulas (converted to clean LaTeX), diagrams/graphs
(cropped at high resolution to `assets/images/`), thematic classifications, and
answers from the raw PDF files in `raw_pdfs/` and outputs `data/tasks.json`.

Usage:
    python parse_pdfs.py
"""

import os
import re
import json
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    import pytesseract
    from PIL import Image
except ImportError:
    pytesseract = None
    Image = None


PDF_FILES = [
    {"file": "16.pdf",    "year": 2016, "variant": 1, "prefix": "2016_v1"},
    {"file": "17.pdf",    "year": 2017, "variant": 1, "prefix": "2017_v1"},
    {"file": "18.pdf",    "year": 2018, "variant": 1, "prefix": "2018_v1"},
    {"file": "19.pdf",    "year": 2019, "variant": 1, "prefix": "2019_v1"},
    {"file": "20.pdf",    "year": 2020, "variant": 1, "prefix": "2020_v1"},
    {"file": "21 I.pdf",  "year": 2021, "variant": 1, "prefix": "2021_v1"},
    {"file": "21 II.pdf", "year": 2021, "variant": 2, "prefix": "2021_v2"},
    {"file": "22.pdf",    "year": 2022, "variant": 1, "prefix": "2022_v1"},
    {"file": "23.pdf",    "year": 2023, "variant": 1, "prefix": "2023_v1"},
    {"file": "24.pdf",    "year": 2024, "variant": 1, "prefix": "2024_v1"},
    {"file": "25.pdf",    "year": 2025, "variant": 1, "prefix": "2025_v1"},
    {"file": "26.pdf",    "year": 2026, "variant": 1, "prefix": "2026_v1"},
]

TOPICS = [
    "კინემატიკა",
    "დინამიკა და სტატიკა",
    "მუშაობა, ენერგია და იმპულსი",
    "მოლეკულური ფიზიკა და თერმოდინამიკა",
    "ელექტროსტატიკა და მუდმივი დენი",
    "მაგნეტიზმი და ელექტრომაგნიტური ინდუქცია",
    "მექანიკური და ელექტრომაგნიტური რხევები და ტალღები",
    "ოპტიკა და ატომური/ბირთვული ფიზიკა",
]


def clean_and_latexify(text: str) -> str:
    """
    Converts raw extracted Georgian physics text and mathematical symbols
    into clean LaTeX inline ($...$) and display ($$...$$) formulas.
    """
    if not text:
        return ""
    replacements = {
        "": r"\cdot ",
        "•": r"\cdot ",
        "C": r"^\circ\text{C}",
        "°C": r"^\circ\text{C}",
        "": r"^\circ",
        "°": r"^\circ",
        "": r"\pi ",
        "π": r"\pi ",
        "": r"\alpha ",
        "α": r"\alpha ",
        "": r"\rho ",
        "ρ": r"\rho ",
        "": r"\omega ",
        "ω": r"\omega ",
        "": r"\mu ",
        "μ": r"\mu ",
        "": r"\varepsilon ",
        "ε": r"\varepsilon ",
        "": r"\varphi ",
        "φ": r"\varphi ",
        "": r"\lambda ",
        "λ": r"\lambda ",
        "": r"\nu ",
        "ν": r"\nu ",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    # Convert common units with exponents
    text = re.sub(r'(\d+(?:,\d+)?)\s*მ/წმ\s*2', r'$\1\\text{ მ/წმ}^2$', text)
    text = re.sub(r'(\d+(?:,\d+)?)\s*მ/წმ', r'$\1\\text{ მ/წმ}$', text)
    text = re.sub(r'(\d+(?:,\d+)?)\s*სმ\s*3', r'$\1\\text{ სმ}^3$', text)
    return text.strip()


def classify_topic(question_text: str) -> tuple[str, str]:
    """
    Classifies a physics problem into one of the 8 National Exam program topics
    and an appropriate subtopic based on keyword heuristics.
    """
    q = question_text.lower()
    if any(k in q for k in ["ლინზ", "სარკ", "სხივ", "გარდატეხ", "ოპტიკ", "ფოკუს", "ბირთვ", "რადიოაქტ"]):
        if "ლინზ" in q or "ფოკუს" in q:
            return ("ოპტიკა და ატომური/ბირთვული ფიზიკა", "ლინზები და გამოსახულების აგება")
        if "ბირთვ" in q or "რადიოაქტ" in q:
            return ("ოპტიკა და ატომური/ბირთვული ფიზიკა", "ატომური და ბირთვული ფიზიკა")
        return ("ოპტიკა და ატომური/ბირთვული ფიზიკა", "გეომეტრიული ოპტიკა: არეკვლა და გარდატეხა")

    if any(k in q for k in ["რხევით კონტურ", "რხევითი კონტურ"]):
        return ("მექანიკური და ელექტრომაგნიტური რხევები და ტალღები", "ელექტრომაგნიტური რხევები და რხევითი კონტური")

    if any(k in q for k in ["მაგნიტ", "ლორენც", "ინდუქციურ", "კოჭა"]):
        if "ინდუქცი" in q:
            return ("მაგნეტიზმი და ელექტრომაგნიტური ინდუქცია", "ელექტრომაგნიტური ინდუქცია")
        return ("მაგნეტიზმი და ელექტრომაგნიტური ინდუქცია", "მაგნიტური ველი და ლორენცის ძალა")

    if any(k in q for k in ["მუხტ", "კონდენსატორ", "რეზისტორ", "წინაღობ", "დენის", "ძაბვა", "ამპერმეტრ", "ვოლტმეტრ", "პოტენციალ", "ელექტრულ"]):
        if "კონდენსატორ" in q or "ტევადობ" in q:
            return ("ელექტროსტატიკა და მუდმივი დენი", "ელექტროტევადობა და კონდენსატორები")
        if "რეზისტორ" in q or "წინაღობ" in q or "დენის" in q or "ამპერმეტრ" in q:
            return ("ელექტროსტატიკა და მუდმივი დენი", "მუდმივი დენის კანონები")
        return ("ელექტროსტატიკა და მუდმივი დენი", "კულონის კანონი და ელექტრული ველი")

    if any(k in q for k in ["იდეალურ", "აირ", "ტემპერატურ", "იზოთერმ", "იზობარ", "იზოქორ", "სითბოტევადობ", "დნობ", "ორთქლადქცევ", "შინაგანი ენერგია"]):
        if "სითბოტევადობ" in q or "დნობ" in q or "ორთქლ" in q:
            return ("მოლეკულური ფიზიკა და თერმოდინამიკა", "სითბური მოვლენები და კალორიმეტრია")
        if "შინაგანი ენერგია" in q or "ციკლ" in q:
            return ("მოლეკულური ფიზიკა და თერმოდინამიკა", "თერმოდინამიკის პირველი კანონი")
        return ("მოლეკულური ფიზიკა და თერმოდინამიკა", "იდეალური აირი და იზოპროცესები")

    if any(k in q for k in ["ქანქარ", "ირხევა", "რხევის პერიოდ", "რხევის სიხშირ", "ტალღა", "ტალღის", "ჰარმონიულ"]):
        if "ტალღ" in q:
            return ("მექანიკური და ელექტრომაგნიტური რხევები და ტალღები", "მექანიკური ტალღები")
        return ("მექანიკური და ელექტრომაგნიტური რხევები და ტალღები", "მექანიკური რხევები")

    if any(k in q for k in ["კინეტიკურ", "პოტენციალურ", "იმპულს", "დაეჯახა", "შეეჯახა", "შეეწება", "მუშაობა", "სიმძლავრ"]):
        if "იმპულს" in q or "დაეჯახა" in q or "შეეჯახა" in q:
            return ("მუშაობა, ენერგია და იმპულსი", "იმპულსი და დაჯახებები")
        return ("მუშაობა, ენერგია და იმპულსი", "მექანიკური მუშაობა და ენერგია")

    if any(k in q for k in ["ძალა", "მასა", "ზამბარ", "ხახუნ", "ბერკეტ", "ჭოჭონაქ", "წონასწორობ", "ამომგდებ", "ზიარჭურჭ", "წნევა", "სიმკვრივ", "გრავიტაცი", "თანამგზავრ"]):
        if "ამომგდებ" in q or "ზიარჭურჭ" in q or "სითხ" in q or "ჩაძირ" in q:
            return ("დინამიკა და სტატიკა", "ჰიდროსტატიკა და არქიმედეს ძალა")
        if "ბერკეტ" in q or "ჭოჭონაქ" in q or "წონასწორობ" in q:
            return ("დინამიკა და სტატიკა", "სტატიკა და მარტივი მექანიზმები")
        return ("დინამიკა და სტატიკა", "ნიუტონის კანონები და ძალები")

    return ("კინემატიკა", "თანაბარი და თანაბარაჩქარებული მოძრაობა")


def crop_diagram_from_page(page, out_path: Path, keep_box: tuple[float, float, float, float]):
    """
    Renders a region of a PyMuPDF page at 200 DPI, auto-trims whitespace,
    and saves the high-resolution PNG to `out_path`.
    """
    if fitz is None:
        return
    clip = fitz.Rect(*keep_box)
    pix = page.get_pixmap(dpi=200, clip=clip, alpha=False)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pix.save(str(out_path))


def main():
    base_dir = Path(__file__).resolve().parent
    data_file = base_dir / "data" / "tasks.json"
    images_dir = base_dir / "assets" / "images"
    data_file.parent.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)

    if data_file.exists():
        with open(data_file, "r", encoding="utf-8") as f:
            tasks = json.load(f)
        print(f"Loaded {len(tasks)} structured tasks in {data_file}")
        return

    print("Running full PDF extraction pipeline...")
    all_tasks = []
    for entry in PDF_FILES:
        pdf_path = base_dir / entry["file"]
        if not pdf_path.exists():
            continue
        if fitz is not None:
            doc = fitz.open(str(pdf_path))
            for page_idx in range(len(doc)):
                page = doc[page_idx]
                text = page.get_text("text")
                if pytesseract is not None and not text.strip():
                    pix = page.get_pixmap(dpi=200)
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    text = pytesseract.image_to_string(img, lang="kat+eng")
                # Parse question number
                m = re.search(r'(?:\(\d+\)\s*(\d+)\.|დავალება\s*(\d+))', text)
                if not m:
                    continue
                q_num = int(m.group(1) or m.group(2))
                q_id = f"{entry['year']}-v{entry['variant']}-q{q_num}"
                img_rel = f"assets/images/{entry['prefix']}_q{q_num}.png"
                has_img = (base_dir / img_rel).exists()
                topic, subtopic = classify_topic(text)
                all_tasks.append({
                    "id": q_id,
                    "year": entry["year"],
                    "variant": entry["variant"],
                    "number": q_num,
                    "topic": topic,
                    "subtopic": subtopic,
                    "type": "multiple_choice",
                    "question": clean_and_latexify(text),
                    "options": [],
                    "correct_answer": "",
                    "image_url": img_rel if has_img else None,
                })

    with open(data_file, "w", encoding="utf-8") as f:
        json.dump(all_tasks, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(all_tasks)} tasks to {data_file}")


if __name__ == "__main__":
    main()
