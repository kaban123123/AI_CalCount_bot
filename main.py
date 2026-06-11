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

def safe_json_text(resp):
    try:
        return resp.json()
    except Exception:
        return resp.text

def extract_items(obj):
    if isinstance(obj, dict):
        for key in ["segmentationResults", "segmentation_results", "predictions", "results", "dishPredictions", "foodSpots", "food_spots", "segments", "items"]:
            value = obj.get(key)
            if isinstance(value, list) and value:
                return value
    return []

def item_name(item):
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        for key in ["name", "dish", "label", "food", "title", "className", "dish_name"]:
            if item.get(key):
                return str(item[key])
        if isinstance(item.get("food_groups"), list) and item["food_groups"]:
            return ", ".join(map(str, item["food_groups"]))
    return "Неизвестное блюдо"

def first_available(dct, keys):
    if not isinstance(dct, dict):
        return None
    for k in keys:
        if k in dct and dct[k] not in (None, "", [], {}):
            return dct[k]
    return None

def analyze_image_with_logmeal(image_bytes: bytes) -> str:
    try:
        files = {"image": ("meal.jpg", image_bytes, "image/jpeg")}

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

        rec_json = safe_json_text(rec_response)
        image_id = first_available(rec_json, ["imageId", "image_id", "id"])
        dishes = extract_items(rec_json)

        lines = []
        if image_id:
            lines.append(f"imageId: {image_id}")

        if dishes:
            lines.append("Распознанные блюда:")
            for i, item in enumerate(dishes[:5], 1):
                lines.append(f"{i}. {item_name(item)}")
        else:
            lines.append("Распознанные блюда не найдены в ответе API.")
            lines.append(f"Ответ API: {rec_json}")

        ingredients_text = None
        if image_id:
            ing_url = "https://api.logmeal.com/v2/nutrition/recipe/ingredients"
            ing_response = requests.post(
                ing_url,
                headers={**logmeal_headers(), "Content-Type": "application/json"},
                json={"imageId": image_id},
                timeout=120,
                verify=True
            )
            if ing_response.status_code == 200:
                ingredients_text = safe_json_text(ing_response)
            else:
                ingredients_text = f"Не удалось получить ingredients: {ing_response.status_code}\n{ing_response.text}"

        if ingredients_text is not None:
            lines.append("")
            lines.append("Ингредиенты / детали:")
            lines.append(str(ingredients_text))

        nutri_text = None
        if image_id:
            nutri_url = "https://api.logmeal.com/v2/nutrition/recipe/nutritionalInfo"
            nutri_response = requests.post(
                nutri_url,
                headers={**logmeal_headers(), "Content-Type": "application/json"},
                json={"imageId": image_id},


0,
                verify=True
            )
            if nutri_response.status_code == 200:
                nutri_text = safe_json_text(nutri_response)
            else:
                nutri_text = f"Не удалось получить нутриенты: {nutri_response.status_code}\n{nutri_response.text}"

        if nutri_text is not None:
            lines.append("")
            lines.append("Нутриенты:")
            if isinstance(nutri_text, dict):
                found = False
                for key in ["calories", "energy", "protein", "fat", "carbs", "carbohydrates"]:
                    val = nutri_text.get(key)
                    if val is not None:
                        lines.append(f"{key}: {val}")
                        found = True
                if not found:
                    lines.append(str(nutri_text))
            else:
                lines.append(str(nutri_text))

        lines.append("")
        lines.append("Если хотите, могу добавить оценку под цель: похудение / поддержание / набор.")
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
    asyncio.run(main()) timeout=12
