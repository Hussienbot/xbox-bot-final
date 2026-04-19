import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from typing import Dict, List, Tuple
from datetime import datetime
import base64

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
        except:
            continue
    return False, "لم يتم العثور على جهاز", False

async def take_screenshot(page, name: str):
    """التقاط صورة وحفظها كـ base64 للطباعة (أو يمكن حفظها كملف)"""
    try:
        screenshot = await page.screenshot()
        b64 = base64.b64encode(screenshot).decode('utf-8')
        print(f"📸 Screenshot {name}: data:image/png;base64,{b64[:100]}... (طول {len(b64)})")
        # يمكنك أيضًا حفظ الملف إذا كان لديك حق الوصول
        # with open(f"{name}.png", "wb") as f:
        #     f.write(screenshot)
    except Exception as e:
        print(f"فشل في التقاط الصورة: {e}")

async def handle_password_entry(page, account_email: str, password: str) -> bool:
    """محاولة متقدمة للتعامل مع شاشة Passkey و Sign in another way"""
    try:
        # انتظار ظهور أي عنصر تفاعلي
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(3)

        # 1. محاولة الضغط على Enter/Space لتجاوز نافذة passkey
        await page.keyboard.press("Escape")  # قد تغلق النافذة
        await asyncio.sleep(1)
        await page.keyboard.press("Enter")
        await asyncio.sleep(1)
        await page.keyboard.press("Space")
        await asyncio.sleep(1)

        # 2. البحث عن أي زر يحوي "Sign in another way" أو "Other ways"
        found = False
        selectors = [
            "button:has-text('Sign in another way')",
            "button:has-text('Other ways to sign in')",
            "a:has-text('Sign in another way')",
            "div[role='button']:has-text('Sign in another way')",
            "button:has-text('Other ways')",
            "button:has-text('Use a password')",
            "button:has-text('Use your password')"
        ]
        for selector in selectors:
            try:
                if await page.locator(selector).count() > 0:
                    await page.click(selector, timeout=3000)
                    print(f"✅ تم النقر على {selector}")
                    found = True
                    await page.wait_for_load_state("networkidle")
                    await asyncio.sleep(2)
                    break
            except:
                continue
        
        if not found:
            # إذا لم نجد أي زر، ننتظر ثواني إضافية ونحاول مرة أخرى
            print("⚠️ لم يتم العثور على زر 'Sign in another way'، ننتظر 5 ثوانٍ...")
            await asyncio.sleep(5)
            for selector in selectors:
                try:
                    if await page.locator(selector).count() > 0:
                        await page.click(selector, timeout=3000)
                        found = True
                        break
                except:
                    continue
        
        # 3. الآن نبحث عن حقل كلمة المرور
        try:
            await page.wait_for_selector("input[type='password']", timeout=15000)
            await page.fill("input[type='password']", password)
            await asyncio.sleep(5)
            return True
        except:
            # إذا لم يظهر حقل كلمة المرور، نحاول النقر على "Use password" إذا ظهر
            try:
                await page.click("button:has-text('Use your password')", timeout=3000)
                await page.wait_for_selector("input[type='password']", timeout=10000)
                await page.fill("input[type='password']", password)
                await asyncio.sleep(5)
                return True
            except:
                pass
        
        # فشل كامل
        await take_screenshot(page, "password_failure")
        return False
        
    except Exception as e:
        print(f"استثناء في handle_password_entry: {e}")
        await take_screenshot(page, "password_exception")
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
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        page = await context.new_page()

        await page.goto("https://www.xbox.com/en-US/auth/msa?action=logIn&returnUrl=http%3A%2F%2Fwww.xbox.com%2Fen-US%2Fplay%2Fconsoles", timeout=DEFAULT_TIMEOUT)
        await page.wait_for_load_state("networkidle")

        # إدخال البريد
        await page.fill("input[type='email']", account['email'])
        await asyncio.sleep(7)  # انتظار 7 ثواني

        # الضغط على Next
        try:
            await page.click("input[type='submit']", timeout=5000)
        except:
            await page.keyboard.press("Enter")
        
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)

        # معالجة كلمة المرور والشاشات البديلة
        success = await handle_password_entry(page, account['email'], account['password'])
        if not success:
            raise Exception("فشل في إدخال كلمة المرور بعد المحاولات")

        # الضغط على زر تسجيل الدخول
        try:
            await page.click("input[type='submit']", timeout=5000)
        except:
            await page.keyboard.press("Enter")
        
        await page.wait_for_load_state("networkidle")

        # "Stay signed in?"
        try:
            await page.click("input[value='Yes']", timeout=3000)
        except:
            pass

        # فحص وجود جهاز
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
