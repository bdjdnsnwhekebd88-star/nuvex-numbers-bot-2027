import asyncio
import logging
import os
import sqlite3
from datetime import datetime
from decimal import Decimal, InvalidOperation

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS = {int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()}
ACTIVATION_CHANNEL = os.getenv("ACTIVATION_CHANNEL", "-1003841049469").strip()
SUPPORT = os.getenv("SUPPORT_USERNAME", "@DF_VJ1").strip()
DB_PATH = os.getenv("DB_PATH", "nuvex.db")
COMMISSION_PERCENT = Decimal(os.getenv("COMMISSION_PERCENT", "5"))

if not TOKEN:
    raise RuntimeError("ضع BOT_TOKEN داخل ملف .env")

logging.basicConfig(level=logging.INFO)
bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ---------------- Database ----------------
db = sqlite3.connect(DB_PATH)
db.row_factory = sqlite3.Row
db.execute("PRAGMA foreign_keys=ON")

def init_db():
    db.executescript("""
    CREATE TABLE IF NOT EXISTS users(
        user_id INTEGER PRIMARY KEY, username TEXT, full_name TEXT,
        balance REAL NOT NULL DEFAULT 0, joined_at TEXT
    );
    CREATE TABLE IF NOT EXISTS listings(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        seller_id INTEGER NOT NULL, country TEXT NOT NULL, category TEXT NOT NULL,
        app TEXT NOT NULL, phone TEXT NOT NULL, price REAL NOT NULL,
        currency TEXT NOT NULL, note TEXT DEFAULT '',
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT, buyer_id INTEGER, order_id INTEGER
    );
    CREATE TABLE IF NOT EXISTS orders(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        listing_id INTEGER NOT NULL, buyer_id INTEGER NOT NULL, seller_id INTEGER NOT NULL,
        amount REAL NOT NULL, currency TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT, delivered_at TEXT
    );
    CREATE TABLE IF NOT EXISTS deposits(
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
        amount REAL NOT NULL, currency TEXT NOT NULL, method TEXT NOT NULL,
        proof TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS withdrawals(
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
        amount REAL NOT NULL, currency TEXT NOT NULL, details TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending', created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS transactions(
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
        kind TEXT NOT NULL, amount REAL NOT NULL, currency TEXT NOT NULL,
        note TEXT, created_at TEXT
    );
    """)
    db.commit()

def q(sql, params=(), one=False):
    cur = db.execute(sql, params)
    rows = cur.fetchall()
    db.commit()
    return rows[0] if one and rows else (None if one else rows)

def is_admin(uid): return uid in ADMIN_IDS
def money(v): return f"{float(v):,.2f}".rstrip("0").rstrip(".")
def now(): return datetime.utcnow().isoformat(timespec="seconds") + "Z"

def register_user(user):
    q("""INSERT INTO users(user_id,username,full_name,joined_at) VALUES(?,?,?,?)
         ON CONFLICT(user_id) DO UPDATE SET username=excluded.username, full_name=excluded.full_name""",
      (user.id, user.username or "", user.full_name, now()))

def user_balance(uid):
    row = q("SELECT balance FROM users WHERE user_id=?", (uid,), one=True)
    return float(row["balance"]) if row else 0.0

def adjust_balance(uid, amount, currency, kind, note):
    q("UPDATE users SET balance=balance+? WHERE user_id=?", (amount, uid))
    q("INSERT INTO transactions(user_id,kind,amount,currency,note,created_at) VALUES(?,?,?,?,?,?)",
      (uid, kind, amount, currency, note, now()))

def main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛒 شراء أرقام"), KeyboardButton(text="➕ بيع رقم")],
            [KeyboardButton(text="📦 طلباتي"), KeyboardButton(text="💳 المحفظة")],
            [KeyboardButton(text="ℹ️ معرفة البوت"), KeyboardButton(text="🆘 الدعم")]
        ], resize_keyboard=True
    )

