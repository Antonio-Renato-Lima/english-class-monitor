import os
import sys
import ctypes
from typing import List, Dict, Any, Optional
from faster_whisper import WhisperModel
from config import WHISPER_MODEL, WHISPER_DEVICE, WHISPER_COMPUTE_TYPE
from helpers.utils.formatters import format_seconds_to_timestamp


def _setup_cuda_dlls():
    """Garante que as DLLs da NVIDIA CUDA 12 (cuBLAS, cuDNN) sejam localizadas no Windows."""
    if sys.platform != "win32":
        return

    try:
        import site
        candidate_dirs = []
        for sp in site.getsitepackages():
            ct2_dir = os.path.join(sp, "ctranslate2")
            if os.path.isdir(ct2_dir):
                candidate_dirs.append(ct2_dir)
            cublas_bin = os.path.join(sp, "nvidia", "cublas", "bin")
            if os.path.isdir(cublas_bin):
                candidate_dirs.append(cublas_bin)
            cudnn_bin = os.path.join(sp, "nvidia", "cudnn", "bin")
            if os.path.isdir(cudnn_bin):
                candidate_dirs.append(cudnn_bin)

        for p in candidate_dirs:
            try:
                os.add_dll_directory(p)
            except Exception:
                pass
            if p not in os.environ.get("PATH", ""):
                os.environ["PATH"] = p + os.pathsep + os.environ.get("PATH", "")

        for p in candidate_dirs:
            for dll_name in ("cublasLt64_12.dll", "cublas64_12.dll"):
                dll_file = os.path.join(p, dll_name)
                if os.path.isfile(dll_file):
                    try:
                        ctypes.CDLL(dll_file)
                    except Exception:
                        pass
    except Exception as e:
        print(f"[Transcriber] Aviso na inicialização de DLLs CUDA: {e}")


_setup_cuda_dlls()

_whisper_instance: Optional[WhisperModel] = None


def get_whisper_model() -> WhisperModel:
    global _whisper_instance
    if _whisper_instance is not None:
        return _whisper_instance

    try:
        print(f"[Transcriber] Carregando Whisper '{WHISPER_MODEL}' em {WHISPER_DEVICE} ({WHISPER_COMPUTE_TYPE})...")
        _whisper_instance = WhisperModel(
            WHISPER_MODEL,
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE_TYPE
        )
        print("[Transcriber] Modelo carregado com sucesso na GPU!")
    except Exception as e:
        print(f"[Transcriber] Falha ao carregar na GPU ({e}), utilizando CPU de fallback...")
        _whisper_instance = WhisperModel(
            WHISPER_MODEL,
            device="cpu",
            compute_type="int8"
        )
        print("[Transcriber] Modelo carregado com sucesso na CPU!")

    return _whisper_instance


def transcribe_audio_file(filepath: str) -> List[Dict[str, Any]]:
    """Transcreve um arquivo WAV/MP3 e retorna os segmentos formatados com minutagem."""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Arquivo de áudio não encontrado: {filepath}")

    model = get_whisper_model()

    print(f"[Transcriber] Iniciando transcrição de: {filepath}")
    
    try:
        segments, info = model.transcribe(
            filepath,
            language="en",
            task="transcribe",
            beam_size=5,
            vad_filter=True,  # Remove silêncios para acelerar
            vad_parameters=dict(min_silence_duration_ms=500)
        )
        # Consome o gerador para garantir que a inferência ocorra dentro do bloco try
        seg_list = list(segments)
    except Exception as e:
        print(f"[Transcriber] Erro durante inferência na GPU ({e}), usando CPU de contingência...")
        fallback_model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
        segments, info = fallback_model.transcribe(
            filepath,
            language="en",
            task="transcribe",
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500)
        )
        seg_list = list(segments)

    results = []
    for s in seg_list:
        text = s.text.strip()
        if not text:
            continue

        results.append({
            "start_seconds": round(s.start, 2),
            "end_seconds": round(s.end, 2),
            "start_str": format_seconds_to_timestamp(s.start),
            "end_str": format_seconds_to_timestamp(s.end),
            "speaker": "Class",
            "text": text
        })

    print(f"[Transcriber] Transcrição concluída: {len(results)} segmentos encontrados.")
    return results
