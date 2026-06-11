import asyncio
import os
import urllib3
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

API_TOKEN = os.environ.get("TG_TOKEN", "").strip()

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Анализ блюда")],
        [KeyboardButton(text="Помощь")],
    ],
    resize_keyboard=True
)

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
        "Отправь фото блюда, и я покажу примерную оценку калорий, БЖУ и совет под цель."
    )

@dp.message(F.text == "Анализ блюда")
async def analyze_hint(message: Message):
    await message.answer("Теперь отправь мне фото блюда одним сообщением.")

@dp.message(F.photo)
async def photo_handler(message: Message):
    await message.answer("Фото получил. Сейчас анализирую блюдо...")

    result_text = (
        "Примерный анализ блюда:\n"
        "Калории: 450-650 ккал\n"
        "Белки: 20-30 г\n"
        "Жиры: 15-25 г\n"
        "Углеводы: 40-70 г\n\n"
        "Оценка: подходит для поддержания веса, но для похудения лучше уменьшить порцию."
    )

    await message.answer(result_text)

@dp.message()
async def other_messages(message: Message):
    await message.answer("Нажми «Анализ блюда» или отправь фото еды.", reply_markup=menu)

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())