def inline(rows):
    return InlineKeyboardMarkup(inline_keyboard=rows)

def admin_button(kind, item_id):
    return inline([[InlineKeyboardButton(text="✅ قبول", callback_data=f"adm:{kind}:ok:{item_id}"),
                    InlineKeyboardButton(text="❌ رفض", callback_data=f"adm:{kind}:no:{item_id}")]])

class SellFlow(StatesGroup):
    country=State(); category=State(); app=State(); phone=State(); price=State(); currency=State(); note=State()

class DepositFlow(StatesGroup):
    amount=State(); currency=State(); method=State(); proof=State()

class WithdrawFlow(StatesGroup):
    amount=State(); currency=State(); details=State()

class SupportFlow(StatesGroup):
    message=State()

@dp.message(CommandStart())
async def start(m: Message):
    register_user(m.from_user)
    await m.answer(
        "𓆩 <b>NUVEX NUMBERS</b> 𓆪\n\n"
        "مرحباً بك في سوق نوفكس للأرقام الافتراضية.\n"
        "تصفّح الأرقام المعروضة أو أضف رقمك للبيع بعد مراجعة الإدارة.\n\n"
        "اختر الخدمة من القائمة بالأسفل 👇",
        reply_markup=main_keyboard()
    )

@dp.message(Command("id"))
async def get_id(m: Message):
    await m.answer(f"معرّف حسابك: <code>{m.from_user.id}</code>")

@dp.message(F.text == "ℹ️ معرفة البوت")
async def about(m: Message):
    await m.answer(
        "𓆩 <b>عن NUVEX NUMBERS</b> 𓆪\n\n"
        "منصة مستقلة لعرض وشراء الأرقام الافتراضية الجاهزة.\n"
        "يمكن للمستخدم عرض رقمه للبيع وتحديد السعر، ثم تراجع الإدارة الإعلان قبل نشره.\n\n"
        "نوفر تصنيفات للأرقام العربية والأجنبية وأرقام المنصات المختلفة.\n"
        "تتم متابعة الطلبات من خلال إدارة المنصة.\n\n"
        "⚠️ استخدم الأرقام وفق القوانين وشروط شركات الاتصالات والمنصات، "
        "ولا تستخدمها لانتحال الهوية أو تجاوز أنظمة الحماية."
    )

@dp.message(F.text == "🆘 الدعم")
async def support(m: Message):
    await m.answer(f"للتواصل مع الدعم الفني: {SUPPORT}\nأو أرسل رسالتك هنا باستخدام /contact")

@dp.message(Command("contact"))
async def contact_start(m: Message, state: FSMContext):
    await state.set_state(SupportFlow.message)
    await m.answer("اكتب رسالتك للدعم، وسيتم إرسالها للإدارة.")

@dp.message(SupportFlow.message)
async def contact_send(m: Message, state: FSMContext):
    for aid in ADMIN_IDS:
        try:
            await bot.send_message(aid, f"🆘 رسالة دعم من {m.from_user.full_name} (<code>{m.from_user.id}</code>):\n\n{m.text or '[مرفق]'}")
        except Exception:
            pass
    await state.clear()
    await m.answer("تم إرسال رسالتك للدعم. ✅", reply_markup=main_keyboard())

# ---------------- Selling ----------------
@dp.message(F.text == "➕ بيع رقم")
async def sell_start(m: Message, state: FSMContext):
    register_user(m.from_user)
    await state.set_state(SellFlow.country)
    await m.answer("🌍 اكتب الدولة ورمزها (مثال: Yemen +967 / USA +1):")

@dp.message(SellFlow.country)
async def sell_country(m: Message, state: FSMContext):
    await state.update_data(country=m.text.strip())
    await state.set_state(SellFlow.category)
    await m.answer("اختر تصنيف الرقم:", reply_markup=inline([
        [InlineKeyboardButton(text="🇸🇦 رقم عربي", callback_data="sellcat:عربي"),
         InlineKeyboardButton(text="🌐 رقم أجنبي", callback_data="sellcat:أجنبي")],
        [InlineKeyboardButton(text="⭐ رقم مميز", callback_data="sellcat:مميز")]
    ]))

