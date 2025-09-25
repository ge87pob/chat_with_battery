#!/usr/bin/env python3
"""
Telegram Battery Bot - Intelligenter Batterie-Assistent
Erstellt tägliche Reports mit witzigen Updates und Charts
"""

import os
import json
import pandas as pd
import requests
import matplotlib.pyplot as plt
import anthropic
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

# Lade Environment Variables
load_dotenv()
import asyncio
from datetime import datetime

class BatteryTelegramBot:
    def __init__(self, token):
        self.token = token
        self.bot = Bot(token=token)
        self.application = Application.builder().token(token).build()
        
        # Cache für tägliche Reports
        self.daily_cache = {}
        self.last_generated_date = None
        
        # Command handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("daily", self.daily_report))
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(CommandHandler("chart", self.chart_command))
        
        # Message handler for general chat
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command handler"""
        welcome_message = """
🔋 **Battery Buddy Bot** ist da! ⚡

Ich bin dein intelligenter Batterie-Assistent und sende dir täglich witzige Updates über deine Batterie-Performance!

**Verfügbare Kommandos:**
/daily - Täglichen Report anfordern
/status - Aktuellen Status abfragen
/chart - Batterie-Chart generieren
/help - Hilfe anzeigen

Lass uns deine Batterie optimieren! 💚
        """
        await update.message.reply_text(welcome_message, parse_mode='Markdown')
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Help command handler"""
        help_text = """
🔋 **Battery Buddy Bot - Hilfe**

**Kommandos:**
/daily - Generiert einen täglichen Batterie-Report
/status - Zeigt aktuellen Batterie-Status
/chart - Erstellt Batterie-Chart
/help - Diese Hilfe anzeigen

**Features:**
⚡ Tägliche Einsparungs-Updates
☀️ Sonnen-Tag Feiern
💰 Wirtschaftlichkeits-Berichte
📊 Automatische Charts
🌤️ Wetter-Prognosen

**Einfach /daily tippen für deinen ersten Report!**
        """
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def daily_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Generate and send daily battery report"""
        try:
            # Zeige "Typing..." an
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
            
            # Lade Daten und generiere Report
            report_data = await self.generate_daily_report()
            
            # Sende Text-Report
            await update.message.reply_text(report_data['message'], parse_mode='Markdown')
            
            # Sende Chart (falls vorhanden)
            if report_data.get('chart_path') and os.path.exists(report_data['chart_path']):
                with open(report_data['chart_path'], 'rb') as chart_file:
                    await context.bot.send_photo(
                        chat_id=update.effective_chat.id,
                        photo=chart_file,
                        caption="📊 Deine Batterie-Charts für heute!"
                    )
            
        except Exception as e:
            await update.message.reply_text(f"❌ Fehler beim Generieren des Reports: {str(e)}")
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show current battery status"""
        try:
            # Lade aktuelle Daten
            df = pd.read_json("data/day1.json")  # Oder aktueller Tag
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            # Berechne aktuelle Metriken
            current_soc = df['SOC_opt'].iloc[-1]
            total_savings = df['electricity_savings_step'].sum()
            current_price = df['foreign_power_costs'].iloc[-1]
            peak_price = df['foreign_power_costs'].max()
            peak_time = df.loc[df['foreign_power_costs'].idxmax(), 'timestamp'].strftime("%H:%M")
            
            # Batterie-Status bestimmen
            if current_soc > 0.8:
                battery_status = "🔋 Voll geladen"
            elif current_soc > 0.5:
                battery_status = "⚡ Gut geladen"
            elif current_soc > 0.2:
                battery_status = "🔋 Teilweise geladen"
            else:
                battery_status = "⚡ Fast leer"
            
            status_message = f"""
🔋 **Aktueller Batterie-Status**

**Ladestand:** {current_soc:.1%} {battery_status}
**Heutige Einsparungen:** {total_savings:.2f}€
**Aktueller Strompreis:** {current_price:.3f}€/kWh
**Peak-Preis heute:** {peak_price:.3f}€/kWh um {peak_time}

**Batterie ist {'🔋 geladen' if current_soc > 0.5 else '⚡ entladen'}**
            """
            
            await update.message.reply_text(status_message, parse_mode='Markdown')
            
        except Exception as e:
            await update.message.reply_text(f"❌ Fehler beim Laden des Status: {str(e)}")
    
    async def chart_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Generate and send battery chart"""
        try:
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_photo")
            
            # Lade Daten
            df = pd.read_json("data/day1.json")
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            # Chart erstellen
            plt.figure(figsize=(12, 6))
            plt.plot(df['timestamp'], df['pv_profile'], label='PV Produktion', color='orange', linewidth=2)
            plt.plot(df['timestamp'], df['pv_utilized_kw_opt'], label='PV genutzt', color='green', linewidth=2)
            plt.fill_between(df['timestamp'], 0, df['pv_to_battery_kw_opt'], color='green', alpha=0.3, label='Batterie geladen')
            plt.fill_between(df['timestamp'], 0, df['battery_to_load_kw_opt'], color='red', alpha=0.3, label='Batterie entladen')
            plt.plot(df['timestamp'], df['SOC_opt'] * 100, label='SOC %', color='blue', linewidth=2)
            
            plt.xlabel('Uhrzeit')
            plt.ylabel('kW / %')
            plt.title('🔋 Batterie-Performance heute')
            plt.legend()
            plt.grid(True, alpha=0.3)
            plt.tight_layout()
            plt.savefig('telegram_chart.png', dpi=150, bbox_inches='tight')
            plt.close()
            
            # Chart senden
            with open('telegram_chart.png', 'rb') as chart_file:
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=chart_file,
                    caption="📊 Deine Batterie-Charts für heute!"
                )
            
        except Exception as e:
            await update.message.reply_text(f"❌ Fehler beim Erstellen des Charts: {str(e)}")
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle general messages with AI integration"""
        user_message = update.message.text
        
        # Zeige "Typing..." an
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        
        try:
            # Lade aktuelle Batterie-Daten für Kontext
            df = pd.read_json("data/day1.json")
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            # Wetterdaten holen
            try:
                weather_data = requests.get('https://api.open-meteo.com/v1/forecast?latitude=48.1374&longitude=11.5755&daily=sunshine_duration,daylight_duration,temperature_2m_max,temperature_2m_min,precipitation_sum&timezone=Europe%2FBerlin&forecast_days=3')
                weather_json = weather_data.json()
                weather_info = {
                    "sun_hours_today": weather_json["daily"]["sunshine_duration"][0] / 3600,
                    "sun_hours_tomorrow": weather_json["daily"]["sunshine_duration"][1] / 3600,
                    "max_temp_today": weather_json["daily"]["temperature_2m_max"][0],
                    "min_temp_today": weather_json["daily"]["temperature_2m_min"][0],
                    "max_temp_tomorrow": weather_json["daily"]["temperature_2m_max"][1],
                    "precipitation_today": weather_json["daily"]["precipitation_sum"][0],
                    "precipitation_tomorrow": weather_json["daily"]["precipitation_sum"][1]
                }
            except:
                weather_info = {
                    "sun_hours_today": 5.0,
                    "sun_hours_tomorrow": 6.0,
                    "max_temp_today": 20.0,
                    "min_temp_today": 10.0,
                    "max_temp_tomorrow": 22.0,
                    "precipitation_today": 0.0,
                    "precipitation_tomorrow": 0.0
                }
            
            # Erstelle Kontext aus Batterie-Daten
            context_data = {
                "current_soc": df['SOC_opt'].iloc[-1],
                "total_savings": df['electricity_savings_step'].sum(),
                "solar_production": df['pv_profile'].sum(),
                "battery_charged": (df['pv_to_battery_kw_opt'].sum() + df['grid_to_battery_kw_opt'].sum()),
                "battery_discharged": (df['battery_to_load_kw_opt'].sum() + df['battery_to_grid_kw_opt'].sum()),
                "peak_price": df['foreign_power_costs'].max(),
                "peak_time": df.loc[df['foreign_power_costs'].idxmax(), 'timestamp'].strftime("%H:%M"),
                "grid_dependence": (df['grid_import_kw_opt'].sum() / df['gross_load'].sum() * 100)
            }
            
            # Erstelle AI-Prompt mit Kontext
            ai_prompt = f"""
Du bist ein intelligenter Batterie-Assistent. Du hilfst dem Nutzer bei Fragen zu seiner Solar-Batterie-Anlage.

AKTUELLE BATTERIE-DATEN:
- Ladestand: {context_data['current_soc']:.1%}
- Heutige Einsparungen: {context_data['total_savings']:.2f}€
- Solar-Produktion: {context_data['solar_production']:.1f} kWh
- Batterie geladen: {context_data['battery_charged']:.1f} kWh
- Batterie entladen: {context_data['battery_discharged']:.1f} kWh
- Peak-Preis: {context_data['peak_price']:.3f}€/kWh um {context_data['peak_time']}
- Netzabhängigkeit: {context_data['grid_dependence']:.1f}%

AKTUELLE WETTER-DATEN:
- Sonnenstunden heute: {weather_info['sun_hours_today']:.1f}h
- Sonnenstunden morgen: {weather_info['sun_hours_tomorrow']:.1f}h
- Temperatur heute: {weather_info['min_temp_today']:.1f}°C - {weather_info['max_temp_today']:.1f}°C
- Temperatur morgen: {weather_info['max_temp_tomorrow']:.1f}°C
- Niederschlag heute: {weather_info['precipitation_today']:.1f}mm
- Niederschlag morgen: {weather_info['precipitation_tomorrow']:.1f}mm

NUTZER-FRAGE: {user_message}

Antworte freundlich, hilfreich und mit vielen Emojis. Erkläre Dinge einfach und verständlich. 
Nutze die Wetterdaten um Zusammenhänge zwischen Wetter und Solar-Produktion zu erklären.
Falls die Frage nichts mit der Batterie zu tun hat, erkläre höflich, dass du nur bei Batterie-Fragen helfen kannst.
Antworte auf Deutsch und in 1-3 Sätzen.
            """
            
            # Anthropic AI aufrufen
            api_key = os.environ.get('ANTHROPIC_API_KEY')
            if not api_key:
                fallback_response = "🔋 Anthropic API Key nicht gefunden! Bitte setze die Umgebungsvariable ANTHROPIC_API_KEY."
                await update.message.reply_text(fallback_response)
                return
            
            client = anthropic.Anthropic(api_key=api_key)
            response = client.messages.create(
                model='claude-3-5-haiku-20241022',
                max_tokens=200,
                messages=[{'role': 'user', 'content': ai_prompt}]
            )
            
            # AI-Antwort extrahieren
            ai_response = ''.join([block.text for block in response.content if hasattr(block, 'text')])
            
            await update.message.reply_text(ai_response)
            
        except Exception as e:
            # Fallback bei Fehlern
            fallback_response = f"🔋 Entschuldigung, ich hatte ein Problem beim Verarbeiten deiner Frage. Versuche es nochmal oder tippe /help für Hilfe!"
            await update.message.reply_text(fallback_response)
    
    async def generate_daily_report(self):
        """Generate daily battery report (dein bestehender Code)"""
        try:
            # Lade Daten
            df = pd.read_json("data/day1.json")
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            # Wetterdaten holen
            try:
                weather_data = requests.get('https://api.open-meteo.com/v1/forecast?latitude=48.1374&longitude=11.5755&daily=sunshine_duration,daylight_duration,temperature_2m_max,temperature_2m_min,precipitation_sum&timezone=Europe%2FBerlin&forecast_days=3')
                weather_json = weather_data.json()
                sun_hours_tomorrow = weather_json["daily"]["sunshine_duration"][1] / 3600
                weather_summary = {
                    "sun_hours_today": weather_json["daily"]["sunshine_duration"][0] / 3600,
                    "sun_hours_tomorrow": sun_hours_tomorrow,
                    "max_temp_today": weather_json["daily"]["temperature_2m_max"][0],
                    "min_temp_today": weather_json["daily"]["temperature_2m_min"][0],
                    "max_temp_tomorrow": weather_json["daily"]["temperature_2m_max"][1],
                    "precipitation_today": weather_json["daily"]["precipitation_sum"][0],
                    "precipitation_tomorrow": weather_json["daily"]["precipitation_sum"][1]
                }
            except:
                sun_hours_tomorrow = 5.0  # Fallback
                weather_summary = {
                    "sun_hours_today": 5.0,
                    "sun_hours_tomorrow": 6.0,
                    "max_temp_today": 20.0,
                    "min_temp_today": 10.0,
                    "max_temp_tomorrow": 22.0,
                    "precipitation_today": 0.0,
                    "precipitation_tomorrow": 0.0
                }
            
            # Zusammenfassung berechnen
            summary = {
                "date": str(df['timestamp'].iloc[0].date()),
                "total_solar": float(round(df['pv_profile'].sum(), 1)),
                "solar_self_consumed": float(round(df['pv_utilized_kw_opt'].sum(), 1)),
                "solar_exported": float(round(df['pv_to_grid_kw_opt'].sum(), 1)),
                "battery_charged": float(round(df['pv_to_battery_kw_opt'].sum() + df['grid_to_battery_kw_opt'].sum(), 1)),
                "battery_discharged": float(round(df['battery_to_load_kw_opt'].sum() + df['battery_to_grid_kw_opt'].sum(), 1)),
                "grid_import": float(round(df['grid_import_kw_opt'].sum(), 1)),
                "grid_export": float(round(df['grid_export_kw_opt'].sum(), 1)),
                "savings": float(round(df['electricity_savings_step'].sum() + df['feed_in_revenue_delta_step'].sum(), 2)),
                "peak_price_time": df.loc[df['foreign_power_costs'].idxmax(), 'timestamp'].strftime("%H:%M"),
                "peak_price": float(round(df['foreign_power_costs'].max(), 2)),
                "cheap_price_time": df.loc[df['foreign_power_costs'].idxmin(), 'timestamp'].strftime("%H:%M"),
                "cheap_price": float(round(df['foreign_power_costs'].min(), 2)),
                "sunniest_hour": df.loc[df['pv_profile'].idxmax(), 'timestamp'].strftime("%H:%M"),
                "solar_coverage_pct": float(round(df['pv_utilized_kw_opt'].sum() / df['gross_load'].sum() * 100, 1)),
                "export_ratio_pct": float(round(df['pv_to_grid_kw_opt'].sum() / df['pv_profile'].sum() * 100, 1)) if df['pv_profile'].sum() > 0 else 0.0,
                "battery_contribution_pct": float(round((df['battery_to_load_kw_opt'].sum() + df['battery_to_grid_kw_opt'].sum()) / df['net_load'].sum() * 100, 1)),
                "soc_swing": float(round(df['SOC_opt'].max() - df['SOC_opt'].min(), 2)),
                "grid_dependence_pct": float(round(df['grid_import_kw_opt'].sum() / df['gross_load'].sum() * 100, 1)),
                "sun_hours_tomorrow": sun_hours_tomorrow
            }
            
            # AI-Text generieren
            prompt = f"""
            You are an assistant that writes short, friendly and funny daily energy summaries for a solar+battery user. 
            Use the provided data to highlight what was interesting about the day. Do not use all the data, just the most interesting bits.
            For example:
            - how sunny it was
            - the sunniest hour
            - when energy was cheap or expensive
            - how the battery was used (charging/discharging and SOC swings)
            - how much money was saved or earned
            - how much energy was self-consumed versus exported
            - grid dependence percentage

            WEATHER CONTEXT:
            - Today's sun hours: {weather_summary['sun_hours_today']:.1f}h
            - Tomorrow's sun hours: {weather_summary['sun_hours_tomorrow']:.1f}h
            - Today's temperature: {weather_summary['min_temp_today']:.1f}°C - {weather_summary['max_temp_today']:.1f}°C
            - Tomorrow's temperature: {weather_summary['max_temp_tomorrow']:.1f}°C
            - Today's precipitation: {weather_summary['precipitation_today']:.1f}mm
            - Tomorrow's precipitation: {weather_summary['precipitation_tomorrow']:.1f}mm

            Use the weather data to explain connections between weather and solar production.
            At the end include how many sun hours are expected tomorrow and how it will impact the energy consumption and prices.

            Make the summary 1–3 sentences long, include as many emojis as possible, 
            and keep it positive and easy to understand. Please use units and include quantity where possible.
            Make it as fun as you can!

            Here is the data:
            {{summary_json}}

            Now write a natural-language summary and just return the summary text, without any extra commentary.
            """
            
            # Claude AI verwenden
            api_key = os.environ.get('ANTHROPIC_API_KEY')
            if not api_key:
                # Fallback ohne AI
                message = f"""
🔋 **Batterie-Report für {summary['date']}**

**Solar-Produktion:** {summary['total_solar']} kWh
**Einsparungen:** {summary['savings']}€
**Batterie geladen:** {summary['battery_charged']} kWh
**Batterie entladen:** {summary['battery_discharged']} kWh
**Peak-Preis:** {summary['peak_price']}€/kWh um {summary['peak_price_time']}

**Morgen erwartet:** {summary['sun_hours_tomorrow']:.1f} Sonnenstunden ☀️
                """
            else:
                try:
                    client = anthropic.Anthropic(api_key=api_key)
                    
                    response = client.messages.create(
                        model='claude-3-5-haiku-20241022',
                        max_tokens=300,
                        messages=[{'role': 'user', 'content': prompt.format(summary_json=json.dumps(summary, ensure_ascii=False))}]
                    )
                    
                    # Text extrahieren
                    message = ''.join([block.text for block in response.content if hasattr(block, 'text')])
                except:
                    # Fallback ohne AI
                    message = f"""
🔋 **Batterie-Report für {summary['date']}**

**Solar-Produktion:** {summary['total_solar']} kWh
**Einsparungen:** {summary['savings']}€
**Batterie geladen:** {summary['battery_charged']} kWh
**Batterie entladen:** {summary['battery_discharged']} kWh
**Peak-Preis:** {summary['peak_price']}€/kWh um {summary['peak_price_time']}

**Morgen erwartet:** {summary['sun_hours_tomorrow']:.1f} Sonnenstunden ☀️
                    """
            
            # Chart erstellen
            plt.figure(figsize=(10,4))
            plt.plot(df['timestamp'], df['pv_profile'], label='PV Produktion', color='orange', linewidth=2)
            plt.plot(df['timestamp'], df['pv_utilized_kw_opt'], label='PV genutzt', color='green', linewidth=2)
            plt.fill_between(df['timestamp'], 0, df['pv_to_battery_kw_opt'], color='green', alpha=0.3, label='Batterie geladen')
            plt.fill_between(df['timestamp'], 0, df['battery_to_load_kw_opt'], color='red', alpha=0.3, label='Batterie entladen')
            plt.xlabel('Uhrzeit')
            plt.ylabel('kW')
            plt.title('🔋 Energiefluss heute')
            plt.legend()
            plt.grid(True, alpha=0.3)
            plt.tight_layout()
            plt.savefig('telegram_chart.png', dpi=150, bbox_inches='tight')
            plt.close()
            
            return {
                'message': message,
                'chart_path': 'telegram_chart.png'
            }
            
        except Exception as e:
            return {
                'message': f"❌ Fehler beim Generieren des Reports: {str(e)}",
                'chart_path': None
            }
    
    def run(self):
        """Start the bot - einfache Version ohne asyncio.run()"""
        print("🤖 Battery Bot startet...")
        self.application.run_polling()

# Bot starten
if __name__ == "__main__":
    # Deinen Bot Token hier einfügen
    BOT_TOKEN = "8412880146:AAETDw8AGPSWU4WpdT3C83e3XQDnFPld3E8"  # Ersetze mit deinem Token
    
    # Bot erstellen und starten
    bot = BatteryTelegramBot(BOT_TOKEN)
    
    # Bot starten
    bot.run()
