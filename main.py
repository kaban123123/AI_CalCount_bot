import asyncio
import json
import os
from pathlib import Path
from datetime import datetime
import logging

import requests
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, BotCommand

# ==================== ЛОГИРОВАНИЕ ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==================== ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ====================
API_TOKEN = os.environ.get("TG_TOKEN", "").strip()
LOGMEAL_TOKEN = os.environ.get("LOGMEAL_TOKEN", "").strip()

if not API_TOKEN:
    logger.error("❌ TG_TOKEN не установлен!")
    exit(1)

if not LOGMEAL_TOKEN:
    logger.error("❌ LOGMEAL_TOKEN не установлен!")
    exit(1)

logger.info(f"✅ TG_TOKEN present: {bool(API_TOKEN)}")
logger.info(f"✅ LOGMEAL_TOKEN present: {bool(LOGMEAL_TOKEN)}")

# ==================== ИНИЦИАЛИЗАЦИЯ БОТА ====================
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# ==================== ПУТИ И ФАЙЛЫ ====================
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

GOALS_FILE = DATA_DIR / "user_goals.json"
PROFILE_FILE = DATA_DIR / "user_profiles.json"
MEALS_FILE = DATA_DIR / "meals_log.json"

# ==================== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ====================
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

# ==================== КЛАВИАТУРЫ ====================

# Главное меню
main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📊 Профиль")],
        [KeyboardButton(text="📸 Анализ блюда")],
        [KeyboardButton(text="📜 История")],
        [KeyboardButton(text="📈 Суточный итог")],
        [KeyboardButton(text="❓ Помощь")],
    ],
    resize_keyboard=True,
    is_persistent=True,
)

# Меню профиля
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

# Выбор пола
gender_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Мужской"), KeyboardButton(text="Женский")],
    ],
    resize_keyboard=True,
    is_persistent=True,
)

# Выбор активности
activity_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Сидячий образ жизни")],
        [KeyboardButton(text="Легкая активность")],
        [KeyboardButton(text="Средняя активность")],
        [KeyboardButton(text="Высокая ��ктивность")],
        [KeyboardButton(text="Очень высокая активность")],
    ],
    resize_keyboard=True,
    is_persistent=True,
)

# Выбор цели
goal_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Похудение")],
        [KeyboardButton(text="Поддержание")],
        [KeyboardButton(text="Набор")],
    ],
    resize_keyboard=True,
    is_persistent=True,
)

# ==================== FSM STATES ====================
class ProfileForm(StatesGroup):
    sex = State()
    age = State()
    height = State()
    weight = State()
    activity = State()
    goal = State()

class PortionForm(StatesGroup):
    dish_name = State()
    calories_per_100 = State()
    portion_grams = State()

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def split_text(text, limit=4000):
    """Разделяет длинный текст на части"""
    return [text[i:i + limit] for i in range(0, len(text), limit)]

def load_json_file(path, default):
    """Загружает JSON файл"""
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки {path}: {e}")
            return default
    return default

def save_json_file(path, data):
    """Сохраняет JSON файл"""
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения {path}: {e}")

def load_state():
    """Загружает состояние из файлов"""
    global user_goals, user_profiles, meals_log
    user_goals = load_json_file(GOALS_FILE, {})
    user_profiles = load_json_file(PROFILE_FILE, {})
    meals_log = load_json_file(MEALS_FILE, {})
    logger.info(f"✅ Загружено профилей: {len(user_profiles)}")

def save_state():
    """Сохраняет состояние в файлы"""
    save_json_file(GOALS_FILE, user_goals)
    save_json_file(PROFILE_FILE, user_profiles)
    save_json_file(MEALS_FILE, meals_log)

def logmeal_headers():
    """Возвращает заголовки для API LogMeal"""
    return {
        "Authorization": f"Bearer {LOGMEAL_TOKEN}",
        "accept": "application/json",
    }

def safe_json(resp):
    """Безопасно парсит JSON ответ"""
    try:
        return resp.json()
    except Exception as e:
        logger.error(f"JSON parse error: {e}")
        return {"error": resp.text}

def extract_list(data):
    """Извлекает список из ответа API"""
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
    """Извлекает название из элемента"""
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
    """Извлекает нутриенты из ответа API"""
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
    """Рассчитывает BMR и TDEE"""
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

