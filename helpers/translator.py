import json
import time
import httpx
from typing import Dict, Any, List
from config import OLLAMA_BASE_URL, DEFAULT_OLLAMA_MODEL

_GOOGLE_URL = "https://translate.googleapis.com/translate_a/single"
_LANG_NAMES = {"en": "English", "pt": "Brazilian Portuguese"}


def _google(text: str, source: str, target: str) -> Dict[str, Any]:
    r = httpx.get(
        _GOOGLE_URL,
        params={"client": "gtx", "sl": source, "tl": target, "dt": "t", "q": text},
        timeout=8.0,
    )
    r.raise_for_status()
    data = r.json()
    translated = "".join(part[0] for part in data[0] if part and part[0])
    detected = data[2] if len(data) > 2 and isinstance(data[2], str) else source
    return {"translation": translated, "detected": detected}


def _ollama(text: str, source: str, target: str) -> str:
    src = _LANG_NAMES.get(source, "the source language")
    tgt = _LANG_NAMES.get(target, target)
    prompt = (
        f"Translate the following text from {src} to {tgt}. "
        f"Reply with ONLY the translation, nothing else.\n\n{text}"
    )
    r = httpx.post(
        f"{OLLAMA_BASE_URL}/api/generate",
        json={"model": DEFAULT_OLLAMA_MODEL, "prompt": prompt, "stream": False, "think": False,
              "options": {"temperature": 0.1}},
        timeout=60.0,
    )
    r.raise_for_status()
    out = r.json().get("response", "").strip()
    if "</think>" in out:  # modelos com raciocínio (ex.: qwen3) podem emitir <think>...</think>
        out = out.split("</think>", 1)[1].strip()
    return out


_PT_HINTS = {
    "o", "a", "os", "as", "de", "do", "da", "que", "não", "nao", "um", "uma", "para", "com",
    "eu", "você", "voce", "é", "e", "em", "se", "por", "mais", "como", "casa", "olá", "ola",
    "obrigado", "bom", "dia", "tudo", "bem", "isso", "esse", "esta", "está", "estou", "muito",
}


def _guess_is_pt(text: str) -> bool:
    low = text.lower()
    if any(ch in low for ch in "ãõçáéíóúâêôà"):
        return True
    words = [w.strip(".,!?;:") for w in low.split()]
    return bool(words) and sum(w in _PT_HINTS for w in words) / len(words) >= 0.3


def _mymemory(text: str, source: str, target: str) -> str:
    r = httpx.get(
        "https://api.mymemory.translated.net/get",
        params={"q": text, "langpair": f"{source}|{target}"},
        timeout=8.0,
    )
    r.raise_for_status()
    data = r.json()
    out = data.get("responseData", {}).get("translatedText", "")
    try:
        score = float(data.get("responseData", {}).get("match", 0))
    except (TypeError, ValueError):
        score = 0.0
    if not out or "MYMEMORY WARNING" in out.upper():
        raise RuntimeError("MyMemory sem resposta válida")
    if score < 0.85:
        # A memória de tradução devolve frases sem relação quando a correspondência é fraca
        raise RuntimeError(f"MyMemory com baixa confiança ({score:.2f})")
    return out


_cache: Dict[tuple, Dict[str, Any]] = {}
_google_blocked_until = 0.0


