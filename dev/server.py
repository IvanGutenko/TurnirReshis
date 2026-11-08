#!/usr/bin/env python3
"""Вариант C: веб-страница + backend API. Только стандартная библиотека Python 3.9+.

Запуск:  python3 server.py            (http://127.0.0.1:8000)
         python3 server.py --host 0.0.0.0 --port 8080   (для хостинга)

API (JSON):
  POST /api/register  {login, password}       регистрация (сразу входит)
  POST /api/login     {login, password}       авторизация, ставит cookie-сессию
  POST /api/logout                            выход
  GET  /api/me                                текущий пользователь
  GET  /api/routes                            маршруты и доступные даты
  POST /api/forecast  {origin, destination, date, price}   прогноз (только для вошедших)
"""
import argparse
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from forecast_core import DATA_DIR, ForecastError, Forecaster

BASE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(BASE, "static")
USERS_FILE = os.environ.get("USERS_FILE", os.path.join(DATA_DIR, "users.json"))
SESSION_TTL = 7 * 24 * 3600
LOGIN_RE = re.compile(r"^[A-Za-z0-9_.\-]{3,32}$")
PBKDF2_ROUNDS = 200_000

FORECASTER = Forecaster()
_users_lock = threading.Lock()
_sessions = {}  # token -> (login, expires_at)
_sessions_lock = threading.Lock()


# --- пользователи -----------------------------------------------------------
def _load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE, encoding="utf-8") as f:
        return json.load(f)


def _save_users(users):
    tmp = USERS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=1)
    os.replace(tmp, USERS_FILE)


def _hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), PBKDF2_ROUNDS).hex()


def register(login, password):
    if not LOGIN_RE.match(login or ""):
        raise ForecastError("Логин: 3–32 символа, латиница, цифры, _ . -")
    if len(password or "") < 6:
        raise ForecastError("Пароль должен быть не короче 6 символов")
    with _users_lock:
        users = _load_users()
        if login.lower() in {u.lower() for u in users}:
            raise ForecastError("Такой логин уже занят")
        salt = secrets.token_hex(16)
        users[login] = {"salt": salt, "hash": _hash(password, salt), "created": int(time.time())}
        _save_users(users)


def check_password(login, password):
    with _users_lock:
        user = _load_users().get(login or "")
    if not user:
        _hash(password or "", "00" * 16)  # одинаковое время ответа для несуществующего логина
        return False
    return hmac.compare_digest(user["hash"], _hash(password or "", user["salt"]))


def new_session(login):
    token = secrets.token_urlsafe(32)
    with _sessions_lock:
        _sessions[token] = (login, time.time() + SESSION_TTL)
    return token


def session_user(token):
    with _sessions_lock:
        item = _sessions.get(token or "")
        if not item:
            return None
        if item[1] < time.time():
            del _sessions[token]
            return None
        return item[0]


# --- HTTP -------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "ReshisAvia/1.0"

    def _send(self, status, body, ctype="application/json; charset=utf-8", headers=None):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _error(self, status, message):
        self._send(status, {"error": message})

    def _token(self):
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        return cookie["session"].value if "session" in cookie else None

    def _json_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > 10_000:
            raise ForecastError("Слишком большой запрос")
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            raise ForecastError("Некорректный JSON") from None
        if not isinstance(data, dict):
            raise ForecastError("Ожидается JSON-объект")
        return data

    @staticmethod
    def _cookie(token, max_age):
        return {"Set-Cookie": f"session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={max_age}"}

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/me":
            return self._send(200, {"login": session_user(self._token())})
        if path == "/api/routes":
            return self._send(200, {"routes": FORECASTER.route_list(), "dates": FORECASTER.dates,
                                    "source": os.path.basename(FORECASTER.forecast_path)})
        static = {"/": "index.html", "/index.html": "index.html", "/app.js": "app.js", "/style.css": "style.css"}
        if path in static:
            ctype = {"html": "text/html", "js": "text/javascript", "css": "text/css"}[static[path].rsplit(".", 1)[1]]
            with open(os.path.join(STATIC, static[path]), "rb") as f:
                return self._send(200, f.read(), ctype + "; charset=utf-8")
        self._error(404, "Не найдено")

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        try:
            if path == "/api/logout":
                with _sessions_lock:
                    _sessions.pop(self._token() or "", None)
                return self._send(200, {"ok": True}, headers=self._cookie("", 0))
            body = self._json_body()
            if path in ("/api/register", "/api/login"):
                login, password = str(body.get("login", "")).strip(), str(body.get("password", ""))
                if path == "/api/register":
                    register(login, password)
                elif not check_password(login, password):
                    return self._error(HTTPStatus.UNAUTHORIZED, "Неверный логин или пароль")
                return self._send(200, {"login": login}, headers=self._cookie(new_session(login), SESSION_TTL))
            if path == "/api/forecast":
                if not session_user(self._token()):
                    return self._error(HTTPStatus.UNAUTHORIZED, "Войдите, чтобы получить прогноз")
                return self._send(200, FORECASTER.forecast(body.get("origin"), body.get("destination"),
                                                           body.get("date"), body.get("price")))
            self._error(404, "Не найдено")
        except ForecastError as e:
            self._error(HTTPStatus.BAD_REQUEST, str(e))

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} {fmt % args}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    args = ap.parse_args()
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Прогноз: {FORECASTER.forecast_path}")
    print(f"Сервер запущен: http://{args.host}:{args.port}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