@dp.callback_query(F.data.startswith("sellcat:"))
async def sell_category(c: CallbackQuery, state: FSMContext):
    await state.update_data(category=c.data.split(":",1)[1])
    await state.set_state(SellFlow.app)
    await c.message.answer("📱 اكتب التطبيق أو الاستخدام المخصص للرقم (مثال: عام / WhatsApp / Telegram):")
    await c.answer()

@dp.message(SellFlow.app)
async def sell_app(m: Message, state: FSMContext):
    await state.update_data(app=m.text.strip())
    await state.set_state(SellFlow.phone)
    await m.answer("اكتب الرقم كاملاً مع مفتاح الدولة. لن يظهر الرقم للعامة قبل إتمام الطلب.")

@dp.message(SellFlow.phone)
async def sell_phone(m: Message, state: FSMContext):
    phone = (m.text or "").strip()
    if len(phone) < 6 or len(phone) > 25:
        return await m.answer("تأكد من كتابة الرقم بشكل صحيح.")
    await state.update_data(phone=phone)
    await state.set_state(SellFlow.price)
    await m.answer("💰 اكتب السعر بالأرقام فقط (مثال: 15 أو 2500):")

@dp.message(SellFlow.price)
async def sell_price(m: Message, state: FSMContext):
    try:
        price = Decimal((m.text or "").replace(",", "").strip())
        if price <= 0 or price > Decimal("100000000"):
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        return await m.answer("السعر غير صحيح. اكتب مبلغاً موجباً بالأرقام فقط.")
    await state.update_data(price=float(price))
    await state.set_state(SellFlow.currency)
    await m.answer("اختر العملة:", reply_markup=inline([
        [InlineKeyboardButton(text="🇾🇪 ريال يمني", callback_data="sellcur:YER"),
         InlineKeyboardButton(text="🇸🇦 ريال سعودي", callback_data="sellcur:SAR")],
        [InlineKeyboardButton(text="🇺🇸 دولار", callback_data="sellcur:USD")]
    ]))

@dp.callback_query(F.data.startswith("sellcur:"))
async def sell_currency(c: CallbackQuery, state: FSMContext):
    await state.update_data(currency=c.data.split(":")[1])
    await state.set_state(SellFlow.note)
    await c.message.answer("أرسل وصفاً مختصراً أو اكتب (لا يوجد):")
    await c.answer()

@dp.message(SellFlow.note)
async def sell_note(m: Message, state: FSMContext):
    d = await state.get_data()
    note = (m.text or "").strip()
    q("""INSERT INTO listings(seller_id,country,category,app,phone,price,currency,note,status,created_at)
         VALUES(?,?,?,?,?,?,?,?,?,?)""",
      (m.from_user.id,d["country"],d["category"],d["app"],d["phone"],d["price"],d["currency"],note,"pending",now()))
    listing = q("SELECT last_insert_rowid() AS id", one=True)["id"]
    await state.clear()
    await m.answer(f"تم استلام إعلانك رقم <b>#{listing}</b> وهو قيد مراجعة الإدارة. سنبلغك بالنتيجة. ✅", reply_markup=main_keyboard())
    for aid in ADMIN_IDS:
        try:
            await bot.send_message(aid,
                f"🆕 <b>إعلان رقم جديد #{listing}</b>\nالبائع: {m.from_user.full_name} (<code>{m.from_user.id}</code>)\n"
                f"الدولة: {d['country']}\nالتصنيف: {d['category']}\nالتطبيق: {d['app']}\n"
                f"الرقم: <code>{d['phone']}</code>\nالسعر: {money(d['price'])} {d['currency']}\nالوصف: {note}",
                reply_markup=admin_button("listing", listing))
        except Exception: pass

