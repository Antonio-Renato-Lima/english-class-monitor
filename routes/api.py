import os
import time
import threading
from flask import Blueprint, request, jsonify, send_file, Response
from config import AUDIO_DIR, SCREENSHOTS_DIR
from helpers.database import (
    create_lesson,
    update_lesson_status,
    save_transcripts,
    save_lesson_ai_analysis,
    get_all_lessons,
    get_lesson,
    get_lesson_transcripts,
    get_lesson_screenshots,
    delete_lesson,
    update_transcript_translations,
)
from helpers.audio_recorder import audio_recorder
from helpers.screen_capture import screen_capture
from helpers.transcriber import transcribe_audio_file
from helpers.live_transcriber import live_transcriber
from helpers.translator import translate, translate_batch
from helpers.ollama_client import generate_study_material
from helpers.utils.formatters import align_transcripts_with_screenshots, export_lesson_to_markdown

api_bp = Blueprint("api", __name__, url_prefix="/api")

# Estado global da sessão em andamento
_session_lock = threading.Lock()
_active_lesson_id = None
_is_processing = False
_processing_stage = ""


# Estado do trabalho de tradução/regeneração (exibido no overlay do front-end)
_job_lock = threading.Lock()
_job = {
    "active": False, "lesson_id": None, "phase": "", "block": 0, "total_blocks": 0,
    "lines_done": 0, "lines_total": 0, "preview": [],
}


def _job_update(**kwargs):
    with _job_lock:
        _job.update(kwargs)


def _job_snapshot():
    with _job_lock:
        return dict(_job)


def _translate_lesson_transcripts(lesson_id: int):
    """Traduz para PT-BR as falas da aula que ainda não têm tradução."""
    global _processing_stage
    pending = [t for t in get_lesson_transcripts(lesson_id) if not t.get("translation")]
    if not pending:
        return

    _processing_stage = "Traduzindo transcrição para português..."
    _job_update(active=True, lesson_id=lesson_id, phase="translating", block=0, total_blocks=0,
                lines_done=0, lines_total=len(pending), preview=[])

    done_lines = {"n": 0}

    def on_block(n, total, batch):
        global _processing_stage
        _processing_stage = f"Traduzindo transcrição para português (bloco {n}/{total})..."
        _job_update(block=n, total_blocks=total, preview=batch[:6], lines_done=done_lines["n"])
        done_lines["n"] += len(batch)  # contado como concluído quando o próximo bloco iniciar

    translations = translate_batch([t["text"] for t in pending], on_block=on_block)
    update_transcript_translations([(t["id"], tr) for t, tr in zip(pending, translations)])
    _job_update(lines_done=len(pending))


def _regenerate_background(lesson_id: int):
    """Traduz as falas e regenera resumo/vocabulário em segundo plano."""
    global _processing_stage
    try:
        _job_update(active=True, lesson_id=lesson_id, phase="translating", block=0, total_blocks=0,
                    lines_done=0, lines_total=0, preview=[])
        try:
            _translate_lesson_transcripts(lesson_id)
        except Exception as e:
            print(f"[API] Erro ao traduzir transcrição: {e}")

        _job_update(phase="summarizing", preview=[])
        _processing_stage = "Gerando resumo e vocabulário..."
        lesson = get_lesson(lesson_id)
        transcripts = get_lesson_transcripts(lesson_id)
        ai_data = generate_study_material(transcripts, lesson_title=lesson.get("title", "Aula de Inglês"))
        save_lesson_ai_analysis(
            lesson_id=lesson_id,
            summary=ai_data["summary"],
            vocabulary_json=ai_data["vocabulary_json"],
            grammar_notes=ai_data["grammar_notes"]
        )
    except Exception as e:
        print(f"[API] Erro ao regenerar material da aula #{lesson_id}: {e}")
    finally:
        _processing_stage = ""
        _job_update(active=False, phase="done", preview=[])


