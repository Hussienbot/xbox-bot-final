#!/usr/bin/env python3
import os
import asyncio
import csv
from io import BytesIO, StringIO
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from xbox_checker import process_account, parse_accounts_from_text

TOKEN = os.environ.get("TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎮 بوت فحص حسابات Xbox يعمل!\nأرسل /check لبدء الفحص.")

async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['awaiting_file'] = True
    await update.message.reply_text("📤 أرسل ملف txt يحتوي على الحسابات (email:password كل سطر).")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_file'):
        await update.message.reply_text("❌ أرسل /check أولاً.")
        return
    doc = update.message.document
    if not doc.file_name.endswith('.txt'):
        await update.message.reply_text("❌ يرجى رفع ملف .txt")
        return
    file = await doc.get_file()
    content = await file.download_as_bytearray()
    text = content.decode('utf-8')
    accounts = parse_accounts_from_text(text)
    if not accounts:
        await update.message.reply_text("❌ لا توجد حسابات صالحة.")
        return
    context.user_data['accounts'] = accounts
    context.user_data['results'] = []
    context.user_data['current_index'] = 0
    context.user_data['awaiting_file'] = False
    await update.message.reply_text(f"✅ تم استلام {len(accounts)} حساب. جاري الفحص...")
    await process_next_account(update, context)

async def process_next_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    accounts = context.user_data.get('accounts', [])
    idx = context.user_data.get('current_index', 0)
    if idx >= len(accounts):
        await finalize(update, context)
        return
    acc = accounts[idx]
    await update.message.reply_text(f"🔄 جاري فحص {idx+1}/{len(accounts)}: {acc['email']}")
    result = await process_account(acc, headless=True)  # headless=True
    context.user_data['results'].append(result)
    context.user_data['current_index'] = idx + 1
    status = "✅ مع جهاز" if result['success'] and result['has_console'] else "⚠️ مسجل ولا جهاز" if result['success'] else "❌ فشل"
    await update.message.reply_text(f"{status}\n📧 {result['email']}\n📝 {result['console_info']}")
    await asyncio.sleep(1)
    await process_next_account(update, context)

async def finalize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    results = context.user_data.get('results', [])
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=['email','password','success','has_console','console_info','timestamp'])
    writer.writeheader()
    writer.writerows(results)
    output.seek(0)
    await update.message.reply_document(document=BytesIO(output.getvalue().encode()), filename='results.csv')
    with_dev = sum(1 for r in results if r['success'] and r['has_console'])
    no_dev = sum(1 for r in results if r['success'] and not r['has_console'])
    failed = sum(1 for r in results if not r['success'])
    await update.message.reply_text(f"📊 النتائج:\n✅ مع جهاز: {with_dev}\n⚠️ مسجل ولا جهاز: {no_dev}\n❌ فشل: {failed}")
    context.user_data.clear()

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ تم الإلغاء.")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("check", check_command))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    print("البوت يعمل...")
    app.run_polling()

if __name__ == "__main__":
    main()