# ---------------- Buying ----------------
@dp.message(F.text == "🛒 شراء أرقام")
async def buy_start(m: Message):
    rows = q("SELECT id,country,category,app,price,currency FROM listings WHERE status='approved' ORDER BY id DESC LIMIT 20")
    if not rows:
        return await m.answer("حالياً لا توجد أرقام متاحة للشراء. حاول لاحقاً.")
    buttons=[]
    for r in rows:
        label=f"#{r['id']} | {r['country']} | {r['category']} | {money(r['price'])} {r['currency']}"
        buttons.append([InlineKeyboardButton(text=label[:60], callback_data=f"view:{r['id']}")])
    await m.answer("🛒 <b>الأرقام المتاحة</b>\nاختر رقماً لعرض التفاصيل:", reply_markup=inline(buttons))

@dp.callback_query(F.data.startswith("view:"))
async def view_listing(c: CallbackQuery):
    lid=int(c.data.split(":")[1])
    r=q("SELECT * FROM listings WHERE id=? AND status='approved'",(lid,),one=True)
    if not r:
        await c.answer("هذا الإعلان لم يعد متاحاً.",show_alert=True); return
    txt=(f"📞 <b>رقم للبيع #{lid}</b>\n\nالدولة: {r['country']}\nالتصنيف: {r['category']}\n"
         f"التطبيق: {r['app']}\nالسعر: <b>{money(r['price'])} {r['currency']}</b>\n"
         f"الوصف: {r['note'] or 'لا يوجد'}\n\nالرقم الكامل لا يظهر إلا بعد إتمام الطلب.")
    await c.message.answer(txt, reply_markup=inline([
        [InlineKeyboardButton(text="🛍 شراء الرقم", callback_data=f"buy:{lid}")]
    ]))
    await c.answer()

@dp.callback_query(F.data.startswith("buy:"))
async def buy_listing(c: CallbackQuery):
    lid=int(c.data.split(":")[1])
    r=q("SELECT * FROM listings WHERE id=? AND status='approved'",(lid,),one=True)
    if not r:
        await c.answer("الإعلان غير متاح.",show_alert=True); return
    if r["seller_id"] == c.from_user.id:
        await c.answer("لا يمكنك شراء إعلانك الخاص.",show_alert=True); return
    bal=user_balance(c.from_user.id)
    if bal < float(r["price"]):
        await c.answer("رصيدك غير كافٍ. افتح المحفظة واشحن رصيدك أولاً.",show_alert=True); return
    q("UPDATE users SET balance=balance-? WHERE user_id=?",(r["price"],c.from_user.id))
    q("INSERT INTO transactions(user_id,kind,amount,currency,note,created_at) VALUES(?,?,?,?,?,?)",
      (c.from_user.id,"purchase_hold",-float(r["price"]),r["currency"],f"حجز قيمة الإعلان #{lid}",now()))
    q("INSERT INTO orders(listing_id,buyer_id,seller_id,amount,currency,status,created_at) VALUES(?,?,?,?,?,?,?)",
      (lid,c.from_user.id,r["seller_id"],r["price"],r["currency"],"pending",now()))
    oid=q("SELECT last_insert_rowid() AS id",one=True)["id"]
    q("UPDATE listings SET status='reserved',buyer_id=?,order_id=? WHERE id=?",(c.from_user.id,oid,lid))
    await c.message.answer(f"تم إنشاء طلب الشراء رقم <b>#{oid}</b>. المبلغ محجوز مؤقتاً حتى مراجعة الإدارة وتسليم الرقم.")
    try:
        await bot.send_message(r["seller_id"],f"🛒 يوجد طلب شراء على إعلانك رقم #{lid}. الطلب قيد المتابعة.")
    except Exception: pass
    for aid in ADMIN_IDS:
        try:
            await bot.send_message(aid,
                f"🛍 <b>طلب شراء #{oid}</b>\nالإعلان: #{lid}\nالمشتري: <code>{c.from_user.id}</code>\n"
                f"البائع: <code>{r['seller_id']}</code>\nالمبلغ: {money(r['price'])} {r['currency']}\n"
                f"الرقم: <code>{r['phone']}</code>\n\nبعد التحقق من التسليم اضغط تأكيد التسليم.",
                reply_markup=inline([[InlineKeyboardButton(text="📦 تأكيد التسليم",callback_data=f"deliver:{oid}"),
                                      InlineKeyboardButton(text="↩️ إلغاء وإرجاع المبلغ",callback_data=f"refund:{oid}")]]))
        except Exception: pass
    await c.answer("تم إنشاء الطلب.")

