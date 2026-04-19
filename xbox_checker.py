import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from typing import Dict, List, Tuple
from datetime import datetime

DEFAULT_TIMEOUT = 60000

async def check_console_availability_with_refresh(page) -> Tuple[bool, str, bool]:
    console_url = "https://www.xbox.com/en-US/play/consoles"
    for attempt in range(3):
        try:
            await page.goto(console_url, timeout=DEFAULT_TIMEOUT)
            await page.wait_for_load_state("domcontentloaded", timeout=DEFAULT_TIMEOUT)
            await asyncio.sleep(5)
            text = (await page.inner_text("body")).lower()
            if "play your console remotely" in text:
                return True, "يوجد جهاز", True
            if "set up your console" in text:
                return False, "مسجل ولا يوجد جهاز", True
            if "sign in to finish setting up" in text:
                return False, "تسجيل دخول غير مكتمل", False
        except Exception:
            continue
    return False, "لم يتم العثور على جهاز", False

async def handle_password_entry(page, password: str) -> bool:
    try:
        # محاولة الضغط على Escape لتجاوز أي نافذة نظام منبثقة
        for _ in range(2):
            await page.keyboard.press("Escape")
            await asyncio.sleep(1)

        # البحث عن حقل كلمة المرور - نستخدم محددات واسعة جداً
        # في الواجهات القديمة، غالباً ما يكون الاسم 'passwd'
        password_input = page.locator("input[type='password'], input[name='passwd'], #i0118")
        
        # إذا لم يظهر الحقل، قد نحتاج للنقر على "Sign in with password"
        if not await password_input.is_visible():
            try:
                # البحث عن أي زر يحتوي على كلمة Password
                pwd_btn = page.locator("text='Password', text='Use your password'")
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
        
        # استخدام User Agent لهاتف أندرويد قديم جداً (لا يدعم Passkey/WebAuthn)
        # هذا يجبر مايكروسوفت على تقديم واجهة تسجيل دخول كلاسيكية
        legacy_ua = "Mozilla/5.0 (Linux; U; Android 4.4.2; en-us; LGMS323 Build/KOT49I.MS32310c) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/30.0.0.0 Mobile Safari/537.36"
        
        context = await browser.new_context(
            user_agent=legacy_ua,
            viewport={'width': 360, 'height': 640}
        )
        page = await context.new_page()
        
        # استخدام رابط تسجيل دخول مباشر وأكثر بساطة
        login_url = "https://login.live.com/login.srf?wa=wsignin1.0&rpsnv=13&ct=" + str(int(datetime.now().timestamp())) + "&rver=7.0.6737.0&wp=MBI_SSL&wreply=https:%2f%2fwww.xbox.com%2fen-US%2fplay%2fconsoles"
        
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
            # محاولة أخيرة: إذا فشل، ربما نحن بالفعل في صفحة كلمة المرور
            pass

        # التعامل مع شاشة البقاء مسجلاً (إذا ظهرت)
        try:
            await page.locator("input[type='submit'], #idSIButton9").click(timeout=5000)
        except:
            pass

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
