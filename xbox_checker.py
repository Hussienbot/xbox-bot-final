import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from typing import Dict, List, Tuple
from datetime import datetime

DEFAULT_TIMEOUT = 60000

async def check_console_availability_with_refresh(page) -> Tuple[bool, str, bool]:
    # نحاول فحص الصفحة الحالية أولاً، ثم نتوجه للرابط المباشر
    urls = ["https://www.xbox.com/en-US/play/consoles", "https://www.xbox.com/play/consoles"]
    
    for url in urls:
        for attempt in range(2):
            try:
                await page.goto(url, timeout=DEFAULT_TIMEOUT)
                await page.wait_for_load_state("domcontentloaded", timeout=DEFAULT_TIMEOUT)
                await asyncio.sleep(7) # وقت كافٍ لتحميل حالة الأجهزة
                
                text = (await page.inner_text("body")).lower()
                
                if "play your console remotely" in text or "start remote play" in text:
                    return True, "يوجد جهاز", True
                if "set up your console" in text or "no consoles found" in text:
                    return False, "مسجل ولا يوجد جهاز", True
                if "sign in" in text and "finish setting up" not in text:
                    # إذا طلب تسجيل دخول مرة أخرى، نحاول الانتظار أكثر
                    await asyncio.sleep(5)
                    text = (await page.inner_text("body")).lower()
                    if "play your console remotely" in text:
                        return True, "يوجد جهاز", True
            except:
                continue
    
    return False, "تسجيل دخول غير مكتمل أو لم يتم العثور على جهاز", False

async def handle_post_login_screens(page):
    """التعامل مع شاشات ما بعد تسجيل الدخول مثل 'Stay signed in' أو 'Protect your account'"""
    try:
        # شاشة Stay signed in?
        stay_signed_in = page.locator("#idSIButton9, input[value='Yes'], text='Yes'")
        if await stay_signed_in.is_visible(timeout=5000):
            await stay_signed_in.click()
            await asyncio.sleep(2)
            
        # شاشة Protect your account / Recovery info (نحاول الضغط على 'Looks good' أو 'Not now')
        not_now = page.locator("text='Not now', text='Skip for now', #iShowSkip, .button-secondary")
        if await not_now.is_visible(timeout=5000):
            await not_now.click()
            await asyncio.sleep(2)
            
        # شاشة Break free from your password (نضغط No thanks)
        no_thanks = page.locator("text='No thanks', text='Not now'")
        if await no_thanks.is_visible(timeout=3000):
            await no_thanks.click()
            await asyncio.sleep(2)
    except:
        pass

async def handle_password_entry(page, password: str) -> bool:
    try:
        # الضغط على Escape لتجاوز أي نافذة نظام منبثقة (Passkey)
        for _ in range(2):
            await page.keyboard.press("Escape")
            await asyncio.sleep(1)

        # البحث عن حقل كلمة المرور
        password_input = page.locator("input[type='password'], input[name='passwd'], #i0118")
        
        if not await password_input.is_visible():
            try:
                # محاولة النقر على خيار "Password" إذا ظهرت قائمة خيارات
                pwd_btn = page.locator("text='Password', [role='button'][name*='Password']")
                if await pwd_btn.is_visible(timeout=5000):
                    await pwd_btn.click()
                    await asyncio.sleep(2)
            except:
                pass

        await password_input.wait_for(state="visible", timeout=15000)
        await password_input.fill(password)
        await asyncio.sleep(1)
        
        # النقر على زر الدخول
        submit_btn = page.locator("input[type='submit'], #idSIButton9")
        await submit_btn.click()
        await asyncio.sleep(3)
        
        # التعامل مع شاشات ما بعد الدخول
        await handle_post_login_screens(page)
        
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
        
        # نستخدم User Agent متوازن لتجنب Passkey وفي نفس الوقت ضمان عمل صفحة Xbox
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"
        
        context = await browser.new_context(user_agent=ua, viewport={'width': 1280, 'height': 720})
        page = await context.new_page()
        
        # رابط تسجيل الدخول المباشر
        login_url = f"https://login.live.com/login.srf?wa=wsignin1.0&rpsnv=13&ct={int(datetime.now().timestamp())}&rver=7.0.6737.0&wp=MBI_SSL&wreply=https:%2f%2fwww.xbox.com%2fen-US%2fplay%2fconsoles"
        
        await page.goto(login_url, timeout=DEFAULT_TIMEOUT)
        await page.wait_for_load_state("domcontentloaded")

        # إدخال البريد
        email_input = page.locator("input[name='loginfmt'], input[type='email'], #i0116")
        await email_input.wait_for(state="visible", timeout=DEFAULT_TIMEOUT)
        await email_input.fill(account['email'])
        
        # النقر على التالي
        await page.locator("input[type='submit'], #idSIButton9").click()
        await asyncio.sleep(3)

        # التعامل مع كلمة المرور
        if not await handle_password_entry(page, account['password']):
            raise Exception("فشل في إدخال كلمة المرور")

        # فحص الجهاز
        has_console, console_info, login_success = await check_console_availability_with_refresh(page)
        result['success'] = login_success
        result['has_console'] = has_console
        result['console_info'] = console_info
        
        await browser.close()
        await p.stop()
    except Exception as e:
        result['console_info'] = f"خطأ: {str(e)[:100]}"
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
