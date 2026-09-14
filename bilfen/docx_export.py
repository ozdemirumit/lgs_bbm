"""Zayif konular + uretilen icerikten Word raporu olusturur.

Web arayuzunde konu anlatimi/sorular icinde HTML tablo ve SVG sekiller
olabilir (bkz. content_generator). Word bunlari dogrudan render edemez:
tablolar gercek bir docx tablosuna cevrilir, SVG'ler icin bir not birakilir.
"""
import re
from pathlib import Path

from docx import Document


def _strip_tags(text):
    text = re.sub(r"<svg[\s\S]*?</svg>", "[Şekil: bu görseli web uygulamasında görebilirsiniz]", text)
    text = re.sub(r"<[^>]+>", "", text)
    return text


def _extract_tables(html):
    """HTML icindeki <table> bloklarini satir/hucre listesi olarak cikarir,
    geri kalan metni bir yer tutucuyla birlikte dondurur."""
    tables = []

    def repl(m):
        tables.append(m.group(0))
        return f"\x00TABLE{len(tables) - 1}\x00"

    remaining = re.sub(r"<table[\s\S]*?</table>", repl, html)
    parsed_tables = []
    for t in tables:
        rows = re.findall(r"<tr[^>]*>([\s\S]*?)</tr>", t)
        parsed_rows = []
        for row in rows:
            cells = re.findall(r"<t[hd][^>]*>([\s\S]*?)</t[hd]>", row)
            parsed_rows.append([_strip_tags(c).strip() for c in cells])
        parsed_tables.append(parsed_rows)
    return remaining, parsed_tables


def _add_rich_content(doc, html_text):
    """Markdown/HTML karisik metni dokumana ekler; <table> varsa gercek Word
    tablosuna cevirir, geri kalan HTML etiketlerini temizler."""
    if not html_text:
        return
    remaining, tables = _extract_tables(html_text)
    for part in re.split(r"(\x00TABLE\d+\x00)", remaining):
        m = re.match(r"\x00TABLE(\d+)\x00", part)
        if m:
            rows = tables[int(m.group(1))]
            if not rows:
                continue
            table = doc.add_table(rows=len(rows), cols=max(len(r) for r in rows))
            table.style = "Table Grid"
            for i, row in enumerate(rows):
                for j, cell in enumerate(row):
                    table.cell(i, j).text = cell
        else:
            text = _strip_tags(part).strip()
            if text:
                for para in text.split("\n\n"):
                    para = para.strip()
                    if para:
                        doc.add_paragraph(para)


def build_exam_report(exam, weak_topics_with_content, output_path):
    doc = Document()
    doc.add_heading(f"{exam['name']} - Hata Analizi Raporu", level=1)
    doc.add_paragraph(f"Tarih: {exam.get('date', '-')}")

    if not weak_topics_with_content:
        doc.add_paragraph("Bu sinavda akran ortalamasinin altinda kalinan bir konu tespit edilmedi.")

    for item in weak_topics_with_content:
        doc.add_heading(f"{item['subject_name']} - {item['topic']}", level=2)
        doc.add_paragraph(
            f"Ogrenci puani: %{item['student']:.1f}  |  Akran ortalamasi: %{item['peer_avg']:.1f}"
        )

        wrong_questions = item.get("wrong_questions") or []
        if wrong_questions:
            doc.add_heading("Gercekten Yanlis Yapilan Soru(lar)", level=3)
            for wq in wrong_questions:
                if not wq.get("okunabildi", True):
                    continue
                doc.add_paragraph(wq.get("soru", ""))
                for key in ["A", "B", "C", "D"]:
                    val = wq.get("secenekler", {}).get(key, "")
                    marker = " (dogru)" if wq.get("isaretli_dogru_cevap") == key else ""
                    doc.add_paragraph(f"    {key}) {val}{marker}")
                if wq.get("image_url"):
                    doc.add_paragraph("(Orijinal soru gorseli/tablosu icin web uygulamasina bakin)")

        content = item["content"]
        doc.add_heading("Konu Anlatimi", level=3)
        _add_rich_content(doc, content.get("anlatim", ""))

        doc.add_heading("Benzer Sorular", level=3)
        for i, q in enumerate(content.get("sorular", []), 1):
            p = doc.add_paragraph()
            p.add_run(f"{i}. {q.get('soru', '')}").bold = True
            if q.get("kaynak_notu"):
                doc.add_paragraph(f"    (LGS'den ilham alindi: {q['kaynak_notu']})")
            if q.get("gorsel_html"):
                _add_rich_content(doc, q["gorsel_html"])
            for key in ["A", "B", "C", "D"]:
                val = q.get("secenekler", {}).get(key, "")
                doc.add_paragraph(f"    {key}) {val}")

        doc.add_heading("Cevap Anahtari ve Cozumler", level=3)
        for i, q in enumerate(content.get("sorular", []), 1):
            doc.add_paragraph(f"{i}. Dogru cevap: {q.get('dogru_cevap', '?')} - {q.get('cozum', '')}")

        doc.add_page_break()

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))
    return output_path
