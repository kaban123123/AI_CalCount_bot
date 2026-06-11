import asyncio
import os
import requests
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

API_TOKEN = os.environ.get("TG_TOKEN", "").strip()
LOGMEAL_TOKEN = os.environ.get("LOGMEAL_TOKEN", "").strip()

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

user_goals = {}

GOAL_CALORIES = {
    "Похудение": 1600,
    "Поддержание": 2200,
    "Набор": 2800,
}

menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Похудение"), KeyboardButton(text="Поддержание"), KeyboardButton(text="Набор")],
        [KeyboardButton(text="Анализ блюда"), KeyboardButton(text="Помощь")],
    ],
    resize_keyboard=True
)

def split_text(text, limit=4000):
    return [text[i:i + limit] for i in range(0, len(text), limit)]

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

def analyze_image_with_logmeal(image_bytes: bytes) -> str:
    try:
        files = {"image": ("meal.jpg", image_bytes, "image/jpeg")}
        rec_url = "https://api.logmeal.com/v2/image/segmentation/complete"
        rec_response = requests.post(rec_url, headers=logmeal_headers(), files=files, timeout=120)

        if rec_response.status_code != 200:
            return f"Ошибка распознавания: {rec_response.status_code}\n{rec_response.text}"

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
                    calories, protein, fat, carbs, fiber,


sugar, score = extract_nutrients(nutri_json)

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
        return "\n".join(lines)

    except Exception as e:
        return f"Ошибка анализа: {e}"

@dp.message(CommandStart())
async def start_handler(message: Message):
    await message.answer(
        "Привет! Я AI_CalCount_bot.\n"
        "Сначала выбери цель: Похудение, Поддержание или Набор.",
        reply_markup=menu
    )

@dp.message(F.text.in_(["Похудение", "Поддержание", "Набор"]))
async def goal_handler(message: Message):
    user_goals[message.from_user.id] = message.text
    daily = GOAL_CALORIES[message.text]
    await message.answer(
        f"Цель установлена: {message.text}\n"
        f"Дневная норма: {daily} ккал.\n"
        f"Теперь отправь фото блюда."
    )

@dp.message(F.text == "Помощь")
async def help_handler(message: Message):
    await message.answer(
        "Сначала выбери цель, потом отправь фото еды.\n"
        "Я покажу калории и сравню с твоей дневной нормой."
    )

@dp.message(F.text == "Анализ блюда")
async def analyze_hint(message: Message):
    await message.answer("Теперь отправь мне фото блюда одним сообщением.")

@dp.message(F.photo)
async def photo_handler(message: Message):
    await message.answer("Фото получил. Сейчас анализирую блюдо...")

    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    file_bytes = await bot.download_file(file.file_path)
    image_data = file_bytes.read()

    result_text = analyze_image_with_logmeal(image_data)

    goal = user_goals.get(message.from_user.id)
    if goal:
        daily = GOAL_CALORIES.get(goal)
        calories = None

        for line in result_text.splitlines():
            if line.startswith("Калории:"):
                try:
                    calories = float(line.split(":", 1)[1].strip().split()[0])
                except Exception:
                    pass
                break

        if calories is not None and daily:
            percent = round((calories / daily) * 100, 1)
            result_text += f"\n\nЭто примерно {percent}% от дневной нормы для цели «{goal}» ({daily} ккал)."

    for part in split_text(result_text):
        await message.answer(part)

@dp.message()
async def other_messages(message: Message):
    await message.answer("Сначала выбери цель: Похудение, Поддержание или Набор.", reply_markup=menu)

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
