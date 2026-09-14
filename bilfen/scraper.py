"""Bilgi Merkezi (bilfen) sinav sonuclarini kazir.

Onceden kalici Chrome profiliyle (bkz. login_flow.py / login.py) yapilmis bir
giris gerektirir. Sifre bu modulde asla islenmez.
"""
import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

from . import video_capture
from .browser import has_profile, launch_persistent

BASE_URL = "https://bilgimerkezi.bilfen.com"
DATA_DIR = Path(__file__).parent.parent / "data"
EXAMS_PATH = DATA_DIR / "exams.json"


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def get_profile(page):
    page.goto(f"{BASE_URL}/sinav")
    links = page.locator('a[href="/profil"]')
    text = ""
    for i in range(links.count()):
        t = links.nth(i).inner_text().strip()
        if "/" in t:
            text = t
            break
    m = re.search(r"(\d+)\s*/\s*\w+", text)
    grade = int(m.group(1)) if m else None
    return {"raw": text, "grade": grade}


def list_exams(page):
    page.goto(f"{BASE_URL}/sinav")
    rows = page.locator("table").first.locator("tr")
    exams = []
    for i in range(rows.count()):
        row = rows.nth(i)
        link = row.locator("a[href*='/sinav/detay/']")
        if link.count() == 0:
            continue
        href = link.first.get_attribute("href")
        m = re.search(r"/sinav/detay/(\d+)", href or "")
        if not m:
            continue
        cells = row.locator("td").all_inner_texts()
        exams.append({
            "id": m.group(1),
            "name": cells[0].strip() if cells else link.first.inner_text().strip(),
            "date": cells[1].strip() if len(cells) > 1 else None,
        })
    return exams


def get_exam_subjects(page, exam_id):
    page.goto(f"{BASE_URL}/sinav/detay/{exam_id}")
    tables = page.locator("table")
    if tables.count() < 2:
        return []
    rows = tables.nth(1).locator("tr")
    subjects = []
    idx = 0
    for i in range(rows.count()):
        row = rows.nth(i)
        link = row.locator("a")
        if link.count() == 0:
            continue
        idx += 1
        cells = row.locator("td").all_inner_texts()
        cells = [c.strip() for c in cells]

        def as_int(v):
            return int(v) if v.isdigit() else None

        subjects.append({
            "index": idx,
            "name": link.first.inner_text().strip(),
            "correct": as_int(cells[1]) if len(cells) > 1 else None,
            "wrong": as_int(cells[2]) if len(cells) > 2 else None,
            "empty": as_int(cells[3]) if len(cells) > 3 else None,
        })
    return subjects


def get_subject_detail(page, exam_id, subject_index):
    page.goto(f"{BASE_URL}/sinav/detay/{exam_id}/?D={subject_index}")
    try:
        page.wait_for_selector("a[href*='vimeo.com']", timeout=8000)
    except Exception:
        pass

    anchors = page.locator("a[href*='vimeo.com']")
    n = anchors.count()
    questions = []
    for i in range(n):
        a = anchors.nth(i)
        video = a.get_attribute("href")
        is_correct = a.locator("span.fa2-checkmark").count() > 0
        questions.append({"no": i + 1, "correct": is_correct, "video": video})

    try:
        charts = page.evaluate(
            "() => (window.AmCharts && window.AmCharts.charts || []).map(c => c.dataProvider)"
        )
    except Exception:
        charts = []

    topics = []
    for chart_data in charts or []:
        for row in chart_data or []:
            if not isinstance(row, dict) or "category" not in row:
                continue
            topics.append({
                "name": row.get("category"),
                "kID": row.get("kID"),
                "student": _to_float(row.get("column-1")),
                "class_avg": _to_float(row.get("column-2")),
                "school_avg": _to_float(row.get("column-3")),
                "all_schools_avg": _to_float(row.get("column-4")),
            })
    return {"questions": questions, "topics": topics}


def load_cached():
    if not EXAMS_PATH.exists():
        return {}
    try:
        old = json.loads(EXAMS_PATH.read_text(encoding="utf-8"))
        return {e["id"]: e for e in old.get("exams", [])}
    except Exception:
        return {}


def sync_all(headless=True, capture_images=True, force_exam_ids=None):
    """Bilfen'den sinav listesini ceker. Daha once detayi cekilmis bir sinav,
    force_exam_ids icinde belirtilmedigi surece TEKRAR taranmaz (onbellekten
    kullanilir) - boylece her senkronizasyonda ayni sinavlarla ugrasilmaz,
    sadece yeni sinavlar veya acikca istenen sinavlar yeniden islenir."""
    if not has_profile():
        raise RuntimeError(
            "Kayitli oturum bulunamadi. Once web arayuzunden 'Bilfen'e Giris Yap' "
            "adimini tamamlayin (veya 'python login.py' calistirin)."
        )

    force_exam_ids = set(force_exam_ids or [])
    cached = load_cached()

    with sync_playwright() as p:
        context = launch_persistent(p, headless=headless)
        page = context.pages[0] if context.pages else context.new_page()
        try:
            profile = get_profile(page)
            exam_list = list_exams(page)
            exams = []
            for exam in exam_list:
                prev = cached.get(exam["id"])
                if prev and "subjects" in prev and exam["id"] not in force_exam_ids:
                    exams.append(prev)
                    continue

                subjects = get_exam_subjects(page, exam["id"])
                for subj in subjects:
                    if not subj["wrong"]:
                        subj["detail"] = {"questions": [], "topics": []}
                        continue
                    detail = get_subject_detail(page, exam["id"], subj["index"])

                    if capture_images:
                        wrong_nos = [q["no"] for q in detail["questions"] if not q["correct"]]
                        images = video_capture.capture_all_wrong_images(
                            page, exam["id"], subj["index"], wrong_nos,
                            force=exam["id"] in force_exam_ids,
                        )
                        for q in detail["questions"]:
                            path = images.get(q["no"])
                            q["image"] = str(path) if path else None

                    subj["detail"] = detail
                exam["subjects"] = subjects
                exams.append(exam)

            # Bilfen'in sinav listesinde artik gorunmeyen (ör. sayfalama nedeniyle
            # dusen) eski sinavlari da yerel gecmiste tutmaya devam et.
            seen_ids = {e["id"] for e in exams}
            for exam_id, prev in cached.items():
                if exam_id not in seen_ids:
                    exams.append(prev)

            data = {"profile": profile, "exams": exams}
            DATA_DIR.mkdir(exist_ok=True)
            EXAMS_PATH.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return data
        finally:
            context.close()


if __name__ == "__main__":
    result = sync_all(headless=True)
    print(f"{len(result['exams'])} sinav bulundu. Veri kaydedildi: {EXAMS_PATH}")
