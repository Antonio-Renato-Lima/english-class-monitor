"""gerar_srt.py
Gera legenda .srt (UTF-8, formato aceito pelo LinkedIn) a partir de um vídeo,
usando faster-whisper com modelo MULTILÍNGUE (pensado para vídeos que misturam
inglês e português).

Uso:
    python gerar_srt.py video.mp4
    python gerar_srt.py video.mp4 --modelo large-v3
    python gerar_srt.py video.mp4 --queimar        # também grava a legenda dentro do vídeo

Rode dentro do .venv do projeto (onde faster-whisper e as libs CUDA já estão).
"""

import argparse
import os
import shutil
import subprocess

from faster_whisper import WhisperModel

# Ajuda o Whisper a acertar nomes próprios (ex.: "Ollama" virou "Leuven" no small.en)
PROMPT = (
    "English Class Monitor, Whisper, faster-whisper, Ollama, Flask, Python, "
    "CUDA, SQLite, LinkedIn, Google Translate. Fala em inglês e português."
)

MAX_CHARS_LINHA = 42
MAX_CHARS_CUE = MAX_CHARS_LINHA * 2  # no máximo 2 linhas por legenda
MAX_SEGUNDOS_CUE = 5.5
MIN_SEGUNDOS_CUE = 0.8


def ts(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def quebrar_linhas(texto: str) -> str:
    if len(texto) <= MAX_CHARS_LINHA:
        return texto
    espacos = [i for i, c in enumerate(texto) if c == " "]
    if not espacos:
        return texto
    i = min(espacos, key=lambda p: abs(p - len(texto) / 2))
    return texto[:i] + "\n" + texto[i + 1 :]


def montar_cues(segmentos):
    """Agrupa palavras (com timestamps) em legendas curtas e legíveis."""
    cues, atual = [], []

    def fechar():
        if atual:
            texto = "".join(w.word for w in atual).strip()
            if texto:
                cues.append([atual[0].start, atual[-1].end, texto])
            atual.clear()

    for seg in segmentos:
        for w in seg.words or []:
            if atual:
                acumulado = "".join(x.word for x in atual)
                if (
                    len(acumulado) + len(w.word) > MAX_CHARS_CUE
                    or w.end - atual[0].start > MAX_SEGUNDOS_CUE
                ):
                    fechar()
            atual.append(w)
            if w.word.strip().endswith((".", "?", "!")):
                fechar()
        fechar()

    # Evita sobreposição e legendas rápidas demais
    for i, cue in enumerate(cues):
        limite = cues[i + 1][0] - 0.01 if i + 1 < len(cues) else cue[1] + 1.0
        cue[1] = min(max(cue[1], cue[0] + MIN_SEGUNDOS_CUE), limite)
    return cues


def escrever_srt(cues, caminho: str):
    # UTF-8 sem BOM, como o LinkedIn exige
    with open(caminho, "w", encoding="utf-8", newline="\n") as f:
        for n, (ini, fim, texto) in enumerate(cues, 1):
            f.write(f"{n}\n{ts(ini)} --> {ts(fim)}\n{quebrar_linhas(texto)}\n\n")


def transcrever(modelo: WhisperModel, video: str, idioma):
    kwargs = dict(
        language=idioma,
        beam_size=5,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500),
        word_timestamps=True,
        initial_prompt=PROMPT,
        condition_on_previous_text=False,
    )
    try:
        # multilingual=True re-detecta o idioma a cada trecho (faster-whisper >= 1.1)
        segs, info = modelo.transcribe(video, multilingual=idioma is None, **kwargs)
    except TypeError:
        segs, info = modelo.transcribe(video, **kwargs)
    return list(segs), info


def gerar(video: str, nome_modelo: str, idioma):
    try:
        print(f"[1/3] Carregando '{nome_modelo}' na GPU (CUDA float16)...")
        modelo = WhisperModel(nome_modelo, device="cuda", compute_type="float16")
        return transcrever(modelo, video, idioma)
    except Exception as e:
        print(f"[aviso] GPU falhou ({e}). Usando CPU int8 (mais lento).")
        modelo = WhisperModel(nome_modelo, device="cpu", compute_type="int8")
        return transcrever(modelo, video, idioma)


def queimar(video: str, srt: str) -> str:
    """Grava a legenda dentro do vídeo (sempre visível, mesmo sem som/CC)."""
    pasta = os.path.dirname(os.path.abspath(srt))
    tmp = os.path.join(
        pasta, "_legenda_tmp.srt"
    )  # nome simples evita problemas de escape
    shutil.copy(srt, tmp)
    saida = os.path.splitext(os.path.abspath(video))[0] + "_legendado.mp4"
    estilo = "FontName=Arial,FontSize=16,Outline=2,Shadow=0,MarginV=30"
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        os.path.abspath(video),
        "-vf",
        f"subtitles=_legenda_tmp.srt:force_style='{estilo}'",
        "-c:a",
        "copy",
        saida,
    ]
    try:
        subprocess.run(cmd, cwd=pasta, check=True)
    finally:
        os.remove(tmp)
    return saida


def main():
    ap = argparse.ArgumentParser(description="Gera legenda SRT com faster-whisper")
    ap.add_argument("video")
    ap.add_argument(
        "--modelo",
        default="medium",
        help="medium (padrão) ou large-v3 para mais qualidade; nunca use *.en aqui",
    )
    ap.add_argument(
        "--idioma",
        default=None,
        help="en ou pt para forçar; vazio detecta e acompanha a mistura",
    )
    ap.add_argument(
        "--saida", default=None, help="caminho do .srt (padrão: ao lado do vídeo)"
    )
    ap.add_argument(
        "--queimar", action="store_true", help="também gera <video>_legendado.mp4"
    )
    args = ap.parse_args()

    srt = args.saida or os.path.splitext(args.video)[0] + ".srt"
    segmentos, info = gerar(args.video, args.modelo, args.idioma)
    print(
        f"[2/3] {len(segmentos)} trechos transcritos (idioma inicial: {info.language})."
    )

    cues = montar_cues(segmentos)
    escrever_srt(cues, srt)
    print(f"[3/3] Legenda salva: {srt} ({len(cues)} legendas)")
    print("      Revise o texto (nomes próprios, trechos em português) antes de subir.")

    if args.queimar:
        print("Gravando a legenda no vídeo...")
        print("Pronto:", queimar(args.video, srt))


if __name__ == "__main__":
    main()
