from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from datetime import timedelta
import jdatetime
import math
import os
import requests  # برای ارتباط با تلگرام

app = Flask(__name__)

# ------------------------------
# تنظیمات تلگرام (توکن خود را اینجا بگذارید)
# ------------------------------
# این توکن کلید ارتباط کد شما با سرورهای تلگرام است
TELEGRAM_TOKEN = "8304154829:AAGonWN7iHoK36MPsdnCqAbEZg-OOu71s9g"

# ------------------------------
# اتصال به دیتابیس
# ------------------------------
database_url = os.environ.get("DATABASE_URL")
if database_url:
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url.replace("postgresql://", "postgresql+psycopg://")
else:
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///futsal.db"

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = "supersecretkey123"
db = SQLAlchemy(app)

# ------------------------------
# مدل‌ها
# ------------------------------
class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    debt = db.Column(db.Integer, default=0)

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey("player.id"), nullable=False)
    date = db.Column(db.String(10), nullable=False)
    player = db.relationship("Player", backref="attendances")

# مدل جدید برای ذخیره کاربران تلگرام
class BotUser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.String(50), unique=True, nullable=False)
    first_name = db.Column(db.String(100), nullable=True)

# ------------------------------
# ابزارها
# ------------------------------
PERSIAN_MONTHS = [
    "فروردین", "اردیبهشت", "خرداد", "تیر",
    "مرداد", "شهریور", "مهر", "آبان",
    "آذر", "دی", "بهمن", "اسفند"
]

def persian_number(number):
    persian_digits = "۰۱۲۳۴۵۶۷۸۹"
    return "".join(persian_digits[int(d)] if d.isdigit() else d for d in str(number))

# ------------------------------
# توابع کمکی تلگرام
# ------------------------------
def get_report_text():
    """متن گزارش وضعیت فعلی بدهی‌ها را می‌سازد"""
    players = Player.query.order_by(Player.name).all()
    if not players:
        return "لیست بازیکنان خالی است."
    
    msg = "⚽️ **وضعیت صندوق فوتسال** ⚽️\n\n"
    total_debt = 0
    for p in players:
        debt_str = f"{persian_number(format(p.debt, ','))} تومان" if p.debt > 0 else "بی‌حساب ✅"
        msg += f"👤 {p.name}: {debt_str}\n"
        total_debt += p.debt
    
    msg += f"\n💰 **مجموع بدهی‌ها:** {persian_number(format(total_debt, ','))} تومان"
    
    now = jdatetime.datetime.now()
    msg += f"\n📅 {persian_number(now.strftime('%Y/%m/%d %H:%M'))}"
    return msg

