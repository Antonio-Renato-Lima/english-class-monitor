// app.js - Monitor & Caderno de Estudos para Aulas de Inglês

let recordingInterval = null;
let currentActiveLessonId = null;
let currentViewingLessonId = null;

// Inicialização
document.addEventListener("DOMContentLoaded", () => {
  setupTabs();
  startStatusPolling();
  loadLessons();
});

// Navegação por Abas
function setupTabs() {
  const tabs = document.querySelectorAll(".tab-btn");
  tabs.forEach(tab => {
    tab.addEventListener("click", () => {
      const target = tab.dataset.tab;
      switchTab(target);
    });
  });
}

function switchTab(tabId) {
  document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
  document.querySelectorAll(".tab-pane").forEach(p => p.classList.remove("active"));

  const btn = document.querySelector(`.tab-btn[data-tab="${tabId}"]`);
  const pane = document.getElementById(tabId);

  if (btn) btn.classList.add("active");
  if (pane) pane.classList.add("active");

  if (tabId === "lessons-tab") {
    loadLessons();
  }
}

// Polling de Status da Gravação e Processamento
function startStatusPolling() {
  setInterval(async () => {
    try {
      const res = await fetch("/api/recording/status");
      const data = await res.json();
      updateRecordingUI(data);
    } catch (e) {
      console.error("Erro ao verificar status:", e);
    }
  }, 1000);
}

function updateRecordingUI(status) {
  updateJobOverlay(status.job);
  const statusPill = document.getElementById("header-status-pill");
  const statusText = document.getElementById("status-text");
  const btnRecord = document.getElementById("btn-record");
  const btnSnap = document.getElementById("btn-snap-now");
  const timerDigits = document.getElementById("timer-digits");
  const meterFill = document.getElementById("meter-fill");
  const slideCountBadge = document.getElementById("slide-count-badge");
  const previewImg = document.getElementById("preview-slide-img");
  const previewPlaceholder = document.getElementById("slide-placeholder");
  const processingBanner = document.getElementById("processing-banner");
  const processingMsg = document.getElementById("processing-msg");

  currentActiveLessonId = status.active_lesson_id;

  // Banner de Processamento (Whisper GPU + Ollama)
  if (status.is_processing) {
    processingBanner.style.display = "flex";
    processingMsg.textContent = status.processing_stage || "Transcrevendo com Whisper na GPU e gerando caderno...";
    statusPill.className = "status-pill processing";
    statusText.textContent = "Processando IA";
  } else {
    processingBanner.style.display = "none";
  }

  // Estado Gravando
  if (status.is_recording) {
    statusPill.className = "status-pill recording";
    statusText.textContent = "Gravando Aula";

    btnRecord.innerHTML = "<span>⏹️</span> Finalizar Aula & Transcrever";
    btnRecord.className = "btn-record-main active";
    btnSnap.disabled = false;

    // Atualiza Timer
    timerDigits.textContent = formatSeconds(status.elapsed_seconds);

    // Barra de Áudio (RMS)
    const pct = Math.min(100, Math.round(status.volume_level * 100));
    meterFill.style.width = `${pct}%`;

    // Slide Preview
    slideCountBadge.textContent = `${status.screenshot_count} slides`;

    if (status.last_screenshot) {
      previewImg.src = `/api/screenshots/${status.last_screenshot}?t=${Date.now()}`;
      previewImg.style.display = "block";
      previewPlaceholder.style.display = "none";
    }
  } else if (!status.is_processing) {
    statusPill.className = "status-pill";
    statusText.textContent = "Pronto";

    btnRecord.innerHTML = "<span>🔴</span> Iniciar Gravação da Aula";
    btnRecord.className = "btn-record-main";
    btnSnap.disabled = true;

    meterFill.style.width = "0%";
  }
}

// Formatação de Segundos em HH:MM:SS
function formatSeconds(totalSecs) {
  const secs = Math.floor(totalSecs);
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  if (h > 0) {
    return `${pad(h)}:${pad(m)}:${pad(s)}`;
  }
  return `${pad(m)}:${pad(s)}`;
}