@dp.callback_query(F.data.startswith("deliver:"))
async def deliver_order(c: CallbackQuery):
    if not is_admin(c.from_user.id): return await c.answer("غير مصرح.",show_alert=True)
    oid=int(c.data.split(":")[1])
    o=q("SELECT * FROM orders WHERE id=? AND status='pending'",(oid,),one=True)
    if not o: return await c.answer("الطلب غير موجود أو تمت معالجته.",show_alert=True)
    listing=q("SELECT phone FROM listings WHERE id=?",(o["listing_id"],),one=True)
    fee=round(float(o["amount"])*float(COMMISSION_PERCENT)/100,2)
    seller_amount=float(o["amount"])-fee
    # seller credited in the same currency; held buyer funds are released to seller less commission
    q("UPDATE users SET balance=balance+? WHERE user_id=?",(seller_amount,o["seller_id"]))
    q("UPDATE orders SET status='completed',delivered_at=? WHERE id=?",(now(),oid))
    q("UPDATE listings SET status='sold' WHERE id=?",(o["listing_id"],))
    q("INSERT INTO transactions(user_id,kind,amount,currency,note,created_at) VALUES(?,?,?,?,?,?)",
      (o["seller_id"],"sale",seller_amount,o["currency"],f"عائد بيع الطلب #{oid} بعد العمولة",now()))
    buyer=o["buyer_id"]
    try: await bot.send_message(buyer,f"✅ تم تأكيد طلبك رقم #{oid}.\nالرقم الذي اشتريته:\n<code>{listing['phone']}</code>\nيرجى استخدامه بشكل قانوني وآمن.")
    except Exception: pass
    try: await bot.send_message(o["seller_id"],f"✅ اكتملت عملية بيعك #{oid} وتم إضافة {money(seller_amount)} {o['currency']} إلى رصيدك بعد عمولة {COMMISSION_PERCENT}%.")
    except Exception: pass
    await c.message.edit_text(f"تم إكمال الطلب #{oid}. تم تحويل صافي المبلغ للبائع.")
    await c.answer("تم.")

@dp.callback_query(F.data.startswith("refund:"))
async def refund_order(c: CallbackQuery):
    if not is_admin(c.from_user.id): return await c.answer("غير مصرح.",show_alert=True)
    oid=int(c.data.split(":")[1])
    o=q("SELECT * FROM orders WHERE id=? AND status='pending'",(oid,),one=True)
    if not o: return await c.answer("الطلب غير موجود أو تمت معالجته.",show_alert=True)
    q("UPDATE users SET balance=balance+? WHERE user_id=?",(o["amount"],o["buyer_id"]))
    q("UPDATE orders SET status='refunded' WHERE id=?",(oid,))
    q("UPDATE listings SET status='approved',buyer_id=NULL,order_id=NULL WHERE id=?",(o["listing_id"],))
    q("INSERT INTO transactions(user_id,kind,amount,currency,note,created_at) VALUES(?,?,?,?,?,?)",
      (o["buyer_id"],"refund",o["amount"],o["currency"],f"استرجاع الطلب #{oid}",now()))
    try: await bot.send_message(o["buyer_id"],f"↩️ تم إلغاء الطلب #{oid} وإرجاع المبلغ إلى محفظتك.")
    except Exception: pass
    await c.message.edit_text(f"تم إلغاء الطلب #{oid} وإرجاع المبلغ.")
    await c.answer("تم.")

