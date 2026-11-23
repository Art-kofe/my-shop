import os
import sqlite3
import requests
from datetime import datetime
from functools import wraps
from flask import (Flask, request, redirect, url_for, session, flash, render_template_string)
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-change-me")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
DB_PATH = "orders.db"

# ---------- БД ----------
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL, phone TEXT NOT NULL, product TEXT NOT NULL,
                comment TEXT, created_at TEXT NOT NULL, status TEXT DEFAULT 'new'
            )
        """)
        conn.commit()

# ---------- Telegram ----------
def send_telegram(text: str) -> bool:
    if not BOT_TOKEN or not CHAT_ID:
        print("⚠️  Telegram не настроен в .env")
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=10
        )
        if not r.ok: print("Telegram error:", r.text)
        return r.ok
    except Exception as e:
        print("Telegram exception:", e)
        return False

# ---------- HTML Шаблоны ----------
INDEX_HTML = """
<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>Заказ</title>
<style>body{font-family:sans-serif;background:#f4f6f8;padding:20px}.c{max-width:400px;margin:0 auto;background:#fff;padding:20px;border-radius:8px}
input,select,textarea{width:100%;padding:8px;margin:10px 0;border:1px solid #ccc;border-radius:4px;box-sizing:border-box}
button{width:100%;padding:10px;background:#2b6cb0;color:#fff;border:none;border-radius:4px;font-size:16px}</style>
</head><body><div class="c">
<h2>Оформить заказ</h2>
{% with messages = get_flashed_messages(with_categories=true) %}
  {% for cat, msg in messages %}<p style="color:red">{{ msg }}</p>{% endfor %}
{% endwith %}
<form method="post" action="/order">
  <input type="text" name="name" required placeholder="Ваше имя *">
  <input type="tel" name="phone" required placeholder="Телефон *">
  <select name="product" required>
    <option value="">-- Выберите товар --</option>
    <option>Товар А (1500р)</option>
    <option>Товар Б (2500р)</option>
  </select>
  <textarea name="comment" placeholder="Комментарий"></textarea>
  <button type="submit">Отправить</button>
</form></div></body></html>
"""

SUCCESS_HTML = """
<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>Успех</title>
<style>body{font-family:sans-serif;text-align:center;padding:50px}</style>
</head><body><h1>✅ Заказ #{{ order_id }} принят!</h1><p>Мы свяжемся с вами.</p><a href="/">Назад</a></body></html>
"""

LOGIN_HTML = """
<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>Вход</title>
<style>body{font-family:sans-serif;display:flex;justify-content:center;padding:50px}form{background:#fff;padding:20px;border-radius:8px}</style>
</head><body><form method="post">
<h2>Админка</h2><input type="password" name="password" placeholder="Пароль" required><br><br>
<button type="submit">Войти</button></form></body></html>
"""

ADMIN_HTML = """
<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>Админка</title>
<style>body{font-family:sans-serif;padding:20px}table{width:100%;border-collapse:collapse;background:#fff}
th,td{border:1px solid #ccc;padding:8px;text-align:left}th{background:#eee}</style>
</head><body>
<h2>Заказы | <a href="/admin/logout">Выйти</a></h2>
<table>
<tr><th>#</th><th>Время</th><th>Имя</th><th>Телефон</th><th>Товар</th><th>Статус</th></tr>
{% for o in orders %}
<tr>
  <td>{{ o.id }}</td><td>{{ o.created_at }}</td><td>{{ o.name }}</td>
  <td>{{ o.phone }}</td><td>{{ o.product }}</td>
  <td>
    <form method="post" action="/admin/order/{{ o.id }}/status">
      <select name="status" onchange="this.form.submit()">
        <option value="new" {% if o.status=='new' %}selected{% endif %}>Новый</option>
        <option value="done" {% if o.status=='done' %}selected{% endif %}>Выполнен</option>
      </select>
    </form>
  </td>
</tr>
{% endfor %}
</table></body></html>
"""

# ---------- Роуты ----------
@app.route("/")
def index(): return render_template_string(INDEX_HTML)

@app.route("/order", methods=["POST"])
def order():
    name, phone, product = request.form.get("name"), request.form.get("phone"), request.form.get("product")
    comment = request.form.get("comment", "")
    if not name or not phone or not product:
        flash("Заполните поля", "error"); return redirect(url_for("index"))
    
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute("INSERT INTO orders (name,phone,product,comment,created_at) VALUES (?,?,?,?,?)",
                           (name, phone, product, comment, created_at))
        order_id = cur.lastrowid; conn.commit()

    send_telegram(f"🛒 <b>Заказ #{order_id}</b>\n👤 {name}\n📞 {phone}\n📦 {product}\n💬 {comment}")
    return render_template_string(SUCCESS_HTML, order_id=order_id)

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("admin"): return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper

@app.route("/admin/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["admin"] = True; return redirect(url_for("admin"))
        flash("Неверный пароль", "error")
    return render_template_string(LOGIN_HTML)

@app.route("/admin/logout")
def logout(): session.pop("admin", None); return redirect(url_for("login"))

@app.route("/admin")
@login_required
def admin():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        orders = conn.execute("SELECT * FROM orders ORDER BY id DESC").fetchall()
    return render_template_string(ADMIN_HTML, orders=orders)

@app.route("/admin/order/<int:order_id>/status", methods=["POST"])
@login_required
def update_status(order_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE orders SET status=? WHERE id=?", (request.form.get("status"), order_id))
        conn.commit()
    return redirect(url_for("admin"))

if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)