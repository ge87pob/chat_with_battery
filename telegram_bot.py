#!/usr/bin/env python3
"""
Telegram Battery Bot - Simple daily reports
"""

import os
import json
import pandas as pd
import requests
import matplotlib.pyplot as plt
import anthropic
import daily_summary
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

load_dotenv()

class BatteryTelegramBot:
    def __init__(self, token):
        self.application = Application.builder().token(token).build()
        self.chat_histories = {}  # Store chat history per chat_id
        self.max_history_messages = 20  # Limit history to last 20 messages per chat
        
        # Add handlers
        self.application.add_handler(CommandHandler("daily", self.daily_report))
        self.application.add_handler(CommandHandler("clear_history", self.clear_history))
        self.application.add_handler(CommandHandler("history", self.show_history))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
    
    async def generate_daily_summary_data(self):
        """Generate daily summary data and chart - callable by LLM as a tool"""
        # Load data
        df = pd.read_json("data/day1.json")
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # Fetch weather
        weather_data = requests.get('https://api.open-meteo.com/v1/forecast?latitude=48.1374&longitude=11.5755&daily=sunshine_duration,daylight_duration&timezone=Europe%2FBerlin&forecast_days=3')
        weather_json = weather_data.json()
        sun_hours_tomorrow = weather_json["daily"]["sunshine_duration"][1] / 3600
        sun_hours_today = weather_json["daily"]["sunshine_duration"][0] / 3600
        
        # Build advanced summary
        summary = daily_summary.build_daily_summary(df, sun_hours_today=sun_hours_today, sun_hours_tomorrow=sun_hours_tomorrow)
        
        # AI prompt for daily summary
        prompt = """
You are an assistant that writes short, friendly and funny daily energy summaries for a solar+battery user. 
Use the provided data to highlight what was interesting about the day. Do not use all the data, just the most interesting bits.
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

Make the summary 1–3 sentences long, include as many emojis as possible, 
and keep it positive and easy to understand. Please use units and include quantity where possible.
Make it as fun as you can! Be aware that you are sending text messages on the phone, so use appropriate formatting.

Here is the data:
{summary_json}

Now write a natural-language summary and just return the summary text, without any extra commentary.
        """
        
        # Call AI for summary
        api_key = os.environ.get('ANTHROPIC_API_KEY', '').strip()
        client = anthropic.Anthropic(api_key=api_key)
        user_input = prompt.format(summary_json=json.dumps(summary, ensure_ascii=False))
        
        response = client.messages.create(
            model='claude-3-5-haiku-20241022',
            max_tokens=300,
            messages=[{'role': 'user', 'content': user_input}]
        )
        
        # Extract text
        reply_parts = []
        for block in response.content:
            text = getattr(block, 'text', None)
            if text is None and isinstance(block, dict):
                text = block.get('text')
            if text:
                reply_parts.append(text)
        message = ''.join(reply_parts) if reply_parts else ''
        
        # Create chart
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
        
        return message, 'telegram_chart.png'
    
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
    
    async def daily_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Daily battery report command handler"""
        chat_id = update.effective_chat.id
        
        # Generate daily summary using the reusable function
        message, chart_path = await self.generate_daily_summary_data()
        
        # Store in chat history
        self.add_to_history(chat_id, 'user', '/daily')
        self.add_to_history(chat_id, 'assistant', f"{message} [Chart sent]")
        
        # Send response
        await update.message.reply_text(message)
        with open(chart_path, 'rb') as chart_file:
            await context.bot.send_photo(chat_id=update.effective_chat.id, photo=chart_file)
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages with agentic tool calling"""
        user_message = update.message.text
        chat_id = update.effective_chat.id
        
        # Get chat history for context
        chat_history = self.get_history_text(chat_id)
        
        # Load basic battery data for context
        df = pd.read_json("data/day1.json")
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        weather_data = requests.get('https://api.open-meteo.com/v1/forecast?latitude=48.1374&longitude=11.5755&daily=sunshine_duration,daylight_duration&timezone=Europe%2FBerlin&forecast_days=3')
        weather_json = weather_data.json()
        sun_hours_tomorrow = weather_json["daily"]["sunshine_duration"][1] / 3600
        sun_hours_today = weather_json["daily"]["sunshine_duration"][0] / 3600
        summary = daily_summary.build_daily_summary(df, sun_hours_today=sun_hours_today, sun_hours_tomorrow=sun_hours_tomorrow)
        
        # Agentic prompt with tool calling capability
        prompt = f"""
You are a helpful battery assistant with access to tools. You can answer questions about the user's solar battery system and take actions based on their requests.

CONVERSATION HISTORY:
{chat_history}

CURRENT USER MESSAGE: {user_message}

AVAILABLE TOOLS:
- generate_daily_summary: Use this when the user asks for a daily summary, daily report, today's performance, or wants to know what happened today. This generates a comprehensive daily summary with charts.

DAILY BATTERY DATA (for answering other questions):
{json.dumps(summary, ensure_ascii=False)}

INSTRUCTIONS:
1. If the user is asking for a daily summary/report/today's performance, respond with: "TOOL_CALL: generate_daily_summary"
2. Otherwise, answer their question using the battery data in 1-3 friendly sentences with emojis
3. Use conversation history for continuity and context

Respond now:
        """
        
        # Call AI with tool detection
        api_key = os.environ.get('ANTHROPIC_API_KEY', '').strip()
        client = anthropic.Anthropic(api_key=api_key)
        
        response = client.messages.create(
            model='claude-3-5-haiku-20241022',
            max_tokens=200,
            messages=[{'role': 'user', 'content': prompt}]
        )
        
        # Extract response
        reply_parts = []
        for block in response.content:
            text = getattr(block, 'text', None)
            if text is None and isinstance(block, dict):
                text = block.get('text')
            if text:
                reply_parts.append(text)
        ai_response = ''.join(reply_parts) if reply_parts else ''
        
        # Check if AI wants to call the daily summary tool
        if "TOOL_CALL: generate_daily_summary" in ai_response:
            # Generate daily summary
            summary_message, chart_path = await self.generate_daily_summary_data()
            
            # Store in chat history
            self.add_to_history(chat_id, 'user', user_message)
            self.add_to_history(chat_id, 'assistant', f"{summary_message} [Chart sent]")
            
            # Send daily summary response
            await update.message.reply_text(summary_message)
            with open(chart_path, 'rb') as chart_file:
                await context.bot.send_photo(chat_id=update.effective_chat.id, photo=chart_file)
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