# ---------------- Wallet ----------------
@dp.message(F.text == "💳 المحفظة")
async def wallet(m: Message):
    bal=user_balance(m.from_user.id)
    await m.answer(
        f"💳 <b>محفظة NUVEX</b>\n\nرصيدك: <b>{money(bal)}</b> (الرصيد يعرض كقيمة إجمالية؛ راجع عملة كل عملية)\n\n"
        "اختر العملية:",
        reply_markup=inline([
            [InlineKeyboardButton(text="➕ إيداع رصيد",callback_data="deposit")],
            [InlineKeyboardButton(text="➖ طلب سحب",callback_data="withdraw")],
            [InlineKeyboardButton(text="📜 سجل العمليات",callback_data="history")]
        ])
    )

@dp.callback_query(F.data=="deposit")
async def deposit_start(c: CallbackQuery,state:FSMContext):
    await state.set_state(DepositFlow.amount); await c.message.answer("اكتب مبلغ الإيداع بالأرقام فقط:"); await c.answer()

@dp.message(DepositFlow.amount)
async def dep_amount(m:Message,state:FSMContext):
    try:
        a=float(Decimal(m.text.strip().replace(",","")))
        if a<=0: raise ValueError
    except Exception: return await m.answer("اكتب مبلغاً صحيحاً.")
    await state.update_data(amount=a); await state.set_state(DepositFlow.currency)
    await m.answer("اختر العملة:",reply_markup=inline([[InlineKeyboardButton(text="YER",callback_data="depcur:YER"),InlineKeyboardButton(text="SAR",callback_data="depcur:SAR"),InlineKeyboardButton(text="USD",callback_data="depcur:USD")]]))

@dp.callback_query(F.data.startswith("depcur:"))
async def dep_currency(c:CallbackQuery,state:FSMContext):
    await state.update_data(currency=c.data.split(":")[1]); await state.set_state(DepositFlow.method)
    await c.message.answer("اكتب طريقة التحويل أو اسم المحفظة التي استخدمتها:"); await c.answer()

@dp.message(DepositFlow.method)
async def dep_method(m:Message,state:FSMContext):
    await state.update_data(method=m.text.strip()); await state.set_state(DepositFlow.proof)
    await m.answer("أرسل صورة إيصال التحويل أو رقم العملية كنص:")

@dp.message(DepositFlow.proof)
async def dep_proof(m:Message,state:FSMContext):
    d=await state.get_data()
    proof=m.text or (m.photo[-1].file_id if m.photo else "مرفق")
    q("INSERT INTO deposits(user_id,amount,currency,method,proof,status,created_at) VALUES(?,?,?,?,?,?,?)",
      (m.from_user.id,d["amount"],d["currency"],d["method"],proof,"pending",now()))
    did=q("SELECT last_insert_rowid() AS id",one=True)["id"]
    await state.clear(); await m.answer(f"تم إرسال طلب الإيداع #{did} للمراجعة. لا يتم إضافة الرصيد إلا بعد التحقق.",reply_markup=main_keyboard())
    for aid in ADMIN_IDS:
        try:
            if m.photo: await bot.send_photo(aid,m.photo[-1].file_id,caption=f"طلب إيداع #{did}\nالمستخدم: {m.from_user.id}\nالمبلغ: {d['amount']} {d['currency']}\nالطريقة: {d['method']}",reply_markup=admin_button("deposit",did))
            else: await bot.send_message(aid,f"طلب إيداع #{did}\nالمستخدم: {m.from_user.id}\nالمبلغ: {d['amount']} {d['currency']}\nالطريقة: {d['method']}\nالإثبات: {proof}",reply_markup=admin_button("deposit",did))
        except Exception: pass

@dp.callback_query(F.data=="withdraw")
async def withdraw_start(c:CallbackQuery,state:FSMContext):
    await state.set_state(WithdrawFlow.amount); await c.message.answer("اكتب مبلغ السحب:"); await c.answer()