def send_telegram_msg(chat_id, text):
    """ارسال پیام به یک کاربر خاص"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Error sending msg to {chat_id}: {e}")

def notify_all_users():
    """ارسال لیست جدید به همه کسانی که ربات را استارت کرده‌اند"""
    text = get_report_text()
    users = BotUser.query.all()
    print(f"📢 Sending updates to {len(users)} users...")
    for user in users:
        send_telegram_msg(user.chat_id, text)

# ------------------------------
# روت وب‌هوک تلگرام (دریافت پیام از تلگرام)
# ------------------------------
@app.route('/bot/webhook', methods=['POST'])
def bot_webhook():
    update = request.json
    if "message" in update:
        chat_id = str(update["message"]["chat"]["id"])
        text = update["message"].get("text", "")
        first_name = update["message"]["chat"].get("first_name", "")

        if text == "/start":
            # 1. ذخیره کاربر اگر جدید است
            user = BotUser.query.filter_by(chat_id=chat_id).first()
            if not user:
                new_user = BotUser(chat_id=chat_id, first_name=first_name)
                db.session.add(new_user)
                db.session.commit()
            
            # 2. ارسال لیست فعلی بلافاصله پس از استارت
            report = get_report_text()
            welcome_msg = f"سلام {first_name} 👋\nبه ربات فوتسال خوش آمدید.\nشما در لیست خبررسانی ثبت شدید.\n\n" + report
            send_telegram_msg(chat_id, welcome_msg)
            
    return "OK", 200

# ------------------------------
# صفحه اصلی
# ------------------------------
@app.route("/")
def index():
    start_jdate = jdatetime.date(1404, 7, 28)
    start_date = jdatetime.datetime(start_jdate.year, start_jdate.month, start_jdate.day)
    today = jdatetime.datetime.now()

    mondays = [start_date + timedelta(days=7 * i) for i in range(12)]
    extra_dates = [jdatetime.date(1404, 7, 7), jdatetime.date(1404, 7, 14), jdatetime.date(1404, 7, 21)]
    mondays.extend([jdatetime.datetime(d.year, d.month, d.day) for d in extra_dates])
    mondays = sorted(mondays)

    players = Player.query.order_by(Player.name).all()
    return render_template(
        "index.html",
        mondays=mondays,
        today=today,
        players=players,
        PERSIAN_MONTHS=PERSIAN_MONTHS,
        persian_number=persian_number,
    )

# ------------------------------
# ورود ادمین
# ------------------------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        password = request.form.get("password")
        if password == "0902":
            session["admin"] = True
            return redirect(url_for("admin_dashboard"))
        else:
            return "رمز اشتباه است!", 403
    return render_template("admin_login.html")

@app.route("/admin/dashboard")
def admin_dashboard():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    now = jdatetime.datetime.now()
    return render_template("admin_dashboard.html", now=now)

# ------------------------------
# مدیریت بازیکنان (با ارسال پیام خودکار)
# ------------------------------
@app.route("/admin/players", methods=["GET", "POST"])
def admin_players():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    players = Player.query.order_by(Player.name).all()

    if request.method == "POST":
        action = request.form.get("action")
        player_id = request.form.get("player_id")
        changed = False  # برای بررسی اینکه آیا تغییری رخ داده یا نه

        if action == "add":
            name = request.form.get("name")
            if name:
                db.session.add(Player(name=name))
                changed = True

        elif action == "delete" and player_id:
            player = Player.query.get(int(player_id))
            if player:
                Attendance.query.filter_by(player_id=player.id).delete()
                db.session.delete(player)
                changed = True

        elif action == "pay" and player_id:
            amount = int(request.form.get("amount", 0))
            player = Player.query.get(int(player_id))
            if player:
                player.debt -= amount
                if player.debt < 0: player.debt = 0
                changed = True

        elif action == "add_debt" and player_id:
            amount = int(request.form.get("amount", 0))
            player = Player.query.get(int(player_id))
            if player and amount > 0:
                player.debt += amount
                changed = True

        db.session.commit()
        
        # اگر تغییری بود، به همه پیام بده
        if changed:
            notify_all_users()

        return redirect(url_for("admin_players"))

    return render_template("admin_players.html", players=players, persian_number=persian_number)

# ------------------------------
# ثبت حضور و تقسیم هزینه (با ارسال پیام خودکار)
# ------------------------------
@app.route("/admin/attendance", methods=["GET", "POST"])
def admin_attendance():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    players = Player.query.order_by(Player.name).all()
    # ... (کد تقویم مشابه قبل) ...
    start_jdate = jdatetime.date(1404, 7, 28)
    start_date = jdatetime.datetime(start_jdate.year, start_jdate.month, start_jdate.day)
    mondays = [start_date + timedelta(days=7 * i) for i in range(12)]
    extra_dates = [jdatetime.date(1404, 7, 7), jdatetime.date(1404, 7, 14), jdatetime.date(1404, 7, 21)]
    mondays.extend([jdatetime.datetime(d.year, d.month, d.day) for d in extra_dates])
    mondays = sorted(mondays)

    mondays_formatted = [
        {"value": jd.togregorian().strftime("%Y-%m-%d"), "label": f"{persian_number(jd.day)} {PERSIAN_MONTHS[jd.month-1]} {persian_number(jd.year)}"}
        for jd in mondays
    ]

    today = jdatetime.datetime.now().strftime("%Y-%m-%d")
    selected_date = request.args.get("date")
    selected_attendance = []

    if selected_date:
        selected_attendance = [a.player_id for a in Attendance.query.filter_by(date=selected_date).all()]

    if request.method == "POST":
        date = request.form.get("date")
        present_ids = request.form.getlist("present")
        
        # ثبت حضور
        Attendance.query.filter_by(date=date).delete()
        for pid in present_ids:
            db.session.add(Attendance(player_id=int(pid), date=date))
        db.session.commit()

        # تقسیم هزینه
        total_cost = request.form.get("cost")
        if total_cost and present_ids:
            total_cost = int(total_cost)
            share = math.ceil(total_cost / len(present_ids) / 1000) * 1000
            for pid in present_ids:
                p = Player.query.get(int(pid))
                p.debt += share
            db.session.commit()
            
            # ارسال پیام به تلگرام چون بدهی‌ها تغییر کرد
            notify_all_users()
            
        return redirect(url_for("admin_attendance", date=date))

    return render_template(
        "admin_attendance.html",
        players=players,
        today=today,
        mondays=mondays_formatted,
        selected_date=selected_date,
        selected_attendance=selected_attendance,
        persian_number=persian_number,
    )

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("index"))

@app.route("/healthz")
def healthz():
    return "OK", 200

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        print("🚀 Tables created. Bot is ready.")
    app.run(host="0.0.0.0", port=5000, debug=True)