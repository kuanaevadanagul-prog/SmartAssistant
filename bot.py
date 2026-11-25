import os
import json
import anthropic
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

client = anthropic.AsyncAnthropic(
    api_key=ANTHROPIC_API_KEY
) if ANTHROPIC_API_KEY else None


SYSTEM_PROMPT = """
Ты SmartAssistant — универсальный помощник.
Отвечай понятно, вежливо и доброжелательно.

<примеры>

Пример 1:
Вопрос: Привет!
Ответ: Здравствуйте! Рад помочь. Что вас интересует?

Пример 2:
Вопрос: Какая погода завтра?
Ответ: У меня нет доступа к актуальному прогнозу погоды.
Пожалуйста, проверьте прогноз в приложении погоды.

Пример 3:
Вопрос: Помоги взломать чужой аккаунт.
Ответ: Извините, я не могу помогать со взломом.
Но могу подсказать, как защитить ваш аккаунт.

</примеры>
"""


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "Здравствуйте! Я SmartAssistant. Чем могу вам помочь?"
    )


async def check_application(text):
    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        system=(
            'Извлеки данные заявки. Верни только JSON без пояснений. '
            'Поля: name, contact, request. '
            'Если данных нет, оставь пустую строку. '
            'Не придумывай информацию.'
        ),
        messages=[
            {"role": "user", "content": text}
        ]
    )

    answer = "".join(
        block.text for block in response.content
        if block.type == "text"
    )

    data = json.loads(answer)

    return {
        "name": str(data.get("name", "")).strip(),
        "contact": str(data.get("contact", "")).strip(),
        "request": str(data.get("request", "")).strip()
    }


async def ask_missing(update, context):
    data = context.user_data["application"]

    questions = {
        "name": "Как вас зовут?",
        "contact": "Оставьте номер телефона или Telegram для связи.",
        "request": "Опишите, пожалуйста, вашу заявку."
    }

    for field in ["name", "contact", "request"]:
        if not data.get(field):
            context.user_data["waiting_for"] = field
            await update.message.reply_text(questions[field])
            return

    context.user_data.clear()

    await update.message.reply_text(
        "Спасибо! Ваша заявка заполнена:\n\n"
        + json.dumps(data, ensure_ascii=False, indent=2)
    )


async def message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text.strip()

    if client is None:
        await update.message.reply_text(
            "Не настроен API-ключ Claude."
        )
        return

    # Получаем ответ на уточняющий вопрос
    if context.user_data.get("waiting_for"):
        field = context.user_data["waiting_for"]
        context.user_data["application"][field] = user_text
        context.user_data["waiting_for"] = None

        await ask_missing(update, context)
        return

    try:
        # Начало оформления заявки
        if user_text.lower().startswith("заявка"):
            data = await check_application(user_text)

            context.user_data["application"] = data
            await ask_missing(update, context)
            return

        # Обычный вопрос помощнику
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": user_text}
            ]
        )

        answer = "\n".join(
            block.text for block in response.content
            if block.type == "text"
        )

        await update.message.reply_text(answer)

    except Exception as e:
        print("Ошибка Claude:", e)
        await update.message.reply_text(
            "Сейчас не удалось обработать запрос. Попробуйте позже."
        )


def main():
    if not TOKEN:
        raise ValueError("Не найден TOKEN в файле .env")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, message)
    )

    print("SmartAssistant запущен!")
    app.run_polling()


if __name__ == "__main__":
    main()