@dp.message(WithdrawFlow.amount)
async def wd_amount(m:Message,state:FSMContext):
    try:
        a=float(Decimal(m.text.strip().replace(",","")))
        if a<=0 or a>user_balance(m.from_user.id): raise ValueError
    except Exception: return await m.answer("المبلغ غير صحيح أو أكبر من رصيدك.")
    await state.update_data(amount=a); await state.set_state(WithdrawFlow.currency)
    await m.answer("اختر العملة:",reply_markup=inline([[InlineKeyboardButton(text="YER",callback_data="wdcur:YER"),InlineKeyboardButton(text="SAR",callback_data="wdcur:SAR"),InlineKeyboardButton(text="USD",callback_data="wdcur:USD")]]))

@dp.callback_query(F.data.startswith("wdcur:"))
async def wd_currency(c:CallbackQuery,state:FSMContext):
    await state.update_data(currency=c.data.split(":")[1]); await state.set_state(WithdrawFlow.details)
    await c.message.answer("أرسل بيانات الاستلام (رقم المحفظة/الحساب واسم المستلم):"); await c.answer()

@dp.message(WithdrawFlow.details)
async def wd_details(m:Message,state:FSMContext):
    d=await state.get_data()
    # Balance is reserved immediately to avoid duplicate withdrawal requests.
    if user_balance(m.from_user.id)<d["amount"]:
        await state.clear(); return await m.answer("رصيدك لم يعد كافياً.")
    q("UPDATE users SET balance=balance-? WHERE user_id=?",(d["amount"],m.from_user.id))
    q("INSERT INTO withdrawals(user_id,amount,currency,details,status,created_at) VALUES(?,?,?,?,?,?)",
      (m.from_user.id,d["amount"],d["currency"],m.text.strip(),"pending",now()))
    wid=q("SELECT last_insert_rowid() AS id",one=True)["id"]
    await state.clear(); await m.answer(f"تم إرسال طلب السحب #{wid} للمراجعة. تم حجز المبلغ مؤقتاً.",reply_markup=main_keyboard())
    for aid in ADMIN_IDS:
        try: await bot.send_message(aid,f"طلب سحب #{wid}\nالمستخدم: {m.from_user.id}\nالمبلغ: {d['amount']} {d['currency']}\nالبيانات: {m.text}",reply_markup=admin_button("withdraw",wid))
        except Exception: pass

@dp.callback_query(F.data=="history")
async def history(c:CallbackQuery):
    rows=q("SELECT kind,amount,currency,note,created_at FROM transactions WHERE user_id=? ORDER BY id DESC LIMIT 12",(c.from_user.id,))
    if not rows: return await c.answer("لا توجد عمليات بعد.",show_alert=True)
    txt="📜 <b>آخر العمليات</b>\n\n"+"\n".join([f"• {r['kind']}: {money(r['amount'])} {r['currency']} — {r['note'] or ''}" for r in rows])
    await c.message.answer(txt); await c.answer()

