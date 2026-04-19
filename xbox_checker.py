# xbox_checker.py - الحل النهائي للتعامل مع نافذة كلمة المرور المنبثقة
import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from typing import Dict, List, Tuple
from datetime import datetime

DEFAULT_TIMEOUT = 90000

async def process_account(account: Dict, headless: bool = True) -> Dict:
    """
    معالجة حساب واحد: تسجيل الدخول إلى Xbox والتحقق من وجود جهاز.
    يتعامل مع النافذة المنبثقة لكلمة المرور باستخدام page.context.expect_page().
    """
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
                '--disable-popup-blocking'   # منع حظر النوافذ المنبثقة
            ]
        )
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = await context.new_page()

        # 1. الذهاب إلى صفحة تسجيل الدخول إلى Microsoft
        login_url = "https://login.live.com/login.srf?wa=wsignin1.0&rpsnv=16&rver=7.0.6737.0&wp=MBI_SSL&wreply=https%3a%2f%2fwww.xbox.com%2fen-US%2fplay%2fconsoles&id=292540"
        await page.goto(login_url, timeout=DEFAULT_TIMEOUT)
        await page.wait_for_load_state("networkidle")

        # 2. إدخال البريد الإلكتروني
        email_input = await page.wait_for_selector("input[type='email'], input[name='loginfmt']", timeout=15000)
        await email_input.fill(account['email'])
        await asyncio.sleep(1)

        # 3. الضغط على زر "Next" والاستعداد لالتقاط النافذة المنبثقة
        next_button = await page.wait_for_selector("input[type='submit'], input#idSIButton9", timeout=10000)
        
        # انتظار ظهور النافذة المنبثقة بعد الضغط مباشرة
        async with page.context.expect_page(timeout=10000) as popup_info:
            await next_button.click()
        
        popup = await popup_info.value
        await popup.wait_for_load_state()

        # 4. إدخال كلمة المرور في النافذة المنبثقة
        password_field = await popup.wait_for_selector("input[type='password'], input[name='passwd']", timeout=10000)
        await password_field.fill(account['password'])
        await asyncio.sleep(1)

        # الضغط على زر تسجيل الدخول في النافذة المنبثقة
        submit_btn = await popup.wait_for_selector("input[type='submit'], input#idSIButton9", timeout=5000)
        await submit_btn.click()
        await popup.wait_for_load_state()
        await popup.close()

        # 5. العودة إلى الصفحة الأصلية
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(3)

        # 6. التعامل مع خيار "Stay signed in?" إن ظهر
        try:
            yes_btn = await page.wait_for_selector("input[value='Yes'], button:has-text('Yes')", timeout=5000)
            await yes_btn.click()
        except:
            pass

        # 7. الانتقال إلى صفحة الأجهزة للتحقق من وجود جهاز Xbox
        console_url = "https://www.xbox.com/en-US/play/consoles"
        has_console = False
        console_info = "لم يتم العثور على جهاز"
        login_success = False

        for attempt in range(3):
            try:
                await page.goto(console_url, timeout=60000)
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(2)
                text = (await page.inner_text('body')).lower()

                if "play your console remotely" in text:
                    has_console = True
                    console_info = "يوجد جهاز (يمكن اللعب عن بعد)"
                    login_success = True
                    break
                elif "set up your console" in text:
                    has_console = False
                    console_info = "مسجل ولا يوجد جهاز"
                    login_success = True
                    break
                elif "sign in to finish setting up" in text:
                    has_console = False
                    console_info = "تسجيل دخول غير مكتمل"
                    login_success = False
                    break
            except Exception:
                continue

        result['success'] = login_success
        result['has_console'] = has_console
        result['console_info'] = console_info

        await browser.close()
        await p.stop()

    except PlaywrightTimeoutError:
        result['console_info'] = "انتهت المهلة أثناء انتظار النافذة المنبثقة أو تسجيل الدخول"
        if p:
            await p.stop()
    except Exception as e:
        result['console_info'] = f"خطأ غير متوقع: {str(e)[:100]}"
        if p:
            await p.stop()

    return result


def parse_accounts_from_text(content: str) -> List[Dict]:
    """
    تحويل محتوى ملف txt إلى قائمة من الحسابات (email:password).
    """
    accounts = []
    for line in content.splitlines():
        line = line.strip()
        if ':' in line and not line.startswith('#'):
            email, pwd = line.split(':', 1)
            accounts.append({'email': email.strip(), 'password': pwd.strip()})
    return accounts
