"""Sinav verisinden ogrencinin yanlis yaptigi/eksik oldugu konulari cikarir."""


def _peer_avg(topic):
    scores = [
        topic.get("class_avg"),
        topic.get("school_avg"),
        topic.get("all_schools_avg"),
    ]
    scores = [s for s in scores if s is not None]
    return sum(scores) / len(scores) if scores else None


def weak_topics(data):
    """Icinde en az bir yanlisin oldugu (puani %100'un altinda olan) tum
    konulari dondurur - akran ortalamasinin altinda olsun ya da olmasin,
    amac ogrencinin gercekten yanlis yaptigi her konuyu calisabilmesi.
    Akran karsilastirmasi (gap) bilgi/siralama icin hesaplanir: en cok
    akranlarin gerisinde kalinan konular basta, ama akranlardan iyi
    olunan konular da (dusuk oncelikle) listede kalir."""
    results = []
    for exam in data.get("exams", []):
        for subj in exam.get("subjects", []):
            for topic in subj.get("detail", {}).get("topics", []):
                student = topic.get("student")
                if student is None or student >= 100:
                    continue
                peer_avg = _peer_avg(topic)
                gap = (peer_avg - student) if peer_avg is not None else None
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
    results.sort(key=lambda r: (r["gap"] if r["gap"] is not None else -999), reverse=True)
    return results