function pad(n) {
  return n < 10 ? "0" + n : n;
}

// Iniciar ou Parar Gravação
async function toggleRecording() {
  const res = await fetch("/api/recording/status");
  const status = await res.json();

  if (status.is_recording) {
    // Parar gravação
    showToast("Finalizando gravação e iniciando IA...");
    try {
      const stopRes = await fetch("/api/recording/stop", { method: "POST" });
      const stopData = await stopRes.json();
      if (stopData.success) {
        showToast("Aula salva! O Whisper transcreverá na GPU e o Ollama gerará os resumos.");
        loadLessons();
      } else {
        showToast(stopData.message, "error");
      }
    } catch (e) {
      showToast("Erro ao finalizar aula.", "error");
    }
  } else {
    // Iniciar gravação
    const titleInput = document.getElementById("lesson-title-input");
    const title = titleInput.value.trim();

    try {
      const startRes = await fetch("/api/recording/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title })
      });
      const startData = await startRes.json();
      if (startData.success) {
        showToast("🎙️ Gravação iniciada! Áudio e slides sendo capturados.");
        titleInput.value = "";
        lastCaptionId = 0;
        clearLiveCaptions();
      } else {
        showToast(startData.message, "error");
      }
    } catch (e) {
      showToast("Erro ao iniciar gravação.", "error");
    }
  }
}

// Captura Manual de Slide
async function triggerCaptureNow() {
  try {
    const res = await fetch("/api/recording/capture_now", { method: "POST" });
    const data = await res.json();
    if (data.success) {
      showToast("📸 Slide capturado com sucesso!");
    } else {
      showToast(data.message, "error");
    }
  } catch (e) {
    showToast("Erro ao capturar slide.", "error");
  }
}

// Carregar Lista de Aulas
async function loadLessons() {
  const container = document.getElementById("lessons-grid");
  try {
    const res = await fetch("/api/lessons");
    const data = await res.json();
    window.lessonsCache = data.lessons || [];

    if (!data.lessons || data.lessons.length === 0) {
      container.innerHTML = `
        <div style="grid-column: 1 / -1; text-align: center; padding: 3rem; color: var(--text-dim);">
          <p style="font-size: 2.5rem; margin-bottom: 0.5rem;">📖</p>
          <p>Nenhuma aula gravada ainda.</p>
          <p style="font-size: 0.85rem; margin-top: 0.25rem;">Entre na sua reunião do Zoom e clique em "Iniciar Gravação da Aula".</p>
        </div>
      `;
      return;
    }

    container.innerHTML = data.lessons.map(lesson => {
      const dur = formatSeconds(lesson.duration_seconds);
      const date = new Date(lesson.created_at).toLocaleDateString("pt-BR", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit"
      });

      let badgeClass = "badge-ready";
      let statusLabel = "Concluída";
      if (lesson.status === "recording") {
        badgeClass = "badge-recording";
        statusLabel = "Gravando";
      } else if (lesson.status === "transcribing" || lesson.status === "processing") {
        badgeClass = "badge-transcribing";
        statusLabel = "Processando IA";
      }

      return `
        <div class="lesson-card" onclick="openLessonNotebook(${lesson.id})">
          <div class="lesson-card-top">
            <h3 class="lesson-title">${escapeHtml(lesson.title)}</h3>
            <span class="badge-status ${badgeClass}">${statusLabel}</span>
          </div>

          <div class="lesson-meta-row">
            <div class="meta-item"><span>📅</span> ${date}</div>
            <div class="meta-item"><span>⏱️</span> ${dur}</div>
            <div class="meta-item"><span>📸</span> ${lesson.screenshot_count || 0} slides</div>
            <div class="meta-item"><span>💬</span> ${lesson.transcript_count || 0} falas</div>
          </div>

          <div class="lesson-actions" onclick="event.stopPropagation()">
            <button class="btn-action btn-view" onclick="openLessonNotebook(${lesson.id})">
              <span>📖</span> Abrir Caderno
            </button>
            <button class="btn-action" onclick="exportMarkdown(${lesson.id})">
              <span>📥</span> Exportar
            </button>
            <button class="btn-action btn-delete" onclick="deleteLessonPrompt(${lesson.id})">
              <span>🗑️</span>
            </button>
          </div>
        </div>
      `;
    }).join("");
  } catch (e) {
    console.error("Erro ao carregar aulas:", e);
  }
}

