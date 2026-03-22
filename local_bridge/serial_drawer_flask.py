import json
import logging
import os
from pathlib import Path

from flask import Flask, jsonify, Response
import serial


BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "drawer_config.json"

DEFAULT_CONFIG = {
    "com_port": "COM3",
    "baudrate": 9600,
    "bytesize": 8,
    "parity": "N",
    "stopbits": 1,
    "timeout": 1,
}

# ESC p m t1 t2
DRAWER_COMMAND = b"\x1B\x70\x00\x19\xFA"


def _load_file_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}

    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        if not isinstance(payload, dict):
            return {}
        return payload
    except Exception:
        logging.exception("No se pudo leer drawer_config.json")
        return {}


def _get_config() -> dict:
    file_config = _load_file_config()
    cfg = {**DEFAULT_CONFIG, **file_config}

    # Variables de entorno tienen mayor prioridad
    cfg["com_port"] = os.getenv("DRAWER_COM_PORT", str(cfg["com_port"]))
    cfg["baudrate"] = int(os.getenv("DRAWER_BAUDRATE", str(cfg["baudrate"])))
    cfg["bytesize"] = int(os.getenv("DRAWER_BYTESIZE", str(cfg["bytesize"])))
    cfg["parity"] = os.getenv("DRAWER_PARITY", str(cfg["parity"]))
    cfg["stopbits"] = int(os.getenv("DRAWER_STOPBITS", str(cfg["stopbits"])))
    cfg["timeout"] = float(os.getenv("DRAWER_TIMEOUT", str(cfg["timeout"])))

    return cfg


def _open_drawer_serial(cfg: dict):
    logging.info("Abriendo cajon por puerto serial: %s", cfg["com_port"])
    with serial.Serial(
        port=cfg["com_port"],
        baudrate=cfg["baudrate"],
        bytesize=cfg["bytesize"],
        parity=cfg["parity"],
        stopbits=cfg["stopbits"],
        timeout=cfg["timeout"],
    ) as ser:
        ser.write(DRAWER_COMMAND)
        ser.flush()


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/status")
    def status():
        cfg = _get_config()
        return jsonify({"ok": True, "mode": "serial", "com_port": cfg["com_port"]})

    @app.get("/abrir-cajon")
    def abrir_cajon():
        cfg = _get_config()
        try:
            _open_drawer_serial(cfg)
            return Response("ok", mimetype="text/plain")
        except Exception as exc:
            logging.exception("Error abriendo cajon")
            return jsonify({"ok": False, "error": str(exc), "com_port": cfg.get("com_port")}), 500

    return app


if __name__ == "__main__":
    logging.basicConfig(
        level=os.getenv("DRAWER_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    host = os.getenv("DRAWER_HOST", "127.0.0.1")
    port = int(os.getenv("DRAWER_PORT", "5000"))

    app = create_app()
    logging.info("Servicio de cajon serial iniciado en http://%s:%s", host, port)
    app.run(host=host, port=port)
