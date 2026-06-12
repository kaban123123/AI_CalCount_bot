import asyncio
import json
import os
from pathlib import Path
from datetime import datetime
import logging

import requests
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_TOKEN = os.environ.get("TG_TOKEN", "").strip()
LOGMEAL_TOKEN = os.environ.get("LOGMEAL_TOKEN", "").strip()

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# ... [остальной код логики бота остаётся без изменений до analyze_image_with_logmeal]

def analyze_image_with_logmeal(image_bytes: bytes):
    """Анализ изображения через LogMeal API"""
    try:
        logger.info(f"Starting LogMeal analysis, image size: {len(image_bytes)} bytes")
        logger.info(f"LogMeal token present: {bool(LOGMEAL_TOKEN)}")
        logger.info(f"LogMeal token first 10 chars: {LOGMEAL_TOKEN[:10] if LOGMEAL_TOKEN else 'NO TOKEN'}")
        
        files = {"image": ("meal.jpg", image_bytes, "image/jpeg")}
        rec_url = "https://api.logmeal.com/v2/image/segmentation/complete"
        
        logger.info(f"Sending request to {rec_url}")
        rec_response = requests.post(rec_url, headers=logmeal_headers(), files=files, timeout=120)
        
        logger.info(f"Response status: {rec_response.status_code}")
        logger.info(f"Response headers: {dict(rec_response.headers)}")

        if rec_response.status_code != 200:
            error_text = rec_response.text[:500]
            logger.error(f"Recognition error: {rec_response.status_code} - {error_text}")
            return None, None, f"❌ Ошибка распознавания (код {rec_response.status_code}). Проверь API ключ или попробуй позже."

        rec_json = safe_json(rec_response)
        logger.info(f"Recognition response type: {type(rec_json)}")
        logger.info(f"Recognition response keys: {list(rec_json.keys()) if isinstance(rec_json, dict) else 'not a dict'}")
        
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
                logger.info(f"Dish name from foodName: {dish_name}")

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
                logger.info(f"Nutrition response keys: {list(nutri_json.keys()) if isinstance(nutri_json, dict) else 'not a dict'}")

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
                error_text = nutri_response.text[:200]
                logger.error(f"Nutrition error: {nutri_response.status_code} - {error_text}")
                lines.append("")
                lines.append(f"⚠️ Не удалось получить нутриенты: {nutri_response.status_code}")
        else:
            lines.append("")
            lines.append("⚠️ Не удалось получить ID изображения")

        logger.info("Analysis completed successfully")
        return calories, dish_name, "\n".join(lines)

    except Exception as e:
        logger.exception(f"Analysis error: {e}")
        return None, None, f"❌ Ошибка анализа: {str(e)}"

@dp.message(F.photo)
async def photo_handler(message: Message):
    await message.answer("⏳ Фото получил. Сейчас анализирую блюдо...")

    try:
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        file_bytes = await bot.download_file(file.file_path)
        image_data = file_bytes.read()

        logger.info(f"Downloaded image: {len(image_data)} bytes")

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
    
    except Exception as e:
        logger.exception(f"Photo handler error: {e}")
        await message.answer(f"❌ Ошибка при обработке фото: {str(e)}", reply_markup=menu)
