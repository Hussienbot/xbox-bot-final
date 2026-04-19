import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from typing import Dict, List, Tuple
from datetime import datetime

# مهلة زمنية إجمالية لكل عملية فحص حساب (لتجنب تعليق البوت)
TOTAL_PROCESS_TIMEOUT = 120 

async def check_console_availability_with_refresh(page) -> Tuple[bool, str, bool]:
    url = "https://www.xbox.com/en-US/play/consoles"
    try:
        # ضبط مهلة العمليات الفردية لـ 30 ثانية
        page.set_default_timeout(30000)
        
        await page.goto(url, wait_until="domcontentloaded")
        await asyncio.sleep(8) # وقت كافٍ لتحميل قائمة الأجهزة
        
        text = (await page.inner_text("body")).lower()
        
        if "play your console remotely" in text or "start remote play" in text:
            return True, "يوجد جهاز", True
        if "set up your console" in text or "no consoles found" in text or "connect a console" in text:
            return False, "مسجل ولا يوجد جهاز", True
            
        # محاولة أخيرة إذا كانت الصفحة بطيئة
        await asyncio.sleep(5)
        text = (await page.inner_text("body")).lower()
        if "play your console" in text:
            return True, "يوجد جهاز", True
            
    except Exception:
        pass
    return False, "مسجل (تحقق يدوي مطلوب)", True

async def handle_password_entry(page, password: str) -> bool:
    try:
        # محاكاة الضغط على Escape لتجاوز أي نافذة نظام منبثقة (Passkey)
        await page.keyboard.press("Escape")
        await asyncio.sleep(2)

        # البحث عن حقل كلمة المرور بمحددات متعددة
        # نستخدم أسلوب البحث المرن
        password_input = page.locator("input[type='password'], input[name='passwd'], #i0118")
        
        # إذا لم يظهر الحقل، نحاول النقر على "Use your password"
        if not await password_input.is_visible():
            try:
                # البحث عن أي زر يحتوي على نص يخص كلمة المرور
                pwd_btn = page.locator("text='Use your password', text='Password', [role='button'][name*='Password']")
                if await pwd_btn.is_visible(timeout=5000):
                    await pwd_btn.click()
                    await asyncio.sleep(3)
            except:
                pass

        # ننتظر ظهور الحقل بحد أقصى 15 ثانية
        await password_input.wait_for(state="visible", timeout=15000)
        await password_input.fill(password)
        await asyncio.sleep(1)
        
        # النقر على زر الدخول
        await page.locator("input[type='submit'], #idSIButton9").click()
        await asyncio.sleep(5)
        
        # التعامل مع شاشة Stay signed in?
        try:
            yes_btn = page.locator("#idSIButton9, input[value='Yes']")
            if await yes_btn.is_visible(timeout=5000):
                await yes_btn.click()
                await asyncio.sleep(2)
        except:
            pass
            
        return True
    except Exception as e:
        print(f"Error in handle_password_entry: {e}")
        return False

async def process_account(account: Dict, headless: bool = True) -> Dict:
    result = {
        'email': account['email'],
        'password': account['password'],
        'success': False,
        'has_console': False,
        'console_info': '',
        'timestamp': datetime.now().isoformat()
    }
    p = None
    try:
        p = await async_playwright().start()
        browser = await p.chromium.launch(headless=headless, args=['--no-sandbox', '--disable-setuid-sandbox'])
        
        # تعطيل Passkey برمجياً عبر حقن كود
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 720}
        )
        # هذا الكود يمنع الموقع من معرفة أن المتصفح يدعم Passkey
        await context.add_init_script("delete window.PublicKeyCredential;")
        
        page = await context.new_page()
        # تعيين مهلة Playwright الافتراضية لـ 45 ثانية لتجاوز حد الـ 30 ثانية
        page.set_default_timeout(45000)
        
        # رابط تسجيل دخول مباشر مع وسيطات إضافية لتقليل الأمان المنبثق
        login_url = f"https://login.live.com/login.srf?wa=wsignin1.0&rpsnv=15&ct={int(datetime.now().timestamp())}&rver=7.0.6737.0&wp=MBI_SSL&wreply=https:%2f%2fwww.xbox.com%2fen-US%2fplay%2fconsoles&uiflavor=web"
        
        await page.goto(login_url, wait_until="domcontentloaded")

        # إدخال البريد
        email_input = page.locator("input[name='loginfmt'], input[type='email']")
        await email_input.wait_for(state="visible")
        await email_input.fill(account['email'])
        await page.locator("input[type='submit'], #idSIButton9").click()
        
        # انتظار معالجة البريد (قد يظهر Passkey هنا)
        await asyncio.sleep(5)

        # إدخال كلمة المرور وتجاوز Passkey
        if not await handle_password_entry(page, account['password']):
            raise Exception("فشل في تجاوز Passkey أو إدخال كلمة المرور")

        # فحص الجهاز
        has_console, console_info, login_success = await check_console_availability_with_refresh(page)
        result['success'] = login_success
        result['has_console'] = has_console
        result['console_info'] = console_info
        
        await browser.close()
        await p.stop()
    except Exception as e:
        # تنظيف رسالة الخطأ لتكون مفهومة
        err_msg = str(e)
        if "Timeout 30000ms" in err_msg:
            result['console_info'] = "خطأ: استغرق تسجيل الدخول وقتاً طويلاً (Timeout)"
        else:
            result['console_info'] = f"خطأ: {err_msg[:50]}"
        if p:
            await p.stop()
    return result

def parse_accounts_from_text(content: str) -> List[Dict]:
    accounts = []
    for line in content.splitlines():
        line = line.strip()
        if ':' in line and not line.startswith('#'):
            parts = line.split(':', 1)
            if len(parts) == 2:
                accounts.append({'email': parts[0].strip(), 'password': parts[1].strip()})
    return accounts
