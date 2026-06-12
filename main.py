import asyncio
import json
import os
from pathlib import Path
from datetime import datetime

import requests
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

API_TOKEN = os.environ.get("TG_TOKEN", "").strip()
LOGMEAL_TOKEN = os.environ.get("LOGMEAL_TOKEN", "").strip()

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

GOALS_FILE = DATA_DIR / "user_goals.json"
PROFILE_FILE = DATA_DIR / "user_profiles.json"
MEALS_FILE = DATA_DIR / "meals_log.json"

user_goals = {}
user_profiles = {}
meals_log = {}

activity_map = {
    "Сидячий образ жизни": 1.2,
    "Легкая активность": 1.375,
    "Средняя активность": 1.55,
    "Высокая активность": 1.725,
    "Очень высокая активность": 1.9,
}

menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Профиль"), KeyboardButton(text="Похудение"), KeyboardButton(text="Поддержание"), KeyboardButton(text="Набор")],
        [KeyboardButton(text="Анализ блюда"), KeyboardButton(text="История"), KeyboardButton(text="Суточный итог"), KeyboardButton(text="Помощь")],
    ],
    resize_keyboard=True,
    is_persistent=True,
)

profile_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Мужской"), KeyboardButton(text="Женский")],
    ],
    resize_keyboard=True,
    is_persistent=True,
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
    is_persistent=True,
)

goal_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Похудение"), KeyboardButton(text="Поддержание"), KeyboardButton(text="Набор")],
    ],
    resize_keyboard=True,
    is_persistent=True,
)

class ProfileForm(StatesGroup):
    sex = State()
    age = State()
    height = State()
    weight = State()
    activity = State()

class PortionForm(StatesGroup):
    portion_grams = State()
    dish_name = State()
    calories_per_100 = State()

def split_text(text, limit=4000):
    return [text[i:i + limit] for i in range(0, len(text), limit)]

def load_json_file(path, default):
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    return default

