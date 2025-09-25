#!/usr/bin/env python3
"""
Telegram Battery Bot - Simple daily reports
"""

import os
import json
import pandas as pd
import requests
import matplotlib.pyplot as plt
import subprocess
import tempfile
import time
import signal
from pathlib import Path
import anthropic
import daily_summary
import json as _json
import call
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
def load_customers_ascii_safe(path: str = "customers.json"):
    try:
        with open(path, "r", encoding="utf-8") as f:
            customers = _json.load(f)
        # Ensure ASCII-safe
        cleaned = []
        for c in customers:
            c2 = {}
            for k, v in c.items():
                if isinstance(v, str):
                    c2[k] = v.encode('ascii', errors='ignore').decode('ascii')
                else:
                    c2[k] = v
            cleaned.append(c2)
        return cleaned
    except Exception as e:
        print(f"Failed to load customers.json: {e}")
        return []

load_dotenv()

class BatteryTelegramBot:
    def __init__(self, token):
        self.application = Application.builder().token(token).build()
        self.chat_histories = {}  # Store chat history per chat_id
        self.max_history_messages = 20  # Limit history to last 20 messages per chat
        
        # API Configuration
        self.api_base_url = "http://91.98.200.67"
        self.data_id = "klassiche-demo-hackathon-evo-9mflyui8"  # TUM Arcisstrasse 80
        self.default_days_back = 17  # Yesterday's data by default
        
        # Customers JSON store
        self.customers = load_customers_ascii_safe()
        
        # Call configuration: prefer customer phone stored in customers.json
        self.call_phone_number = None  # resolved dynamically
        
        # Add handlers
        self.application.add_handler(CommandHandler("daily", self.daily_report))
        self.application.add_handler(CommandHandler("clear_history", self.clear_history))
        self.application.add_handler(CommandHandler("history", self.show_history))
        self.application.add_handler(CommandHandler("customer_info", self.show_customer_info))
        self.application.add_handler(CommandHandler("customers", self.list_customers))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
    
    # Simplified: removed legacy cleaning helpers
    
    def get_customer_context(self) -> str:
        for c in self.customers:
            if c.get('data_id') == self.data_id:
                parts = [f"Customer: {c.get('name','Unknown')}" ]
                if c.get('business_type'): parts.append(f"Business: {c['business_type']}")
                if c.get('building_type'): parts.append(f"Building: {c['building_type']}")
                if c.get('location'): parts.append(f"Location: {c['location']}")
                if c.get('capacity_info'): parts.append(f"Details: {c['capacity_info']}")
                if c.get('special_notes'): parts.append(f"Notes: {c['special_notes']}")
                return " | ".join(parts)
        return f"Customer: Unknown | ID: {self.data_id}"

    def get_call_phone_number(self) -> str:
        """Return phone number from the active customer record, or env fallback."""
        for c in self.customers:
            if c.get('data_id') == self.data_id:
                phone = c.get('phone_number')
                if phone:
                    return phone
        return os.environ.get('CALL_TARGET_NUMBER', '+4917623883131')

    def fetch_energy_data(self, days_back=None):
        """Fetch energy data from the API"""
        if days_back is None:
            days_back = self.default_days_back
            
        url = f"{self.api_base_url}/api/energy-data"
        params = {
            "id": self.data_id,
            "days_back": days_back
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            api_data = response.json()
            
            # Convert to pandas DataFrame like the original format
            df = pd.DataFrame(api_data['data'])
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            # Add metadata for context
            metadata = api_data.get('metadata', {})
            
            return df, metadata
            
        except requests.exceptions.RequestException as e:
            print(f"Error fetching data from API: {e}")
            # Fallback to local data if API fails
            print("Falling back to local data...")
            df = pd.read_json("data/day1.json")
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            return df, {"source": "local_fallback"}
    
    def build_daily_summary_prompt(self, days_back=None):
        """Build and return the exact daily-summary LLM prompt and the dataframe for charting."""
        df, metadata = self.fetch_energy_data(days_back)
        weather_data = requests.get('https://api.open-meteo.com/v1/forecast?latitude=48.1374&longitude=11.5755&daily=sunshine_duration,daylight_duration&timezone=Europe%2FBerlin&forecast_days=3')
        weather_json = weather_data.json()
        sun_hours_tomorrow = weather_json["daily"]["sunshine_duration"][1] / 3600
        sun_hours_today = weather_json["daily"]["sunshine_duration"][0] / 3600
        summary = daily_summary.build_daily_summary(df, sun_hours_today=sun_hours_today, sun_hours_tomorrow=sun_hours_tomorrow)
        data_source = metadata.get('source', 'api')
        requested_date = metadata.get('requested_date', 'recent')
        customer_context = self.get_customer_context()
        summary_data = json.dumps(summary, ensure_ascii=False)
        prompt = f"""You are an assistant that writes short, friendly and funny daily energy summaries for a solar+battery system. 
Use the provided data to highlight what was interesting about the day. Do not use all the data, just the most interesting bits.

CUSTOMER: {customer_context}
DATA INFO: Using {data_source} data for {requested_date}
For example:
- how sunny it was
- the sunniest hour
- when the peak price hour was and the cheapest price hour, and explain if the battery charged/discharged smartly to save money. 
- how the battery was used (charging/discharging and SOC swings)
- how much money was saved or earned
- how much energy was self-consumed versus exported
- grid dependence percentage
- CO2 only if asked not in initial summary

At the end include how many sun hours are expected tommorrow and how it will impact the energy consumptioin and prices.

Make the summary 1-3 sentences long, include as many emojis as possible, 
and keep it positive and easy to understand. Please use units and include quantity where possible.
Make it as fun as you can! Be aware that you are sending text messages on the phone, so use appropriate formatting.

Here is the data:
{summary_data}

Now write a natural-language summary and just return the summary text, without any extra commentary."""
        return prompt, df

    async def generate_daily_summary_data(self, days_back=None):
        """Generate daily summary text and chart."""
        prompt, df = self.build_daily_summary_prompt(days_back)
        api_key = os.environ.get('ANTHROPIC_API_KEY', '').strip()
        client = anthropic.Anthropic(api_key=api_key)
        try:
            response = client.messages.create(
                model='claude-3-5-haiku-20241022',
                max_tokens=300,
                messages=[{'role': 'user', 'content': prompt}]
            )
        except Exception as e:
            print(f"Error generating daily summary: {e}")
            return "⚠️ Unable to generate daily summary right now. Please try again later.", ['telegram_chart.png']
        reply_parts = []
        for block in response.content:
            text = getattr(block, 'text', None)
            if text is None and isinstance(block, dict):
                text = block.get('text')
            if text:
                reply_parts.append(text)
        message = ''.join(reply_parts) if reply_parts else ''
        # Generate charts via battery_graphics (Puppeteer). Fallback to matplotlib if it fails.
        try:
            chart_paths = self.generate_charts_with_battery_graphics(df)
            if chart_paths:
                return message, chart_paths
        except Exception as e:
            print("battery_graphics capture failed:", e)

        # Fallback chart (matplotlib) if Puppeteer flow fails
        try:
            plt.figure(figsize=(10,4))
            plt.plot(df['timestamp'], df['pv_profile'], label='PV production')
            plt.plot(df['timestamp'], df['pv_utilized_kw_opt'], label='PV used')
            plt.fill_between(df['timestamp'], 0, df['pv_to_battery_kw_opt'], color='green', alpha=0.3, label='Battery charging')
            plt.fill_between(df['timestamp'], 0, df['battery_to_load_kw_opt'], color='red', alpha=0.3, label='Battery discharging')
            plt.xlabel('Time')
            plt.ylabel('kW')
            plt.title('Energy flow today')
            plt.legend()
            plt.tight_layout()
            plt.savefig('telegram_chart.png')
            plt.close()
            return message, ['telegram_chart.png']
        except Exception as e:
            print('Matplotlib fallback failed:', e)
            return message, []

    def wait_for_http(self, url: str, timeout_seconds: int = 30) -> bool:
        start = time.time()
        while time.time() - start < timeout_seconds:
            try:
                r = requests.get(url, timeout=2)
                if r.status_code < 500:
                    return True
            except Exception:
                pass
            time.sleep(0.5)
        return False

    def generate_charts_with_battery_graphics(self, df: pd.DataFrame):
        """Use the battery_graphics app + Puppeteer to export chart PNGs for the provided dataframe.
        Returns a list of absolute file paths to the images.
        """
        project_root = Path(__file__).resolve().parent
        graphics_dir = project_root / 'battery_graphics'
        screenshots_dir = graphics_dir / 'screenshots'
        screenshots_dir.mkdir(parents=True, exist_ok=True)

        # Serialize dataframe to a temporary JSON file matching EnergyDataItem[]
        tmp_json = None
        try:
            # Ensure timestamps are ISO strings
            df_out = df.copy()
            if not pd.api.types.is_string_dtype(df_out['timestamp']):
                df_out['timestamp'] = df_out['timestamp'].astype(str)
            # Write temp file
            tmp_fd, tmp_path = tempfile.mkstemp(prefix='energy_data_', suffix='.json')
            os.close(tmp_fd)
            tmp_json = Path(tmp_path)
            with open(tmp_json, 'w', encoding='utf-8') as f:
                json.dump(df_out.to_dict(orient='records'), f, ensure_ascii=False)

            # Ensure dev server is running. Allow override via env BATTERY_SITE_URL.
            vite_url = os.environ.get('BATTERY_SITE_URL', 'http://localhost:8080/')
            spawned = False
            dev_proc = None
            if not self.wait_for_http(vite_url, timeout_seconds=2):
                # Start Vite dev server
                dev_proc = subprocess.Popen(
                    ['npm', 'run', 'dev'],
                    cwd=str(graphics_dir),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )
                spawned = True
                # Wait up to 30s for server to be ready
                if not self.wait_for_http(vite_url, timeout_seconds=30):
                    # Stop spawned server and raise
                    try:
                        dev_proc.terminate()
                    except Exception:
                        pass
                    raise RuntimeError(f'Vite dev server did not become ready on {vite_url}')

            # Run the capture script
            cmd = [
                'node',
                'scripts/capture-charts.mjs',
                '--data', str(tmp_json),
                '--site', vite_url,
                '--out', 'screenshots',
                '--delay', os.environ.get('CAPTURE_DELAY_MS', '3000')
            ]
            result = subprocess.run(cmd, cwd=str(graphics_dir), capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                print('capture-charts stdout:', result.stdout)
                print('capture-charts stderr:', result.stderr)
                raise RuntimeError('capture-charts failed')

            energy_path = screenshots_dir / 'energy-chart.png'
            battery_path = screenshots_dir / 'battery-price-chart.png'
            paths = []
            if energy_path.exists():
                paths.append(str(energy_path))
            if battery_path.exists():
                paths.append(str(battery_path))
            return paths
        finally:
            # Cleanup temp json
            try:
                if tmp_json and Path(tmp_json).exists():
                    os.remove(tmp_json)
            except Exception:
                pass
            # Attempt to stop dev server if we started it (best-effort)
            try:
                if 'dev_proc' in locals() and dev_proc is not None and dev_proc.poll() is None:
                    dev_proc.terminate()
            except Exception:
                pass
    
    def add_to_history(self, chat_id: int, role: str, message: str):
        """Add a message to chat history"""
        if chat_id not in self.chat_histories:
            self.chat_histories[chat_id] = []
        
        # Add message with timestamp
        self.chat_histories[chat_id].append({
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'role': role,  # 'user' or 'assistant'
            'message': message
        })
        
        # Keep only the last N messages
        if len(self.chat_histories[chat_id]) > self.max_history_messages:
            self.chat_histories[chat_id] = self.chat_histories[chat_id][-self.max_history_messages:]
    
    def get_history_text(self, chat_id: int) -> str:
        """Get chat history as formatted text"""
        if chat_id not in self.chat_histories or not self.chat_histories[chat_id]:
            return "No previous conversation history."
        
        history_parts = []
        for msg in self.chat_histories[chat_id]:
            role_label = "👤 User" if msg['role'] == 'user' else "🤖 Assistant"
            history_parts.append(f"{role_label} ({msg['timestamp']}): {msg['message']}")
        
        return "\n".join(history_parts)
    
    async def clear_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Clear chat history for this chat"""
        chat_id = update.effective_chat.id
        if chat_id in self.chat_histories:
            del self.chat_histories[chat_id]
        await update.message.reply_text("🧹 Chat history cleared! Starting fresh.")
    
    async def show_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show current chat history"""
        chat_id = update.effective_chat.id
        history_text = self.get_history_text(chat_id)
        await update.message.reply_text(f"📜 **Chat History:**\n\n{history_text}")
    
    async def show_customer_info(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show current customer information"""
        customer = None
        for c in self.customers:
            if c.get('data_id') == self.data_id:
                customer = c
                break
        if not customer:
            await update.message.reply_text(f"❌ Customer not found for ID: {self.data_id}")
            return
        def val(x):
            return x if (x is not None and x != "") else 'N/A'
        info_text = (
            "🏢 **Customer Information**\n\n"
            f"**Name:** {val(customer.get('name'))}\n"
            f"**Business:** {val(customer.get('business_type'))}\n"
            f"**Building:** {val(customer.get('building_type'))}\n"
            f"**Location:** {val(customer.get('location'))}\n"
            f"**Address:** {val(customer.get('address'))}\n\n"
            f"**Details:** {val(customer.get('capacity_info'))}\n"
            f"**Notes:** {val(customer.get('special_notes'))}\n\n"
            f"**Data ID:** `{val(customer.get('data_id'))}`"
        )
        await update.message.reply_text(info_text)
    
    async def list_customers(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List all customers from JSON"""
        if not self.customers:
            await update.message.reply_text("📋 No customers found.")
            return
        out = ["📋 **All Customers:**\n"]
        for c in self.customers:
            status = "🟢 Active" if c.get('data_id') == self.data_id else "⚪ Available"
            out.append(f"{status} **{c.get('name','Unknown')}**")
            out.append(f"   📍 {c.get('location','Unknown location')}")
            out.append(f"   🏢 {c.get('business_type','Unknown business')}")
            out.append(f"   🆔 `{c.get('data_id','')}`\n")
        await update.message.reply_text("\n".join(out))
    
    async def daily_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Daily battery report command handler"""
        chat_id = update.effective_chat.id
        
        # Generate daily summary using the reusable function
        message, chart_paths = await self.generate_daily_summary_data()
        
        # Store in chat history
        self.add_to_history(chat_id, 'user', '/daily')
        self.add_to_history(chat_id, 'assistant', f"{message} [Charts sent]")
        
        # Send response
        await update.message.reply_text(message)
        for p in chart_paths or []:
            try:
                with open(p, 'rb') as chart_file:
                    await context.bot.send_photo(chat_id=update.effective_chat.id, photo=chart_file)
            except Exception as e:
                print('Failed to send chart', p, e)
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages with agentic tool calling"""
        user_message = update.message.text
        chat_id = update.effective_chat.id
        
        
        # Get chat history for context
        chat_history = self.get_history_text(chat_id)
        
        # Load basic battery data for context using API
        df, metadata = self.fetch_energy_data()
        weather_data = requests.get('https://api.open-meteo.com/v1/forecast?latitude=48.1374&longitude=11.5755&daily=sunshine_duration,daylight_duration&timezone=Europe%2FBerlin&forecast_days=3')
        weather_json = weather_data.json()
        sun_hours_tomorrow = weather_json["daily"]["sunshine_duration"][1] / 3600
        sun_hours_today = weather_json["daily"]["sunshine_duration"][0] / 3600
        summary = daily_summary.build_daily_summary(df, sun_hours_today=sun_hours_today, sun_hours_tomorrow=sun_hours_tomorrow)
        
        # Add metadata and customer context for regular chat
        data_source = metadata.get('source', 'api')
        requested_date = metadata.get('requested_date', 'recent')
        customer_context = self.get_customer_context()
        clean_chat_history = chat_history
        summary_data = json.dumps(summary, ensure_ascii=False)
        
        # Agentic prompt with tool calling capability
        prompt = f"""You are a helpful battery assistant with access to tools. You can answer questions about the solar+battery system.

CUSTOMER: {customer_context}

CONVERSATION HISTORY:
{clean_chat_history}

CURRENT USER MESSAGE: {user_message}

AVAILABLE TOOLS:
- generate_daily_summary: Use this when the user asks for a daily summary, daily report, today's performance, or wants to know what happened today. This generates a comprehensive daily summary with charts.
- initiate_call: Use this when the user asks to talk, wants a call, requests a phone conversation, or similar. Provide a short one-sentence purpose for the call.

BATTERY DATA ({data_source} data for {requested_date}):
{summary_data}

INSTRUCTIONS:
1. If the user is asking for a daily summary/report/today's performance, respond with: "TOOL_CALL: generate_daily_summary"
2. If the user asks for a call (talk/call/phone/speak), respond with: "TOOL_CALL: initiate_call"
3. If the user is frustrated or doesn't seem to understand the answer, offer to call them (do not tool call yet).
4. Otherwise, answer their question using the battery data in 1-3 friendly sentences with emojis
5. Use conversation history for continuity and context

Respond now:"""
        
        # Call AI with tool detection
        api_key = os.environ.get('ANTHROPIC_API_KEY', '').strip()
        client = anthropic.Anthropic(api_key=api_key)
        
        try:
            response = client.messages.create(
                model='claude-3-5-haiku-20241022',
                max_tokens=200,
                messages=[{'role': 'user', 'content': prompt}]
            )
        except Exception as e:
            print(f"Error calling AI API: {e}")
            # Fallback response
            await update.message.reply_text("⚠️ Sorry, I'm having trouble processing your request right now. Please try again later.")
            return
        
        # Extract response
        reply_parts = []
        for block in response.content:
            text = getattr(block, 'text', None)
            if text is None and isinstance(block, dict):
                text = block.get('text')
            if text:
                reply_parts.append(text)
        ai_response = ''.join(reply_parts) if reply_parts else ''
        
        # Check if AI wants to call a tool
        if "TOOL_CALL: generate_daily_summary" in ai_response:
            # Generate daily summary
            summary_message, chart_paths = await self.generate_daily_summary_data()
            
            # Store in chat history
            self.add_to_history(chat_id, 'user', user_message)
            self.add_to_history(chat_id, 'assistant', f"{summary_message} [Charts sent]")
            
            # Send daily summary response
            await update.message.reply_text(summary_message)
            for p in chart_paths or []:
                try:
                    with open(p, 'rb') as chart_file:
                        await context.bot.send_photo(chat_id=update.effective_chat.id, photo=chart_file)
                except Exception as e:
                    print('Failed to send chart', p, e)
        elif "TOOL_CALL: initiate_call" in ai_response:
            # Build prompt by reusing the exact daily-summary LLM prompt
            prompt_text, _df = self.build_daily_summary_prompt()
            # Also build a custom first message using Anthropic with recent chat history
            chat_context = self.get_history_text(chat_id)
            fm_prompt = f"""You are a voice assistant calling the user about their solar+battery energy day.
Given the following conversation history and the fact that the call is being initiated now, write a single, friendly, concise first sentence to start the call.
It should reference the user's last request where relevant and briefly mention why you are calling.
Keep it natural and spoken, 10-20 words, no emojis.

CONVERSATION HISTORY (most recent last):
{chat_context}

Return only the one sentence to say on the call."""
            api_key = os.environ.get('ANTHROPIC_API_KEY', '').strip()
            client = anthropic.Anthropic(api_key=api_key)
            first_message = None
            try:
                fm_resp = client.messages.create(
                    model='claude-3-5-haiku-20241022',
                    max_tokens=60,
                    messages=[{'role': 'user', 'content': fm_prompt}]
                )
                parts = []
                for block in fm_resp.content:
                    text = getattr(block, 'text', None)
                    if text is None and isinstance(block, dict):
                        text = block.get('text')
                    if text:
                        parts.append(text)
                first_message = ''.join(parts).strip()
            except Exception as e:
                print("Failed to generate first message:", e)
                first_message = None

            try:
                target_number = self.get_call_phone_number()
                call.submit_batch_call(target_number, prompt=prompt_text, first_message=first_message)
                self.add_to_history(chat_id, 'user', user_message)
                self.add_to_history(chat_id, 'assistant', f"📞 Call initiated. First line: {first_message or '[default]'}")
                await update.message.reply_text('📞 Initiating a call now. We will reach out shortly.')
            except Exception as e:
                await update.message.reply_text(f"⚠️ Could not initiate call: {e}")
        else:
            # Regular response
            self.add_to_history(chat_id, 'user', user_message)
            self.add_to_history(chat_id, 'assistant', ai_response)
            await update.message.reply_text(ai_response)
    
    def run(self):
        """Start the bot"""
        print("Battery Bot starting...")
        self.application.run_polling()

if __name__ == "__main__":
    BOT_TOKEN = "8412880146:AAETDw8AGPSWU4WpdT3C83e3XQDnFPld3E8"
    bot = BatteryTelegramBot(BOT_TOKEN)
    bot.run()