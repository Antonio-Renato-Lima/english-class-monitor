import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Servidor Flask
PORT = int(os.getenv("PORT", 8002))
HOST = os.getenv("HOST", "127.0.0.1")
DEBUG = os.getenv("DEBUG", "True").lower() == "true"
SECRET_KEY = os.getenv("SECRET_KEY", "aulas-ingles-secret-key-2026")

# Pastas de Armazenamento
STORAGE_DIR = os.path.join(BASE_DIR, "storage")
AUDIO_DIR = os.path.join(STORAGE_DIR, "audio")
SCREENSHOTS_DIR = os.path.join(STORAGE_DIR, "screenshots")

for folder in (STORAGE_DIR, AUDIO_DIR, SCREENSHOTS_DIR):
    os.makedirs(folder, exist_ok=True)

# Banco de Dados SQLite
DB_NAME = os.getenv("DB_NAME", "aulas_ingles.db")
DB_PATH = os.path.join(STORAGE_DIR, DB_NAME)

# Modelo Whisper (Transcrição de Áudio com IA Local)
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small.en")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cuda")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "float16")

# Ollama Local (Resumo, Vocabulário e Gramática)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
DEFAULT_OLLAMA_MODEL = os.getenv("DEFAULT_OLLAMA_MODEL", "qwen3:8b")

# Captura de Tela (Slides)
SCREENSHOT_INTERVAL = int(os.getenv("SCREENSHOT_INTERVAL", 15))
SLIDE_CHANGE_THRESHOLD = float(os.getenv("SLIDE_CHANGE_THRESHOLD", 0.04))
MONITOR_INDEX = int(os.getenv("MONITOR_INDEX", 0))
