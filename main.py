import asyncio
import json
import os
from pathlib import Path

import requests
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
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
        [KeyboardButton(text="Анализ блюда"), KeyboardButton(text="История"), KeyboardButton(text="Помощь")],
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

def load_state():
    global user_goals, user_profiles, meals_log
    user_goals = load_json_file(GOALS_FILE, {})
    user_profiles = load_json_file(PROFILE_FILE, {})
    meals_log = load_json_file(MEALS_FILE, {})

def save_state():
    save_json_file(GOALS_FILE, user_goals)
    save_json_file(PROFILE_FILE, user_profiles)
    save_json_file(MEALS_FILE, meals_log)

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

def set_goal(uid, goal):
    user_goals[str(uid)] = goal
    save_state()

def get_goal(uid):
    return user_goals.get(str(uid))

def append_meal(uid, meal_text):
    key = str(uid)
    meals_log.setdefault(key, [])
    meals_log[key].append(meal_text)
    meals_log[key] = meals_log[key][-20:]
    save_state()

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

        return calories, "\n".join(lines)

    except Exception as e:
        return None, f"Ошибка анализа: {e}"

def profile_summary(profile):
    bmr, tdee = calculate_tdee(profile)
    return (
        f"Пол: {profile['sex']}\n"
        f"Возраст: {profile['age']}\n"
        f"Рост: {profile['height']} см\n"
        f"Вес: {profile['weight']} кг\n"
        f"Активность: {profile['activity']}\n"
        f"BMR: {bmr} ккал\n"
        f"TDEE: {tdee} ккал\n"
    )

@dp.message(CommandStart())
async def start_handler(message: Message):
    profile = get_profile(message.from_user.id)
    if profile:
        await message.answer(
            "Привет! Профиль уже сохранён.\n\n" + profile_summary(profile) +
            "\nВыбери цель или отправь фото блюда.",
            reply_markup=menu
        )
    else:
        await message.answer(
            "Привет! Я AI_CalCount_bot.\n"
            "Сначала нажми «Профиль» и задай параметры тела.",
            reply_markup=menu
        )

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
        "Профиль сохранён.\n\n" + profile_summary(data) +
        "\nТеперь можно выбрать цель и отправлять фото еды.",
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
            f"Цель установлена: {message.text}\n"
            f"Твоя дневная норма: {target} ккал.\n"
            f"Теперь отправь фото блюда.",
            reply_markup=menu
        )
    else:
        await message.answer(
            f"Цель установлена: {message.text}\n"
            f"Сначала заполни профиль, чтобы я мог посчитать норму по телу.",
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

@dp.message(F.text == "Помощь")
async def help_handler(message: Message):
    await message.answer(
        "Схема работы:\n"
        "1) Нажми «Профиль» и введи данные тела.\n"
        "2) Выбери цель.\n"
        "3) Отправь фото блюда.\n"
        "4) Получишь калории и сравнение с нормой.\n\n"
        "Команда «История» покажет последние анализы.",
        reply_markup=menu
    )

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
        "Выбери «Профиль», затем цель, затем отправь фото блюда.",
        reply_markup=menu
    )

async def main():
    load_state()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
