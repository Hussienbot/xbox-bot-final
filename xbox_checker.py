import asyncio
from playwright.async_api import async_playwright
from typing import Dict, List, Tuple
from datetime import datetime

DEFAULT_TIMEOUT = 60000

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

async def handle_password_entry(page, account_email: str, password: str) -> bool:
    """محاولة إدخال كلمة المرور بعد ظهور حقلها أو زر Sign in another way"""
    try:
        # انتظار ظهور حقل كلمة المرور أو البدائل
        await page.wait_for_selector(
            "input[type='password'], input[name='passwd'], button:has-text('Sign in another way')",
            timeout=15000
        )
        # إذا ظهر حقل كلمة المرور مباشرة
        if await page.locator("input[type='password'], input[name='passwd']").count() > 0:
            await page.fill("input[type='password'], input[name='passwd']", password)
            await asyncio.sleep(5)
            return True
        # إذا ظهر زر "Sign in another way"
        if await page.locator("button:has-text('Sign in another way')").count() > 0:
            await page.click("button:has-text('Sign in another way')")
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)
        # قد يظهر "Use your password"
        if await page.locator("button:has-text('Use your password')").count() > 0:
            await page.click("button:has-text('Use your password')")
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)
        # الآن يجب أن يظهر حقل كلمة المرور
        await page.wait_for_selector("input[type='password'], input[name='passwd']", timeout=10000)
        await page.fill("input[type='password'], input[name='passwd']", password)
        await asyncio.sleep(5)
        return True
    except Exception as e:
        print(f"خطأ في handle_password_entry: {e}")
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
        browser = await p.chromium.launch(
            headless=headless,
            args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-features=WebAuthentication'
            ]
        )
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        page = await context.new_page()

        login_url = "https://login.live.com/login.srf?wa=wsignin1.0&rpsnv=16&rver=7.0.0000.0&wp=MBI_SSL&wreply=https:%2F%2Fwww.xbox.com%2Fen-US%2Fplay%2Fconsoles&id=292540&prompt=login"
        await page.goto(login_url, timeout=DEFAULT_TIMEOUT)
        await page.wait_for_load_state("networkidle")

        # إدخال البريد
        await page.fill("input[name='loginfmt']", account['email'])
        await asyncio.sleep(7)
        await page.click("input[type='submit']")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(3)

        # التحقق مما إذا كانت شاشة Passkey عالقة (لا يوجد حقل كلمة مرور ولا زر بديل)
        has_pwd = await page.locator("input[type='password'], input[name='passwd']").count() > 0
        has_alt = await page.locator("button:has-text('Sign in another way'), a:has-text('Sign in another way')").count() > 0
        if not has_pwd and not has_alt:
            # شاشة Passkey محتملة -> نغلق الصفحة ونفتح صفحة جديدة (محاكاة فتح علامة تبويب جديدة)
            print("⚠️ شاشة Passkey محتملة، نغلق الصفحة الحالية ونفتح صفحة جديدة...")
            await page.close()
            page = await context.new_page()
            await page.goto(login_url, timeout=DEFAULT_TIMEOUT)
            await page.wait_for_load_state("networkidle")
            await page.fill("input[name='loginfmt']", account['email'])
            await asyncio.sleep(7)
            await page.click("input[type='submit']")
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)
            # الآن يجب أن يظهر "Sign in another way" أو حقل كلمة المرور

        # معالجة كلمة المرور
        if not await handle_password_entry(page, account['email'], account['password']):
            raise Exception("فشل في إدخال كلمة المرور")

        await page.click("input[type='submit']")
        await page.wait_for_load_state("networkidle")

        # تجاوز "Stay signed in"
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
