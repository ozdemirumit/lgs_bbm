// Arka planda (baska bir sekmede "Yeniden Analiz Et" veya bir konu uretimi
// suruyorken) bu sayfadaki "Çalış" butonlarinin, sayfa yenilenmeden "Aç"a
// donmesini saglar. data-topic attribute'lu her ".weak-topic-item" icin
// birkac saniyede bir /api/cached_status sorgulanir.
(function () {
  function collectItems() {
    return Array.from(document.querySelectorAll(".weak-topic-item:not(.is-ready)")).map(
      (el) => ({
        exam_id: el.dataset.examId,
        subject_index: parseInt(el.dataset.subjectIndex, 10),
        kID: el.dataset.kid,
      })
    );
  }

  function markReady(el) {
    el.classList.add("is-ready");
    const badgeSlot = el.querySelector(".cached-badge-slot");
    if (badgeSlot && !badgeSlot.querySelector(".badge")) {
      badgeSlot.innerHTML = '<span class="badge bg-success">hazır</span>';
    }
    const btn = el.querySelector(".topic-action-btn");
    if (btn) {
      btn.textContent = "Aç";
      btn.classList.remove("btn-outline-danger");
      btn.classList.add("btn-outline-success");
    }
  }

  async function poll() {
    const items = collectItems();
    if (!items.length) return;
    let status;
    try {
      const res = await fetch("/api/cached_status", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items }),
      });
      if (!res.ok) return;
      status = await res.json();
    } catch (e) {
      return; // sessizce yut, bir sonraki turda tekrar dener
    }
    document.querySelectorAll(".weak-topic-item:not(.is-ready)").forEach((el) => {
      const key = `${el.dataset.examId}_${el.dataset.subjectIndex}_${el.dataset.kid}`;
      if (status[key]) markReady(el);
    });
  }

  if (document.querySelector(".weak-topic-item")) {
    poll();
    setInterval(poll, 8000);
  }
})();
