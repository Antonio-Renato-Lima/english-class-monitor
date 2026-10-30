"""Google Cloud Translation (API oficial v2) com trava de cota mensal de caracteres."""
import json
import os
import threading
import time
from typing import List

import httpx

from config import STORAGE_DIR, GOOGLE_TRANSLATE_API_KEY, GOOGLE_TRANSLATE_MONTHLY_LIMIT

_URL = "https://translation.googleapis.com/language/translate/v2"
_USAGE_FILE = os.path.join(STORAGE_DIR, "google_translate_usage.json")
_lock = threading.Lock()


class QuotaExceeded(Exception):
    """A cota mensal de caracteres configurada seria ultrapassada."""


def is_enabled() -> bool:
    return bool(GOOGLE_TRANSLATE_API_KEY)


def _current_month() -> str:
    return time.strftime("%Y-%m")


def _load() -> dict:
    try:
        with open(_USAGE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("month") == _current_month():
            return data
    except Exception:
        pass
    return {"month": _current_month(), "chars": 0}  # novo mês: contador zerado


def _save(data: dict):
    tmp = _USAGE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, _USAGE_FILE)


def get_usage() -> dict:
    with _lock:
        data = _load()
    return {
        "enabled": is_enabled(),
        "month": data["month"],
        "used": data["chars"],
        "limit": GOOGLE_TRANSLATE_MONTHLY_LIMIT,
        "remaining": max(0, GOOGLE_TRANSLATE_MONTHLY_LIMIT - data["chars"]),
    }


def _reserve(chars: int):
    """Reserva caracteres ANTES da chamada; recusa se ultrapassar o limite."""
    with _lock:
        data = _load()
        if data["chars"] + chars > GOOGLE_TRANSLATE_MONTHLY_LIMIT:
            raise QuotaExceeded(
                f"Cota mensal do Google oficial atingida ({data['chars']:,}/{GOOGLE_TRANSLATE_MONTHLY_LIMIT:,} caracteres)"
            )
        data["chars"] += chars
        _save(data)


def _refund(chars: int):
    with _lock:
        data = _load()
        data["chars"] = max(0, data["chars"] - chars)
        _save(data)


def translate_texts(texts: List[str], source: str = "en", target: str = "pt") -> List[str]:
    """Traduz uma lista de textos (um 'q' por item). Lança QuotaExceeded se passar do limite."""
    if not is_enabled():
        raise RuntimeError("Chave da API do Google Cloud Translation não configurada")
    if not texts:
        return []

    chars = sum(len(t) for t in texts)
    _reserve(chars)
    try:
        r = httpx.post(
            _URL,
            params={"key": GOOGLE_TRANSLATE_API_KEY},
            json={"q": texts, "source": source, "target": target, "format": "text"},
            timeout=20.0,
        )
        r.raise_for_status()
        items = r.json()["data"]["translations"]
        if len(items) != len(texts):
            raise RuntimeError("API oficial devolveu um número de traduções diferente do enviado")
        return [i["translatedText"] for i in items]
    except Exception:
        _refund(chars)  # requisição não concluída: não consome cota
        raise
