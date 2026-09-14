"""Sinav verisinden ogrencinin akranlarina gore zayif oldugu konulari cikarir."""


def _peer_avg(topic):
    scores = [
        topic.get("class_avg"),
        topic.get("school_avg"),
        topic.get("all_schools_avg"),
    ]
    scores = [s for s in scores if s is not None]
    return sum(scores) / len(scores) if scores else None


def weak_topics(data):
    """Ogrencinin puaninin akran ortalamasinin altinda kaldigi konulari,
    en buyuk farktan en kucuge dogru siralanmis olarak dondurur."""
    results = []
    for exam in data.get("exams", []):
        for subj in exam.get("subjects", []):
            for topic in subj.get("detail", {}).get("topics", []):
                student = topic.get("student")
                if student is None:
                    continue
                peer_avg = _peer_avg(topic)
                if peer_avg is None:
                    continue
                gap = peer_avg - student
                if gap <= 0:
                    continue
                results.append({
                    "exam_id": exam["id"],
                    "exam_name": exam["name"],
                    "subject_index": subj["index"],
                    "subject_name": subj["name"],
                    "kID": topic.get("kID"),
                    "topic": topic.get("name"),
                    "student": student,
                    "peer_avg": peer_avg,
                    "gap": gap,
                })
    results.sort(key=lambda r: -r["gap"])
    return results