def translate(text: str, direction: str = "auto") -> Dict[str, Any]:
    """direction: 'auto' (pt->en / qualquer->pt), 'en-pt' ou 'pt-en'."""
    global _google_blocked_until
    text = (text or "").strip()
    if not text:
        return {"translation": "", "source": "", "target": ""}

    key = (text, direction)
    if key in _cache:
        return _cache[key]

    if direction == "en-pt":
        source, target = "en", "pt"
    elif direction == "pt-en":
        source, target = "pt", "en"
    else:
        source, target = "auto", "pt"

    errors = []

    # 1) Google (endpoint não oficial; pode devolver 429)
    try:
        if time.time() < _google_blocked_until:
            raise RuntimeError("Google em pausa após limite de requisições (429)")
        res = _google(text, source, target)
        if direction == "auto" and res["detected"].startswith("pt"):
            source, target = "pt", "en"
            res = _google(text, source, target)
        elif direction == "auto":
            source = res["detected"]
        result = {"translation": res["translation"], "source": source, "target": target, "engine": "google"}
        _cache[key] = result
        return result
    except Exception as e:
        if "429" in str(e):
            _google_blocked_until = time.time() + 90
        errors.append(f"Google: {e}")
        print(f"[Translator] Google falhou ({e}), tentando Ollama...")

    # Sem detecção do Google, deduz o idioma de origem
    if source == "auto":
        source = "pt" if _guess_is_pt(text) else "en"
    target = "en" if source == "pt" else "pt"

    # 2) Ollama local (melhor qualidade que a memória de tradução para frases curtas)
    try:
        result = {"translation": _ollama(text, source, target), "source": source, "target": target, "engine": "ollama"}
        _cache[key] = result
        return result
    except Exception as e:
        errors.append(f"Ollama: {e}")
        raise RuntimeError(
            "Nenhum tradutor disponível (o Google limitou as requisições e o Ollama não respondeu). "
            "Inicie o Ollama ou tente novamente em instantes. " + " | ".join(errors)
        )


# ===== Tradução em lote (caderno de transcrição) =====
def _google_batch(lines: List[str]) -> List[str]:
    """Traduz várias linhas numa só requisição (separadas por quebra de linha)."""
    res = _google("\n".join(lines), "en", "pt")["translation"]
    out = res.split("\n")
    if len(out) != len(lines):
        raise RuntimeError("Google devolveu um número de linhas diferente do enviado")
    return [o.strip() for o in out]


def _ollama_batch(lines: List[str]) -> List[str]:
    numbered = "\n".join(f"{i + 1}. {l}" for i, l in enumerate(lines))
    prompt = (
        "Translate each numbered English line to Brazilian Portuguese. "
        'Reply ONLY with JSON in the form {"translations": ["...", "..."]} '
        f"with exactly {len(lines)} strings, in the same order.\n\n{numbered}"
    )
    r = httpx.post(
        f"{OLLAMA_BASE_URL}/api/generate",
        json={"model": DEFAULT_OLLAMA_MODEL, "prompt": prompt, "stream": False,
              "think": False, "format": "json", "options": {"temperature": 0.1}},
        timeout=180.0,
    )
    r.raise_for_status()
    items = json.loads(r.json().get("response", "{}")).get("translations", [])
    if len(items) != len(lines):
        raise RuntimeError("Ollama devolveu um número de traduções diferente do enviado")
    return [str(i).strip() for i in items]


def translate_batch(lines: List[str], progress=None) -> List[str]:
    """Traduz EN->PT uma lista de linhas, preservando a ordem. Falhas viram string vazia."""
    global _google_blocked_until
    results = [""] * len(lines)

    # Agrupa em blocos de até ~3000 caracteres / 40 linhas
    chunks, cur, cur_len = [], [], 0
    for idx, line in enumerate(lines):
        if cur and (cur_len + len(line) > 3000 or len(cur) >= 40):
            chunks.append(cur)
            cur, cur_len = [], 0
        cur.append(idx)
        cur_len += len(line) + 1
    if cur:
        chunks.append(cur)

    for n, idxs in enumerate(chunks):
        batch = [lines[i] for i in idxs]
        out = None

        if time.time() >= _google_blocked_until:
            try:
                out = _google_batch(batch)
            except Exception as e:
                if "429" in str(e):
                    _google_blocked_until = time.time() + 90
                print(f"[Translator] Lote {n + 1}/{len(chunks)}: Google falhou ({e})")

        if out is None:
            try:
                out = _ollama_batch(batch)
            except Exception as e:
                print(f"[Translator] Lote {n + 1}/{len(chunks)}: Ollama falhou ({e})")

        if out:
            for i, t in zip(idxs, out):
                results[i] = t

        if progress:
            progress(n + 1, len(chunks))
        time.sleep(0.6)

    return results
