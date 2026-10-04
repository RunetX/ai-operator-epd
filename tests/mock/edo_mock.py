r"""Мок оператора ЭДО для пакета ЭТрН: принимает отправку титула из 1С и пишет журнал.

Настоящий обмен с 1С-ЭДО и ГИС ЭПД в демо не идет: транспорт пакета (ИИОЭ_Транспорт)
отправляет титул сюда, если в константе ИИОЭ_АдресТестовогоСервераОператораЭДО задан адрес мока.
Ответы контрагентов (Т2, Т3, Т4, отказы) мок не рассылает: их создает генератор состояний в тестовом расширении.

    python tests/mock/edo_mock.py --port 8882

API для 1С:
    POST /send     {"etrn": УИД, "title": "T1", "file_id": ..., "workflow_id": ..., "message": УИД}
                   -> 200 {"ok": true, "message_id": ...}
                   -> 200 {"ok": false, "code": ..., "text": ..., "blocking": bool} - ошибка оператора

Управление:
    POST /_mock/mode     {"send": "ok" | "error" | "transient"} - как отвечать на следующие отправки
    GET  /_mock/journal  [{"path": ..., "body": {...}, "answer": {...}}, ...]
    POST /_mock/reset    очистить журнал, режим ok
"""

import argparse
import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ERRORS = {
    "error": {"ok": False, "code": "EPD-422", "blocking": True,
              "text": "Не заполнен КПП грузополучателя: титул не соответствует формату ГИС ЭПД."},
    "transient": {"ok": False, "code": "EPD-503", "blocking": False,
                  "text": "Сервис оператора временно недоступен, повторите отправку позже."},
}


class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.mode = "ok"
        self.journal = []


class Handler(BaseHTTPRequestHandler):
    state = State()

    def log_message(self, *args):
        pass

    def _send(self, status, payload):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8-sig") or "{}"
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"_raw": raw}

    def do_GET(self):
        if self.path == "/_mock/journal":
            with self.state.lock:
                self._send(200, list(self.state.journal))
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        body = self._body()
        with self.state.lock:
            if self.path == "/_mock/mode":
                mode = body.get("send", "ok")
                if mode not in ("ok", "error", "transient"):
                    self._send(400, {"error": f"unknown mode {mode}"})
                    return
                self.state.mode = mode
                self._send(200, {"mode": mode})
            elif self.path == "/_mock/reset":
                self.state.mode = "ok"
                self.state.journal = []
                self._send(200, {"reset": True})
            elif self.path == "/send":
                if self.state.mode == "ok":
                    answer = {"ok": True, "message_id": str(uuid.uuid4())}
                else:
                    answer = dict(ERRORS[self.state.mode])
                self.state.journal.append({"path": self.path, "body": body, "answer": answer})
                self._send(200, answer)
            else:
                self.state.journal.append({"path": self.path, "body": body, "answer": None})
                self._send(404, {"error": "not found"})


def start(port):
    """Запускает мок в фоновом потоке и возвращает сервер (server.shutdown() останавливает)."""
    Handler.state = State()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8882)
    ThreadingHTTPServer(("127.0.0.1", parser.parse_args().port), Handler).serve_forever()


if __name__ == "__main__":
    main()
