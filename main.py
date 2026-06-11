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

menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Анализ блюда")],
        [KeyboardButton(text="Помощь")],
    ],
    resize_keyboard=True
)

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

def analyze_image_with_logmeal(image_bytes: bytes) -> str:
    try:
        files = {
            "image": ("meal.jpg", image_bytes, "image/jpeg")
        }

        rec_url = "https://api.logmeal.com/v2/image/segmentation/complete"
        rec_response = requests.post(
            rec_url,
            headers=logmeal_headers(),
            files=files,
            timeout=120
        )

        if rec_response.status_code != 200:
            return f"Ошибка распознавания: {rec_response.status_code}\n{rec_response.text}"

        rec_json = safe_json(rec_response)
        image_id = None
        if isinstance(rec_json, dict):
            image_id = rec_json.get("imageId") or rec_json.get("image_id") or rec_json.get("id")

        dishes = extract_list(rec_json)

        lines = []
        if image_id:
            lines.append(f"imageId: {image_id}")

        if dishes:
            lines.append("Распознанные блюда:")
            for i, item in enumerate(dishes[:5], 1):
                lines.append(f"{i}. {get_name(item)}")
        else:
            lines.append("Не удалось извлечь блюда из ответа API.")
            lines.append(f"Ответ API: {rec_json}")

        if image_id:
            nutri_url = "https://api.logmeal.com/v2/nutrition/recipe/nutritionalInfo"
            nutri_response = requests.post(
                nutri_url,
                headers=logmeal_headers(),
                json={"imageId": image_id},
                timeout=120
            )

            lines.append("")
            lines.append("Нутриенты:")

            if nutri_response.status_code == 200:
                nutri_json = safe_json(nutri_response)
                if isinstance(nutri_json, dict):
                    found = False
                    for key in ["calories", "energy", "protein", "fat", "carbs", "carbohydrates"]:
                        if key in nutri_json:
                            lines.append(f"{key}: {nutri_json[key]}")
                            found = True
                    if not found:
                        lines.append(str(nutri_json))
                else:
                    lines.append(str(nutri_json))
            else:
                lines.append(f"Не удалось получить нутриенты: {nutri_response.status_code}")
                lines.append(nutri_response.text)

        lines.append("")
        lines.append("Если хотите, могу добавить оценку под цель: похудение / поддержание / набор.")
        return "\n".join(lines)

    except Exception as e:
        return f"Ошибка анализа: {e}"


dp.message(CommandStart())
async def start_handler(message: Message):
    await message.answer(
        "Привет! Я AI_CalCount_bot.\n"
        "Нажми «Анализ блюда» и отправь фото еды.",
        reply_markup=menu
    )

@dp.message(F.text == "Помощь")
async def help_handler(message: Message):
    await message.answer("Отправь фото блюда, и я покажу примерную оценку калорий и БЖУ.")

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
    await message.answer(result_text)

@dp.message()
async def other_messages(message: Message):
    await message.answer("Нажми «Анализ блюда» или отправь фото еды.", reply_markup=menu)

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())@
