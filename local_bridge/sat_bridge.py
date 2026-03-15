import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

try:
    import win32print
except Exception as exc:
    raise RuntimeError("pywin32 no esta instalado o no se pudo importar") from exc


DEFAULT_PRINTER = os.getenv("SAT_PRINTER_NAME", "SAT TP-1580")
DEFAULT_ENCODING = os.getenv("SAT_ENCODING", "cp850")

app = FastAPI(title="SAT Local Bridge", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class PrintPayload(BaseModel):
    text: str
    printer_name: str | None = None


class DrawerPayload(BaseModel):
    printer_name: str | None = None


def _send_raw(printer_name: str, data: bytes, job_name: str):
    try:
        handle = win32print.OpenPrinter(printer_name)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"No se pudo abrir impresora: {printer_name}. {exc}")

    try:
        job = win32print.StartDocPrinter(handle, 1, (job_name, None, "RAW"))
        win32print.StartPagePrinter(handle)
        win32print.WritePrinter(handle, data)
        win32print.EndPagePrinter(handle)
        win32print.EndDocPrinter(handle)
        return job
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error enviando datos RAW a impresora: {exc}")
    finally:
        win32print.ClosePrinter(handle)


@app.get("/status")
def status():
    default_printer = win32print.GetDefaultPrinter()
    return {
        "ok": True,
        "default_printer": default_printer,
        "configured_printer": DEFAULT_PRINTER,
    }


@app.post("/print-ticket")
def print_ticket(payload: PrintPayload):
    printer = payload.printer_name or DEFAULT_PRINTER
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="El ticket esta vacio")

    esc_init = b"\x1b@"
    esc_cut = b"\n\n\n\x1dVA0"
    body = text.encode(DEFAULT_ENCODING, errors="replace")
    _send_raw(printer, esc_init + body + esc_cut, "Ticket SAT")
    return {"ok": True, "printer": printer}


@app.post("/open-drawer")
def open_drawer(payload: DrawerPayload):
    printer = payload.printer_name or DEFAULT_PRINTER
    esc_init = b"\x1b@"
    esc_pulse = b"\x1bp\x00\x19\xfa"
    _send_raw(printer, esc_init + esc_pulse, "Abrir cajon SAT")
    return {"ok": True, "printer": printer}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("sat_bridge:app", host="127.0.0.1", port=8787, reload=False)
