import asyncio
import json
import os
from pathlib import Path
from datetime import datetime, timedelta
import logging

import requests
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    BotCommand,
    ReplyKeyboardRemove,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

API_TOKEN = os.environ.get("TG_TOKEN", "").strip()
LOGMEAL_TOKEN = os.environ.get("LOGMEAL_TOKEN", "").strip()

if not API_TOKEN:
    logger.error("TG_TOKEN не установлен!")
    raise SystemExit(1)

if not LOGMEAL_TOKEN:
    logger.error("LOGMEAL_TOKEN не установлен!")
    raise SystemExit(1)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

GOALS_FILE = DATA_DIR / "user_goals.json"
PROFILE_FILE = DATA_DIR / "user_profiles.json"
MEALS_FILE = DATA_DIR / "meals_log.json"
SETTINGS_FILE = DATA_DIR / "user_settings.json"
FAVORITES_FILE = DATA_DIR / "favorites.json"
ACTIVITY_FILE = DATA_DIR / "activity_log.json"

user_goals = {}
user_profiles = {}
meals_log = {}
user_settings = {}
favorites = {}
activity_log = {}

activity_map = {
    "Сидячий образ жизни": 1.2,
    "Легкая активность": 1.375,
    "Средняя активность": 1.55,
    "Высокая активность": 1.725,
    "Очень высокая активность": 1.9,
}

exercise_map = {
    "Ходьба (5 км/ч)": 3.5,
    "Бег трусцой (8 км/ч)": 8.0,
    "Бег (12 км/ч)": 12.0,
    "Велосипед (15 км/ч)": 6.0,
    "Плавание": 7.0,
    "Йога": 3.0,
    "Тренировка с весами": 6.0,
    "HIIT тренировка": 10.0,
    "Футбол": 8.0,
    "Теннис": 7.0,
}

main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📊 Профиль")],
        [KeyboardButton(text="📸 Анализ блюда")],
        [KeyboardButton(text="⭐ Избранное")],
        [KeyboardButton(text="📜 История")],
        [KeyboardButton(text="📈 Статистика")],
        [KeyboardButton(text="🏃 Упражнения")],
        [KeyboardButton(text="❓ Помощь")],
    ],
    resize_keyboard=True,
    is_persistent=True,
)

profile_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Создать профиль")],
        [KeyboardButton(text="✏️ Редактировать профиль")],
        [KeyboardButton(text="🗑️ Удалить профиль")],
        [KeyboardButton(text="◀️ Назад в меню")],
    ],
    resize_keyboard=True,
    is_persistent=True,
)

gender_menu = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Мужской"), KeyboardButton(text="Женский")]],
    resize_keyboard=True,
)

activity_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Сидячий образ жизни")],
        [KeyboardButton(text="Легкая активность")],
        [KeyboardButton(text="Средняя активность")],
        [KeyboardButton(text="Высокая активность")],
        [KeyboardButton(text="Очень высокая активность")],
    ],
    resize_keyboard=True,
)

goal_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Похудение")],
        [KeyboardButton(text="Поддержание")],
        [KeyboardButton(text="Набор")],
    ],
    resize_keyboard=True,
)

exercise_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Ходьба (5 км/ч)")],
        [KeyboardButton(text="Бег трусцой (8 км/ч)")],
        [KeyboardButton(text="Бег (12 км/ч)")],
        [KeyboardButton(text="Велосипед (15 км/ч)")],
        [KeyboardButton(text="Плавание")],
        [KeyboardButton(text="Йога")],
        [KeyboardButton(text="Тренировка с весами")],
        [KeyboardButton(text="HIIT тренировка")],
        [KeyboardButton(text="Футбол")],
        [KeyboardButton(text="Теннис")],
        [KeyboardButton(text="◀️ Назад")],
    ],
    resize_keyboard=True,
)

confirm_delete_menu = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="✅ Да, удалить"), KeyboardButton(text="❌ Отмена")]],
    resize_keyboard=True,
)