def get_target_calories(profile, goal):
    """Получает целевые калории на основе профиля и цели"""
    _, tdee = calculate_tdee(profile)
    if goal == "Похудение":
        return round(tdee - 400)
    elif goal == "Поддержание":
        return round(tdee)
    else:  # Набор
        return round(tdee + 300)

def get_profile(uid):
    """Получает профиль пользователя"""
    return user_profiles.get(str(uid), {})

def set_profile(uid, profile):
    """Сохраняет профиль пользователя"""
    user_profiles[str(uid)] = profile
    save_state()

def delete_profile(uid):
    """Удаляет профиль пользователя"""
    key = str(uid)
    if key in user_profiles:
        del user_profiles[key]
    if key in user_goals:
        del user_goals[key]
    if key in meals_log:
        del meals_log[key]
    save_state()

def set_goal(uid, goal):
    """Устанавливает цель пользователя"""
    user_goals[str(uid)] = goal
    save_state()

def get_goal(uid):
    """Получает цель пользователя"""
    return user_goals.get(str(uid))

def append_meal(uid, meal_entry):
    """Добавляет запись о приеме пищи"""
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
    """Получает приемы пищи за сегодня"""
    key = str(uid)
    today = datetime.now().strftime("%Y-%m-%d")
    meals = meals_log.get(key, [])
    return [m for m in meals if m.get("date") == today]

def extract_calories_from_text(text):
    """Извлекает калории из текста"""
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
    """Анализирует изображение через LogMeal API"""
    try:
        logger.info(f"Starting LogMeal analysis, image size: {len(image_bytes)} bytes")
        
        files = {"image": ("meal.jpg", image_bytes, "image/jpeg")}
        rec_url = "https://api.logmeal.com/v2/image/segmentation/complete"
        
        logger.info(f"Sending request to {rec_url}")
        rec_response = requests.post(rec_url, headers=logmeal_headers(), files=files, timeout=120)
        
        logger.info(f"Response status: {rec_response.status_code}")

        if rec_response.status_code != 200:
            error_text = rec_response.text[:500]
            logger.error(f"Recognition error: {rec_response.status_code} - {error_text}")
            return None, None, f"❌ Ошибка распознавания (код {rec_response.status_code}). Проверь API ключ или попробуй позже."

        rec_json = safe_json(rec_response)
        
        image_id = None
        dish_name = None

        if isinstance(rec_json, dict):
            image_id = rec_json.get("imageId") or rec_json.get("image_id") or rec_json.get("id")
            logger.info(f"Image ID: {image_id}")

            items = extract_list(rec_json)
            logger.info(f"Extracted items count: {len(items)}")
            
            if items:
                dish_name = get_name(items[0])
                logger.info(f"Dish name from items: {dish_name}")

            if not dish_name:
                food_name = rec_json.get("foodName")
                if isinstance(food_name, list) and food_name:
                    dish_name = str(food_name[0])
                elif isinstance(food_name, str) and food_name.strip():
                    dish_name = food_name.strip()

        if not dish_name:
            logger.warning("Dish not recognized")
            return None, None, "⚠️ Не удалось распознать блюдо. Попробуй фото получше или используй /manual для ручного ввода."

        lines = [f"🍽 Распознанное блюдо: {dish_name}"]
        calories = None

        if image_id:
            nutri_url = "https://api.logmeal.com/v2/nutrition/recipe/nutritionalInfo"
            logger.info(f"Requesting nutritional info for image_id: {image_id}")
            
            nutri_response = requests.post(
                nutri_url,
                headers=logmeal_headers(),
                json={"imageId": image_id},
                timeout=120
            )

            logger.info(f"Nutrition response status: {nutri_response.status_code}")

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

        logger.info("Analysis completed successfully")
        return calories, dish_name, "\n".join(lines)

    except Exception as e:
        logger.exception(f"Analysis error: {e}")
        return None, None, f"❌ Ошибка анализа: {str(e)}"

def profile_summary(profile, uid):
    """Форматирует информацию профиля"""
    bmr, tdee = calculate_tdee(profile)
    goal = get_goal(uid)
    target = get_target_calories(profile, goal) if goal else tdee
    
    return (
        f"👤 Пол: {profile['sex']}\n"
        f"🎂 Возраст: {profile['age']}\n"
        f"📏 Рост: {profile['height']} см\n"
        f"⚖️ Вес: {profile['weight']} кг\n"
        f"🏃 Активность: {profile['activity']}\n"
        f"🎯 Цель: {goal if goal else 'Не установлена'}\n"
        f"🔥 BMR: {bmr} ккал\n"
        f"⚡ TDEE: {tdee} ккал\n"
        f"📋 Дневная норма: {target} ккал\n"
    )

