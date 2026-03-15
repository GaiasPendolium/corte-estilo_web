import json
import os
import threading
import tkinter as tk
from tkinter import messagebox, ttk

import requests
import uvicorn
import win32print

from sat_bridge import app


CONFIG_FILE = os.path.join(os.path.dirname(__file__), "bridge_config.json")
HOST = "127.0.0.1"
PORT = 8787


class SatBridgeGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("SAT Bridge Manager")
        self.root.geometry("520x320")
        self.server = None
        self.thread = None

        self.printers = self._list_printers()
        self.config = self._load_config()

        self._build_ui()
        self._refresh_status()

    def _list_printers(self):
        try:
            flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
            data = win32print.EnumPrinters(flags)
            return [item[2] for item in data]
        except Exception:
            return []

    def _load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        default_printer = "SAT TP-1580"
        if self.printers:
            default_printer = self.printers[0]
        return {"printer_name": default_printer, "encoding": "cp850"}

    def _save_config(self):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.config, f, ensure_ascii=True, indent=2)

    def _build_ui(self):
        container = ttk.Frame(self.root, padding=16)
        container.pack(fill=tk.BOTH, expand=True)

        ttk.Label(container, text="SAT TP-1580 / SAT 119X", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        ttk.Label(container, text="Inicia el puente local para imprimir y abrir caja desde la web.").pack(anchor="w", pady=(0, 10))

        row1 = ttk.Frame(container)
        row1.pack(fill=tk.X, pady=6)
        ttk.Label(row1, text="Impresora", width=14).pack(side=tk.LEFT)
        self.printer_var = tk.StringVar(value=self.config.get("printer_name", "SAT TP-1580"))
        self.printer_combo = ttk.Combobox(row1, textvariable=self.printer_var, values=self.printers, state="normal")
        self.printer_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)

        row2 = ttk.Frame(container)
        row2.pack(fill=tk.X, pady=6)
        ttk.Label(row2, text="Encoding", width=14).pack(side=tk.LEFT)
        self.encoding_var = tk.StringVar(value=self.config.get("encoding", "cp850"))
        ttk.Entry(row2, textvariable=self.encoding_var).pack(side=tk.LEFT, fill=tk.X, expand=True)

        row3 = ttk.Frame(container)
        row3.pack(fill=tk.X, pady=12)
        ttk.Button(row3, text="Guardar config", command=self.save_config).pack(side=tk.LEFT)
        ttk.Button(row3, text="Iniciar bridge", command=self.start_bridge).pack(side=tk.LEFT, padx=8)
        ttk.Button(row3, text="Detener bridge", command=self.stop_bridge).pack(side=tk.LEFT)

        row4 = ttk.Frame(container)
        row4.pack(fill=tk.X, pady=6)
        ttk.Button(row4, text="Probar estado", command=self._refresh_status).pack(side=tk.LEFT)
        ttk.Button(row4, text="Abrir /docs", command=self.open_docs).pack(side=tk.LEFT, padx=8)

        self.status_var = tk.StringVar(value="Estado: detenido")
        ttk.Label(container, textvariable=self.status_var, foreground="#0f766e").pack(anchor="w", pady=(12, 4))

        self.url_var = tk.StringVar(value=f"URL: http://{HOST}:{PORT}/status")
        ttk.Label(container, textvariable=self.url_var).pack(anchor="w")

    def save_config(self):
        self.config["printer_name"] = self.printer_var.get().strip() or "SAT TP-1580"
        self.config["encoding"] = self.encoding_var.get().strip() or "cp850"
        self._save_config()

        try:
            requests.post(
                f"http://{HOST}:{PORT}/config",
                json={"printer_name": self.config["printer_name"], "encoding": self.config["encoding"]},
                timeout=2,
            )
        except Exception:
            pass

        messagebox.showinfo("SAT Bridge", "Configuración guardada")

    def start_bridge(self):
        if self.thread and self.thread.is_alive():
            messagebox.showinfo("SAT Bridge", "El bridge ya está en ejecución")
            return

        self.save_config()
        os.environ["SAT_PRINTER_NAME"] = self.config["printer_name"]
        os.environ["SAT_ENCODING"] = self.config["encoding"]

        def run_server():
            self.server = uvicorn.Server(
                uvicorn.Config(app, host=HOST, port=PORT, log_level="warning")
            )
            self.server.run()

        self.thread = threading.Thread(target=run_server, daemon=True)
        self.thread.start()
        self.root.after(600, self._refresh_status)

    def stop_bridge(self):
        if self.server:
            self.server.should_exit = True
        self.root.after(800, self._refresh_status)

    def _refresh_status(self):
        try:
            r = requests.get(f"http://{HOST}:{PORT}/status", timeout=2)
            data = r.json()
            self.status_var.set(
                f"Estado: activo | Impresora: {data.get('configured_printer', '-')} | Encoding: {data.get('encoding', '-') }"
            )
        except Exception:
            self.status_var.set("Estado: detenido")

    def open_docs(self):
        import webbrowser

        webbrowser.open(f"http://{HOST}:{PORT}/docs")


def main():
    root = tk.Tk()
    SatBridgeGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
