import threading
import time
from typing import List, Dict, Any

import numpy as np

from helpers.audio_recorder import audio_recorder
from helpers.transcriber import get_whisper_model

SAMPLE_RATE = 16000
TICK_SECONDS = 0.5          # frequência de leitura de novos trechos de áudio
SILENCE_RMS = 0.008         # abaixo disso o trecho é considerado silêncio
END_SILENCE_SECONDS = 0.7   # pausa que encerra uma frase
MAX_UTTERANCE_SECONDS = 8.0 # força o corte se a pessoa falar sem pausar
MIN_UTTERANCE_SECONDS = 0.8 # ignora ruídos muito curtos


class LiveTranscriber:
    """Gera legendas em tempo real a partir dos mesmos buffers do AudioRecorder."""

    def __init__(self):
        self._thread = None
        self._running = False
        self._lock = threading.Lock()
        self._captions: List[Dict[str, Any]] = []
        self._model_lock = threading.Lock()
        self.status = "idle"  # idle | loading | listening

    def start(self):
        if self._running:
            return
        with self._lock:
            self._captions = []
        self._running = True
        self.status = "loading"
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        self.status = "idle"

    def get_captions(self, since: int = 0) -> List[Dict[str, Any]]:
        with self._lock:
            return [c for c in self._captions if c["id"] > since]

    def _take_new(self, idx_loop: int, idx_mic: int):
        with audio_recorder._lock:
            new_loop = audio_recorder._loop_chunks[idx_loop:]
            new_mic = audio_recorder._mic_chunks[idx_mic:]
        loop_audio = np.concatenate(new_loop) if new_loop else np.zeros(0, dtype=np.float32)
        mic_audio = np.concatenate(new_mic) if new_mic else np.zeros(0, dtype=np.float32)
        n = max(len(loop_audio), len(mic_audio))
        loop_audio = np.pad(loop_audio, (0, n - len(loop_audio)))
        mic_audio = np.pad(mic_audio, (0, n - len(mic_audio)))
        mixed = loop_audio * 0.85 + mic_audio
        return mixed.astype(np.float32), idx_loop + len(new_loop), idx_mic + len(new_mic)

    def _emit(self, audio: np.ndarray, start_offset: float):
        try:
            model = get_whisper_model()
            with self._model_lock:
                segments, _ = model.transcribe(
                    np.clip(audio, -1.0, 1.0),
                    language="en",
                    task="transcribe",
                    beam_size=1,
                    vad_filter=True,
                    vad_parameters=dict(min_silence_duration_ms=300),
                    condition_on_previous_text=False,
                )
                text = " ".join(s.text.strip() for s in segments).strip()
        except Exception as e:
            print(f"[LiveTranscriber] Erro na transcrição ao vivo: {e}")
            return

        if not text:
            return
        with self._lock:
            self._captions.append({
                "id": len(self._captions) + 1,
                "time": round(start_offset, 1),
                "text": text,
            })

    def _run(self):
        try:
            get_whisper_model()  # carrega o modelo antes de começar a ouvir
        except Exception as e:
            print(f"[LiveTranscriber] Falha ao carregar modelo: {e}")
            self.status = "idle"
            return

        self.status = "listening"
        idx_loop = idx_mic = 0
        pending = np.zeros(0, dtype=np.float32)
        pending_start = 0.0
        processed_seconds = 0.0
        has_speech = False

        while self._running and audio_recorder.is_recording:
            time.sleep(TICK_SECONDS)
            new_audio, idx_loop, idx_mic = self._take_new(idx_loop, idx_mic)
            if len(new_audio) == 0:
                continue

            tail_rms = float(np.sqrt(np.mean(np.square(new_audio))))
            if not has_speech:
                if tail_rms < SILENCE_RMS:
                    processed_seconds += len(new_audio) / SAMPLE_RATE
                    continue
                has_speech = True
                pending_start = processed_seconds

            pending = np.concatenate([pending, new_audio])
            processed_seconds += len(new_audio) / SAMPLE_RATE
            dur = len(pending) / SAMPLE_RATE

            silent_tail = False
            tail_n = int(END_SILENCE_SECONDS * SAMPLE_RATE)
            if len(pending) >= tail_n:
                last = pending[-tail_n:]
                silent_tail = float(np.sqrt(np.mean(np.square(last)))) < SILENCE_RMS

            if silent_tail or dur >= MAX_UTTERANCE_SECONDS:
                if dur >= MIN_UTTERANCE_SECONDS:
                    self._emit(pending, pending_start)
                pending = np.zeros(0, dtype=np.float32)
                has_speech = False

        # Descarrega o que sobrou ao encerrar
        if len(pending) / SAMPLE_RATE >= MIN_UTTERANCE_SECONDS:
            self._emit(pending, pending_start)
        self.status = "idle"


live_transcriber = LiveTranscriber()

