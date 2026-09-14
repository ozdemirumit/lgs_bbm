"""Zayif konular + uretilen icerikten Word raporu olusturur."""
from pathlib import Path

from docx import Document


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

        content = item["content"]
        doc.add_heading("Konu Anlatimi", level=3)
        doc.add_paragraph(content.get("anlatim", ""))

        doc.add_heading("Benzer Sorular", level=3)
        for i, q in enumerate(content.get("sorular", []), 1):
            p = doc.add_paragraph()
            p.add_run(f"{i}. {q.get('soru', '')}").bold = True
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
