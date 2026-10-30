import json
from typing import List, Dict, Any


def format_seconds_to_timestamp(seconds: float) -> str:
    secs = int(seconds)
    hours = secs // 3600
    minutes = (secs % 3600) // 60
    rem_secs = secs % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{rem_secs:02d}"
    return f"{minutes:02d}:{rem_secs:02d}"


def align_transcripts_with_screenshots(
    transcripts: List[Dict[str, Any]],
    screenshots: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Associa cada bloco de transcrição com o print de tela mais recente
    ou mais próximo daquele momento da aula.
    """
    if not transcripts:
        return []

    if not screenshots:
        return [
            {
                "timestamp_str": t["start_str"],
                "start_seconds": t["start_seconds"],
                "text": t["text"],
                "translation": t.get("translation") or "",
                "screenshot": None
            }
            for t in transcripts
        ]

    aligned = []
    for t in transcripts:
        t_sec = t["start_seconds"]
        # Encontra o print tirado antes ou mais próximo do momento falado
        matching_screen = None
        candidates = [s for s in screenshots if s["timestamp_seconds"] <= t_sec + 2.0]
        if candidates:
            matching_screen = candidates[-1]
        else:
            matching_screen = screenshots[0]

        aligned.append({
            "timestamp_str": t["start_str"],
            "start_seconds": t["start_seconds"],
            "end_seconds": t["end_seconds"],
            "text": t["text"],
            "translation": t.get("translation") or "",
            "screenshot": matching_screen["filename"] if matching_screen else None,
            "screenshot_time": matching_screen["timestamp_str"] if matching_screen else None,
        })

    return aligned


def export_lesson_to_markdown(
    lesson: Dict[str, Any],
    transcripts: List[Dict[str, Any]],
    screenshots: List[Dict[str, Any]]
) -> str:
    """Gera um arquivo Markdown rico para estudo (compatível com Obsidian / Notion)."""
    title = lesson.get("title", "Aula de Inglês")
    date_str = lesson.get("started_at", "")
    duration_str = format_seconds_to_timestamp(lesson.get("duration_seconds", 0))

    md = [
        f"# 🇬🇧 {title}",
        f"**Data:** {date_str}  ",
        f"**Duração:** {duration_str}\n",
        "---",
        "## 📌 Resumo da Aula",
        lesson.get("ai_summary") or "Resumo ainda não gerado.",
        "\n---",
        "## 📚 Vocabulário & Expressões-Chave"
    ]

    vocab_raw = lesson.get("vocabulary_json")
    if vocab_raw:
        try:
            vocab_list = json.loads(vocab_raw)
            for item in vocab_list:
                term = item.get("term", "")
                meaning = item.get("meaning", "")
                example = item.get("example", "")
                md.append(f"- **{term}**: {meaning}")
                if example:
                    md.append(f"  > *\"{example}\"*")
        except Exception:
            md.append("*(Erro ao formatar vocabulário)*")
    else:
        md.append("Nenhum vocabulário cadastrado.")

    if lesson.get("grammar_notes"):
        md.append("\n---")
        md.append("## ✍️ Dicas Gramaticais & Correções")
        md.append(lesson["grammar_notes"])

    md.append("\n---")
    md.append("## 📝 Transcrição & Lousa / Slides")

    aligned = align_transcripts_with_screenshots(transcripts, screenshots)
    last_screen = None

    for item in aligned:
        curr_screen = item.get("screenshot")
        if curr_screen and curr_screen != last_screen:
            md.append(f"\n### 📸 Slide [{item.get('screenshot_time', '')}]")
            md.append(f"![Slide](storage/screenshots/{curr_screen})\n")
            last_screen = curr_screen

        md.append(f"**[{item['timestamp_str']}]** {item['text']}")
        if item.get("translation"):
            md.append(f"> 🇧🇷 *{item['translation']}*")

    return "\n".join(md)
