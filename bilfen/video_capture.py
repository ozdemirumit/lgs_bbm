"""Yanlis yapilan sorularin video cozumunden (Lity lightbox + Vimeo) ekran goruntusu yakalar.

Bilfen sitesi her soru numarasina bir Vimeo video cozumu baglar (data-lity ile acilan
bir lightbox icinde). Bu video, sorunun orijinal metnini ve secenekleri gosteren bir
Doceri kaydidir (ogretmen elle isaretleyerek anlatir). Bu modul API/Anthropic
cagirmaz; sadece tarayici ile ekran goruntusu alir.
"""
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
IMAGES_DIR = DATA_DIR / "question_images"

BASE_URL = "https://bilgimerkezi.bilfen.com"


def capture_wrong_question_image(page, exam_id, subject_index, question_no, force=False):
    """Belirtilen soru numarasina tiklayip acilan video kutusunun ekran goruntusunu
    data/question_images/ altina kaydeder. Basarili olursa Path, olmazsa None doner."""
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    out_path = IMAGES_DIR / f"{exam_id}_{subject_index}_{question_no}.png"
    if out_path.exists() and not force:
        return out_path

    page.goto(f"{BASE_URL}/sinav/detay/{exam_id}/?D={subject_index}")
    anchors = page.locator("a[href*='vimeo.com']")
    if anchors.count() < question_no:
        return None

    anchor = anchors.nth(question_no - 1)
    href = anchor.get_attribute("href") or ""
    if href.rstrip("/").endswith("/0"):
        # video baglantisi yok
        return None

    try:
        anchor.click()
        page.wait_for_selector(".lity, .lity-iframe-container, .lity-content", timeout=8000)
        page.wait_for_timeout(2000)

        dialog = page.locator(".lity-content").first
        if dialog.count() == 0:
            dialog = page.locator(".lity-iframe-container").first
        if dialog.count() > 0:
            dialog.screenshot(path=str(out_path))
        else:
            page.screenshot(path=str(out_path))
    except Exception:
        try:
            page.screenshot(path=str(out_path))
        except Exception:
            return None
    finally:
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
        except Exception:
            pass

    return out_path if out_path.exists() else None


def capture_all_wrong_images(page, exam_id, subject_index, wrong_question_numbers, force=False):
    """Bir dersteki tum yanlis sorular icin ekran goruntusu yakalar.
    {question_no: Path|None} sozlugu doner."""
    results = {}
    for qno in wrong_question_numbers:
        results[qno] = capture_wrong_question_image(page, exam_id, subject_index, qno, force=force)
    return results