# ==================== ОБРАБОТЧИКИ КОМАНД ====================

@dp.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    """Обработчик команды /start"""
    await state.clear()
    profile = get_profile(message.from_user.id)
    if profile:
        await message.answer(
            f"👋 Привет, {message.from_user.first_name}!\n\n"
            f"Твой профиль:\n\n{profile_summary(profile, message.from_user.id)}",
            reply_markup=main_menu
        )
    else:
        await message.answer(
            "👋 Привет! Я AI_CalCount_bot.\n"
            "🍽️ Я помогу тебе считать калории и следить за питанием.\n\n"
            "⭐ Сначала создай свой профиль, нажав на кнопку 📊 Профиль",
            reply_markup=main_menu
        )

@dp.message(Command("manual"))
async def manual_input_command(message: Message, state: FSMContext):
    """Команда /manual для ручного ввода порции"""
    await state.clear()
    await state.set_state(PortionForm.dish_name)
    await message.answer("📝 Введи название блюда:")

# ==================== ОБРАБОТЧИКИ ГЛАВНОГО МЕНЮ ====================

@dp.message(StateFilter(None), F.text == "📊 Профиль")
async def profile_button(message: Message, state: FSMContext):
    """Нажатие кнопки 'Профиль'"""
    profile = get_profile(message.from_user.id)
    
    if profile:
        await message.answer(
            f"Твой текущий профиль:\n\n{profile_summary(profile, message.from_user.id)}",
            reply_markup=profile_menu
        )
    else:
        await message.answer(
            "У тебя нет профиля. Создай новый!",
            reply_markup=profile_menu
        )

@dp.message(StateFilter(None), F.text == "📸 Анализ блюда")
async def analyze_button(message: Message):
    """Нажатие кнопки 'Анализ блюда'"""
    profile = get_profile(message.from_user.id)
    if not profile:
        await message.answer(
            "⚠️ Сначала создай профиль, чтобы я мог считать калории правильно!",
            reply_markup=main_menu
        )
        return
    
    await message.answer("📸 Теперь отправь мне фото блюда одним сообщением.")

@dp.message(StateFilter(None), F.text == "📜 История")
async def history_button(message: Message):
    """Нажатие кнопки 'История'"""
    items = meals_log.get(str(message.from_user.id), [])
    if not items:
        await message.answer("📜 История пока пустая.", reply_markup=main_menu)
        return
    text = "📜 Последние анализы:\n\n" + "\n\n".join([item.get("text", "") for item in items[-5:]])
    for part in split_text(text):
        await message.answer(part)
    await message.answer("Выбери действие:", reply_markup=main_menu)

@dp.message(StateFilter(None), F.text == "📈 Суточный итог")
async def daily_summary_button(message: Message):
    """Нажатие кнопки 'Суточный итог'"""
    profile = get_profile(message.from_user.id)
    today_meals = get_today_meals(message.from_user.id)
    
    if not profile:
        await message.answer("⚠️ Сначала создай профиль.", reply_markup=main_menu)
        return
    
    if not today_meals:
        await message.answer("📊 Еще не было приемов пищи за сегодня.", reply_markup=main_menu)
        return
    
    goal = get_goal(message.from_user.id)
    target = get_target_calories(profile, goal)
    
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
        f"{'─' * 30}\n"
        f"Приемы пищи:\n" + "\n".join(meal_list) + f"\n"
        f"{'─' * 30}\n\n"
        f"🔢 Всего калорий: {total_calories:.0f} ккал\n"
        f"🎯 Дневная норма: {target} ккал\n"
        f"📈 Процент от нормы: {percent}%\n"
        f"⬜ Осталось: {remaining:.0f} ккал"
    )
    
    await message.answer(summary, reply_markup=main_menu)

@dp.message(StateFilter(None), F.text == "❓ Помощь")
async def help_button(message: Message):
    """Нажатие кнопки 'Помощь'"""
    await message.answer(
        "📖 Как пользоваться ботом:\n\n"
        "1️⃣ Нажми 📊 Профиль → Создать профиль\n"
        "2️⃣ Введи свои данные (пол, возраст, рост, вес, активность)\n"
        "3️⃣ Выбери цель (Похудение/Поддержание/Набор)\n"
        "4️⃣ Нажми 📸 Анализ блюда и отправь фото еды\n"
        "5️⃣ Получи информацию о калориях и нутриентах\n"
        "6️⃣ Проверяй 📈 Суточный итог, чтобы видеть сумму калорий за день\n\n"
        "💡 Команды:\n"
        "/manual — ручной ввод порции (если фото не распознано)\n"
        "/start — главное меню",
        reply_markup=main_menu
    )

