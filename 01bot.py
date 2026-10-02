import asyncio
import logging
import os
import sqlite3
import re
import random
from datetime import datetime, timedelta
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = 5908360782

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

SERVICES = [
    "Консультация и осмотр",
    "Лечение кариеса",
    "Профессиональная чистка",
    "Удаление зуба",
    "Имплантация",
    "Протезирование"
]

CABINETS = ["Кабинет №1", "Кабинет №2", "Кабинет №3", "Кабинет №4"]
DOCTORS = ["Иванов И.И.", "Петров П.П.", "Сидорова А.А.", "Кузнецов Д.Д.", "Смирнова Е.Е."]
AGE_OPTIONS = ["До 18", "18–30", "30–45", "45–60", "60+"]
TIMES = ["09:00", "10:30", "12:00", "14:00", "16:00", "18:00"]

# ================= БАЗА =================
def init_db():
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            phone TEXT,
            username TEXT,
            age TEXT,
            pain_level TEXT,
            notes TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            service TEXT,
            date TEXT,
            time TEXT,
            cabinet TEXT,
            doctor TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_user(user_id, name, phone, username, age="", pain_level="", notes=""):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("""
        INSERT INTO users (user_id, name, phone, username, age, pain_level, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            name=excluded.name,
            phone=excluded.phone,
            username=excluded.username,
            age=excluded.age,
            pain_level=excluded.pain_level,
            notes=excluded.notes
    """, (user_id, name, phone, username, age, pain_level, notes))
    conn.commit()
    conn.close()