def _process_lesson_background(lesson_id: int, audio_filename: str):
    """Processa a transcrição via Whisper na GPU e gera o material de estudos via Ollama em segundo plano."""
    global _is_processing, _processing_stage

    try:
        _is_processing = True
        _processing_stage = "Transcrevendo áudio com Whisper (GPU)..."
        update_lesson_status(lesson_id, status="transcribing")

        audio_path = os.path.join(AUDIO_DIR, audio_filename)
        segments = []
        if os.path.exists(audio_path):
            try:
                segments = transcribe_audio_file(audio_path)
                save_transcripts(lesson_id, segments)
            except Exception as e:
                print(f"[API Background] Erro na transcrição Whisper: {e}")

        try:
            _translate_lesson_transcripts(lesson_id)
        except Exception as e:
            print(f"[API Background] Erro ao traduzir transcrição: {e}")

        _processing_stage = "Gerando resumo e vocabulário com Ollama..."
        lesson = get_lesson(lesson_id)
        title = lesson.get("title", "Aula de Inglês") if lesson else "Aula de Inglês"

        ai_data = generate_study_material(segments, lesson_title=title)

        save_lesson_ai_analysis(
            lesson_id=lesson_id,
            summary=ai_data["summary"],
            vocabulary_json=ai_data["vocabulary_json"],
            grammar_notes=ai_data["grammar_notes"]
        )

        update_lesson_status(lesson_id, status="ready")
        print(f"[API Background] Aula #{lesson_id} concluída com sucesso!")

    except Exception as e:
        print(f"[API Background] Erro ao processar aula #{lesson_id}: {e}")
        update_lesson_status(lesson_id, status="failed")
    finally:
        _is_processing = False
        _processing_stage = ""
        _job_update(active=False, phase="done", preview=[])


@api_bp.route("/recording/start", methods=["POST"])
def start_recording():
    global _active_lesson_id

    with _session_lock:
        if audio_recorder.is_recording or screen_capture.is_capturing:
            return jsonify({
                "success": False,
                "message": "Uma gravação já está em andamento.",
                "lesson_id": _active_lesson_id
            }), 400

        data = request.get_json(silent=True) or {}
        title = data.get("title", "").strip()
        if not title:
            # Título automático com data/hora
            title = f"Aula de Inglês - {time.strftime('%d/%m/%Y %H:%M')}"

        lesson_id = create_lesson(title=title)
        _active_lesson_id = lesson_id

        # Inicia áudio e captura de tela
        audio_recorder.start()
        screen_capture.start(lesson_id=lesson_id)
        live_transcriber.start()

        return jsonify({
            "success": True,
            "message": "Gravação iniciada com sucesso!",
            "lesson_id": lesson_id,
            "title": title
        })


@api_bp.route("/recording/stop", methods=["POST"])
def stop_recording():
    global _active_lesson_id

    with _session_lock:
        if not audio_recorder.is_recording and not screen_capture.is_capturing:
            return jsonify({"success": False, "message": "Nenhuma gravação ativa."}), 400

        lesson_id = _active_lesson_id
        _active_lesson_id = None

        # Para legendas ao vivo e captura de tela
        live_transcriber.stop()
        screen_capture.stop()

        # Para gravação de áudio e salva WAV
        audio_filename, duration = audio_recorder.stop(lesson_id=lesson_id)

        update_lesson_status(
            lesson_id=lesson_id,
            status="processing",
            duration_seconds=duration,
            audio_filename=audio_filename
        )

        # Dispara transcrição e IA em background
        if audio_filename:
            t = threading.Thread(
                target=_process_lesson_background,
                args=(lesson_id, audio_filename),
                daemon=True
            )
            t.start()
        else:
            update_lesson_status(lesson_id, status="ready", duration_seconds=duration)

        return jsonify({
            "success": True,
            "message": "Gravação finalizada. A transcrição e análise da aula foram iniciadas!",
            "lesson_id": lesson_id,
            "duration_seconds": duration,
            "audio_filename": audio_filename
        })


@api_bp.route("/recording/status", methods=["GET"])
def recording_status():
    is_rec = audio_recorder.is_recording or screen_capture.is_capturing
    elapsed = 0.0
    if is_rec and audio_recorder.start_time > 0:
        elapsed = max(0.0, time.time() - audio_recorder.start_time)

    return jsonify({
        "is_recording": is_rec,
        "is_processing": _is_processing,
        "processing_stage": _processing_stage,
        "job": _job_snapshot(),
        "active_lesson_id": _active_lesson_id,
        "elapsed_seconds": round(elapsed, 1),
        "volume_level": round(audio_recorder.current_volume, 2),
        "screenshot_count": screen_capture.captured_count if is_rec else 0,
        "last_screenshot": screen_capture.last_screenshot_filename if is_rec else None
    })


@api_bp.route("/live/captions", methods=["GET"])
def live_captions():
    since = request.args.get("since", default=0, type=int)
    return jsonify({
        "success": True,
        "status": live_transcriber.status,
        "captions": live_transcriber.get_captions(since),
    })


