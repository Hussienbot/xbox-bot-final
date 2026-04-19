import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from typing import Dict, List, Tuple
from datetime import datetime

# المهلة الزمنية الافتراضية للعمليات الفردية
TIMEOUT_VAL = 25000 

async def check_console_availability_with_refresh(page) -> Tuple[bool, str, bool]:
    url = "https://www.xbox.com/en-US/play/consoles"
    try:
        # التوجه المباشر لصفحة الأجهزة
        await page.goto(url, timeout=TIMEOUT_VAL, wait_until="domcontentloaded")
        await asyncio.sleep(5) # وقت كافٍ لتحميل حالة الأجهزة
        
        text = (await page.inner_text("body")).lower()
        
        if "play your console remotely" in text or "start remote play" in text:
            return True, "يوجد جهاز", True
        if "set up your console" in text or "no consoles found" in text or "connect a console" in text:
            return False, "مسجل ولا يوجد جهاز", True
            
        # إذا لم نجد النصوص السابقة، ربما نحتاج لانتظار أطول قليلاً
        await asyncio.sleep(3)
        text = (await page.inner_text("body")).lower()
        if "play your console" in text:
            return True, "يوجد جهاز", True
            
    except Exception:
        pass
    return False, "مسجل (تحقق يدوي مطلوب)", True

async def handle_password_entry(page, password: str) -> bool:
    try:
        # إغلاق أي نافذة منبثقة (Escape)
        await page.keyboard.press("Escape")
        
        # البحث عن حقل كلمة المرور
        password_input = page.locator("input[type='password'], input[name='passwd'], #i0118")
        
        # محاولة تجاوز Passkey إذا ظهرت
        if not await password_input.is_visible():
            try:
                pwd_option = page.locator("text='Use your password', text='Password'")
                if await pwd_option.is_visible(timeout=5000):
                    await pwd_option.click()
                    await asyncio.sleep(2)
            except:
                pass

        await password_input.wait_for(state="visible", timeout=15000)
        await password_input.fill(password)
        
        # النقر على زر الدخول
        await page.locator("input[type='submit'], #idSIButton9").click()
        await asyncio.sleep(3)
        
        # تخطي شاشات ما بعد تسجيل الدخول بسرعة
        try:
            # Stay signed in?
            yes_btn = page.locator("#idSIButton9, input[value='Yes']")
            if await yes_btn.is_visible(timeout=5000):
                await yes_btn.click()
        except:
            pass
            
        return True
    except Exception:
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
        
        # تعطيل WebAuthn (Passkey) برمجياً
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 720}
        )
        await context.add_init_script("delete window.PublicKeyCredential;")
        
        page = await context.new_page()
        
        # رابط تسجيل دخول مباشر
        login_url = f"https://login.live.com/login.srf?wa=wsignin1.0&rpsnv=15&ct={int(datetime.now().timestamp())}&rver=7.0.6737.0&wp=MBI_SSL&wreply=https:%2f%2fwww.xbox.com%2fen-US%2fplay%2fconsoles"
        
        await page.goto(login_url, timeout=TIMEOUT_VAL, wait_until="domcontentloaded")

        # إدخال البريد
        email_input = page.locator("input[name='loginfmt'], input[type='email']")
        await email_input.wait_for(state="visible", timeout=TIMEOUT_VAL)
        await email_input.fill(account['email'])
        await page.locator("input[type='submit'], #idSIButton9").click()
        await asyncio.sleep(3)

        # إدخال كلمة المرور
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
        result['console_info'] = f"خطأ: {str(e)[:50]}"
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
