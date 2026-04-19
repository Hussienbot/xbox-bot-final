import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from typing import Dict, List, Tuple
from datetime import datetime

DEFAULT_TIMEOUT = 60000

async def check_console_availability_with_refresh(page) -> Tuple[bool, str, bool]:
    console_url = "https://www.xbox.com/en-US/play/consoles"
    for attempt in range(3):
        try:
            await page.goto(console_url, timeout=60000)
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)
            text = (await page.inner_text('body')).lower()
            if "play your console remotely" in text:
                return True, "يوجد جهاز", True
            if "set up your console" in text:
                return False, "مسجل ولا يوجد جهاز", True
            if "sign in to finish setting up" in text:
                return False, "تسجيل دخول غير مكتمل", False
        except Exception as e:
            continue
    return False, "لم يتم العثور على جهاز", False

# الدالة المعدلة التي تتعامل مع "Sign in another way" و "Use your password"
async def handle_password_entry(page, account_email: str, password: str) -> bool:
    """
    التعامل مع جميع طرق إدخال كلمة المرور:
    - حقل كلمة المرور المباشر
    - خيار "Sign in another way" ثم "Use your password"
    - خيار "Use a passkey" أو "Use a password"
    """
    try:
        # انتظار ظهور أي من الخيارات (حقل كلمة المرور أو أزرار بديلة)
        await page.wait_for_selector(
            "input[type='password'], button:has-text('Sign in another way'), button:has-text('Use a password'), button:has-text('Use your password'), button:has-text('Other ways to sign in')",
            timeout=15000
        )
        
        # 1. إذا ظهر حقل كلمة المرور مباشرة
        if await page.locator("input[type='password']").count() > 0:
            await page.fill("input[type='password']", password)
            await asyncio.sleep(5)
            return True
        
        # 2. إذا ظهر خيار "Sign in another way" أو "Other ways to sign in"
        other_way_selectors = [
            "button:has-text('Sign in another way')",
            "button:has-text('Other ways to sign in')",
            "a:has-text('Sign in another way')"
        ]
        for selector in other_way_selectors:
            if await page.locator(selector).count() > 0:
                await page.click(selector)
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(2)
                break
        
        # 3. الآن نبحث عن "Use your password" أو "Use a password"
        use_password_selectors = [
            "button:has-text('Use your password')",
            "button:has-text('Use a password')",
            "button:has-text('Use password')"
        ]
        for selector in use_password_selectors:
            if await page.locator(selector).count() > 0:
                await page.click(selector)
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(2)
                break
        
        # 4. أخيرًا، انتظر حقل كلمة المرور وأدخلها
        await page.wait_for_selector("input[type='password']", timeout=10000)
        await page.fill("input[type='password']", password)
        await asyncio.sleep(5)
        return True
        
    except Exception as e:
        print(f"خطأ في handle_password_entry: {e}")
        # طباعة جزء من الصفحة لمعرفة المشكلة
        try:
            content = await page.content()
            print(content[:1000])
        except:
            pass
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
        browser = await p.chromium.launch(headless=headless, args=['--no-sandbox'])
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        page = await context.new_page()
        await page.goto("https://www.xbox.com/en-US/auth/msa?action=logIn&returnUrl=http%3A%2F%2Fwww.xbox.com%2Fen-US%2Fplay%2Fconsoles", timeout=DEFAULT_TIMEOUT)
        await page.wait_for_load_state("networkidle")
        await page.fill("input[type='email']", account['email'])
        await asyncio.sleep(7)
        await page.click("input[type='submit']")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(3)
        
        password_success = await handle_password_entry(page, account['email'], account['password'])
        if not password_success:
            raise Exception("فشل في إدخال كلمة المرور")
        
        await page.click("input[type='submit']")
        await page.wait_for_load_state("networkidle")
        try:
            await page.click("input[value='Yes']", timeout=3000)
        except:
            pass
        
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
