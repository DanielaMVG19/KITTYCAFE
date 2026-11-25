"""Cafetería Hello Kitty. Ejecutar con python app.py."""
import base64
import binascii
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
DATABASE = ROOT / "cafeteria_kitty.sqlite3"
STATIC = ROOT / "static"
CATEGORIES = ("Bebidas", "Repostería", "Desayunos")
METHODS = ("Efectivo", "Tarjeta")
ADMIN_PASSWORD = os.environ.get("KITTY_ADMIN_PASSWORD", "Kitty2026")
SEED = [
    ("Latte fresa Kitty", "Bebidas", "Leche de fresa con espresso, hielo y una decoración dulce de Hello Kitty.", 7900, "latte"),
    ("Capuchino con moñito", "Bebidas", "Espresso con leche espumada y un moñito rosa sobre el café.", 6500, "capuchino"),
    ("Cheesecake de fresa", "Repostería", "Rebanada de queso cremosa con fresa y un moñito de chocolate rosa.", 8900, "cheesecake"),
    ("Waffles de vainilla", "Desayunos", "Mini waffles dorados con plátano y miel de maple.", 9500, "waffles"),
    ("Galletas Kitty", "Repostería", "Dos galletas de vainilla con glaseado blanco, chocolate y moñito rosa.", 5500, "galletas"),
    ("Brownie con helado", "Repostería", "Brownie de chocolate tibio con una bola de helado de vainilla.", 8500, "brownie"),
]


