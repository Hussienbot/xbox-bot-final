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

async def handle_password_entry(page, email: str, password: str) -> bool:
    try:
        await page.wait_for_selector("input[type='password']", timeout=5000)
        await page.fill("input[type='password']", password)
        await asyncio.sleep(5)
        return True
    except:
        # محاولة النقر على "Use your password" إن وجد
        try:
            await page.click("button:has-text('Use your password')", timeout=3000)
            await page.wait_for_selector("input[type='password']", timeout=5000)
            await page.fill("input[type='password']", password)
            await asyncio.sleep(5)
            return True
        except:
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
        browser = await p.chromium.launch(headless=headless, args=['--no-sandbox'])  # مهم لـ Linux
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
        if not await handle_password_entry(page, account['email'], account['password']):
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