def update_user_field(user_id, field, value):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute(f"UPDATE users SET {field} = ? WHERE user_id = ?", (value, user_id))
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("SELECT name, phone, username, age, pain_level, notes FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row

def save_appointment(user_id, service, date, time, cabinet, doctor):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("""
        INSERT INTO appointments (user_id, service, date, time, cabinet, doctor, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (user_id, service, date, time, cabinet, doctor, datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    conn.close()

def get_appointments(user_id):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("""
        SELECT service, date, time, cabinet, doctor FROM appointments
        WHERE user_id = ? ORDER BY id DESC
    """, (user_id,))
    rows = c.fetchall()
    conn.close()
    return rows

# ================= УТИЛИТЫ =================
def is_valid_phone(phone: str) -> bool:
    cleaned = re.sub(r"[^\d]", "", phone)
    return 10 <= len(cleaned) <= 15

def format_phone(phone: str) -> str:
    cleaned = re.sub(r"[^\d]", "", phone)
    if len(cleaned) == 10:
        return "+7" + cleaned
    return "+" + cleaned

def get_week_dates(offset=0):
    today = datetime.now().date()
    start = today + timedelta(days=offset * 7)
    days_ru = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
    dates = []
    for i in range(7):
        d = start + timedelta(days=i)
        day_name = days_ru[d.weekday()]
        dates.append(d.strftime(f"%d.%m ({day_name})"))
    return dates

# ================= СОСТОЯНИЯ =================
class Booking(StatesGroup):
    choosing_service = State()
    choosing_date = State()
    choosing_time = State()
    entering_name = State()
    entering_phone = State()
    choosing_age = State()
    choosing_pain = State()
    entering_pain_level = State()
    entering_notes = State()
    confirming = State()

class EditProfile(StatesGroup):
    editing_name = State()
    editing_phone = State()

# ================= КЛАВИАТУРЫ =================
def main_menu_kb():
    b = InlineKeyboardBuilder()
    b.button(text="🦷  Записаться на приём", callback_data="menu_book")
    b.button(text="👨‍⚕️  Наши врачи", callback_data="menu_doctors")
    b.button(text="⭐  Отзывы", callback_data="menu_reviews")
    b.button(text="🏥  О клинике", callback_data="menu_about")
    b.button(text="📢  Реклама", callback_data="menu_ads")
    b.adjust(1)
    return b.as_markup()

def services_kb():
    b = InlineKeyboardBuilder()
    for i, s in enumerate(SERVICES):
        b.button(text=f"▫️ {s}", callback_data=f"service_{i}")
    b.button(text="⬅️  Назад", callback_data="back_main")
    b.adjust(1)
    return b.as_markup()

def dates_kb(offset=0):
    b = InlineKeyboardBuilder()
    for d in get_week_dates(offset):
        b.button(text=f"📅 {d}", callback_data=f"date_{d}")
    b.button(text="⬅️  Пред. неделя", callback_data=f"week_{offset-1}")
    b.button(text="След. неделя ➡️", callback_data=f"week_{offset+1}")
    b.button(text="⬅️  Назад", callback_data="back_service")
    b.adjust(1, 1, 1, 1, 1, 1, 1, 2, 1)
    return b.as_markup()

def times_kb():
    b = InlineKeyboardBuilder()
    for t in TIMES:
        b.button(text=f"🕐  {t}", callback_data=f"time_{t}")
    b.button(text="⬅️  Назад", callback_data="back_date")
    b.adjust(2)
    return b.as_markup()

def age_kb():
    b = InlineKeyboardBuilder()
    for a in AGE_OPTIONS:
        b.button(text=a, callback_data=f"age_{a}")
    b.adjust(2)
    return b.as_markup()

def pain_kb():
    b = InlineKeyboardBuilder()
    b.button(text="😊  Нет боли", callback_data="pain_no")
    b.button(text="😐  Есть боль", callback_data="pain_yes")
    b.adjust(1)
    return b.as_markup()

def pain_level_kb():
    b = InlineKeyboardBuilder()
    for i in range(1, 11):
        b.button(text=str(i), callback_data=f"painlvl_{i}")
    b.adjust(5, 5)
    return b.as_markup()

def notes_kb():
    b = InlineKeyboardBuilder()
    b.button(text="⏭  Пропустить", callback_data="notes_skip")
    b.adjust(1)
    return b.as_markup()

def confirm_kb(data_ok=True):
    b = InlineKeyboardBuilder()
    if data_ok:
        b.button(text="✅  Подтвердить", callback_data="confirm_yes")
    else:
        b.button(text="⚠️  Заполните все поля", callback_data="confirm_blocked")
    b.button(text="✏️  Изменить", callback_data="confirm_edit")
    b.button(text="❌  Отменить", callback_data="confirm_no")
    b.adjust(1)
    return b.as_markup()

def profile_kb():
    b = InlineKeyboardBuilder()
    b.button(text="✏️  Изменить имя", callback_data="edit_name")
    b.button(text="📞  Изменить телефон", callback_data="edit_phone")
    b.button(text="📋  Мои записи", callback_data="my_appointments")
    b.button(text="🏠  Главное меню", callback_data="back_main")
    b.adjust(1)
    return b.as_markup()

def back_menu_kb():
    b = InlineKeyboardBuilder()
    b.button(text="🏠  Главное меню", callback_data="back_main")
    b.adjust(1)
    return b.as_markup()

# ================= ГЛАВНОЕ МЕНЮ =================
async def show_main_menu(target, edit=False):
    text = (
        "🦷 <b>ДЕНТАЛ ПРОФИ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "🏥 Стоматологическая клиника\n\n"
        "✨ <i>Забота о вашей улыбке — наша работа</i>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Выберите действие:"
    )
    if edit:
        await target.message.edit_text(text, parse_mode="HTML", reply_markup=main_menu_kb())
    else:
        await target.answer(text, parse_mode="HTML", reply_markup=main_menu_kb())

@dp.message(CommandStart())
async def start(message: types.Message, state: FSMContext):
    await state.clear()
    await show_main_menu(message)

@dp.callback_query(F.data == "back_main")
async def back_main(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await show_main_menu(callback, edit=True)

# ================= ВРАЧИ =================
@dp.callback_query(F.data == "menu_doctors")
async def doctors(callback: types.CallbackQuery):
    text = (
        "👨‍⚕️ <b>НАШИ ВРАЧИ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "⭐ <b>Иванов И.И.</b> — 4.9\n"
        "Стоматолог-терапевт · 15 лет опыта\n\n"
        "⭐ <b>Петров П.П.</b> — 4.8\n"
        "Хирург-имплантолог · 12 лет опыта\n\n"
        "⭐ <b>Сидорова А.А.</b> — 5.0\n"
        "Ортодонт · 10 лет опыта\n\n"
        "⭐ <b>Кузнецов Д.Д.</b> — 4.7\n"
        "Протезист · 8 лет опыта\n\n"
        "⭐ <b>Смирнова Е.Е.</b> — 4.9\n"
        "Гигиенист · 7 лет опыта"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=back_menu_kb())

# ================= ОТЗЫВЫ =================
@dp.callback_query(F.data == "menu_reviews")
async def reviews(callback: types.CallbackQuery):
    text = (
        "⭐ <b>ОТЗЫВЫ ПАЦИЕНТОВ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "💬 <i>«Отличная клиника! Лечение прошло безболезненно, врач всё объяснил. Рекомендую.»</i>\n"
        "— Анна · ★★★★★\n\n"
        "💬 <i>«Записался через бота за минуту. Приняли вовремя, без очередей.»</i>\n"
        "— Дмитрий · ★★★★★\n\n"
        "💬 <i>«Профессиональный подход, чистка прошла комфортно.»</i>\n"
        "— Елена · ★★★★★\n\n"
        "💬 <i>«Сделал имплантацию — всё чётко, никаких проблем.»</i>\n"
        "— Сергей · ★★★★★"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=back_menu_kb())

# ================= ПРОФИЛЬ =================
@dp.callback_query(F.data == "menu_profile")
async def profile(callback: types.CallbackQuery):
    user = get_user(callback.from_user.id)
    if not user:
        await callback.message.edit_text(
            "👤 <b>МОЙ ПРОФИЛЬ</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "Профиль пока пуст.\n"
            "Запишитесь на приём — данные сохранятся автоматически.",
            parse_mode="HTML",
            reply_markup=back_menu_kb()
        )
        return

    name, phone, username, age, pain, notes = user
    text = (
        "👤 <b>МОЙ ПРОФИЛЬ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📛 <b>Имя:</b> {name or '—'}\n"
        f"📞 <b>Телефон:</b> {phone or '—'}\n"
        f"🆔 <b>Telegram:</b> @{username or '—'}\n"
        f"🎂 <b>Возраст:</b> {age or '—'}\n"
        f"💊 <b>Боль:</b> {pain or '—'}\n"
        f"📝 <b>Заметки:</b> {notes or '—'}\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Выберите действие:"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=profile_kb())

@dp.callback_query(F.data == "my_appointments")
async def my_appointments(callback: types.CallbackQuery):
    apps = get_appointments(callback.from_user.id)
    if not apps:
        await callback.message.edit_text(
            "📋 <b>МОИ ЗАПИСИ</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "У вас пока нет записей.",
            parse_mode="HTML",
            reply_markup=back_menu_kb()
        )
        return

    text = "📋 <b>МОИ ЗАПИСИ</b>\n━━━━━━━━━━━━━━━━━━━━\n"
    for i, (service, date, time, cabinet, doctor) in enumerate(apps, 1):
        text += f"\n<b>{i}.</b> {service}\n📅 {date} · 🕐 {time}\n🚪 {cabinet} · 👨‍⚕️ {doctor}\n"

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=back_menu_kb())

@dp.callback_query(F.data == "edit_name")
async def edit_name(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("✏️ Введите новое имя:")
    await state.set_state(EditProfile.editing_name)

@dp.message(EditProfile.editing_name)
async def save_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("⚠️ Слишком короткое имя.")
        return
    update_user_field(message.from_user.id, "name", name)
    await state.clear()
    await message.answer("✅ Имя обновлено.", reply_markup=back_menu_kb())

@dp.callback_query(F.data == "edit_phone")
async def edit_phone(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("📞 Введите новый номер телефона:")
    await state.set_state(EditProfile.editing_phone)

@dp.message(EditProfile.editing_phone)
async def save_phone(message: types.Message, state: FSMContext):
    phone = message.text.strip()
    if not is_valid_phone(phone):
        await message.answer("⚠️ Некорректный номер. Пример: +79101234567")
        return
    update_user_field(message.from_user.id, "phone", format_phone(phone))
    await state.clear()
    await message.answer("✅ Телефон обновлён.", reply_markup=back_menu_kb())

# ================= О КЛИНИКЕ =================
@dp.callback_query(F.data == "menu_about")
async def about(callback: types.CallbackQuery):
    text = (
        "🏥 <b>О КЛИНИКЕ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "🦷 <b>Дентал Профи</b>\n\n"
        "Современная стоматологическая клиника.\n\n"
        "🕐 <b>Режим работы:</b>\n"
        "Пн–Пт: 9:00 – 20:00\n"
        "Сб: 10:00 – 18:00\n"
        "Вс: выходной\n\n"
        "📞 <b>Телефон:</b> +7 (900) 000-00-00\n"
        "📍 <b>Адрес:</b> Улица Пушкина, дом Калатушкина\n\n"
        "✅ <b>Преимущества:</b>\n"
        "• Современное оборудование\n"
        "• Опытные врачи\n"
        "• Безболезненное лечение\n"
        "• Гарантия на услуги"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=back_menu_kb())

# ================= РЕКЛАМА =================
@dp.callback_query(F.data == "menu_ads")
async def ads(callback: types.CallbackQuery):
    text = (
        "📢 <b>РЕКЛАМНОЕ МЕСТО</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "💼 Здесь могла быть <b>ваша реклама</b>.\n\n"
        "Этот бот ежедневно видят десятки пациентов. "
        "Разместите свою рекламу и получайте новых клиентов.\n\n"
        "📩 <b>По вопросам рекламы:</b>\n"
        "Напишите администратору."
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=back_menu_kb())

# ================= ЗАПИСЬ =================
@dp.callback_query(F.data == "menu_book")
async def book_start(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "🦷 <b>ЗАПИСЬ НА ПРИЁМ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Шаг 1. Выберите услугу:",
        parse_mode="HTML",
        reply_markup=services_kb()
    )
    await state.set_state(Booking.choosing_service)

@dp.callback_query(F.data.startswith("service_"), Booking.choosing_service)
async def choose_service(callback: types.CallbackQuery, state: FSMContext):
    idx = int(callback.data.split("_", 1)[1])
    service = SERVICES[idx]
    await state.update_data(service=service, week_offset=0)
    await callback.message.edit_text(
        f"🦷 Услуга: <b>{service}</b>\n\nШаг 2. Выберите дату:",
        parse_mode="HTML",
        reply_markup=dates_kb(0)
    )
    await state.set_state(Booking.choosing_date)

@dp.callback_query(F.data.startswith("week_"), Booking.choosing_date)
async def change_week(callback: types.CallbackQuery, state: FSMContext):
    offset = int(callback.data.split("_")[1])
    if offset < 0:
        offset = 0
    if offset > 4:
        offset = 4
    await state.update_data(week_offset=offset)
    await callback.message.edit_text(
        "📅 Выберите дату:",
        parse_mode="HTML",
        reply_markup=dates_kb(offset)
    )

@dp.callback_query(F.data == "back_service", Booking.choosing_date)
async def back_service(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🦷 Шаг 1. Выберите услугу:",
        parse_mode="HTML",
        reply_markup=services_kb()
    )
    await state.set_state(Booking.choosing_service)

@dp.callback_query(F.data.startswith("date_"), Booking.choosing_date)
async def choose_date(callback: types.CallbackQuery, state: FSMContext):
    date = callback.data.split("_", 1)[1]
    await state.update_data(date=date)
    await callback.message.edit_text(
        f"📅 Дата: <b>{date}</b>\n\nШаг 3. Выберите время:",
        parse_mode="HTML",
        reply_markup=times_kb()
    )
    await state.set_state(Booking.choosing_time)

@dp.callback_query(F.data == "back_date", Booking.choosing_time)
async def back_date(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "📅 Шаг 2. Выберите дату:",
        parse_mode="HTML",
        reply_markup=dates_kb(0)
    )
    await state.set_state(Booking.choosing_date)

@dp.callback_query(F.data.startswith("time_"), Booking.choosing_time)
async def choose_time(callback: types.CallbackQuery, state: FSMContext):
    time = callback.data.split("_", 1)[1]
    await state.update_data(time=time)
    await callback.message.edit_text(
        f"🕐 Время: <b>{time}</b>\n\nШаг 4. Введите ваше имя:",
        parse_mode="HTML"
    )
    await state.set_state(Booking.entering_name)

@dp.message(Booking.entering_name)
async def enter_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("⚠️ Введите имя (минимум 2 символа).")
        return
    await state.update_data(name=name)
    await message.answer("📞 Шаг 5. Введите номер телефона (от 10 до 15 цифр):")
    await state.set_state(Booking.entering_phone)

@dp.message(Booking.entering_phone)
async def enter_phone(message: types.Message, state: FSMContext):
    phone = message.text.strip()
    if not is_valid_phone(phone):
        await message.answer("⚠️ Некорректный номер. Пример: +79101234567")
        return
    await state.update_data(phone=format_phone(phone))
    await message.answer("🎂 Шаг 6. Укажите возраст:", reply_markup=age_kb())
    await state.set_state(Booking.choosing_age)

@dp.callback_query(F.data.startswith("age_"), Booking.choosing_age)
async def choose_age(callback: types.CallbackQuery, state: FSMContext):
    age = callback.data.split("_", 1)[1]
    await state.update_data(age=age)
    await callback.message.edit_text(
        f"🎂 Возраст: <b>{age}</b>\n\nШаг 7. Есть ли боль?",
        parse_mode="HTML",
        reply_markup=pain_kb()
    )
    await state.set_state(Booking.choosing_pain)

@dp.callback_query(F.data == "pain_no", Booking.choosing_pain)
async def pain_no(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(pain="Нет")
    await callback.message.edit_text(
        "💊 Боль: <b>Нет</b>\n\nШаг 8. Дополнительная информация (аллергии, пожелания):",
        parse_mode="HTML",
        reply_markup=notes_kb()
    )
    await state.set_state(Booking.entering_notes)

@dp.callback_query(F.data == "pain_yes", Booking.choosing_pain)
async def pain_yes(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "💊 Оцените уровень боли от 1 до 10:",
        parse_mode="HTML",
        reply_markup=pain_level_kb()
    )
    await state.set_state(Booking.entering_pain_level)

@dp.callback_query(F.data.startswith("painlvl_"), Booking.entering_pain_level)
async def pain_level(callback: types.CallbackQuery, state: FSMContext):
    lvl = callback.data.split("_", 1)[1]
    await state.update_data(pain=f"Есть, уровень {lvl}/10")
    await callback.message.edit_text(
        f"💊 Боль: <b>уровень {lvl}/10</b>\n\nШаг 8. Дополнительная информация:",
        parse_mode="HTML",
        reply_markup=notes_kb()
    )
    await state.set_state(Booking.entering_notes)

@dp.callback_query(F.data == "notes_skip", Booking.entering_notes)
async def notes_skip(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(notes="—")
    await show_confirm(callback, state)

@dp.message(Booking.entering_notes)
async def enter_notes(message: types.Message, state: FSMContext):
    await state.update_data(notes=message.text.strip()[:300])
    await show_confirm(message, state)

async def show_confirm(target, state: FSMContext):
    data = await state.get_data()
    cabinet = random.choice(CABINETS)
    doctor = random.choice(DOCTORS)
    await state.update_data(cabinet=cabinet, doctor=doctor)

    text = (
        "📋 <b>ПРОВЕРЬТЕ ЗАЯВКУ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🦷 <b>Услуга:</b> {data.get('service', '—')}\n"
        f"📅 <b>Дата:</b> {data.get('date', '—')}\n"
        f"🕐 <b>Время:</b> {data.get('time', '—')}\n"
        f"👤 <b>Имя:</b> {data.get('name', '—')}\n"
        f"📞 <b>Телефон:</b> {data.get('phone', '—')}\n"
        f"🎂 <b>Возраст:</b> {data.get('age', '—')}\n"
        f"💊 <b>Боль:</b> {data.get('pain', '—')}\n"
        f"📝 <b>Заметки:</b> {data.get('notes', '—')}\n"
        f"🚪 <b>Кабинет:</b> {cabinet}\n"
        f"👨‍⚕️ <b>Врач:</b> {doctor}\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Всё верно?"
    )
    if isinstance(target, types.CallbackQuery):
        await target.message.edit_text(text, parse_mode="HTML", reply_markup=confirm_kb(True))
    else:
        await target.answer(text, parse_mode="HTML", reply_markup=confirm_kb(True))
    await state.set_state(Booking.confirming)

@dp.callback_query(F.data == "confirm_blocked")
async def confirm_blocked(callback: types.CallbackQuery):
    await callback.answer("Заполните все обязательные поля!", show_alert=True)

@dp.callback_query(F.data == "confirm_yes", Booking.confirming)
async def confirm_yes(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    save_user(
        callback.from_user.id,
        data.get('name', ''),
        data.get('phone', ''),
        callback.from_user.username or '',
        data.get('age', ''),
        data.get('pain', ''),
        data.get('notes', '')
    )
    save_appointment(
        callback.from_user.id,
        data.get('service', ''),
        data.get('date', ''),
        data.get('time', ''),
        data.get('cabinet', ''),
        data.get('doctor', '')
    )

    admin_text = (
        "🔔 <b>НОВАЯ ЗАЯВКА</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🦷 <b>Услуга:</b> {data.get('service')}\n"
        f"📅 <b>Дата:</b> {data.get('date')}\n"
        f"🕐 <b>Время:</b> {data.get('time')}\n"
        f"🚪 <b>Кабинет:</b> {data.get('cabinet')}\n"
        f"👨‍⚕️ <b>Врач:</b> {data.get('doctor')}\n\n"
        f"👤 <b>Имя:</b> {data.get('name')}\n"
        f"📞 <b>Телефон:</b> {data.get('phone')}\n"
        f"🎂 <b>Возраст:</b> {data.get('age')}\n"
        f"💊 <b>Боль:</b> {data.get('pain')}\n"
        f"📝 <b>Заметки:</b> {data.get('notes')}\n\n"
        f"🆔 @{callback.from_user.username or 'нет'}"
    )
    try:
        await bot.send_message(ADMIN_CHAT_ID, admin_text, parse_mode="HTML")
    except Exception as e:
        logging.error(f"Ошибка: {e}")

    await callback.message.edit_text(
        "✅ <b>ЗАЯВКА ПРИНЯТА</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Администратор свяжется с вами для подтверждения.\n\n"
        "Спасибо, что выбрали <b>Дентал Профи</b>!",
        parse_mode="HTML",
        reply_markup=back_menu_kb()
    )
    await state.clear()

@dp.callback_query(F.data == "confirm_edit", Booking.confirming)
async def confirm_edit(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🦷 Шаг 1. Выберите услугу заново:",
        parse_mode="HTML",
        reply_markup=services_kb()
    )
    await state.set_state(Booking.choosing_service)

@dp.callback_query(F.data == "confirm_no", Booking.confirming)
async def confirm_no(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "❌ <b>Запись отменена.</b>\n\n"
        "Возвращайтесь, когда будете готовы!",
        parse_mode="HTML",
        reply_markup=back_menu_kb()
    )

# ================= ЗАПУСК =================
async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())