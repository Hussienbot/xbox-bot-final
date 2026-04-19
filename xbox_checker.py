import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from typing import Dict, List, Tuple
from datetime import datetime

# مهلة زمنية كافية للعمليات
TIMEOUT_VAL = 60000 

async def check_console_availability_with_refresh(page) -> Tuple[bool, str, bool]:
    url = "https://www.xbox.com/en-US/play/consoles"
    try:
        # نستخدم User Agent حديث لضمان عمل صفحة Xbox بشكل صحيح
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

async def handle_password_entry(page, password: str) -> bool:
    try:
        # 1. محاولة الضغط على Escape لإغلاق أي نافذة نظام منبثقة فوراً
        await page.keyboard.press("Escape")
        await asyncio.sleep(2)

        # 2. البحث عن حقل كلمة المرور مباشرة أولاً
        password_input = page.locator("input[type='password'], input[name='passwd'], #i0118")
        
        # 3. إذا لم يظهر حقل الباسورد، نبحث عن زر "Use your password" أو "Password"
        if not await password_input.is_visible():
            print("Password field not visible, looking for options...")
            
            # استراتيجية البحث عن الزر الصحيح مهما كانت الخيارات الأخرى
            # نبحث عن أي عنصر يحتوي على نص "Password" أو "كلمة المرور"
            password_options = [
                "text='Use your password'", 
                "text='Password'", 
                "text='استخدام كلمة المرور'",
                "text='كلمة المرور'",
                "[role='button'][name*='password' i]",
                "[role='link'][name*='password' i]"
            ]
            
            for selector in password_options:
                try:
                    option = page.locator(selector).first
                    if await option.is_visible(timeout=3000):
                        print(f"Found password option with selector: {selector}")
                        await option.click()
                        await asyncio.sleep(3)
                        break
                except:
                    continue

        # 4. الانتظار النهائي لظهور الحقل وإدخال البيانات
        await password_input.wait_for(state="visible", timeout=20000)
        await password_input.fill(password)
        await asyncio.sleep(1)
        
        # 5. النقر على زر الدخول
        submit_btn = page.locator("input[type='submit'], #idSIButton9, #idSIButton8")
        await submit_btn.click()
        await asyncio.sleep(5)
        
        # 6. تخطي شاشات "Stay signed in" أو "Protect account"
        try:
            # نضغط "Yes" أو "Next" أو "Skip" لتجاوز أي شيء يعيق الوصول للنتيجة
            final_btns = ["input[value='Yes']", "#idSIButton9", "text='Not now'", "text='Skip'"]
            for btn_sel in final_btns:
                btn = page.locator(btn_sel)
                if await btn.is_visible(timeout=3000):
                    await btn.click()
                    await asyncio.sleep(2)
        except:
            pass
            
        return True
    except Exception as e:
        print(f"Error in handle_password_entry: {e}")
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
        browser = await p.chromium.launch(headless=headless, args=['--no-sandbox', '--disable-setuid-sandbox'])
        
        # نستخدم User Agent متوازن لتجنب Passkey وضمان عمل الموقع
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        
        context = await browser.new_context(user_agent=ua, viewport={'width': 1280, 'height': 720})
        # تعطيل WebAuthn لتقليل ظهور Passkey
        await context.add_init_script("delete window.PublicKeyCredential;")
        
        page = await context.new_page()
        page.set_default_timeout(TIMEOUT_VAL)
        
        login_url = f"https://login.live.com/login.srf?wa=wsignin1.0&rpsnv=15&ct={int(datetime.now().timestamp())}&rver=7.0.6737.0&wp=MBI_SSL&wreply=https:%2f%2fwww.xbox.com%2fen-US%2fplay%2fconsoles"
        
        await page.goto(login_url, wait_until="domcontentloaded")

        # إدخال البريد
        email_input = page.locator("input[name='loginfmt'], input[type='email']")
        await email_input.wait_for(state="visible")
        await email_input.fill(account['email'])
        await page.locator("input[type='submit'], #idSIButton9").click()
        
        await asyncio.sleep(4)

        # التعامل مع كلمة المرور وتجاوز الخيارات المتعددة
        if not await handle_password_entry(page, account['password']):
            raise Exception("فشل في الوصول لحقل كلمة المرور")

        # فحص الجهاز
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