// Abrir Detalhes / Caderno Inteligente
async function openLessonNotebook(lessonId) {
  currentViewingLessonId = lessonId;
  switchTab("notebook-tab");

  const titleEl = document.getElementById("notebook-title");
  const metaEl = document.getElementById("notebook-meta");
  const audioEl = document.getElementById("lesson-audio-player");
  const summaryEl = document.getElementById("notebook-summary");
  const vocabEl = document.getElementById("notebook-vocab");
  const grammarEl = document.getElementById("notebook-grammar");
  const timelineEl = document.getElementById("notebook-timeline");

  titleEl.textContent = "Carregando aula...";
  metaEl.textContent = "";
  summaryEl.textContent = "Carregando...";
  vocabEl.innerHTML = "";
  timelineEl.innerHTML = "";

  try {
    const res = await fetch(`/api/lessons/${lessonId}`);
    const data = await res.json();
    if (!data.success) {
      showToast(data.message, "error");
      return;
    }

    const lesson = data.lesson;
    titleEl.textContent = lesson.title || "Aula de Inglês";
    metaEl.textContent = `Gravada em ${lesson.started_at || ''} • Duração: ${formatSeconds(lesson.duration_seconds)}`;

    // Áudio
    if (lesson.audio_filename) {
      audioEl.src = `/api/lessons/${lesson.id}/audio`;
      audioEl.parentElement.style.display = "flex";
    } else {
      audioEl.parentElement.style.display = "none";
    }

    // Resumo
    summaryEl.textContent = lesson.ai_summary || "O resumo desta aula ainda não foi gerado.";

    // Vocabulário
    if (lesson.vocabulary_json) {
      try {
        const vocabList = JSON.parse(lesson.vocabulary_json);
        if (vocabList.length > 0) {
          vocabEl.innerHTML = vocabList.map(v => `
            <div class="vocab-item">
              <div class="vocab-term">${escapeHtml(v.term)}</div>
              <div class="vocab-meaning">${escapeHtml(v.meaning)}</div>
              ${v.example ? `<div class="vocab-example">"${escapeHtml(v.example)}"</div>` : ''}
            </div>
          `).join("");
        } else {
          vocabEl.innerHTML = "<p style='color: var(--text-dim);'>Nenhum termo em destaque cadastrado.</p>";
        }
      } catch (e) {
        vocabEl.innerHTML = "<p style='color: var(--text-dim);'>Erro ao ler vocabulário.</p>";
      }
    } else {
      vocabEl.innerHTML = "<p style='color: var(--text-dim);'>Vocabulário não gerado.</p>";
    }

    // Gramática
    if (lesson.grammar_notes) {
      grammarEl.parentElement.style.display = "block";
      grammarEl.textContent = lesson.grammar_notes;
    } else {
      grammarEl.parentElement.style.display = "none";
    }

    // Linha do tempo Sincronizada (Slide + Fala)
    renderTimeline(data.aligned_notebook);

  } catch (e) {
    showToast("Erro ao abrir caderno da aula.", "error");
  }
}

