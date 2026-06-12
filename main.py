import asyncio
import json
import os
from pathlib import Path

import requests
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
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

GOAL_CALORIES = {
    "Похудение": 1600,
    "Поддержание": 2200,
    "Набор": 2800,
}

user_goals = {}
user_profiles = {}
meals_log = {}

menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Похудение"), KeyboardButton(text="Поддержание"), KeyboardButton(text="Набор")],
        [KeyboardButton(text="Анализ блюда"), KeyboardButton(text="История"), KeyboardButton(text="Помощь")],
    ],
    resize_keyboard=True,
    is_persistent=True,
)

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
    return "Неизвестное блюдо"

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

def analyze_image_with_logmeal(image_bytes: bytes):
    try:
        files = {"image": ("meal.jpg", image_bytes, "image/jpeg")}
        rec_url = "https://api.logmeal.com/v2/image/segmentation/complete"
        rec_response = requests.post(rec_url, headers=logmeal_headers(), files=files, timeout=120)

        if rec_response.status_code != 200:
            return None, f"Ошибка распознавания: {rec_response.status_code}\n{rec_response.text}"

        rec_json = safe_json(rec_response)
        image_id = None
        dish_name = "Неизвестное блюдо"

        if isinstance(rec_json, dict):
            image_id = rec_json.get("imageId") or rec_json.get("image_id") or rec_json.get("id")

            items = extract_list(rec_json)
            if items:
                dish_name = get_name(items[0])

            food_name = rec_json.get("foodName")
            if isinstance(food_name, list) and food_name:
                dish_name = str(food_name[0])
            elif isinstance(food_name, str) and food_name.strip():
                dish_name = food_name.strip()

        lines = [f"Распознанное блюдо: {dish_name}"]
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
                    lines.append("Пищевая ценность на 100 г:")

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
                    lines.append("Не удалось разобрать данные о питательности.")
            else:
                lines.append("")
                lines.append(f"Не удалось получить нутриенты: {nutri_response.status_code}")

        lines.append("")
        lines.append("Выбери цель кнопкой снизу, и я буду сравнивать блюда с твоей нормой.")
        return calories, "\n".join(lines)

    except Exception as e:
        return None, f"Ошибка анализа: {e}"

def get_goal(uid):
    return user_goals.get(str(uid))

def set_goal(uid, goal):
    user_goals[str(uid)] = goal
    save_state()

def append_meal(uid, meal_text):
    key = str(uid)
    meals_log.setdefault(key, [])
    meals_log[key].append(meal_text)
    meals_log[key] = meals_log[key][-20:]
    save_state()

def get_profile(uid):
    return user_profiles.get(str(uid), {})

def set_profile(uid, profile):
    user_profiles[str(uid)] = profile
    save_state()

@dp.message(CommandStart())
async def start_handler(message: Message):
    await message.answer(
        "Привет! Я AI_CalCount_bot.\n"
        "Сначала выбери цель: Похудение, Поддержание или Набор.",
        reply_markup=menu
    )

@dp.message(F.text.in_(["Похудение", "Поддержание", "Набор"]))
async def goal_handler(message: Message):
    set_goal(message.from_user.id, message.text)
    daily = GOAL_CALORIES[message.text]
    await message.answer(
        f"Цель установлена: {message.text}\n"
        f"Дневная норма: {daily} ккал.\n"
        f"Теперь отправь фото блюда.",
        reply_markup=menu
    )

@dp.message(F.text == "Помощь")
async def help_handler(message: Message):
    await message.answer(
        "Команды и кнопки:\n"
        "• Похудение / Поддержание / Набор — цель.\n"
        "• Анализ блюда — подсказка.\n"
        "• История — последние анализы.\n\n"
        "После выбора цели отправь фото еды.",
        reply_markup=menu
    )

@dp.message(F.text == "История")
async def history_handler(message: Message):
    items = meals_log.get(str(message.from_user.id), [])
    if not items:
        await message.answer("История пока пустая.", reply_markup=menu)
        return
    text = "Последние анализы:\n\n" + "\n\n".join(items[-5:])
    for part in split_text(text):
        await message.answer(part, reply_markup=menu)

@dp.message(F.text == "Анализ блюда")
async def analyze_hint(message: Message):
    await message.answer("Теперь отправь мне фото блюда одним сообщением.", reply_markup=menu)

@dp.message(F.photo)
async def photo_handler(message: Message):
    await message.answer("Фото получил. Сейчас анализирую блюдо...")

    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    file_bytes = await bot.download_file(file.file_path)
    image_data = file_bytes.read()

    calories, result_text = analyze_image_with_logmeal(image_data)

    goal = get_goal(message.from_user.id)
    if goal and calories is not None:
        daily = GOAL_CALORIES.get(goal)
        if daily:
            percent = round((float(calories) / daily) * 100, 1)
            result_text += f"\n\nЭто примерно {percent}% от дневной нормы для цели «{goal}» ({daily} ккал)."

    append_meal(message.from_user.id, result_text)

    for part in split_text(result_text):
        await message.answer(part, reply_markup=menu)

@dp.message()
async def other_messages(message: Message):
    await message.answer(
        "Выбери цель или отправь фото блюда.",
        reply_markup=menu
    )

async def main():
    load_state()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