@contextmanager
def database():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize():
    with database() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS dishes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL, category TEXT NOT NULL,
                description TEXT NOT NULL, price INTEGER NOT NULL CHECK(price > 0),
                photo BLOB, photo_type TEXT, stock_photo TEXT
            );
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY, ticket TEXT NOT NULL, created TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS admin_sessions (
                token TEXT PRIMARY KEY, expiry INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS settings (name TEXT PRIMARY KEY);
        """)
        inserted = db.execute("INSERT OR IGNORE INTO settings VALUES ('menu_seeded')")
        if inserted.rowcount:
            db.executemany("""
                INSERT INTO dishes (name, category, description, price, stock_photo)
                VALUES (?, ?, ?, ?, ?)
            """, SEED)


class RequestError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def format_price(cents):
    return f"${cents // 100:,}.{cents % 100:02d} MXN"


def clean_text(data, key, length):
    value = data.get(key)
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > length:
        raise RequestError("Revisa el nombre y la descripción del platillo.")
    return " ".join(value.split())


def dish_values(data):
    name = clean_text(data, "name", 70)
    description = clean_text(data, "description", 280)
    category = data.get("category")
    price = data.get("price")
    if category not in CATEGORIES:
        raise RequestError("Selecciona una categoría del menú.")
    if type(price) is not int or not 1 <= price <= 99999999:
        raise RequestError("Ingresa un precio válido en pesos.")
    return name, category, description, price


def photo_values(data):
    value = data.get("photo")
    if not isinstance(value, str):
        raise RequestError("Selecciona una foto JPG, PNG o WebP.")
    match = re.fullmatch(r"data:(image/(?:jpeg|png|webp));base64,([A-Za-z0-9+/=]+)", value)
    if not match:
        raise RequestError("Selecciona una foto JPG, PNG o WebP.")
    photo_type, encoded = match.groups()
    try:
        photo = base64.b64decode(encoded, validate=True)
    except binascii.Error as error:
        raise RequestError("No se pudo leer la foto.") from error
    valid_header = {
        "image/jpeg": photo.startswith(b"\xff\xd8\xff"),
        "image/png": photo.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/webp": photo.startswith(b"RIFF") and photo[8:12] == b"WEBP",
    }
    if not valid_header[photo_type] or len(photo) > 2 * 1024 * 1024:
        raise RequestError("La foto debe ser válida y pesar hasta 2 MB.")
    return photo, photo_type


class RestaurantHandler(BaseHTTPRequestHandler):
    def send_bytes(self, body, content_type, status=200, headers=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; img-src 'self' data:; object-src 'none'; "
                         "base-uri 'none'; frame-ancestors 'none'")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, data, status=200, headers=None):
        self.send_bytes(json.dumps(data, ensure_ascii=False).encode(),
                        "application/json; charset=utf-8", status, headers)

    def read_json(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 3 * 1024 * 1024:
                raise RequestError("El tamaño de la solicitud no es válido.", 413)
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError
            return data
        except (ValueError, UnicodeDecodeError) as error:
            raise RequestError("La solicitud no es válida.") from error

    def session_token(self):
        cookies = SimpleCookie()
        cookies.load(self.headers.get("Cookie", ""))
        value = cookies.get("kitty_session")
        return value.value if value else ""

    def is_admin(self, db):
        return db.execute(
            "SELECT 1 FROM admin_sessions WHERE token = ? AND expiry > ?",
            (self.session_token(), int(time.time())),
        ).fetchone() is not None

    def do_GET(self):
        self.dispatch()

    def do_POST(self):
        self.dispatch()

    def do_PUT(self):
        self.dispatch()

    def do_DELETE(self):
        self.dispatch()

    def dispatch(self):
        path = urlsplit(self.path).path
        try:
            if self.command != "GET":
                origin = self.headers.get("Origin")
                if origin and urlsplit(origin).netloc != self.headers.get("Host"):
                    raise RequestError("Origen inválido.", 403)
            if path.startswith("/api/"):
                self.api(path)
            elif self.command == "GET":
                self.static_file(path)
            else:
                raise RequestError("Método no permitido.", 405)
        except RequestError as error:
            self.send_json({"error": str(error)}, error.status)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except sqlite3.Error as error:
            self.log_error("%s", error)
            self.send_json({"error": "Ocurrió un error al guardar o consultar los datos."}, 500)

    def static_file(self, path):
        files = {"/": "index.html", "/admin": "index.html",
                 "/static/app.js": "app.js", "/static/style.css": "style.css"}
        if re.fullmatch(r"/static/fotos/[a-z]+\.webp", path):
            filename = path.removeprefix("/static/")
        else:
            filename = files.get(path)
        if filename is None or not (STATIC / filename).is_file():
            raise RequestError("Página no encontrada.", 404)
        content_type = {
            ".html": "text/html; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".webp": "image/webp",
        }[Path(filename).suffix]
        self.send_bytes((STATIC / filename).read_bytes(), content_type)

    def api(self, path):
        method = self.command
        with database() as db:
            if (method, path) == ("GET", "/api/menu"):
                rows = db.execute("""
                    SELECT id, name, category, description, price, stock_photo
                    FROM dishes ORDER BY id
                """)
                dishes = []
                for row in rows:
                    dish = dict(row)
                    stock_photo = dish.pop("stock_photo")
                    dish["image"] = (f"/static/fotos/{stock_photo}.webp" if stock_photo
                                     else f"/api/photo/{dish['id']}")
                    dishes.append(dish)
                self.send_json(dishes)
            elif method == "GET" and re.fullmatch(r"/api/photo/[0-9]{1,18}", path):
                row = db.execute("SELECT photo, photo_type FROM dishes WHERE id = ?",
                                 (path.rsplit("/", 1)[1],)).fetchone()
                if row is None or row["photo"] is None:
                    raise RequestError("Foto no encontrada.", 404)
                self.send_bytes(row["photo"], row["photo_type"])
            elif (method, path) == ("POST", "/api/checkout"):
                self.checkout(db, self.read_json())
            elif (method, path) == ("POST", "/api/login"):
                password = self.read_json().get("password", "")
                if not isinstance(password, str) or not hmac.compare_digest(
                        password.encode(), ADMIN_PASSWORD.encode()):
                    raise RequestError("Contraseña incorrecta.", 401)
                token = secrets.token_urlsafe(32)
                now = int(time.time())
                db.execute("DELETE FROM admin_sessions WHERE expiry <= ?", (now,))
                db.execute("INSERT INTO admin_sessions VALUES (?, ?)", (token, now + 28800))
                db.commit()
                self.send_json({"authenticated": True}, headers={"Set-Cookie":
                    f"kitty_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800"})
            elif (method, path) == ("POST", "/api/logout"):
                db.execute("DELETE FROM admin_sessions WHERE token = ?", (self.session_token(),))
                db.commit()
                self.send_json({"authenticated": False}, headers={"Set-Cookie":
                    "kitty_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"})
            elif (method, path) == ("GET", "/api/session"):
                self.send_json({"authenticated": self.is_admin(db)})
            elif path == "/api/dishes" or re.fullmatch(r"/api/dishes/[0-9]{1,18}", path):
                if not self.is_admin(db):
                    raise RequestError("Inicia sesión como administrador.", 401)
                self.manage_dishes(db, method, path)
            else:
                raise RequestError("Ruta no encontrada.", 404)

    def manage_dishes(self, db, method, path):
        if method == "POST" and path == "/api/dishes":
            data = self.read_json()
            cursor = db.execute("""
                INSERT INTO dishes (name, category, description, price, photo, photo_type)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (*dish_values(data), *photo_values(data)))
            db.commit()
            self.send_json({"id": cursor.lastrowid}, 201)
            return

        dish_id = path.rsplit("/", 1)[1]
        if dish_id == "dishes":
            raise RequestError("Método no permitido.", 405)
        if method == "PUT":
            data = self.read_json()
            values = dish_values(data)
            if data.get("photo") is not None:
                cursor = db.execute("""
                    UPDATE dishes
                    SET name = ?, category = ?, description = ?, price = ?,
                        photo = ?, photo_type = ?, stock_photo = NULL
                    WHERE id = ?
                """, (*values, *photo_values(data), dish_id))
            else:
                cursor = db.execute("""
                    UPDATE dishes SET name = ?, category = ?, description = ?, price = ?
                    WHERE id = ?
                """, (*values, dish_id))
        elif method == "DELETE":
            cursor = db.execute("DELETE FROM dishes WHERE id = ?", (dish_id,))
        else:
            raise RequestError("Método no permitido.", 405)
        if not cursor.rowcount:
            raise RequestError("El platillo ya no está disponible.", 404)
        db.commit()
        self.send_json({"id": int(dish_id)})

    def checkout(self, db, data):
        items, method, order_id = data.get("items"), data.get("method"), data.get("order_id")
        if (not isinstance(items, list) or not 1 <= len(items) <= 100
                or method not in METHODS or not isinstance(order_id, str)
                or not re.fullmatch(r"[0-9a-f]{32}", order_id)):
            raise RequestError("Revisa los platillos y el método de pago.")
        db.execute("BEGIN IMMEDIATE")
        order = db.execute("SELECT ticket FROM orders WHERE id = ?", (order_id,)).fetchone()
        if order:
            self.send_ticket(order_id, order["ticket"])
            return

        total, lines, ids = 0, [], set()
        for item in items:
            if not isinstance(item, dict):
                raise RequestError("El carrito contiene un platillo inválido.")
            dish_id, quantity, price = item.get("id"), item.get("quantity"), item.get("price")
            if (type(dish_id) is not int or not 0 < dish_id < 10**18
                    or dish_id in ids or type(quantity) is not int or not 1 <= quantity <= 99):
                raise RequestError("El carrito contiene un platillo o cantidad inválida.")
            ids.add(dish_id)
            dish = db.execute("SELECT name, price FROM dishes WHERE id = ?", (dish_id,)).fetchone()
            if dish is None or dish["price"] != price:
                raise RequestError("El menú cambió. Revisa tu carrito y vuelve a confirmar.", 409)
            subtotal = dish["price"] * quantity
            total += subtotal
            lines.append(f"{quantity} x {dish['name']} | {format_price(dish['price'])} c/u | {format_price(subtotal)}")

        created = datetime.now().astimezone()
        ticket = "\n".join([
            "CAFETERÍA HELLO KITTY", "Ticket de pedido · Pago simulado",
            f"Folio: HK-{order_id.upper()}", f"Fecha: {created:%d/%m/%Y %H:%M %z}",
            f"Método: {method} (simulado)", "", *lines, "",
            f"TOTAL: {format_price(total)}", "", "Gracias por tu pedido.", "",
        ])
        db.execute("INSERT INTO orders VALUES (?, ?, ?)", (order_id, ticket, created.isoformat()))
        db.commit()
        self.send_ticket(order_id, ticket)

    def send_ticket(self, order_id, ticket):
        self.send_bytes(ticket.encode(), "text/plain; charset=utf-8", headers={
            "Content-Disposition": f'attachment; filename="ticket-{order_id}.txt"'})


if __name__ == "__main__":
    initialize()
    port = int(os.environ.get("KITTY_PORT", "8000"))
    with ThreadingHTTPServer(("127.0.0.1", port), RestaurantHandler) as server:
        print(f"Cafetería Hello Kitty: http://127.0.0.1:{port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nServidor detenido.")