function renderTimeline(aligned) {
  const container = document.getElementById("notebook-timeline");

  if (!aligned || aligned.length === 0) {
    container.innerHTML = "<p style='color: var(--text-dim); padding: 1.5rem;'>Nenhuma transcrição disponível para esta aula.</p>";
    return;
  }

  // Agrupa transcrições pelo slide atual
  const groups = [];
  let currentGroup = null;

  aligned.forEach(item => {
    const s = item.screenshot;
    if (!currentGroup || currentGroup.screenshot !== s) {
      currentGroup = {
        screenshot: s,
        screenshot_time: item.screenshot_time,
        lines: [item]
      };
      groups.push(currentGroup);
    } else {
      currentGroup.lines.push(item);
    }
  });

  container.innerHTML = groups.map(g => {
    const slideImg = g.screenshot
      ? `<div class="timeline-slide">
           <img src="/api/screenshots/${g.screenshot}" alt="Slide ${g.screenshot_time}" onclick="window.open('/api/screenshots/${g.screenshot}', '_blank')">
           <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 0.35rem; text-align: center;">Slide aos ${g.screenshot_time || ''}</div>
         </div>`
      : `<div class="timeline-slide" style="display: flex; align-items: center; justify-content: center; background: rgba(0,0,0,0.2); border-radius: var(--radius-md); color: var(--text-dim); font-size: 0.8rem;">
           Sem slide capturado
         </div>`;

    const speechLines = g.lines.map(line => `
      <div class="transcript-line">
        <span class="time-tag" onclick="seekAudio(${line.start_seconds})">${line.timestamp_str}</span>
        <div class="spoken-block">
          <span class="spoken-text">${escapeHtml(line.text)}</span>
          ${line.translation ? `<div class="line-translation">${escapeHtml(line.translation)}</div>` : ""}
        </div>
      </div>
    `).join("");

    return `
      <div class="timeline-entry">
        ${slideImg}
        <div class="timeline-transcripts">
          ${speechLines}
        </div>
      </div>
    `;
  }).join("");
}

// Navegar áudio para segundo específico
function seekAudio(seconds) {
  const audioEl = document.getElementById("lesson-audio-player");
  if (audioEl && !isNaN(seconds)) {
    audioEl.currentTime = seconds;
    audioEl.play();
  }
}

// Regenerar IA para a aula atual (roda em segundo plano; o overlay mostra o progresso)
async function regenerateAiMaterial() {
  if (!currentViewingLessonId) return;
  try {
    const res = await fetch(`/api/lessons/${currentViewingLessonId}/generate_ai`, { method: "POST" });
    const data = await res.json();
    if (!data.success) {
      showToast(data.message, "error");
      return;
    }
    jobDismissed = false;
    // Mostra o overlay imediatamente, sem esperar o próximo ciclo de polling
    updateJobOverlay({ active: true, phase: "translating", block: 0, total_blocks: 0, lines_done: 0, lines_total: 0, preview: [], lesson_id: currentViewingLessonId });
  } catch (e) {
    showToast("Erro ao reprocessar aula.", "error");
  }
}

// ===== Overlay de progresso (tradução / resumo) =====
let jobWasActive = false;
let jobDismissed = false;
let jobLessonId = null;

function hideJobOverlay() {
  jobDismissed = true;
  const overlay = document.getElementById("job-overlay");
  overlay.classList.remove("open");
  overlay.setAttribute("aria-hidden", "true");
}