# ==================== ОБРАБОТЧИКИ МЕНЮ ПРОФИЛЯ ====================

@dp.message(F.text == "➕ Создать профиль")
async def create_profile_button(message: Message, state: FSMContext):
    """Создание нового профиля"""
    await state.set_state(ProfileForm.sex)
    await message.answer("Выбери пол:", reply_markup=gender_menu)

@dp.message(F.text == "✏️ Редактировать профиль")
async def edit_profile_button(message: Message, state: FSMContext):
    """Редактирование профиля"""
    profile = get_profile(message.from_user.id)
    if not profile:
        await message.answer("У тебя нет профиля для редактирования!", reply_markup=profile_menu)
        return
    
    await state.set_state(ProfileForm.sex)
    await message.answer("Выбери пол:", reply_markup=gender_menu)

@dp.message(F.text == "🗑️ Удалить профиль")
async def delete_profile_button(message: Message, state: FSMContext):
    """Удаление профиля"""
    delete_profile(message.from_user.id)
    await state.clear()
    await message.answer(
        "🗑️ Профиль удален.\n\n"
        "Нажми 📊 Профиль для создания нового.",
        reply_markup=main_menu
    )

@dp.message(F.text == "◀️ Назад в меню")
async def back_to_main_menu(message: Message, state: FSMContext):
    """Возврат в главное меню"""
    await state.clear()
    await message.answer("Выбери действие:", reply_markup=main_menu)

# ==================== ОБРАБОТЧИКИ ЗАПОЛНЕНИЯ ПРОФИЛЯ ====================

@dp.message(ProfileForm.sex, F.text.in_(["Мужской", "Женский"]))
async def profile_sex(message: Message, state: FSMContext):
    """Ввод пола"""
    await state.update_data(sex=message.text)
    await state.set_state(ProfileForm.age)
    await message.answer("Введи возраст числом (10-100):")

@dp.message(ProfileForm.age)
async def profile_age(message: Message, state: FSMContext):
    """Ввод возраста"""
    try:
        age = int(message.text)
        if age < 10 or age > 100:
            raise ValueError
    except Exception:
        await message.answer("❌ Введи возраст числом от 10 до 100.")
        return
    await state.update_data(age=age)
    await state.set_state(ProfileForm.height)
    await message.answer("Введи рост в сантиметрах (100-250):")

@dp.message(ProfileForm.height)
async def profile_height(message: Message, state: FSMContext):
    """Ввод роста"""
    try:
        height = float(message.text.replace(",", "."))
        if height < 100 or height > 250:
            raise ValueError
    except Exception:
        await message.answer("❌ Введи рост числом, например 175.")
        return
    await state.update_data(height=height)
    await state.set_state(ProfileForm.weight)
    await message.answer("Введи вес в килограммах (30-300):")

@dp.message(ProfileForm.weight)
async def profile_weight(message: Message, state: FSMContext):
    """Ввод веса"""
    try:
        weight = float(message.text.replace(",", "."))
        if weight < 30 or weight > 300:
            raise ValueError
    except Exception:
        await message.answer("❌ Введи вес числом, например 72.5.")
        return
    await state.update_data(weight=weight)
    await state.set_state(ProfileForm.activity)
    await message.answer("Выбери уровень активности:", reply_markup=activity_menu)

@dp.message(ProfileForm.activity)
async def profile_activity(message: Message, state: FSMContext):
    """Ввод активности"""
    if message.text not in activity_map:
        await message.answer("❌ Выбери активность из предложенных вариантов.")
        return
    await state.update_data(activity=message.text)
    await state.set_state(ProfileForm.goal)
    await message.answer("Выбери свою цель:", reply_markup=goal_menu)

