# 🇬🇧 English Class Monitor & Study Notebook

Sistema inteligente para captura de tela (slides/lousa), legendas ao vivo em tempo real, transcrição acelerada por GPU e geração automática de cadernos de estudo para aulas de inglês (Zoom, Teams, Google Meet).

---

## 🚀 Principais Funcionalidades

1. **🎙️ Gravação de Áudio Dual (WASAPI Loopback + Microfone):**
   - Captura em canais separados o áudio do sistema (voz do professor/colegas que sai nos alto-falantes ou fones) e o seu microfone.
   - Mixagem automática em WAV 16 kHz com equalização de volume.

2. **💬 Legendas ao Vivo em Tempo Real (Estilo Teams / Zoom):**
   - Transcrição contínua na tela enquanto a aula acontece usando o **faster-whisper** na GPU.
   - Detecção de pausas de fala (VAD) para exibir frases instantaneamente.
   - Clique em qualquer fala na tela para enviá-la direto ao Tradutor Rápido.

3. **🌐 Tradutor Rápido Integrado (Com Trava de Segurança):**
   - Tradução ágil entre Inglês e Português sem precisar abrir outra aba ou aplicativo.
   - Suporte a acionamento direto via tecla **Enter** (e `Shift+Enter` para quebra de linha).
   - Suporte à API oficial do **Google Cloud Translation** com **trava mensal de caracteres configurável** (padrão 500.000 caracteres gratuitos), além de fallback resiliente para modelos locais via **Ollama**.

4. **📸 Detecção Inteligente de Mudança de Slide:**
   - Capturas de tela automáticas sempre que o professor muda de slide, compartilha uma nova tela ou escreve na lousa.
   - Botão rápido de captura manual para momentos pontuais.

5. **⚡ Transcrição Completa Pós-Aula (NVIDIA RTX / CUDA):**
   - Processamento completo na GPU (`float16`), transcrevendo 1 hora de aula em menos de 2 minutos com minutagem exata.

6. **📖 Caderno de Estudos com Tradução Linha a Linha & IA:**
   - Cada fala transcrita inclui a tradução correspondente em português logo abaixo, com estilo visual destacado.
   - Geração automática de resumo didático, anotações gramaticais e lista de vocabulário/phrasal verbs via **Ollama** (ex: `qwen3:8b` ou `llama3`).
   - Modal com overlay em tempo real exibindo o progresso de tradução por blocos.

7. **🎧 Linha do Tempo Sincronizada (Slide + Áudio):**
   - Associa cada slide ao momento exato em que o assunto foi explicado.
   - Player de áudio interativo: clique em qualquer minutagem para ouvir o trecho.

8. **📥 Exportação para Obsidian e Notion:**
   - Exportação completa em formato **Markdown** estruturado com imagens, vocabulário e transcrições bilíngues.

---

## 📂 Arquitetura do Projeto

```
AulasIngles/
├── app.py                     # Entry point (create_app, CORS, Blueprints)
├── config.py                  # Exportador de configurações
├── requirements.txt           # Dependências do projeto
├── iniciar.bat                # Script rápido para iniciar o servidor
├── .env.example               # Modelo de variáveis de ambiente
├── gerar_srt.py               # Utilitário para gerar legendas .srt para vídeos (ex: LinkedIn)
├── helpers/
│   ├── config/
│   │   └── settings.py        # Configurações de portas, diretórios e modelos
│   ├── database.py            # SQLite para aulas, transcrições e screenshots
│   ├── audio_recorder.py      # Gravação de Loopback do Windows + Microfone
│   ├── live_transcriber.py    # Streaming de legendas ao vivo na GPU
│   ├── screen_capture.py      # Captura de tela com detecção de mudança de slide
│   ├── transcriber.py         # Whisper na GPU (CUDA / faster-whisper)
│   ├── translator.py          # Mecanismo de tradução e tradução em lote
│   ├── google_cloud_translate.py # API oficial Google Cloud com trava de cota
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
└── storage/                   # Armazenamento local persistente (ignorado pelo git)
    ├── audio/                 # Áudios gravados das aulas (.wav)
    └── screenshots/           # Prints dos slides da aula (.png)
```

---

## 🛠️ Como Instalar e Replicar

### 1. Pré-requisitos
- **Python 3.10 ou superior**
- **Placa de Vídeo NVIDIA** com suporte a CUDA (recomendado para aceleração por GPU)
- **Ollama** instalado localmente (opcional, para resumos e tradução offline): [ollama.com](https://ollama.com)
  - Modelo recomendado: `ollama run qwen3:8b` (ou `llama3:8b`)

### 2. Clonar o Repositório e Instalar Dependências
```bash
git clone https://github.com/SEU_USUARIO/NOME_DO_REPOSITORIO.git
cd NOME_DO_REPOSITORIO

# Criar e ativar o ambiente virtual
python -m venv .venv
.\.venv\Scripts\activate   # No Windows

# Instalar dependências
pip install -r requirements.txt
```

### 3. Configurar as Variáveis de Ambiente
Copie o arquivo `.env.example` para `.env`:
```bash
copy .env.example .env
```
Edite o arquivo `.env` para personalizar (portas, modelo do Ollama, ou opcionalmente adicionar sua chave do Google Cloud Translation):
```env
GOOGLE_TRANSLATE_API_KEY=sua_chave_opcional
GOOGLE_TRANSLATE_MONTHLY_LIMIT=500000
```
*(Se deixar a chave vazia, o sistema utilizará tradutores gratuitos e o Ollama local automaticamente).*

---

## ▶️ Como Executar

### Opção 1: Atalho Rápido (Windows)
Basta dar dois cliques no arquivo:
```cmd
iniciar.bat
```

### Opção 2: Pelo Terminal
```powershell
.\.venv\Scripts\activate
python app.py
```

Acesse a interface no navegador:
👉 **http://127.0.0.1:8002**

---

## 🛡️ Segurança e Privacidade
- Todos os áudios gravados, imagens de tela e arquivos de banco de dados (`storage/` e `.env`) ficam **estritamente locais na sua máquina** e estão configurados no `.gitignore`.
- Seus dados de aula não sobem para nenhum servidor externo.
- As transcrições do Whisper rodam localmente na GPU.
