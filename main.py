import asyncio
import os
import urllib3
import requests
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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

def extract_dishes(seg_json):
    dishes = []

    if isinstance(seg_json, dict):
        for key in ["segmentationResults", "segmentation_results", "predictions", "results", "dishPredictions"]:
            value = seg_json.get(key)
            if isinstance(value, list):
                dishes.extend(value)

        if not dishes:
            for key in ["foodSpots", "food_spots", "segments", "items"]:
                value = seg_json.get(key)
                if isinstance(value, list):
                    dishes.extend(value)

    return dishes

def dish_name(item):
    if isinstance(item, str):
        return item

    if isinstance(item, dict):
        for key in ["name", "dish", "label", "food", "title", "className", "dish_name"]:
            if key in item and item[key]:
                return str(item[key])

        if "food_groups" in item and isinstance(item["food_groups"], list) and item["food_groups"]:
            return ", ".join(map(str, item["food_groups"]))

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
            timeout=120,
            verify=True
        )

        if rec_response.status_code != 200:
            return f"Ошибка распознавания: {rec_response.status_code}\n{rec_response.text}"

        rec_json = rec_response.json()
        image_id = rec_json.get("imageId") or rec_json.get("image_id")
        dishes = extract_dishes(rec_json)

        lines = []
        if image_id:
            lines.append(f"imageId: {image_id}")

        if dishes:
            lines.append("Распознанные блюда:")
            for i, item in enumerate(dishes[:5], 1):
                lines.append(f"{i}. {dish_name(item)}")
        else:
            lines.append("Блюда не удалось извлечь из ответа API.")

        nutri_url = "https://api.logmeal.com/v2/nutrition/recipe/nutritionalInfo"

        nutri_payload = {}
        if image_id:
            nutri_payload["imageId"] = image_id

        nutri_response = requests.post(
            nutri_url,
            headers={**logmeal_headers(), "Content-Type": "application/json"},
            json=nutri_payload,
            timeout=120,
            verify=True
        )

        if nutri_response.status_code == 200:
            nutri_json = nutri_response.json()
            lines.append("")
            lines.append("Нутриенты:")

            if isinstance(nutri_json, dict):
                added = False
                for key in ["calories", "energy", "protein", "fat", "carbs", "carbohydrates"]:
                    if key in nutri_json:
                        lines.append(f"{key}: {nutri_json[key]}")
                        added = True

                if not added:
                    lines.append(str(nutri_json))
            else:
                lines.append(str(nutri_json))
        else:
            lines.append("")
            lines.append(f"Нутриенты не получены: {nutri_response.status_code}")
            lines.append(nutri_response.text)

        lines.append("")
        lines.append("Если хотите, могу добавить


под цель: похудение / поддержание / набор.")
        return "\n".join(lines)

    except Exception as e:
        return f"Ошибка анализа: {e}"

@dp.message(CommandStart())
async def start_handler(message: Message):
    await message.answer(
        "Привет! Я AI_CalCount_bot.\n"
        "Нажми «Анализ блюда» и отправь фото еды.",
        reply_markup=menu
    )

@dp.message(F.text == "Помощь")
async def help_handler(message: Message):
    await message.answer(
        "Отправь фото блюда, и я покажу примерную оценку калорий и БЖУ."
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
    await message.answer(result_text)

@dp.message()
async def other_messages(message: Message):
    await message.answer("Нажми «Анализ блюда» или отправь фото еды.", reply_markup=menu)

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
