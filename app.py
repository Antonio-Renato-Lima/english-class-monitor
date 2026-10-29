"""app.py
======
Arquivo principal da aplicação (entrypoint).
Inicializa o servidor Flask, configura CORS e registra as rotas (Blueprints)
da API e da interface Web, seguindo o padrão de arquitetura do BotTonho e AulasDescomplica.
"""

import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from flask import Flask
from flask_cors import CORS
from config import PORT, HOST, DEBUG, SECRET_KEY
from helpers.database import init_db
from routes.api import api_bp
from routes.web import web_bp


def create_app():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(base_dir, "templates")
    static_path = os.path.join(base_dir, "static")

    app = Flask(__name__, template_folder=template_path, static_folder=static_path)
    app.config["SECRET_KEY"] = SECRET_KEY

    # Habilita CORS
    CORS(app, resources={r"/*": {"origins": "*"}})

    # Inicializa banco de dados SQLite
    init_db()

    # Registra Blueprints
    app.register_blueprint(web_bp)
    app.register_blueprint(api_bp)

    return app


if __name__ == "__main__":
    app = create_app()
    print("==================================================================")
    print("🇬🇧 English Class Monitor & Transcriber (Padrão BotTonho / Descomplica)")
    print(f"🚀 Servidor iniciado em: http://{HOST}:{PORT}")
    print("==================================================================")
    app.run(host=HOST, port=PORT, debug=DEBUG)