@dp.message(ProfileForm.goal)
async def profile_goal(message: Message, state: FSMContext):
    """Ввод цели"""
    if message.text not in ["Похудение", "Поддержание", "Набор"]:
        await message.answer("❌ Выбери цель из предложенных вариантов.")
        return
    
    data = await state.get_data()
    set_profile(message.from_user.id, data)
    set_goal(message.from_user.id, message.text)
    
    await state.clear()
    await message.answer(
        f"✅ Профиль сохранен!\n\n"
        f"{profile_summary(data, message.from_user.id)}\n"
        f"Отлично! Теперь ты можешь анализировать блюда! 🍽️",
        reply_markup=main_menu
    )

# ==================== ОБРАБОТЧИКИ РУЧНОГО ВВОДА ====================

@dp.message(PortionForm.dish_name)
async def manual_dish_name(message: Message, state: FSMContext):
    """Ввод названия блюда"""
    await state.update_data(dish_name=message.text)
    await state.set_state(PortionForm.calories_per_100)
    await message.answer("📊 Введи калории на 100 г (число):")

@dp.message(PortionForm.calories_per_100)
async def manual_calories_per_100(message: Message, state: FSMContext):
    """Ввод калорий на 100г"""
    try:
        calories_per_100 = float(message.text.replace(",", "."))
        if calories_per_100 <= 0:
            raise ValueError
    except Exception:
        await message.answer("❌ Введи положительное число, например 150 или 150.5")
        return
    
    await state.update_data(calories_per_100=calories_per_100)
    await state.set_state(PortionForm.portion_grams)
    await message.answer("⚖️ Введи вес порции в граммах (число):")

@dp.message(PortionForm.portion_grams)
async def manual_portion_grams(message: Message, state: FSMContext):
    """Ввод веса порции"""
    try:
        portion_grams = float(message.text.replace(",", "."))
        if portion_grams <= 0:
            raise ValueError
    except Exception:
        await message.answer("❌ Введи положительное число, например 200 или 250.5")
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
        goal = get_goal(message.from_user.id)
        target = get_target_calories(profile, goal)
        
        percent = round((total_calories / target) * 100, 1)
        result_text += f"\n\nЭто примерно {percent}% от твоей дневной нормы ({target} ккал)."
    
    append_meal(message.from_user.id, result_text)
    await state.clear()
    
    await message.answer(result_text, reply_markup=main_menu)

# ==================== ОБРАБОТЧИК ФОТО ====================

@dp.message(StateFilter(None), F.photo)
async def photo_handler(message: Message):
    """Обработка отправленного фото"""
    profile = get_profile(message.from_user.id)
    if not profile:
        await message.answer(
            "⚠️ Сначала создай профиль!",
            reply_markup=main_menu
        )
        return
    
    await message.answer("⏳ Фото получил. Сейчас анализирую блюдо...")

    try:
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        file_bytes = await bot.download_file(file.file_path)
        image_data = file_bytes.read()

        logger.info(f"Downloaded image: {len(image_data)} bytes")

        calories, dish_name, result_text = analyze_image_with_logmeal(image_data)

        if profile and calories is not None:
            goal = get_goal(message.from_user.id)
            target = get_target_calories(profile, goal)

            percent = round((float(calories) / target) * 100, 1)
            result_text += f"\n\nЭто примерно {percent}% от твоей дневной нормы ({target} ккал)."

        append_meal(message.from_user.id, result_text)

        for part in split_text(result_text):
            await message.answer(part)
        
        await message.answer("Выбери действие:", reply_markup=main_menu)
    
    except Exception as e:
        logger.exception(f"Photo handler error: {e}")
        await message.answer(
            f"❌ Ошибка при обработке фото: {str(e)}\n\n"
            f"Используй /manual для ручного ввода.",
            reply_markup=main_menu
        )

# ==================== ОБРАБОТЧИК ОСТАЛЬНОГО ====================

@dp.message()
async def other_messages(message: Message):
    """Обработчик прочих сообщений"""
    await message.answer(
        "Я не понимаю это сообщение 🤔\n\n"
        "Используй меню ниже 👇",
        reply_markup=main_menu
    )

# ==================== ГЛАВНАЯ ФУНКЦИЯ ====================

async def set_bot_commands():
    """Устанавливает команды бота"""
    commands = [
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="manual", description="Ручной ввод порции"),
    ]
    await bot.set_my_commands(commands)

async def main():
    """Главная функция запуска бота"""
    logger.info("🚀 Запуск бота...")
    load_state()
    await set_bot_commands()
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("✅ Бот запущен и ожидает сообщений...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⛔ Бот остановлен.")
    except Exception as e:
        logger.exception(f"❌ Критическая ошибка: {e}")