period_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📅 За день")],
        [KeyboardButton(text="📊 За неделю")],
        [KeyboardButton(text="📈 За месяц")],
        [KeyboardButton(text="◀️ Назад")],
    ],
    resize_keyboard=True,
)

class ProfileForm(StatesGroup):
    sex = State()
    age = State()
    height = State()
    weight = State()
    activity = State()
    goal = State()

class DeleteProfileForm(StatesGroup):
    confirm = State()

class ExerciseForm(StatesGroup):
    exercise = State()
    duration = State()

class PortionForm(StatesGroup):
    dish_name = State()
    calories_per_100 = State()
    portion_grams = State()

def split_text(text, limit=4000):
    return [text[i:i + limit] for i in range(0, len(text), limit)]

def load_json_file(path, default):
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки {path}: {e}")
            return default
    return default

def save_json_file(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения {path}: {e}")

def load_state():
    global user_goals, user_profiles, meals_log, user_settings, favorites, activity_log
    user_goals = load_json_file(GOALS_FILE, {})
    user_profiles = load_json_file(PROFILE_FILE, {})
    meals_log = load_json_file(MEALS_FILE, {})
    user_settings = load_json_file(SETTINGS_FILE, {})
    favorites = load_json_file(FAVORITES_FILE, {})
    activity_log = load_json_file(ACTIVITY_FILE, {})
    logger.info("Состояние загружено")

def save_state():
    save_json_file(GOALS_FILE, user_goals)
    save_json_file(PROFILE_FILE, user_profiles)
    save_json_file(MEALS_FILE, meals_log)
    save_json_file(SETTINGS_FILE, user_settings)
    save_json_file(FAVORITES_FILE, favorites)
    save_json_file(ACTIVITY_FILE, activity_log)

def logmeal_headers():
    return {
        "Authorization": f"Bearer {LOGMEAL_TOKEN}",
        "accept": "application/json",
    }

def safe_json(resp):
    try:
        return resp.json()
    except Exception:
        return {"error": resp.text}

def extract_list(data):
    if isinstance(data, dict):
        for key in [
            "segmentationResults", "segmentation_results", "predictions",
            "results", "dishPredictions", "foodSpots", "food_spots",
            "segments", "items"
        ]:
            value = data.get(key)
            if isinstance(value, list) and value:
                return value
    return []

def get_name(item):
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        for key in ["name", "dish", "label", "food", "title", "className", "dish_name"]:
            if item.get(key):
                return str(item[key])
        fg = item.get("food_groups")
        if isinstance(fg, list) and fg:
            return ", ".join(map(str, fg))
    return None

def extract_nutrients(nutri_json):
    info = nutri_json.get("nutritional_info", {})
    total = info.get("totalNutrients", {})
    calories = total.get("ENERC_KCAL", {}).get("quantity")
    protein = total.get("PROCNT", {}).get("quantity")
    fat = total.get("FAT", {}).get("quantity")
    carbs = total.get("CHOCDF", {}).get("quantity")
    fiber = total.get("FIBTG", {}).get("quantity")
    sugar = total.get("SUGAR", {}).get("quantity")
    score = nutri_json.get("image_nutri_score", {}).get("nutri_score_category")
    return calories, protein, fat, carbs, fiber, sugar, score

def calculate_tdee(profile):
    sex = profile.get("sex")
    age = profile.get("age")
    height = profile.get("height")
    weight = profile.get("weight")
    activity = profile.get("activity")

    if sex not in ("Мужской", "Женский"):
        raise ValueError("Некорректный пол")
    if age is None or height is None or weight is None:
        raise ValueError("Профиль заполнен не полностью")

    age = float(age)
    height = float(height)
    weight = float(weight)

    if sex == "Мужской":
        bmr = 10 * weight + 6.25 * height - 5 * age + 5
    else:
        bmr = 10 * weight + 6.25 * height - 5 * age - 161

    tdee = bmr * activity_map.get(activity, 1.2)
    return round(bmr), round(tdee)

def get_target_calories(profile, goal):
    _, tdee = calculate_tdee(profile)
    if goal == "Похудение":
        return round(tdee - 400)
    if goal == "Набор":
        return round(tdee + 300)
    return round(tdee)

def get_daily_macros(profile, goal):
    target_cal = get_target_calories(profile, goal)
    if goal == "Похудение":
        p, f, c = 0.30, 0.25, 0.45
    elif goal == "Набор":
        p, f, c = 0.25, 0.25, 0.50
    else:
        p, f, c = 0.30, 0.30, 0.40
    protein_g = round(target_cal * p / 4)
    fat_g = round(target_cal * f / 9)
    carbs_g = round(target_cal * c / 4)
    return target_cal, protein_g, fat_g, carbs_g

def get_profile(uid):
    return user_profiles.get(str(uid), {})

def set_profile(uid, profile):
    user_profiles[str(uid)] = profile
    save_state()

def delete_profile(uid):
    key = str(uid)
    for store in [user_profiles, user_goals, meals_log, favorites, user_settings, activity_log]:
        store.pop(key, None)
    save_state()

def set_goal(uid, goal):
    user_goals[str(uid)] = goal
    save_state()

def get_goal(uid):
    return user_goals.get(str(uid))

def append_meal(uid, meal_entry):
    key = str(uid)
    entry = {
        "timestamp": datetime.now().isoformat(),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "text": meal_entry,
    }
    meals_log.setdefault(key, [])
    meals_log[key].append(entry)
    meals_log[key] = meals_log[key][-200:]
    save_state()

def append_activity(uid, activity_entry):
    key = str(uid)
    entry = {
        "timestamp": datetime.now().isoformat(),
        "date": datetime.now().strftime("%Y-%m-%d"),
        "text": activity_entry,
    }
    activity_log.setdefault(key, [])
    activity_log[key].append(entry)
    activity_log[key] = activity_log[key][-200:]
    save_state()

def get_today_meals(uid):
    today = datetime.now().strftime("%Y-%m-%d")
    return [m for m in meals_log.get(str(uid), []) if m.get("date") == today]

def get_week_meals(uid):
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    return [m for m in meals_log.get(str(uid), []) if m.get("date") >= week_ago]

def get_month_meals(uid):
    month_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    return [m for m in meals_log.get(str(uid), []) if m.get("date") >= month_ago]

def extract_calories_from_text(text):
    try:
        for line in text.splitlines():
            if "Итого:" in line and "ккал" in line:
                return float(line.split(":")[1].strip().split()[0])
            if "Калории:" in line and "ккал" in line:
                return float(line.split(":")[1].strip().split()[0])
    except Exception:
        pass
    return None

def add_favorite(uid, dish_name, calories):
    key = str(uid)
    favorites.setdefault(key, [])
    favorites[key].append({
        "name": dish_name,
        "calories": calories,
        "added": datetime.now().isoformat(),
    })
    favorites[key] = favorites[key][-50:]
    save_state()

def get_favorites(uid):
    return favorites.get(str(uid), [])

def profile_summary(profile, uid):
    try:
        bmr, tdee = calculate_tdee(profile)
        goal = get_goal(uid)
        target = get_target_calories(profile, goal) if goal else tdee

        macros_text = ""
        if goal:
            _, p_g, f_g, c_g = get_daily_macros(profile, goal)
            macros_text = f"БЖУ в день: Б {p_g} г / Ж {f_g} г / У {c_g} г\n"

        return (
            f"Пол: {profile.get('sex', '—')}\n"
            f"Возраст: {profile.get('age', '—')}\n"
            f"Рост: {profile.get('height', '—')} см\n"
            f"Вес: {profile.get('weight', '—')} кг\n"
            f"Активность: {profile.get('activity', '—')}\n"
            f"Цель: {goal if goal else 'Не установлена'}\n"
            f"BMR: {bmr} ккал\n"
            f"TDEE: {tdee} ккал\n"
            f"Дневная норма: {target} ккал\n"
            f"{macros_text}"
        )
    except Exception:
        return (
            f"Пол: {profile.get('sex', '—')}\n"
            f"Возраст: {profile.get('age', '—')}\n"
            f"Рост: {profile.get('height', '—')} см\n"
            f"Вес: {profile.get('weight', '—')} кг\n"
            f"Активность: {profile.get('activity', '—')}\n"
            f"Цель: {get_goal(uid) if get_goal(uid) else 'Не установлена'}\n"
            f"Профиль заполнен не полностью."
        )

def get_statistics(uid, period="day"):
    profile = get_profile(uid)
    if not profile:
        return "Профиль не найден"
    if period == "day":
        meals = get_today_meals(uid)
        period_name = "за день"
        divider = 1
    elif period == "week":
        meals = get_week_meals(uid)
        period_name = "за неделю"
        divider = 7
    else:
        meals = get_month_meals(uid)
        period_name = "за месяц"
        divider = 30
    if not meals:
        return f"Нет данных {period_name}"
    total_calories = 0
    for meal in meals:
        cal = extract_calories_from_text(meal.get("text", ""))
        if cal is not None:
            total_calories += cal
    goal = get_goal(uid)
    target = get_target_calories(profile, goal)
    avg_per_day = total_calories / divider
    percent = round((total_calories / (target * divider)) * 100, 1) if target > 0 else 0
    return (
        f"Статистика {period_name}\n\n"
        f"Приемов пищи: {len(meals)}\n"
        f"Всего калорий: {total_calories:.0f} ккал\n"
        f"Среднее в день: {avg_per_day:.0f} ккал\n"
        f"% от нормы: {percent}%\n"
    )

def analyze_image_with_logmeal(image_bytes: bytes):
    try:
        files = {"image": ("meal.jpg", image_bytes, "image/jpeg")}
        rec_response = requests.post(
            "https://api.logmeal.com/v2/image/segmentation/complete",
            headers=logmeal_headers(),
            files=files,
            timeout=120,
        )

        if rec_response.status_code == 429:
            retry_after = rec_response.headers.get("RateLimit-Reset") or rec_response.headers.get("retry-after")
            return None, None, None, (
                "Сервис распознавания временно недоступен из-за лимита запросов.\n"
                + (f"Попробуй снова через {retry_after} сек." if retry_after else "Попробуй позже.")
            )

        if rec_response.status_code != 200:
            return None, None, None, f"Ошибка распознавания: {rec_response.status_code}"

        rec_json = safe_json(rec_response)
        image_id = None
        dish_name = None

        if isinstance(rec_json, dict):
            image_id = rec_json.get("imageId") or rec_json.get("image_id") or rec_json.get("id")
            items = extract_list(rec_json)
            if items:
                dish_name = get_name(items[0])
            if not dish_name:
                food_name = rec_json.get("foodName")
                if isinstance(food_name, list) and food_name:
                    dish_name = str(food_name[0])
                elif isinstance(food_name, str) and food_name.strip():
                    dish_name = food_name.strip()

        if not image_id:
            return None, dish_name, None, "Не удалось получить данные по блюду."

        if not dish_name:
            dish_name = "Блюдо не распознано точно"

        lines = [f"Распознанное блюдо: {dish_name}"]
        calories = None
        score = None

        nutri_response = requests.post(
            "https://api.logmeal.com/v2/nutrition/recipe/nutritionalInfo",
            headers=logmeal_headers(),
            json={"imageId": image_id},
            timeout=120,
        )

        if nutri_response.status_code == 429:
            retry_after = nutri_response.headers.get("RateLimit-Reset") or nutri_response.headers.get("retry-after")
            return None, dish_name, None, (
                "Сервис нутриентов временно недоступен из-за лимита запросов.\n"
                + (f"Попробуй снова через {retry_after} сек." if retry_after else "Попробуй позже.")
            )

        if nutri_response.status_code == 200:
            nutri_json = safe_json(nutri_response)
            if isinstance(nutri_json, dict):
                calories, protein, fat, carbs, fiber, sugar, score = extract_nutrients(nutri_json)
                if calories is not None:
                    lines.append("")
                    lines.append("Пищевая ценность на 100 г:")
                    lines.append(f"Калории: {calories} ккал")
                    if protein is not None:
                        lines.append(f"Белки: {protein} г")
                    if fat is not None:
                        lines.append(f"Жиры: {fat} г")
                    if carbs is not None:
                        lines.append(f"Углеводы: {carbs} г")
                    if fiber is not None:
                        lines.append(f"Клетчатка: {fiber} г")
                    if sugar is not None:
                        lines.append(f"Сахар: {sugar} г")
                    if score:
                        lines.append(f"Nutri-Score: {score}")

        if calories is None:
            return None, dish_name, score, "Не удалось получить нутриенты для блюда."

        return calories, dish_name, score, "\n".join(lines)

    except Exception as e:
        logger.exception("Analysis error")
        return None, None, None, f"Ошибка анализа: {e}"

@dp.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    await state.clear()
    profile = get_profile(message.from_user.id)
    if profile:
        await message.answer(
            f"Привет, {message.from_user.first_name}!\n\nТвой профиль:\n\n{profile_summary(profile, message.from_user.id)}",
            reply_markup=main_menu,
        )
    else:
        await message.answer(
            "Привет! Я AI_CalCount_bot PRO.\nСначала создай профиль.",
            reply_markup=main_menu,
        )

@dp.message(Command("manual"))
async def manual_input_command(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(PortionForm.dish_name)
    await message.answer("Введи название блюда:")

@dp.message(Command("profile"))
async def cmd_profile(message: Message, state: FSMContext):
    await state.clear()
    profile = get_profile(message.from_user.id)
    if profile:
        await message.answer(profile_summary(profile, message.from_user.id), reply_markup=profile_menu)
    else:
        await message.answer("Профиля нет. Создай новый.", reply_markup=profile_menu)

@dp.message(Command("goal"))
async def cmd_goal(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(ProfileForm.goal)
    await message.answer("Выбери цель:", reply_markup=goal_menu)

@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    await message.answer(get_statistics(message.from_user.id, "day"), reply_markup=main_menu)

@dp.message(Command("week"))
async def cmd_week_stats(message: Message):
    await message.answer(get_statistics(message.from_user.id, "week"), reply_markup=main_menu)

@dp.message(Command("reset"))
async def cmd_reset(message: Message, state: FSMContext):
    await state.clear()
    delete_profile(message.from_user.id)
    await message.answer("Профиль и данные удалены.", reply_markup=main_menu)

@dp.message(StateFilter(None), F.text == "📊 Профиль")
async def profile_button(message: Message):
    profile = get_profile(message.from_user.id)
    if profile:
        await message.answer(profile_summary(profile, message.from_user.id), reply_markup=profile_menu)
    else:
        await message.answer("У тебя нет профиля. Создай новый.", reply_markup=profile_menu)

@dp.message(StateFilter(None), F.text == "📸 Анализ блюда")
async def analyze_button(message: Message):
    if not get_profile(message.from_user.id):
        await message.answer("Сначала создай профиль.", reply_markup=main_menu)
        return
    await message.answer("Теперь отправь фото блюда.")

@dp.message(StateFilter(None), F.text == "⭐ Избранное")
async def favorites_button(message: Message):
    fav = get_favorites(message.from_user.id)
    if not fav:
        await message.answer("Избранных блюд пока нет.", reply_markup=main_menu)
        return
    text = "Избранные блюда:\n\n"
    for i, item in enumerate(fav[-10:], 1):
        text += f"{i}. {item['name']} — {item['calories']:.0f} ккал\n"
    await message.answer(text, reply_markup=main_menu)

@dp.message(StateFilter(None), F.text == "📜 История")
async def history_button(message: Message):
    items = meals_log.get(str(message.from_user.id), [])
    if not items:
        await message.answer("История пока пустая.", reply_markup=main_menu)
        return
    text = "Последние анализы:\n\n" + "\n\n".join([i.get("text", "") for i in items[-5:]])
    for part in split_text(text):
        await message.answer(part, reply_markup=main_menu)

@dp.message(StateFilter(None), F.text == "📈 Статистика")
async def statistics_button(message: Message):
    if not get_profile(message.from_user.id):
        await message.answer("Сначала создай профиль.", reply_markup=main_menu)
        return
    await message.answer("Выбери период:", reply_markup=period_menu)

@dp.message(StateFilter(None), F.text == "📅 За день")
async def stats_day(message: Message):
    await message.answer(get_statistics(message.from_user.id, "day"), reply_markup=main_menu)

@dp.message(StateFilter(None), F.text == "📊 За неделю")
async def stats_week(message: Message):
    await message.answer(get_statistics(message.from_user.id, "week"), reply_markup=main_menu)

@dp.message(StateFilter(None), F.text == "📈 За месяц")
async def stats_month(message: Message):
    await message.answer(get_statistics(message.from_user.id, "month"), reply_markup=main_menu)

@dp.message(StateFilter(None), F.text == "🏃 Упражнения")
async def exercise_button(message: Message, state: FSMContext):
    if not get_profile(message.from_user.id):
        await message.answer("Сначала создай профиль.", reply_markup=main_menu)
        return
    await state.set_state(ExerciseForm.exercise)
    await message.answer("Выбери упражнение:", reply_markup=exercise_menu)

@dp.message(StateFilter(None), F.text == "❓ Помощь")
async def help_button(message: Message):
    await message.answer(
        "Профиль, анализ блюд, избранное, история, статистика, упражнения.\n"
        "Команды: /manual, /profile, /goal, /stats, /week, /reset",
        reply_markup=main_menu,
    )

@dp.message(StateFilter(None), F.text == "➕ Создать профиль")
async def create_profile_button(message: Message, state: FSMContext):
    await state.set_state(ProfileForm.sex)
    await message.answer("Выбери пол:", reply_markup=gender_menu)

@dp.message(StateFilter(None), F.text == "✏️ Редактировать профиль")
async def edit_profile_button(message: Message, state: FSMContext):
    if not get_profile(message.from_user.id):
        await message.answer("Профиля нет.", reply_markup=profile_menu)
        return
    await state.set_state(ProfileForm.sex)
    await message.answer("Выбери пол:", reply_markup=gender_menu)

@dp.message(StateFilter(None), F.text == "🗑️ Удалить профиль")
async def delete_profile_start(message: Message, state: FSMContext):
    if not get_profile(message.from_user.id):
        await message.answer("Профиля нет.", reply_markup=profile_menu)
        return
    await state.set_state(DeleteProfileForm.confirm)
    await message.answer("Удалить профиль и данные?", reply_markup=confirm_delete_menu)

@dp.message(StateFilter(None), F.text == "◀️ Назад в меню")
async def back_to_main_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню:", reply_markup=main_menu)

@dp.message(StateFilter(None), F.text == "◀️ Назад")
async def back_button(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню:", reply_markup=main_menu)

@dp.message(StateFilter(ProfileForm.sex), F.text.in_(["Мужской", "Женский"]))
async def profile_sex(message: Message, state: FSMContext):
    await state.update_data(sex=message.text)
    await state.set_state(ProfileForm.age)
    await message.answer("Введи возраст (10-100):", reply_markup=ReplyKeyboardRemove())

@dp.message(StateFilter(ProfileForm.age))
async def profile_age(message: Message, state: FSMContext):
    try:
        age = int(message.text)
        if not (10 <= age <= 100):
            raise ValueError
    except Exception:
        await message.answer("Введи возраст числом от 10 до 100.")
        return
    await state.update_data(age=age)
    await state.set_state(ProfileForm.height)
    await message.answer("Введи рост в см (100-250):")

@dp.message(StateFilter(ProfileForm.height))
async def profile_height(message: Message, state: FSMContext):
    try:
        height = float(message.text.replace(",", "."))
        if not (100 <= height <= 250):
            raise ValueError
    except Exception:
        await message.answer("Введи рост числом, например 175.")
        return
    await state.update_data(height=height)
    await state.set_state(ProfileForm.weight)
    await message.answer("Введи вес в кг (30-300):")

@dp.message(StateFilter(ProfileForm.weight))
async def profile_weight(message: Message, state: FSMContext):
    try:
        weight = float(message.text.replace(",", "."))
        if not (30 <= weight <= 300):
            raise ValueError
    except Exception:
        await message.answer("Введи вес числом, например 72.5.")
        return
    await state.update_data(weight=weight)
    await state.set_state(ProfileForm.activity)
    await message.answer("Выбери уровень активности:", reply_markup=activity_menu)

@dp.message(StateFilter(ProfileForm.activity), F.text.in_(list(activity_map.keys())))
async def profile_activity(message: Message, state: FSMContext):
    await state.update_data(activity=message.text)
    await state.set_state(ProfileForm.goal)
    await message.answer("Выбери цель:", reply_markup=goal_menu)

@dp.message(StateFilter(ProfileForm.goal), F.text.in_(["Похудение", "Поддержание", "Набор"]))
async def profile_goal(message: Message, state: FSMContext):
    data = await state.get_data()

    required_keys = ["sex", "age", "height", "weight", "activity"]
    if any(data.get(k) is None for k in required_keys):
        await message.answer("Профиль заполнен не полностью. Начни создание профиля заново.")
        await state.clear()
        return

    set_profile(message.from_user.id, data)
    set_goal(message.from_user.id, message.text)

    await state.clear()
    await message.answer(
        f"Профиль сохранен.\n\n{profile_summary(data, message.from_user.id)}",
        reply_markup=main_menu,
    )

@dp.message(StateFilter(DeleteProfileForm.confirm), F.text == "✅ Да, удалить")
async def confirm_delete_profile(message: Message, state: FSMContext):
    delete_profile(message.from_user.id)
    await state.clear()
    await message.answer("Профиль удален.", reply_markup=main_menu)

@dp.message(StateFilter(DeleteProfileForm.confirm), F.text == "❌ Отмена")
async def cancel_delete_profile(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Удаление отменено.", reply_markup=main_menu)

@dp.message(StateFilter(ExerciseForm.exercise), F.text == "◀️ Назад")
async def exercise_back(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню:", reply_markup=main_menu)

@dp.message(StateFilter(ExerciseForm.exercise), F.text.in_(list(exercise_map.keys())))
async def select_exercise(message: Message, state: FSMContext):
    await state.update_data(exercise=message.text)
    await state.set_state(ExerciseForm.duration)
    await message.answer(f"Сколько минут длилась тренировка '{message.text}'?")

@dp.message(StateFilter(ExerciseForm.duration))
async def exercise_duration(message: Message, state: FSMContext):
    try:
        duration = int(message.text)
        if duration <= 0:
            raise ValueError
    except Exception:
        await message.answer("Введи положительное число минут.")
        return
    data = await state.get_data()
    exercise = data.get("exercise")
    profile = get_profile(message.from_user.id)
    weight = float(profile.get("weight"))
    calories_burned = round((exercise_map[exercise] * weight * duration) / 60)
    result_text = (
        f"Упражнение: {exercise}\n"
        f"Время: {duration} мин\n"
        f"Сожжено: {calories_burned} ккал"
    )
    append_activity(message.from_user.id, result_text)
    await state.clear()
    await message.answer(result_text, reply_markup=main_menu)

@dp.message(StateFilter(None), F.photo)
async def photo_handler(message: Message, state: FSMContext):
    profile = get_profile(message.from_user.id)
    if not profile:
        await message.answer("Сначала создай профиль.", reply_markup=main_menu)
        return

    await message.answer("Анализирую блюдо...")

    try:
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        file_bytes = await bot.download_file(file.file_path)
        image_data = file_bytes.read()

        calories_100, dish_name, score, base_text = analyze_image_with_logmeal(image_data)

        if calories_100 is None:
            await message.answer(
                base_text or "Не удалось распознать блюдо. Попробуй другое фото или /manual.",
                reply_markup=main_menu,
            )
            return

        await state.update_data(
            dish_name=dish_name,
            calories_per_100=calories_100,
            base_text=base_text,
            nutri_score=score,
        )
        await state.set_state(PortionForm.portion_grams)

        await message.answer(
            base_text + "\n\nНапиши, сколько примерно грамм было на тарелке (число).",
            reply_markup=ReplyKeyboardRemove()
        )

    except Exception as e:
        logger.exception("Photo handler error")
        await message.answer(f"Ошибка обработки фото: {e}", reply_markup=main_menu)

@dp.message(StateFilter(PortionForm.dish_name))
async def manual_dish_name(message: Message, state: FSMContext):
    await state.update_data(dish_name=message.text)
    await state.set_state(PortionForm.calories_per_100)
    await message.answer("Введи калории на 100 г:")

@dp.message(StateFilter(PortionForm.calories_per_100))
async def manual_calories_per_100(message: Message, state: FSMContext):
    try:
        calories_per_100 = float(message.text.replace(",", "."))
        if calories_per_100 <= 0:
            raise ValueError
    except Exception:
        await message.answer("Введи положительное число.")
        return
    await state.update_data(calories_per_100=calories_per_100)
    await state.set_state(PortionForm.portion_grams)
    await message.answer("Введи вес порции в граммах:")

@dp.message(StateFilter(PortionForm.portion_grams))
async def portion_grams_handler(message: Message, state: FSMContext):
    try:
        portion_grams = float(message.text.replace(",", "."))
        if portion_grams <= 0:
            raise ValueError
    except Exception:
        await message.answer("Введи положительное число грамм.")
        return

    data = await state.get_data()
    dish_name = data.get("dish_name", "Блюдо")
    calories_per_100 = float(data.get("calories_per_100", 0))
    base_text = data.get("base_text")
    nutri_score = data.get("nutri_score")

    total_calories = (calories_per_100 * portion_grams) / 100

    if base_text:
        result_text = (
            base_text
            + f"\n\nВес порции: {portion_grams:.0f} г"
            + f"\nИтого: {total_calories:.0f} ккал"
        )
    else:
        result_text = (
            f"Ручной ввод\n\n"
            f"Блюдо: {dish_name}\n"
            f"Калории на 100 г: {calories_per_100} ккал\n"
            f"Порция: {portion_grams:.0f} г\n"
            f"Итого: {total_calories:.0f} ккал"
        )

    if nutri_score:
        result_text += f"\nNutri-Score (для порции): {nutri_score}"

    profile = get_profile(message.from_user.id)
    if profile:
        goal = get_goal(message.from_user.id)
        target = get_target_calories(profile, goal)
        if target:
            percent = round((total_calories / target) * 100, 1)
            result_text += f"\n\nЭто {percent}% от твоей нормы ({target} ккал)."

    append_meal(message.from_user.id, result_text)

    if dish_name:
        add_favorite(message.from_user.id, dish_name, total_calories)

    await state.clear()

    for part in split_text(result_text):
        await message.answer(part, reply_markup=main_menu)

@dp.message()
async def other_messages(message: Message):
    await message.answer("Используй меню ниже.", reply_markup=main_menu)

async def set_bot_commands():
    await bot.set_my_commands([
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="profile", description="Профиль"),
        BotCommand(command="goal", description="Цель"),
        BotCommand(command="stats", description="Статистика за день"),
        BotCommand(command="week", description="Статистика за неделю"),
        BotCommand(command="manual", description="Ручной ввод"),
        BotCommand(command="reset", description="Сброс профиля"),
    ])

async def main():
    load_state()
    await set_bot_commands()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
