import json
import httpx
from typing import Dict, Any, List
from config import OLLAMA_BASE_URL, DEFAULT_OLLAMA_MODEL


def check_ollama_available() -> bool:
    try:
        r = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=2.0)
        return r.status_code == 200
    except Exception:
        return False


def generate_study_material(transcripts: List[Dict[str, Any]], lesson_title: str) -> Dict[str, Any]:
    """
    Gera resumo didático, lista de vocabulário/phrasal verbs e anotações gramaticais
    a partir da transcrição da aula de inglês.
    """
    if not transcripts:
        return {
            "summary": "Nenhuma fala foi capturada durante a aula.",
            "vocabulary_json": "[]",
            "grammar_notes": ""
        }

    # Monta texto corrido com minutagem
    transcript_text = "\n".join([f"[{t['start_str']}] {t['text']}" for t in transcripts[:150]])

    prompt = f"""Você é um professor e tutor de inglês especializado em preparar materiais de estudo claros e práticos para alunos brasileiros.

Abaixo está a transcrição de uma aula de inglês recente ({lesson_title}):
---
{transcript_text}
---

Com base exclusivamente no conteúdo falado na aula, gere um relatório de estudo completo estruturado EXATAMENTE no seguinte formato JSON (sem blocos extras de conversa fora do JSON):

{{
  "summary": "Resumo estruturado dos tópicos principais abordados na aula, dinâmicas feitas e assuntos discutidos (em português claro e didático).",
  "vocabulary": [
    {{
      "term": "palavra ou phrasal verb relevante usado na aula",
      "meaning": "significado e tradução em português",
      "example": "frase de exemplo em inglês contextualizada na aula"
    }}
  ],
  "grammar_notes": "Anotações gramaticais importantes: estruturas trabalhadas (tempos verbais, preposições, pronúncias, falsos amigos ou erros corrigidos pelo professor durante a aula)."
}}
"""

    if not check_ollama_available():
        print("[OllamaClient] Ollama não está acessível no momento.")
        return {
            "summary": "Aula gravada com sucesso. (Ollama indisponível para gerar o resumo automático agora).",
            "vocabulary_json": "[]",
            "grammar_notes": ""
        }

    try:
        print(f"[OllamaClient] Enviando transcrição para o modelo '{DEFAULT_OLLAMA_MODEL}'...")
        response = httpx.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": DEFAULT_OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {
                    "temperature": 0.3,
                    "num_predict": 2048
                }
            },
            timeout=120.0
        )

        if response.status_code == 200:
            result = response.json()
            raw_text = result.get("response", "").strip()
            parsed = json.loads(raw_text)

            summary = parsed.get("summary", "")
            vocab_list = parsed.get("vocabulary", [])
            grammar = parsed.get("grammar_notes", "")

            return {
                "summary": summary,
                "vocabulary_json": json.dumps(vocab_list, ensure_ascii=False),
                "grammar_notes": grammar
            }
        else:
            print(f"[OllamaClient] Resposta inesperada do Ollama: {response.status_code}")
    except Exception as e:
        print(f"[OllamaClient] Erro ao comunicar com Ollama: {e}")

    # Fallback básico
    return {
        "summary": "Aula gravada e transcrita com sucesso.",
        "vocabulary_json": "[]",
        "grammar_notes": ""
    }