function updateJobOverlay(job) {
  if (!job) return;
  const overlay = document.getElementById("job-overlay");

  if (job.active) {
    jobWasActive = true;
    jobLessonId = job.lesson_id;
    const title = document.getElementById("job-title");
    const subtitle = document.getElementById("job-subtitle");
    const fill = document.getElementById("job-progress-fill");
    const stats = document.getElementById("job-stats");
    const preview = document.getElementById("job-preview");
    const engineEl = document.getElementById("job-engine");

    // Aviso do motor de tradução em uso (Google / fallback Ollama)
    if (job.phase === "translating" && job.engine) {
      const labels = {
        google: "🌐 Traduzindo com Google Tradutor",
        ollama: "⚠️ " + (job.notice || "Usando Ollama local"),
        failed: "❌ " + (job.notice || "Falha ao traduzir este bloco")
      };
      engineEl.textContent = labels[job.engine] || "";
      engineEl.className = `job-engine show ${job.engine}`;
    } else {
      engineEl.className = "job-engine";
    }

    if (job.phase === "summarizing") {
      title.textContent = "Gerando resumo e vocabulário...";
      subtitle.textContent = "Quase pronto! O Ollama está montando o material de estudo.";
      fill.classList.add("indeterminate");
      stats.innerHTML = "";
      preview.innerHTML = "";
    } else {
      title.textContent = "Traduzindo transcrição...";
      subtitle.textContent = "Cada bloco de falas é traduzido para português.";
      if (job.total_blocks > 0) {
        fill.classList.remove("indeterminate");
        const pct = Math.round(((job.block - 1) / job.total_blocks) * 100);
        fill.style.width = `${Math.max(3, pct)}%`;
        stats.innerHTML = `<span>Bloco ${job.block} de ${job.total_blocks}</span><span>${job.lines_done} de ${job.lines_total} falas</span>`;
      } else {
        fill.classList.add("indeterminate");
        stats.innerHTML = "<span>Preparando...</span>";
      }
      preview.innerHTML = (job.preview || []).map(l => `<div class="job-preview-line">${escapeHtml(l)}</div>`).join("");
    }

    if (!jobDismissed) {
      overlay.classList.add("open");
      overlay.setAttribute("aria-hidden", "false");
    }
  } else if (jobWasActive) {
    // Terminou: fecha o overlay e atualiza o caderno
    jobWasActive = false;
    jobDismissed = false;
    overlay.classList.remove("open");
    overlay.setAttribute("aria-hidden", "true");
    showToast("Tradução e material de estudo atualizados!");
    loadLessons();
    if (currentViewingLessonId && currentViewingLessonId === jobLessonId) {
      openLessonNotebook(currentViewingLessonId);
    }
  }
}

// Exportar Markdown
function exportMarkdown(lessonId) {
  const id = lessonId || currentViewingLessonId;
  if (!id) return;
  window.location.href = `/api/lessons/${id}/export_markdown`;
}

// Excluir Aula
async function deleteLessonPrompt(lessonId) {
  const lesson = (window.lessonsCache || []).find(l => l.id === lessonId);
  const name = lesson ? lesson.title : "esta aula";
  const confirmed = await confirmDialog({
    title: "Excluir aula?",
    message: `<strong>${escapeHtml(name)}</strong><br>O áudio, os slides e a transcrição serão apagados permanentemente.`,
    okText: "Excluir"
  });
  if (!confirmed) return;
  try {
    const res = await fetch(`/api/lessons/${lessonId}`, { method: "DELETE" });
    const data = await res.json();
    if (data.success) {
      showToast("Aula excluída com sucesso.");
      loadLessons();
      if (currentViewingLessonId === lessonId) {
        switchTab("lessons-tab");
      }
    } else {
      showToast(data.message, "error");
    }
  } catch (e) {
    showToast("Erro ao excluir aula.", "error");
  }
}

