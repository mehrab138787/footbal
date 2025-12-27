from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from datetime import timedelta
import jdatetime
import math
import os
import requests 

app = Flask(__name__)

# ------------------------------
# تنظیمات تلگرام (توکن ربات شما)
# ------------------------------
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
    # این تابع فقط برای نمایش اعداد در HTML (پنل ادمین) باقی می‌ماند
    persian_digits = "۰۱۲۳۴۵۶۷۸۹"
    return "".join(persian_digits[int(d)] if d.isdigit() else d for d in str(number))

# ------------------------------
# توابع کمکی تلگرام (تغییر یافته)
# ------------------------------
def get_report_text():
    """متن گزارش وضعیت فعلی بدهی‌ها را می‌سازد"""
    players = Player.query.order_by(Player.name).all()
    
    # 1. بخش گزارش بدهی‌ها
    msg = "🏆 **گزارش صندوق فوتسال** ⚽️\n\n"
    total_debt = 0
    
    if not players:
        msg += "لیست بازیکنان خالی است."
    else:
        for p in players:
            total_debt += p.debt
            
            # نمایش اعداد انگلیسی (طبق درخواست شما) با جداکننده هزارگان
            debt_amount_en = format(p.debt, ',')
            
            if p.debt > 0:
                # استفاده از قالب Monospace برای بدهی (زیبا و شیک)
                debt_str = f"`{debt_amount_en} تومان`"
            else:
                debt_str = "بی‌حساب ✅"
                
            # استفاده از Bold برای نام بازیکن
            msg += f"👤 **{p.name}:** {debt_str}\n"

    # 2. بخش مجموع بدهی‌ها
    total_debt_en = format(total_debt, ',')
    msg += f"\n💰 **مجموع کل بدهی:** `{total_debt_en} تومان`"
    
    # 3. بخش تاریخ و ساعت هجری شمسی (تغییرات اصلی اینجا اعمال شد)
    now = jdatetime.datetime.now()
    
    # ساختن تاریخ و ساعت شمسی دقیق
    j_date_str = now.strftime("%A") + " " + persian_number(now.strftime("%d %B %Y"))
    time_str = now.strftime("%H:%M:%S")
    
    msg += f"\n\n🕒 **تاریخ:** {j_date_str}"
    msg += f"\n⏳ **ساعت به‌روزرسانی:** `{time_str}`"
    
    return msg

def send_telegram_msg(chat_id, text):
    """ارسال پیام به یک کاربر خاص"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    # Parse mode را روی MarkdownV2 تنظیم می‌کنیم چون Bold و Monospace استفاده کردیم
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "MarkdownV2"} 
    try:
        # کاراکترهای خاص در MarkdownV2 باید Escape شوند. 
        # چون از f-string پایتون استفاده می‌کنیم، باید backslashها را دوبار بنویسیم.
        # فقط کاراکترهای خاصی که در متن گزارش آمده‌اند (مثل پرانتز) باید escape شوند
        # اما چون ما از آن‌ها استفاده نکردیم، نیازی به Escape بیشتر نیست.
        
        # اگر در آینده کاراکترهایی مثل . - ! + = و غیره استفاده شد، باید قبل از ارسال Escape شوند.
        # چون فعلاً از آن‌ها استفاده نکردیم، همان payload بالا کافی است.
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Error sending msg to {chat_id}: {e}")

def notify_all_users():
    """ارسال لیست جدید به همه کسانی که ربات را استارت کرده‌اند"""
    with app.app_context(): 
        # توجه: تلگرام در MarkdownV2 به 't' برای نمایش 'toman' حساس است. 
        # کاراکترهای خاص مانند ویرگول (,) و پرانتز () باید Escape شوند اگر در متن آزاد باشند.
        # ما از آنها در بخش‌هایی استفاده کردیم که توسط ` (monospace) احاطه شده‌اند، 
        # که در این حالت نیاز به Escape نیست.
        text = get_report_text().replace('.', '\\.').replace('-', '\\-').replace('(', '\\(').replace(')', '\\)')
        
        users = BotUser.query.all()
        print(f"📢 Sending updates to {len(users)} users...")
        for user in users:
            send_telegram_msg(user.chat_id, text)

# ------------------------------
# روت وب‌هوک تلگرام
# ------------------------------
@app.route('/bot/webhook', methods=['POST'])
def bot_webhook():
    update = request.json
    
    if "message" in update:
        chat_id = str(update["message"]["chat"]["id"])
        text = update["message"].get("text", "")
        first_name = update["message"]["chat"].get("first_name", "")

        if text == "/start":
            user = BotUser.query.filter_by(chat_id=chat_id).first()
            if not user:
                new_user = BotUser(chat_id=chat_id, first_name=first_name)
                db.session.add(new_user)
                db.session.commit()
                # پیام خوش آمدگویی
                welcome_msg = f"سلام {first_name} 👋\nبه ربات فوتسال خوش آمدید.\nشما برای دریافت به‌روزرسانی‌های خودکار ثبت شدید."
                send_telegram_msg(chat_id, welcome_msg)
            
            # ارسال گزارش اصلی
            report = get_report_text().replace('.', '\\.').replace('-', '\\-').replace('(', '\\(').replace(')', '\\)')
            send_telegram_msg(chat_id, report)
            
    return "OK", 200


# ------------------------------
# صفحه اصلی و روت‌های ادمین
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

@app.route("/admin/players", methods=["GET", "POST"])
def admin_players():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    players = Player.query.order_by(Player.name).all()

    if request.method == "POST":
        action = request.form.get("action")
        player_id = request.form.get("player_id")
        changed = False

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
        
        if changed:
            notify_all_users()

        return redirect(url_for("admin_players"))

    return render_template("admin_players.html", players=players, persian_number=persian_number)

@app.route("/admin/attendance", methods=["GET", "POST"])
def admin_attendance():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    players = Player.query.order_by(Player.name).all()
    
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
        
        Attendance.query.filter_by(date=date).delete()
        for pid in present_ids:
            db.session.add(Attendance(player_id=int(pid), date=date))
        db.session.commit()

        total_cost = request.form.get("cost")
        if total_cost and present_ids:
            total_cost = int(total_cost)
            share = math.ceil(total_cost / len(present_ids) / 1000) * 1000
            for pid in present_ids:
                p = Player.query.get(int(pid))
                p.debt += share
            db.session.commit()
            
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
    app.run(host="0.0.0.0", port=5000, debug=True)