def save_json_file(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_state():
    global user_goals, user_profiles, meals_log
    user_goals = load_json_file(GOALS_FILE, {})
    user_profiles = load_json_file(PROFILE_FILE, {})
    meals_log = load_json_file(MEALS_FILE, {})

def save_state():
    save_json_file(GOALS_FILE, user_goals)
    save_json_file(PROFILE_FILE, user_profiles)
    save_json_file(MEALS_FILE, meals_log)

def logmeal_headers():
    return {
        "Authorization": f"Bearer {LOGMEAL_TOKEN}",
        "accept": "application/json",
    }

def safe_json(resp):
    try:
        return resp.json()
    except Exception:
        return resp.text

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
    age = float(profile.get("age"))
    height = float(profile.get("height"))
    weight = float(profile.get("weight"))
    activity = profile.get("activity")

    if sex == "Мужской":
        bmr = 10 * weight + 6.25 * height - 5 * age + 5
    else:
        bmr = 10 * weight + 6.25 * height - 5 * age - 161

    factor = activity_map.get(activity, 1.2)
    tdee = bmr * factor
    return round(bmr), round(tdee)

def get_profile(uid):
    return user_profiles.get(str(uid), {})

def set_profile(uid, profile):
    user_profiles[str(uid)] = profile
    save_state()

def delete_profile(uid):
    key = str(uid)
    if key in user_profiles:
        del user_profiles[key]
    if key in user_goals:
        del user_goals[key]
    save_state()

def set_goal(uid, goal):
    user_goals[str(uid)] = goal
    save_state()

def get_goal(uid):
    return user_goals.get(str(uid))

def append_meal(uid, meal_entry):
    """Сохраняет запись о приеме пищи с временем"""
    key = str(uid)
    timestamp = datetime.now().isoformat()
    entry = {
        "timestamp": timestamp,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "text": meal_entry
    }
    meals_log.setdefault(key, [])
    meals_log[key].append(entry)
    meals_log[key] = meals_log[key][-100:]
    save_state()

def get_today_meals(uid):
    """Получает все приемы пищи за сегодня"""
    key = str(uid)
    today = datetime.now().strftime("%Y-%m-%d")
    meals = meals_log.get(key, [])
    return [m for m in meals if m.get("date") == today]

def extract_calories_from_text(text):
    """Пытается извлечь калории из текста анализа"""
    try:
        lines = text.split("\n")
        for line in lines:
            if "Калории:" in line and "ккал" in line:
                parts = line.split(":")
                if len(parts) > 1:
                    cal_str = parts[1].strip().split()[0]
                    return float(cal_str)
    except Exception:
        pass
    return None

def analyze_image_with_logmeal(image_bytes: bytes):
    try:
        files = {"image": ("meal.jpg", image_bytes, "image/jpeg")}
        rec_url = "https://api.logmeal.com/v2/image/segmentation/complete"
        rec_response = requests.post(rec_url, headers=logmeal_headers(), files=files, timeout=120)

        if rec_response.status_code != 200:
            return None, None, f"Ошибка распознавания: {rec_response.status_code}"

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

        # Если блюдо не распознано
        if not dish_name:
            return None, None, "⚠️ Не удалось распознать блюдо. Попробуй фото получше или используй /manual для ручного ввода."

        lines = [f"🍽 Распознанное блюдо: {dish_name}"]
        calories = None

        if image_id:
            nutri_url = "https://api.logmeal.com/v2/nutrition/recipe/nutritionalInfo"
            nutri_response = requests.post(
                nutri_url,
                headers=logmeal_headers(),
                json={"imageId": image_id},
                timeout=120
            )

            if nutri_response.status_code == 200:
                nutri_json = safe_json(nutri_response)

                if isinstance(nutri_json, dict):
                    calories, protein, fat, carbs, fiber, sugar, score = extract_nutrients(nutri_json)

                    lines.append("")
                    lines.append("📊 Пищевая ценность на 100 г:")

                    if calories is not None:
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
                else:
                    lines.append("")
                    lines.append("⚠️ Не удалось разобрать данные о питательности.")
            else:
                lines.append("")
                lines.append(f"⚠️ Не удалось получить нутриенты: {nutri_response.status_code}")
        else:
            lines.append("")
            lines.append("⚠️ Не удалось получить подробные нутриенты. Используй /manual для ручного ввода.")

        return calories, dish_name, "\n".join(lines)

    except Exception as e:
        return None, None, f"❌ Ошибка анализа: {e}"

def profile_summary(profile):
    bmr, tdee = calculate_tdee(profile)
    return (
        f"👤 Пол: {profile['sex']}\n"
        f"🎂 Возраст: {profile['age']}\n"
        f"📏 Рост: {profile['height']} см\n"
        f"⚖️ Вес: {profile['weight']} кг\n"
        f"🏃 Активность: {profile['activity']}\n"
        f"🔥 BMR: {bmr} ккал\n"
        f"⚡ TDEE: {tdee} ккал\n"
    )

@dp.message(CommandStart())
async def start_handler(message: Message):
    profile = get_profile(message.from_user.id)
    if profile:
        await message.answer(
            "Привет! Профиль уже сохранён.\n\n" + profile_summary(profile) +
            "\nВыбери цель или отправь фото блюда.\n\n"
            "Команды: /profile, /reset_profile, /manual",
            reply_markup=menu
        )
    else:
        await message.answer(
            "Привет! Я AI_CalCount_bot.\n"
            "Сначала нажми «Профиль» и задай параметры тела.",
            reply_markup=menu
        )

@dp.message(Command("profile"))
async def profile_command(message: Message, state: FSMContext):
    await state.set_state(ProfileForm.sex)
    await message.answer("Выбери пол:", reply_markup=profile_menu)

@dp.message(F.text == "Профиль")
async def profile_start(message: Message, state: FSMContext):
    await state.set_state(ProfileForm.sex)
    await message.answer("Выбери пол:", reply_markup=profile_menu)

@dp.message(ProfileForm.sex)
async def profile_sex(message: Message, state: FSMContext):
    if message.text not in ["Мужской", "Женский"]:
        await message.answer("Выбери пол кнопкой.")
        return
    await state.update_data(sex=message.text)
    await state.set_state(ProfileForm.age)
    await message.answer("Введи возраст числом:")

@dp.message(ProfileForm.age)
async def profile_age(message: Message, state: FSMContext):
    try:
        age = int(message.text)
        if age < 10 or age > 100:
            raise ValueError
    except Exception:
        await message.answer("Введи возраст числом от 10 до 100.")
        return
    await state.update_data(age=age)
    await state.set_state(ProfileForm.height)
    await message.answer("Введи рост в сантиметрах:")

@dp.message(ProfileForm.height)
async def profile_height(message: Message, state: FSMContext):
    try:
        height = float(message.text.replace(",", "."))
        if height < 100 or height > 250:
            raise ValueError
    except Exception:
        await message.answer("Введи рост числом, например 175.")
        return
    await state.update_data(height=height)
    await state.set_state(ProfileForm.weight)
    await message.answer("Введи вес в килограммах:")

@dp.message(ProfileForm.weight)
async def profile_weight(message: Message, state: FSMContext):
    try:
        weight = float(message.text.replace(",", "."))
        if weight < 30 or weight > 300:
            raise ValueError
    except Exception:
        await message.answer("Введи вес числом, например 72.5.")
        return
    await state.update_data(weight=weight)
    await state.set_state(ProfileForm.activity)
    await message.answer("Выбери уровень активности:", reply_markup=activity_menu)

@dp.message(ProfileForm.activity)
async def profile_activity(message: Message, state: FSMContext):
    if message.text not in activity_map:
        await message.answer("Выбери активность кнопкой.")
        return
    await state.update_data(activity=message.text)
    data = await state.get_data()
    set_profile(message.from_user.id, data)
    await state.clear()
    await message.answer(
        "✅ Профиль сохранён.\n\n" + profile_summary(data) +
        "\nТеперь можно выбрать цель и отправлять фото еды.",
        reply_markup=menu
    )

@dp.message(Command("reset_profile"))
async def reset_profile_handler(message: Message):
    delete_profile(message.from_user.id)
    await message.answer(
        "🗑️ Профиль и все данные удалены.\n\n"
        "Нажми «Профиль» для создания нового профиля.",
        reply_markup=menu
    )

@dp.message(F.text.in_(["Похудение", "Поддержание", "Набор"]))
async def goal_handler(message: Message):
    set_goal(message.from_user.id, message.text)
    profile = get_profile(message.from_user.id)
    if profile:
        _, tdee = calculate_tdee(profile)
        if message.text == "Похудение":
            target = round(tdee - 400)
        elif message.text == "Поддержание":
            target = round(tdee)
        else:
            target = round(tdee + 300)
        await message.answer(
            f"🎯 Цель установлена: {message.text}\n"
            f"📋 Твоя дневная норма: {target} ккал.\n"
            f"Теперь отправь фото блюда.",
            reply_markup=menu
        )
    else:
        await message.answer(
            f"🎯 Цель установлена: {message.text}\n"
            f"⚠️ Сначала заполни профиль, чтобы я мог посчитать норму по телу.",
            reply_markup=menu
        )

@dp.message(F.text == "История")
async def history_handler(message: Message):
    items = meals_log.get(str(message.from_user.id), [])
    if not items:
        await message.answer("📜 История пока пустая.", reply_markup=menu)
        return
    text = "📜 Последние анализы:\n\n" + "\n\n".join([item.get("text", "") for item in items[-5:]])
    for part in split_text(text):
        await message.answer(part, reply_markup=menu)

@dp.message(F.text == "Суточный итог")
async def daily_summary_handler(message: Message):
    profile = get_profile(message.from_user.id)
    today_meals = get_today_meals(message.from_user.id)
    
    if not profile:
        await message.answer("⚠️ Сначала заполни профиль.", reply_markup=menu)
        return
    
    if not today_meals:
        await message.answer("📊 Еще не было приемов пищи за сегодня.", reply_markup=menu)
        return
    
    _, tdee = calculate_tdee(profile)
    goal = get_goal(message.from_user.id)
    
    if goal == "Похудение":
        target = round(tdee - 400)
    elif goal == "Набор":
        target = round(tdee + 300)
    else:
        target = round(tdee)
    
    total_calories = 0
    meal_list = []
    
    for i, meal in enumerate(today_meals, 1):
        meal_text = meal.get("text", "")
        calories = extract_calories_from_text(meal_text)
        
        if calories:
            total_calories += calories
            first_line = meal_text.split("\n")[0]
            meal_list.append(f"{i}. {first_line} — {calories:.0f} ккал")
        else:
            meal_list.append(f"{i}. {meal_text.split(chr(10))[0]}")
    
    remaining = max(0, target - total_calories)
    percent = round((total_calories / target) * 100, 1) if target > 0 else 0
    
    summary = (
        f"📊 СУТОЧНЫЙ ИТОГ за {datetime.now().strftime('%d.%m.%Y')}\n\n"
        f"{'='.join([''])}=\n"
        f"Приемы пищи:\n" + "\n".join(meal_list) + f"\n"
        f"{'='.join([''])}=\n\n"
        f"🔢 Всего калорий: {total_calories:.0f} ккал\n"
        f"🎯 Дневная норма: {target} ккал\n"
        f"📈 Процент от нормы: {percent}%\n"
        f"⬜ Осталось: {remaining:.0f} ккал"
    )
    
    await message.answer(summary, reply_markup=menu)

@dp.message(F.text == "Помощь")
async def help_handler(message: Message):
    await message.answer(
        "📖 Схема работы:\n"
        "1) Нажми «Профиль» и введи данные тела.\n"
        "2) Выбери цель.\n"
        "3) Отправь фото блюда.\n"
        "4) Получишь калории и сравнение с нормой.\n\n"
        "📋 Команды:\n"
        "/profile — заполнить профиль заново\n"
        "/reset_profile — удалить профиль\n"
        "/manual — ручной ввод порции\n\n"
        "📊 История и Суточный итог — аналитика приемов пищи",
        reply_markup=menu
    )

@dp.message(F.text == "Анализ блюда")
async def analyze_hint(message: Message):
    await message.answer("📸 Теперь отправь мне фото блюда одним сообщением.", reply_markup=menu)

@dp.message(Command("manual"))
async def manual_input_command(message: Message, state: FSMContext):
    await state.set_state(PortionForm.dish_name)
    await message.answer("📝 Введи название блюда:")

@dp.message(PortionForm.dish_name)
async def manual_dish_name(message: Message, state: FSMContext):
    await state.update_data(dish_name=message.text)
    await state.set_state(PortionForm.calories_per_100)
    await message.answer("📊 Введи калории на 100 г:")

@dp.message(PortionForm.calories_per_100)
async def manual_calories_per_100(message: Message, state: FSMContext):
    try:
        calories_per_100 = float(message.text.replace(",", "."))
    except Exception:
        await message.answer("❌ Введи число, например 150 или 150.5")
        return
    
    await state.update_data(calories_per_100=calories_per_100)
    await state.set_state(PortionForm.portion_grams)
    await message.answer("⚖️ Введи вес порции в граммах:")

@dp.message(PortionForm.portion_grams)
async def manual_portion_grams(message: Message, state: FSMContext):
    try:
        portion_grams = float(message.text.replace(",", "."))
    except Exception:
        await message.answer("❌ Введи число, например 200 или 250.5")
        return
    
    if portion_grams <= 0:
        await message.answer("❌ Вес должен быть больше 0.")
        return
    
    data = await state.get_data()
    dish_name = data.get("dish_name")
    calories_per_100 = data.get("calories_per_100")
    
    total_calories = (calories_per_100 * portion_grams) / 100
    
    result_text = (
        f"🍽️ Ручной ввод\n\n"
        f"Блюдо: {dish_name}\n"
        f"Калории на 100 г: {calories_per_100} ккал\n"
        f"Вес порции: {portion_grams} г\n"
        f"➡️ Итого: {total_calories:.0f} ккал"
    )
    
    profile = get_profile(message.from_user.id)
    if profile:
        _, tdee = calculate_tdee(profile)
        goal = get_goal(message.from_user.id)
        
        if goal == "Похудение":
            target = round(tdee - 400)
        elif goal == "Набор":
            target = round(tdee + 300)
        else:
            target = round(tdee)
        
        percent = round((total_calories / target) * 100, 1)
        result_text += f"\n\nЭто примерно {percent}% от твоей дневной нормы ({target} ккал)."
    
    append_meal(message.from_user.id, result_text)
    await state.clear()
    
    await message.answer(result_text, reply_markup=menu)

@dp.message(F.photo)
async def photo_handler(message: Message):
    await message.answer("⏳ Фото получил. Сейчас анализирую блюдо...")

    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    file_bytes = await bot.download_file(file.file_path)
    image_data = file_bytes.read()

    calories, dish_name, result_text = analyze_image_with_logmeal(image_data)

    profile = get_profile(message.from_user.id)
    if profile and calories is not None:
        _, tdee = calculate_tdee(profile)
        goal = get_goal(message.from_user.id)

        if goal == "Похудение":
            target = round(tdee - 400)
        elif goal == "Набор":
            target = round(tdee + 300)
        else:
            target = round(tdee)

        percent = round((float(calories) / target) * 100, 1)
        result_text += f"\n\nЭто примерно {percent}% от твоей дневной нормы ({target} ккал)."

    append_meal(message.from_user.id, result_text)

    for part in split_text(result_text):
        await message.answer(part, reply_markup=menu)

@dp.message()
async def other_messages(message: Message):
    await message.answer(
        "Выбери «Профиль», затем цель, затем отправь фото блюда.\n\n"
        "Или используй /manual для ручного ввода.",
        reply_markup=menu
    )

async def main():
    load_state()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