@api_bp.route("/translate", methods=["POST"])
def translate_text():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "")[:5000]
    direction = data.get("direction", "auto")
    try:
        result = translate(text, direction)
        return jsonify({"success": True, **result})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 502


@api_bp.route("/recording/capture_now", methods=["POST"])
def capture_now():
    if not screen_capture.is_capturing:
        return jsonify({"success": False, "message": "Nenhuma aula gravando no momento."}), 400

    filename = screen_capture.capture_now()
    if filename:
        return jsonify({
            "success": True,
            "message": "Slide capturado com sucesso!",
            "filename": filename
        })
    return jsonify({"success": False, "message": "Falha ao capturar tela."}), 500


@api_bp.route("/lessons", methods=["GET"])
def list_lessons():
    lessons = get_all_lessons()
    return jsonify({"success": True, "lessons": lessons})


@api_bp.route("/lessons/<int:lesson_id>", methods=["GET"])
def get_lesson_detail(lesson_id: int):
    lesson = get_lesson(lesson_id)
    if not lesson:
        return jsonify({"success": False, "message": "Aula não encontrada."}), 404

    transcripts = get_lesson_transcripts(lesson_id)
    screenshots = get_lesson_screenshots(lesson_id)
    aligned = align_transcripts_with_screenshots(transcripts, screenshots)

    return jsonify({
        "success": True,
        "lesson": lesson,
        "transcripts": transcripts,
        "screenshots": screenshots,
        "aligned_notebook": aligned
    })


@api_bp.route("/lessons/<int:lesson_id>", methods=["DELETE"])
def remove_lesson(lesson_id: int):
    success = delete_lesson(lesson_id)
    if success:
        return jsonify({"success": True, "message": "Aula excluída com sucesso."})
    return jsonify({"success": False, "message": "Aula não encontrada."}), 404


@api_bp.route("/lessons/<int:lesson_id>/audio", methods=["GET"])
def stream_lesson_audio(lesson_id: int):
    lesson = get_lesson(lesson_id)
    if not lesson or not lesson.get("audio_filename"):
        return jsonify({"success": False, "message": "Áudio não encontrado."}), 404

    audio_path = os.path.join(AUDIO_DIR, lesson["audio_filename"])
    if not os.path.exists(audio_path):
        return jsonify({"success": False, "message": "Arquivo de áudio não existe no disco."}), 404

    return send_file(audio_path, mimetype="audio/wav")


@api_bp.route("/screenshots/<filename>", methods=["GET"])
def serve_screenshot(filename: str):
    # Proteção de path traversal simples
    safe_filename = os.path.basename(filename)
    filepath = os.path.join(SCREENSHOTS_DIR, safe_filename)
    if not os.path.exists(filepath):
        return jsonify({"success": False, "message": "Imagem não encontrada."}), 404

    return send_file(filepath, mimetype="image/png")


@api_bp.route("/lessons/<int:lesson_id>/generate_ai", methods=["POST"])
def regenerate_ai_material(lesson_id: int):
    lesson = get_lesson(lesson_id)
    if not lesson:
        return jsonify({"success": False, "message": "Aula não encontrada."}), 404

    transcripts = get_lesson_transcripts(lesson_id)
    if not transcripts:
        return jsonify({"success": False, "message": "Aula não possui transcrições."}), 400

    if _job_snapshot()["active"]:
        return jsonify({"success": False, "message": "Já existe uma tradução/regeneração em andamento."}), 409

    _job_update(active=True, lesson_id=lesson_id, phase="translating", block=0, total_blocks=0,
                lines_done=0, lines_total=0, preview=[])
    threading.Thread(target=_regenerate_background, args=(lesson_id,), daemon=True).start()

    return jsonify({"success": True, "message": "Regeneração iniciada.", "lesson_id": lesson_id})


@api_bp.route("/lessons/<int:lesson_id>/export_markdown", methods=["GET"])
def export_markdown(lesson_id: int):
    lesson = get_lesson(lesson_id)
    if not lesson:
        return jsonify({"success": False, "message": "Aula não encontrada."}), 404

    transcripts = get_lesson_transcripts(lesson_id)
    screenshots = get_lesson_screenshots(lesson_id)
    md_content = export_lesson_to_markdown(lesson, transcripts, screenshots)

    filename = f"aula_{lesson_id}_{lesson.get('title', 'ingles').replace(' ', '_')}.md"
    return Response(
        md_content,
        mimetype="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
