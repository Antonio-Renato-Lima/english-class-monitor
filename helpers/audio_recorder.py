import os
import time
import threading
import warnings
import soundcard as sc
import numpy as np
from scipy.io import wavfile
from typing import Optional, Tuple, List
from config import AUDIO_DIR

# Suprime avisos benignos de descontinuidade de buffer do driver WASAPI
warnings.filterwarnings("ignore", category=sc.SoundcardRuntimeWarning)


class AudioRecorder:
    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self.is_recording = False
        self._threads: List[threading.Thread] = []
        self._loop_chunks: List[np.ndarray] = []
        self._mic_chunks: List[np.ndarray] = []
        self._lock = threading.Lock()
        self.current_volume: float = 0.0
        self.start_time: float = 0.0

    def start(self):
        with self._lock:
            if self.is_recording:
                return
            self.is_recording = True
            self._loop_chunks = []
            self._mic_chunks = []
            self.current_volume = 0.0
            self.start_time = time.time()
            self._threads = []

            # Inicia thread dedicada para capturar áudio do sistema (Zoom/Meet/Teams)
            t_loop = threading.Thread(target=self._record_loopback_worker, daemon=True)
            # Inicia thread dedicada para capturar microfone do usuário
            t_mic = threading.Thread(target=self._record_mic_worker, daemon=True)

            self._threads = [t_loop, t_mic]
            t_loop.start()
            t_mic.start()

    def _record_loopback_worker(self):
        """Thread independente para captura contínua de áudio do alto-falante (loopback)."""
        loopback_mic = None
        try:
            default_spk = sc.default_speaker()
            loopback_mic = sc.get_microphone(id=str(default_spk.name), include_loopback=True)
        except Exception as e:
            print(f"[AudioRecorder] Aviso ao obter loopback: {e}")
            return

        chunk_frames = int(self.sample_rate * 0.4)  # 400ms chunks

        try:
            with loopback_mic.recorder(samplerate=self.sample_rate, channels=1) as rec:
                while self.is_recording:
                    try:
                        data = rec.record(numframes=chunk_frames)
                        if data.ndim > 1:
                            data = np.mean(data, axis=1)
                        f32 = data.astype(np.float32)

                        with self._lock:
                            self._loop_chunks.append(f32)
                            rms = float(np.sqrt(np.mean(np.square(f32)))) if len(f32) > 0 else 0.0
                            self.current_volume = max(self.current_volume, min(1.0, rms * 4.0))
                    except Exception:
                        time.sleep(0.05)
        except Exception as e:
            print(f"[AudioRecorder] Erro no gravador de loopback: {e}")

    def _record_mic_worker(self):
        """Thread independente para captura contínua do microfone físico do usuário."""
        user_mic = None
        try:
            user_mic = sc.default_microphone()
        except Exception as e:
            print(f"[AudioRecorder] Aviso ao obter microfone: {e}")
            return

        chunk_frames = int(self.sample_rate * 0.4)  # 400ms chunks

        try:
            with user_mic.recorder(samplerate=self.sample_rate, channels=1) as rec:
                while self.is_recording:
                    try:
                        data = rec.record(numframes=chunk_frames)
                        if data.ndim > 1:
                            data = np.mean(data, axis=1)
                        f32 = data.astype(np.float32)

                        with self._lock:
                            self._mic_chunks.append(f32)
                            rms = float(np.sqrt(np.mean(np.square(f32)))) if len(f32) > 0 else 0.0
                            self.current_volume = max(self.current_volume, min(1.0, rms * 4.0))
                    except Exception:
                        time.sleep(0.05)
        except Exception as e:
            print(f"[AudioRecorder] Erro no gravador de microfone: {e}")

    def stop(self, lesson_id: int) -> Tuple[Optional[str], float]:
        """Finaliza a gravação, sincroniza os canais de áudio, salva o arquivo WAV e retorna (filename, duration_seconds)."""
        with self._lock:
            self.is_recording = False

        for t in self._threads:
            t.join(timeout=2.0)

        duration = max(0.0, time.time() - self.start_time)

        loop_audio = np.concatenate(self._loop_chunks, axis=0) if self._loop_chunks else None
        mic_audio = np.concatenate(self._mic_chunks, axis=0) if self._mic_chunks else None

        if loop_audio is None and mic_audio is None:
            return None, duration

        try:
            # Sincroniza e equaliza o tamanho dos arrays se ambos existirem
            if loop_audio is not None and mic_audio is not None:
                max_len = max(len(loop_audio), len(mic_audio))
                if len(loop_audio) < max_len:
                    loop_audio = np.pad(loop_audio, (0, max_len - len(loop_audio)))
                if len(mic_audio) < max_len:
                    mic_audio = np.pad(mic_audio, (0, max_len - len(mic_audio)))

                # Áudio do sistema (professor/Zoom) + Microfone do usuário
                mixed = loop_audio * 0.85 + mic_audio * 1.0
            elif loop_audio is not None:
                mixed = loop_audio
            else:
                mixed = mic_audio

            # Clipa e converte para PCM 16-bit
            clamped = np.clip(mixed, -1.0, 1.0)
            int16_audio = (clamped * 32767).astype(np.int16)

            filename = f"lesson_{lesson_id}.wav"
            filepath = os.path.join(AUDIO_DIR, filename)

            wavfile.write(filepath, self.sample_rate, int16_audio)
            actual_duration = len(int16_audio) / float(self.sample_rate)
            return filename, actual_duration
        except Exception as e:
            print(f"[AudioRecorder] Erro ao salvar arquivo WAV: {e}")
            return None, duration


# Instância global singleton
audio_recorder = AudioRecorder(sample_rate=16000)