# ---------------- Admin actions ----------------
@dp.callback_query(F.data.startswith("adm:"))
async def admin_review(c:CallbackQuery):
    if not is_admin(c.from_user.id): return await c.answer("غير مصرح.",show_alert=True)
    _,kind,decision,sid=c.data.split(":"); sid=int(sid)
    if kind=="listing":
        row=q("SELECT * FROM listings WHERE id=? AND status='pending'",(sid,),one=True)
        if not row: return await c.answer("تمت معالجة الإعلان مسبقاً.",show_alert=True)
        status="approved" if decision=="ok" else "rejected"
        q("UPDATE listings SET status=? WHERE id=?",(status,sid))
        try: await bot.send_message(row["seller_id"],f"{'✅ تمت الموافقة' if decision=='ok' else '❌ تم رفض'} إعلانك رقم #{sid}.")
        except Exception: pass
        await c.message.edit_text(f"تمت مراجعة الإعلان #{sid}: {status}")
    elif kind=="deposit":
        row=q("SELECT * FROM deposits WHERE id=? AND status='pending'",(sid,),one=True)
        if not row: return await c.answer("تمت معالجة الطلب مسبقاً.",show_alert=True)
        if decision=="ok":
            q("UPDATE deposits SET status='approved' WHERE id=?",(sid,))
            adjust_balance(row["user_id"],row["amount"],row["currency"],"deposit",f"إيداع #{sid}")
            msg=f"✅ تمت الموافقة على إيداعك #{sid} وإضافة {money(row['amount'])} {row['currency']}."
        else:
            q("UPDATE deposits SET status='rejected' WHERE id=?",(sid,)); msg=f"❌ تم رفض طلب الإيداع #{sid}."
        try: await bot.send_message(row["user_id"],msg)
        except Exception: pass
        await c.message.edit_text(f"تمت معالجة الإيداع #{sid}.")
    elif kind=="withdraw":
        row=q("SELECT * FROM withdrawals WHERE id=? AND status='pending'",(sid,),one=True)
        if not row: return await c.answer("تمت معالجة الطلب مسبقاً.",show_alert=True)
        if decision=="ok":
            q("UPDATE withdrawals SET status='paid' WHERE id=?",(sid,))
            msg=f"✅ تمت الموافقة على طلب السحب #{sid}. تواصل مع الدعم إذا لم تستلم المبلغ."
        else:
            q("UPDATE withdrawals SET status='rejected' WHERE id=?",(sid,))
            q("UPDATE users SET balance=balance+? WHERE user_id=?",(row["amount"],row["user_id"]))
            q("INSERT INTO transactions(user_id,kind,amount,currency,note,created_at) VALUES(?,?,?,?,?,?)",
              (row["user_id"],"withdraw_refund",row["amount"],row["currency"],f"إرجاع طلب سحب #{sid}",now()))
            msg=f"❌ تم رفض طلب السحب #{sid} وإرجاع المبلغ إلى رصيدك."
        try: await bot.send_message(row["user_id"],msg)
        except Exception: pass
        await c.message.edit_text(f"تمت معالجة السحب #{sid}.")
    await c.answer("تم.")

@dp.message(Command("admin"))
async def admin_panel(m:Message):
    if not is_admin(m.from_user.id): return await m.answer("غير مصرح.")
    stats=q("SELECT (SELECT COUNT(*) FROM users) users,(SELECT COUNT(*) FROM listings WHERE status='pending') pending_listings,(SELECT COUNT(*) FROM orders WHERE status='pending') pending_orders,(SELECT COUNT(*) FROM deposits WHERE status='pending') pending_deposits,(SELECT COUNT(*) FROM withdrawals WHERE status='pending') pending_withdrawals",one=True)
    await m.answer(
        "👑 <b>لوحة إدارة NUVEX</b>\n\n"
        f"المستخدمون: {stats['users']}\nإعلانات بانتظار المراجعة: {stats['pending_listings']}\n"
        f"طلبات شراء معلقة: {stats['pending_orders']}\nطلبات إيداع: {stats['pending_deposits']}\nطلبات سحب: {stats['pending_withdrawals']}\n\n"
        f"العمولة الحالية: {COMMISSION_PERCENT}%\nقناة التفعيلات: <code>{ACTIVATION_CHANNEL}</code>"
    )

@dp.message(F.text == "📦 طلباتي")
async def my_orders(m:Message):
    rows=q("SELECT id,amount,currency,status,created_at FROM orders WHERE buyer_id=? OR seller_id=? ORDER BY id DESC LIMIT 10",(m.from_user.id,m.from_user.id))
    if not rows: return await m.answer("لا توجد طلبات حتى الآن.")
    await m.answer("📦 <b>آخر طلباتك</b>\n\n"+"\n".join([f"#{r['id']} — {money(r['amount'])} {r['currency']} — {r['status']}" for r in rows]))

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
