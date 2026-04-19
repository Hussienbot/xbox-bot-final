import os
import asyncio
import csv
from io import BytesIO, StringIO
from datetime import datetime

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from xbox_checker import process_account, parse_accounts_from_text

TOKEN = os.environ.get("TOKEN")  # سيتم تعيينه عبر متغيرات البيئة

# ------------------- أوامر البوت -------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎮 **بوت فحص حسابات Xbox**\n\n"
        "• أرسل `/check` لبدء العملية.\n"
        "• قم برفع ملف `txt` يحتوي على الحسابات (كل سطر: `email:password`).\n"
        "• سيقوم البوت بفحص الحسابات واحداً تلو الآخر وإرسال النتائج.\n"
        "• في النهاية ستحصل على ملف CSV وملخص.\n\n"
        "⚠️ البوت يعمل في وضع الخلفية (headless).",
        parse_mode='Markdown'
    )

async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['awaiting_file'] = True
    await update.message.reply_text("📤 أرسل ملف نصي `txt` يحتوي على الحسابات (email:password كل سطر).")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_file'):
        await update.message.reply_text("❌ أرسل `/check` أولاً.")
        return
    doc = update.message.document
    if not doc.file_name.endswith('.txt'):
        await update.message.reply_text("❌ يرجى رفع ملف نصي بصيغة .txt")
        return
    file = await doc.get_file()
    content = await file.download_as_bytearray()
    text = content.decode('utf-8', errors='ignore')
    accounts = parse_accounts_from_text(text)
    if not accounts:
        await update.message.reply_text("❌ لم يتم العثور على حسابات صالحة في الملف.")
        return
    context.user_data['accounts'] = accounts
    context.user_data['results'] = []
    context.user_data['current_index'] = 0
    context.user_data['awaiting_file'] = False
    await update.message.reply_text(f"✅ تم استلام {len(accounts)} حساب. سيبدأ الفحص الآن...")
    await process_next_account(update, context)

async def process_next_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    accounts = context.user_data.get('accounts', [])
    index = context.user_data.get('current_index', 0)
    if index >= len(accounts):
        await finalize_results(update, context)
        return
    account = accounts[index]
    await update.message.reply_text(f"🔄 جاري فحص {index+1}/{len(accounts)}: `{account['email']}`", parse_mode='Markdown')
    result = await process_account(account, headless=True)
    context.user_data.setdefault('results', []).append(result)
    context.user_data['current_index'] = index + 1
    if result['success'] and result['has_console']:
        status = "✅ **مع جهاز**"
    elif result['success']:
        status = "⚠️ **مسجل ولا جهاز**"
    else:
        status = "❌ **فشل**"
    await update.message.reply_text(f"{status}\n📧 {result['email']}\n📝 {result['console_info']}")
    await asyncio.sleep(2)
    await process_next_account(update, context)

async def finalize_results(update: Update, context: ContextTypes.DEFAULT_TYPE):
    results = context.user_data.get('results', [])
    if not results:
        await update.message.reply_text("لا توجد نتائج.")
        return
    # إنشاء ملف CSV في الذاكرة
    output = StringIO()
    fieldnames = ['email', 'password', 'success', 'has_console', 'console_info', 'timestamp']
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(results)
    output.seek(0)
    await update.message.reply_document(
        document=BytesIO(output.getvalue().encode('utf-8')),
        filename=f'xbox_results_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    )
    with_dev = sum(1 for r in results if r['success'] and r['has_console'])
    logged_no_dev = sum(1 for r in results if r['success'] and not r['has_console'])
    failed = sum(1 for r in results if not r['success'])
    summary = f"📊 **النتائج النهائية**\n✅ مع جهاز: {with_dev}\n⚠️ مسجل ولا جهاز: {logged_no_dev}\n❌ فشل: {failed}\n📌 الإجمالي: {len(results)}"
    await update.message.reply_text(summary, parse_mode='Markdown')
    context.user_data.clear()

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ تم إلغاء العملية.")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("check", check_command))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    print("🤖 البوت يعمل...")
    app.run_polling()

if __name__ == "__main__":
    main()
