# 🇬🇧 English Class Monitor & Study Notebook

Sistema inteligente para captura de tela (slides/lousa) e transcrição de áudio em tempo real de aulas de inglês (Zoom, Teams, Google Meet), seguindo **exatamente a mesma arquitetura modular do BotTonho e AulasDescomplica**.

---

## 🚀 Principais Funcionalidades

1. **Gravação de Áudio Dual (WASAPI Loopback + Microfone):**
   - Captura tanto a voz do professor e colegas que sai nos seus alto-falantes/fones quanto a sua voz no microfone.
   - Mixagem automática em WAV 16kHz de alta fidelidade.
2. **Detecção Inteligente de Mudança de Slide:**
   - Tira prints automáticos sempre que o professor muda de slide, compartilha a tela ou escreve na lousa.
   - Botão rápido para captura manual a qualquer instante.
3. **Transcrição Acelerada por GPU (NVIDIA RTX 3060):**
   - Roda o modelo **Whisper** localmente com aceleração CUDA (`float16`).
   - Transcreve uma aula de 1 hora em menos de 2 minutos, com minutagem exata e 100% de privacidade.
4. **Caderno de Estudos Inteligente (Ollama / Llama / Qwen):**
   - Gera resumo estruturado da aula.
   - Extrai lista de vocabulário, phrasal verbs e expressões usadas com significado e exemplos.
   - Anota pontos gramaticais e correções feitas pelo professor.
5. **Linha do Tempo Sincronizada (Slide + Fala):**
   - O visualizador alinha a imagem da tela no exato minuto em que a explicação foi dada.
   - Permite clicar em qualquer timestamp para ouvir o trecho do áudio correspondente.
6. **Exportação:**
   - Exporta o caderno completo para **Markdown** formatado para Obsidian ou Notion.

---

## 📂 Arquitetura do Projeto (Padrão BotTonho / AulasDescomplica)

```
d:\Aplicações\AulasIngles\
├── app.py                     # Entry point (create_app, CORS, Blueprints)
├── config.py                  # Exportador de configurações
├── requirements.txt           # Dependências do projeto
├── iniciar.bat                # Atalho rápido para iniciar o servidor
├── .env                       # Variáveis de ambiente
├── helpers/
│   ├── config/
│   │   └── settings.py        # Configurações de portas, diretórios e modelos
│   ├── database.py            # SQLite para aulas, transcrições e screenshots
│   ├── audio_recorder.py      # Gravação de Loopback do Windows + Microfone
│   ├── screen_capture.py      # Captura de tela com detecção de mudança de slide
│   ├── transcriber.py         # Whisper na GPU (CUDA / faster-whisper)
│   ├── ollama_client.py       # Integração local com Ollama (Resumo e Vocabulário)
│   └── utils/
│       └── formatters.py      # Minutagem e exportação para Markdown
├── routes/
│   ├── web.py                 # Blueprint da interface web (Dashboard)
│   └── api.py                 # Endpoints REST (Gravação, Status, Aulas, Mídia)
├── static/
│   ├── css/style.css          # Tema escuro moderno e glassmorphism
│   └── js/app.js              # Controle de gravação, timer e renderização
├── templates/
│   └── index.html             # Interface Web do Monitor e Caderno
└── storage/                   # Armazenamento persistente local
    ├── audio/                 # Áudios gravados das aulas (.wav)
    └── screenshots/           # Prints dos slides da aula (.png)
```

---

## 🛠️ Como Executar

### Opção 1: Atalho Rápido
Basta dar dois cliques no arquivo:
```cmd
iniciar.bat
```

### Opção 2: Pelo Terminal
```powershell
cd d:\Aplicações\AulasIngles
.\.venv\Scripts\activate
python app.py
```

Acesse no navegador:
👉 **http://127.0.0.1:8002**