// Toasts de Notificação
function showToast(message, type = "info") {
  const container = document.getElementById("toast-container");
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `<span>${type === "error" ? "⚠️" : "✨"}</span> ${escapeHtml(message)}`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateX(50px)";
    toast.style.transition = "all 0.3s ease";
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

function escapeHtml(text) {
  if (!text) return "";
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}


// ===== Legendas ao Vivo =====
let lastCaptionId = 0;
let liveLoopStarted = false;

function startLiveCaptionsPolling() {
  if (liveLoopStarted) return;
  liveLoopStarted = true;
  setInterval(async () => {
    try {
      const res = await fetch(`/api/live/captions?since=${lastCaptionId}`);
      const data = await res.json();
      updateLiveBadge(data.status);
      if (data.captions && data.captions.length) appendCaptions(data.captions);
    } catch (e) { /* servidor ocupado, tenta de novo */ }
  }, 1000);
}

function updateLiveBadge(status) {
  const badge = document.getElementById("live-status-badge");
  if (!badge) return;
  badge.textContent = status === "listening" ? "🟢 Ouvindo"
    : status === "loading" ? "⏳ Carregando modelo..."
    : "Aguardando aula";
}

function appendCaptions(captions) {
  const box = document.getElementById("live-captions");
  const empty = box.querySelector(".live-empty");
  if (empty) empty.remove();
  box.querySelectorAll(".caption-line.latest").forEach(el => el.classList.remove("latest"));

  captions.forEach((c, i) => {
    lastCaptionId = Math.max(lastCaptionId, c.id);
    const line = document.createElement("div");
    line.className = "caption-line" + (i === captions.length - 1 ? " latest" : "");
    line.title = "Clique para traduzir";
    line.innerHTML = `<span class="caption-time">${formatSeconds(c.time)}</span><span>${escapeHtml(c.text)}</span>`;
    line.addEventListener("click", () => {
      document.getElementById("translate-input").value = c.text;
      document.getElementById("translate-direction").value = "en-pt";
      runTranslate();
    });
    box.appendChild(line);
  });

  if (document.getElementById("live-autoscroll").checked) {
    box.scrollTop = box.scrollHeight;
  }
}

function clearLiveCaptions() {
  document.getElementById("live-captions").innerHTML =
    '<p class="live-empty">Tela limpa. Novas falas aparecerão aqui.</p>';
}

// ===== Tradutor =====
async function runTranslate() {
  const input = document.getElementById("translate-input");
  const resultEl = document.getElementById("translate-result");
  const metaEl = document.getElementById("translate-meta");
  const text = input.value.trim();
  if (!text) return;

  resultEl.textContent = "Traduzindo...";
  try {
    const res = await fetch("/api/translate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, direction: document.getElementById("translate-direction").value })
    });
    if (res.status === 404) {
      resultEl.textContent = "";
      showToast("Rota de tradução não encontrada. Reinicie o servidor (iniciar.bat).", "error");
      return;
    }
    const data = await res.json();
    if (data.success) {
      resultEl.textContent = data.translation;
      metaEl.textContent = `${(data.source || "").toUpperCase()} → ${(data.target || "").toUpperCase()} • ${data.engine}`;
    } else {
      resultEl.textContent = "";
      showToast(data.message || "Falha ao traduzir.", "error");
    }
  } catch (e) {
    resultEl.textContent = "";
    showToast("Erro ao traduzir.", "error");
  }
}

function copyTranslation() {
  const text = document.getElementById("translate-result").textContent;
  if (text) navigator.clipboard.writeText(text).then(() => showToast("Tradução copiada!"));
}

function swapTranslation() {
  const input = document.getElementById("translate-input");
  const result = document.getElementById("translate-result").textContent;
  const meta = document.getElementById("translate-meta").textContent;
  if (!result || !meta || result === "Traduzindo...") return;
  input.value = result;
  const sel = document.getElementById("translate-direction");
  if (sel.value === "en-pt") sel.value = "pt-en";
  else if (sel.value === "pt-en") sel.value = "en-pt";
  runTranslate();
}

document.addEventListener("DOMContentLoaded", () => {
  startLiveCaptionsPolling();
  document.getElementById("translate-input").addEventListener("keydown", e => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) runTranslate();
  });
});


// ===== Modal de confirmação estilizado =====
function confirmDialog({ title = "Confirmar", message = "", okText = "Confirmar", cancelText = "Cancelar" } = {}) {
  return new Promise(resolve => {
    const modal = document.getElementById("confirm-modal");
    const okBtn = document.getElementById("confirm-ok");
    const cancelBtn = document.getElementById("confirm-cancel");
    document.getElementById("confirm-title").textContent = title;
    document.getElementById("confirm-message").innerHTML = message;
    okBtn.textContent = okText;
    cancelBtn.textContent = cancelText;

    const close = result => {
      modal.classList.remove("open");
      modal.setAttribute("aria-hidden", "true");
      okBtn.onclick = cancelBtn.onclick = modal.onclick = null;
      document.removeEventListener("keydown", onKey);
      resolve(result);
    };
    const onKey = e => {
      if (e.key === "Escape") close(false);
    };

    okBtn.onclick = () => close(true);
    cancelBtn.onclick = () => close(false);
    modal.onclick = e => { if (e.target === modal) close(false); };
    document.addEventListener("keydown", onKey);

    modal.classList.add("open");
    modal.setAttribute("aria-hidden", "false");
    cancelBtn.focus();
  });
}
