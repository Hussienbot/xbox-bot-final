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
        
        legacy_ua = "Mozilla/5.0 (BlackBerry; U; BlackBerry 9900; en) AppleWebKit/534.11+ (KHTML, like Gecko) Version/7.1.0.342 Mobile Safari/534.11+"
        
        context = await browser.new_context(user_agent=legacy_ua, viewport={'width': 360, 'height': 640})
        page = await context.new_page()
        page.set_default_timeout(TIMEOUT_VAL)
        
        login_url = f"https://login.live.com/login.srf?wa=wsignin1.0&rpsnv=15&ct={int(datetime.now().timestamp())}&rver=7.0.6737.0&wp=MBI_SSL&wreply=https:%2f%2fwww.xbox.com%2fen-US%2fplay%2fconsoles"
        
        await page.goto(login_url, wait_until="domcontentloaded")

        # 1. إدخال البريد
        email_input = page.locator("input[name='loginfmt'], input[type='email']")
        await email_input.wait_for(state="visible")
        await email_input.fill(account['email'])
        await page.locator("input[type='submit'], #idSIButton9").click()
        await asyncio.sleep(3)

        # 2. معالجة شاشة "Sign in another way" إذا ظهرت
        try:
            # البحث عن أي نص يحتوي على "use your password" (حساسية الأحرف لا تهم)
            use_password_btn = page.locator("text=/use your password/i")
            if await use_password_btn.count() > 0:
                await use_password_btn.first.click()
                await asyncio.sleep(2)
            else:
                # قد يكون الخيار مخفياً خلف "Show more options"
                more_options = page.locator("text=/show more options/i")
                if await more_options.count() > 0:
                    await more_options.first.click()
                    await asyncio.sleep(1)
                    # بعد ظهور الخيارات، نضغط على Use your password
                    use_password_btn = page.locator("text=/use your password/i")
                    if await use_password_btn.count() > 0:
                        await use_password_btn.first.click()
                        await asyncio.sleep(2)
        except Exception as e:
            # إذا لم نجد الخيارات، نكمل عادي (قد لا تظهر هذه الشاشة)
            pass

        # 3. إدخال كلمة المرور
        password_input = page.locator("input[type='password'], input[name='passwd']")
        await password_input.wait_for(state="visible", timeout=20000)
        await password_input.fill(account['password'])
        
        await page.locator("input[type='submit'], #idSIButton9").click()
        await asyncio.sleep(5)

        # 4. تخطي شاشة "Stay signed in" إذا ظهرت
        try:
            yes_btn = page.locator("input[value='Yes'], #idSIButton9")
            if await yes_btn.is_visible(timeout=5000):
                await yes_btn.click()
                await asyncio.sleep(3)
        except:
            pass

        # 5. فحص الجهاز
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
