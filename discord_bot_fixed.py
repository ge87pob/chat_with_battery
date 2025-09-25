#!/usr/bin/env python3
"""
Discord Battery Bot - Fixed Version
Kein Rekursionsfehler, einfache Struktur
"""

import os
import sys
import asyncio
import discord
from discord.ext import commands
import pandas as pd
import matplotlib.pyplot as plt
import anthropic
from dotenv import load_dotenv
import subprocess

# Lade Environment Variables
load_dotenv()

# Bot Setup
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Lade API Keys aus config.env
from dotenv import load_dotenv
load_dotenv('config.env')

# Voice Features (optional)
VOICE_AVAILABLE = False
ELEVENLABS_AVAILABLE = False
BOT_IS_SPEAKING = False

try:
    import speech_recognition as sr
    import pyttsx3
    import pyaudio
    VOICE_AVAILABLE = True
    print("🎤 Voice-Features verfügbar!")
except ImportError:
    print("⚠️ Voice-Features nicht verfügbar - Bot funktioniert trotzdem!")

try:
    import requests
    import tempfile
    ELEVENLABS_AVAILABLE = True
    print("🎤 ElevenLabs API verfügbar!")
except ImportError:
    print("⚠️ ElevenLabs nicht verfügbar - verwende Standard-TTS")

@bot.event
async def on_ready():
    print(f'🔋 {bot.user} ist online!')
    print(f'Bot ist in {len(bot.guilds)} Servern aktiv')

@bot.event
async def on_voice_state_update(member, before, after):
    """Automatisches Zuhören wenn User Voice Channel beitritt"""
    print(f"🔍 Voice State Update: {member.display_name} ({member.id})")
    print(f"   Vorher: {before.channel}")
    print(f"   Nachher: {after.channel}")
    
    # User tritt Voice Channel bei
    if before.channel is None and after.channel is not None:
        print(f"🎤 {member.display_name} ist Voice Channel beigetreten: {after.channel.name}")
        
        # Starte automatisches Zuhören für 1 Minute
        asyncio.create_task(auto_listen_on_join(member, after.channel))
    
    # User verlässt Voice Channel
    elif before.channel is not None and after.channel is None:
        print(f"🔇 {member.display_name} hat Voice Channel verlassen")
        # Stoppe automatisches Zuhören
        if hasattr(bot, 'auto_listening_task'):
            bot.auto_listening_task.cancel()
            print("🔇 Automatisches Zuhören gestoppt")

async def auto_listen_on_join(member, voice_channel):
    """Automatisches Zuhören für 1 Minute nach Voice Channel Beitritt"""
    if not VOICE_AVAILABLE:
        print("❌ Voice-Features nicht verfügbar")
        return
    
    try:
        print(f"🎤 Starte automatisches Zuhören für {member.display_name}...")
        
        # Erstelle Embed
        embed = discord.Embed(
            title="🎤 Intelligentes Zuhören aktiv!",
            description=f"Hallo {member.display_name}! Ich höre dir zu und antworte nach **2 Sekunden Stille**! 🎧",
            color=0x00ff00
        )
        embed.add_field(
            name="🗣️ Du kannst alles fragen:",
            value="• Batterie & Solar-Produktion\n• Wetter & Temperatur\n• Einsparungen & Strompreise\n• Oder einfach plaudern!",
            inline=False
        )
        embed.add_field(
            name="⏰ Intelligente Antworten:",
            value="Ich antworte automatisch nach **2 Sekunden Stille**\nWenn du gar nichts sagst, stoppe ich nach **10 Sekunden**",
            inline=False
        )
        
        # Sende Embed in den Voice Channel
        await voice_channel.send(embed=embed)
        
        # Starte intelligentes Zuhören
        start_time = asyncio.get_event_loop().time()
        last_speech_time = start_time
        silence_threshold = 2.0  # 2 Sekunden Stille bis Antwort
        no_speech_timeout = 10.0  # 10 Sekunden wenn gar nichts gesagt wird
        conversation_active = False
        accumulated_text = ""
        
        recognizer = sr.Recognizer()
        
        while True:
            try:
                with sr.Microphone() as source:
                    # Kurze Pause zwischen Aufnahmen
                    recognizer.adjust_for_ambient_noise(source, duration=0.3)
                    
                    # Höre 3 Sekunden zu
                    
                    # Kürzerer Timeout um "listening timed out" zu vermeiden
                    audio = recognizer.listen(source, timeout=0.5, phrase_time_limit=3)
                    
                    # Speech-to-Text
                    text = recognizer.recognize_google(audio, language='de-DE')
                    print(f"🎤 Auto-erkannt: {text}")
                    
                    # Aktualisiere letzte Sprechzeit
                    last_speech_time = asyncio.get_event_loop().time()
                    conversation_active = True
                    accumulated_text += text + " "
                    
                    # Sammle Text aber antworte NICHT sofort
                    print(f"🗣️ Gesprochen: {text}")
                    
                    # Wenn Bot gerade spricht -> sofort unterbrechen!
                    if BOT_IS_SPEAKING:
                        print(f"🔇 Bot spricht gerade - unterbreche und höre zu!")
                        # Stoppe Bot-Sprechen (wird in TTS-Funktion automatisch zurückgesetzt)
                        BOT_IS_SPEAKING = False
                        
                        # Antworte sofort auf Unterbrechung
                        interrupt_embed = discord.Embed(
                            title="🔇 Ich höre zu!",
                            description=f"Du hast mich unterbrochen. Ich höre: **{text}**",
                            color=0xffff00
                        )
                        await voice_channel.send(embed=interrupt_embed)
                        
                        # Generiere sofort Antwort
                        await generate_voice_response(text)
                        
                        # Reset für nächste Konversation
                        conversation_active = False
                        accumulated_text = ""
                        last_speech_time = asyncio.get_event_loop().time()
                    else:
                        # Bot wartet bis 2 Sekunden Stille!
                        pass
                        
            except sr.WaitTimeoutError:
                # Timeout ist normal - prüfe auf Stille
                current_time = asyncio.get_event_loop().time()
                time_since_last_speech = current_time - last_speech_time
                time_since_start = current_time - start_time
                
                # Wenn 10 Sekunden gar nichts gesagt wird -> ABBRECHEN
                if time_since_start >= no_speech_timeout and not conversation_active:
                    print(f"⏰ 10 Sekunden ohne Sprache - breche ab")
                    break
                
                # Wenn 2 Sekunden Stille und Konversation aktiv -> ANTWORTEN
                elif conversation_active and time_since_last_speech >= silence_threshold:
                    print(f"🔇 2 Sekunden Stille erkannt, antworte auf: {accumulated_text.strip()}")
                    
                    if accumulated_text.strip():
                        # Zeige dass Bot verstanden hat und antwortet
                        response_embed = discord.Embed(
                            title="🎤 Ich habe verstanden:",
                            description=f"**{accumulated_text.strip()}**",
                            color=0x0099ff
                        )
                        await voice_channel.send(embed=response_embed)
                        
                        # Generiere AI-Antwort und spreche sie
                        await generate_voice_response(accumulated_text.strip())
                        
                        # Reset für nächste Konversation
                        conversation_active = False
                        accumulated_text = ""
                        last_speech_time = current_time
                
                pass
            except sr.UnknownValueError:
                # Keine Sprache erkannt - normal, weiter hören
                pass
            except sr.RequestError as e:
                print(f"❌ STT Fehler: {e}")
            except Exception as e:
                print(f"❌ Auto-Zuhören Fehler: {e}")
            
            # Kurze Pause um Rekursion zu vermeiden
            await asyncio.sleep(0.1)
        
        # Zeit abgelaufen
        timeout_embed = discord.Embed(
            title="⏰ Automatisches Zuhören beendet",
            description="1 Minute ist um! Ich höre nicht mehr automatisch zu.\n\nVerwende `!listen_now` für Push-to-Talk.",
            color=0xffff00
        )
        await voice_channel.send(embed=timeout_embed)
        print("⏰ Automatisches Zuhören beendet - 1 Minute abgelaufen")
        
    except Exception as e:
        print(f"❌ Auto-Zuhören Fehler: {e}")
        error_embed = discord.Embed(
            title="❌ Fehler beim automatischen Zuhören",
            description=f"Fehler: {str(e)}",
            color=0xff0000
        )
        await voice_channel.send(embed=error_embed)

@bot.command(name='start')
async def start_command(ctx):
    """Start command handler"""
    welcome_embed = discord.Embed(
        title="🔋 Battery Buddy Bot ist da! ⚡",
        description="Ich bin dein intelligenter Batterie-Assistent!",
        color=0x00ff00
    )
    
    welcome_embed.add_field(
        name="📋 Verfügbare Commands:",
        value="`!daily` - Täglichen Report anfordern\n"
              "`!status` - Aktuellen Status abfragen\n"
              "`!chart` - Batterie-Chart generieren\n"
              "`!test_elevenlabs` - 🎤 ElevenLabs TTS testen\n"
              "`!battery_help` - Hilfe anzeigen",
        inline=False
    )
    
    await ctx.send(embed=welcome_embed)

@bot.command(name='daily')
async def daily_command(ctx):
    """Generiert einen täglichen Batterie-Report mit Wetter-Integration"""
    try:
        # Lade Daten
        df = pd.read_json("data/day1.json")
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # Berechne Statistiken
        current_soc = df['SOC_opt'].iloc[-1]
        total_savings = df['electricity_savings_step'].sum()
        solar_production = df['pv_profile'].sum()
        peak_price = df['foreign_power_costs'].max()
        
        # Wetterdaten holen
        weather_info = await get_weather_data()
        
        # Erstelle Embed
        daily_embed = discord.Embed(
            title="📊 Täglicher Batterie-Report",
            color=0x00ff00
        )
        
        daily_embed.add_field(
            name="🔋 Ladestand",
            value=f"{current_soc:.1%}",
            inline=True
        )
        
        daily_embed.add_field(
            name="💰 Einsparungen",
            value=f"{total_savings:.2f}€",
            inline=True
        )
        
        daily_embed.add_field(
            name="☀️ Solar-Produktion",
            value=f"{solar_production:.1f} kWh",
            inline=True
        )
        
        daily_embed.add_field(
            name="🌤️ Heute",
            value=f"☀️ {weather_info['sun_hours_today']:.1f}h\n🌡️ {weather_info['min_temp_today']:.0f}°-{weather_info['max_temp_today']:.0f}°C",
            inline=True
        )
        
        daily_embed.add_field(
            name="🌤️ Morgen",
            value=f"☀️ {weather_info['sun_hours_tomorrow']:.1f}h\n🌡️ {weather_info['max_temp_tomorrow']:.0f}°C",
            inline=True
        )
        
        daily_embed.add_field(
            name="📈 Höchster Strompreis",
            value=f"{peak_price:.3f}€/kWh",
            inline=True
        )
        
        await ctx.send(embed=daily_embed)
        
    except Exception as e:
        error_embed = discord.Embed(
            title="❌ Fehler",
            description=f"Fehler beim Laden der Daten: {str(e)}",
            color=0xff0000
        )
        await ctx.send(embed=error_embed)

@bot.command(name='status')
async def status_command(ctx):
    """Zeigt aktuellen Batterie-Status"""
    try:
        # Lade Daten
        df = pd.read_json("data/day1.json")
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # Aktuelle Werte
        current_soc = df['SOC_opt'].iloc[-1]
        current_price = df['foreign_power_costs'].iloc[-1]
        current_time = df['timestamp'].iloc[-1]
        
        status_embed = discord.Embed(
            title="🔋 Aktueller Batterie-Status",
            color=0x0099ff
        )
        
        status_embed.add_field(
            name="⏰ Zeit",
            value=current_time.strftime("%H:%M"),
            inline=True
        )
        
        status_embed.add_field(
            name="🔋 Ladestand",
            value=f"{current_soc:.1%}",
            inline=True
        )
        
        status_embed.add_field(
            name="💰 Strompreis",
            value=f"{current_price:.3f}€/kWh",
            inline=True
        )
        
        await ctx.send(embed=status_embed)
        
    except Exception as e:
        error_embed = discord.Embed(
            title="❌ Fehler",
            description=f"Fehler beim Laden der Daten: {str(e)}",
            color=0xff0000
        )
        await ctx.send(embed=error_embed)

@bot.command(name='chart')
async def chart_command(ctx):
    """Erstellt Batterie-Chart"""
    try:
        # Lade Daten
        df = pd.read_json("data/day1.json")
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # Erstelle Chart
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))
        
        # SOC Chart
        ax1.plot(df['timestamp'], df['SOC_opt'], label='SOC', color='blue', linewidth=2)
        ax1.set_ylabel('SOC (%)')
        ax1.set_title('Batterie-Ladestand über Zeit')
        ax1.grid(True, alpha=0.3)
        ax1.legend()
        
        # Strompreis Chart
        ax2.plot(df['timestamp'], df['foreign_power_costs'], label='Strompreis', color='red', linewidth=2)
        ax2.set_ylabel('Preis (€/kWh)')
        ax2.set_xlabel('Zeit')
        ax2.set_title('Strompreis über Zeit')
        ax2.grid(True, alpha=0.3)
        ax2.legend()
        
        plt.tight_layout()
        plt.savefig('battery_chart.png', dpi=150, bbox_inches='tight')
        plt.close()
        
        # Sende Chart
        with open('battery_chart.png', 'rb') as f:
            chart_file = discord.File(f, filename='battery_chart.png')
            
        chart_embed = discord.Embed(
            title="📊 Batterie-Chart",
            description="Hier ist dein aktueller Batterie-Chart!",
            color=0x0099ff
        )
        
        chart_embed.set_image(url="attachment://battery_chart.png")
        
        await ctx.send(embed=chart_embed, file=chart_file)
        
    except Exception as e:
        error_embed = discord.Embed(
            title="❌ Fehler",
            description=f"Fehler beim Erstellen des Charts: {str(e)}",
            color=0xff0000
        )
        await ctx.send(embed=error_embed)

@bot.command(name='test_elevenlabs')
async def test_elevenlabs(ctx):
    """Teste ElevenLabs TTS"""
    if not ELEVENLABS_AVAILABLE:
        embed = discord.Embed(
            title="❌ ElevenLabs nicht verfügbar",
            description="Installiere: pip install elevenlabs",
            color=0xff0000
        )
        await ctx.send(embed=embed)
        return
    
    try:
        embed = discord.Embed(
            title="🎤 Teste ElevenLabs...",
            description="Generiere realistische KI-Stimme...",
            color=0x0099ff
        )
        await ctx.send(embed=embed)
        
        test_text = "Hallo! Ich bin dein ElevenLabs Voice Assistant für Batterie-Monitoring!"
        
        # ElevenLabs TTS über API
        await elevenlabs_tts_api(test_text)
        
        embed = discord.Embed(
            title="✅ ElevenLabs Test erfolgreich!",
            description="Du solltest jetzt eine **realistische KI-Stimme** gehört haben! 🎤✨",
            color=0x00ff00
        )
        await ctx.send(embed=embed)
        
    except Exception as e:
        embed = discord.Embed(
            title="❌ ElevenLabs Test fehlgeschlagen",
            description=f"Fehler: {str(e)}",
            color=0xff0000
        )
        await ctx.send(embed=embed)

@bot.command(name='listen_now')
async def listen_now(ctx):
    """Push-to-Talk - Bot hört zu und antwortet mit Stimme!"""
    if not VOICE_AVAILABLE:
        embed = discord.Embed(
            title="❌ Speech Recognition nicht verfügbar",
            description="Installiere: pip install speech_recognition pyttsx3 pyaudio",
            color=0xff0000
        )
        await ctx.send(embed=embed)
        return
    
    try:
        embed = discord.Embed(
            title="🎤 Höre zu...",
            description="Sprich jetzt! Ich höre 5 Sekunden zu...",
            color=0x0099ff
        )
        await ctx.send(embed=embed)
        
        # Speech Recognition
        recognizer = sr.Recognizer()
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            audio = recognizer.listen(source, timeout=0.5, phrase_time_limit=5)
        
        # Speech-to-Text
        text = recognizer.recognize_google(audio, language='de-DE')
        print(f"🎤 Erkannt: {text}")
        
        # Erstelle Antwort
        result_embed = discord.Embed(
            title="🎤 Ich habe verstanden:",
            description=f"**{text}**",
            color=0x00ff00
        )
        await ctx.send(embed=result_embed)
        
        # Generiere AI-Antwort und spreche sie
        await generate_voice_response(text)
        
    except sr.WaitTimeoutError:
        error_embed = discord.Embed(
            title="⏰ Timeout",
            description="Ich habe nichts gehört. Versuche es nochmal!",
            color=0xffff00
        )
        await ctx.send(embed=error_embed)
    except sr.UnknownValueError:
        error_embed = discord.Embed(
            title="❌ Keine Sprache erkannt",
            description="Ich konnte nichts verstehen. Versuche es nochmal!",
            color=0xff0000
        )
        await ctx.send(embed=error_embed)
    except Exception as e:
        error_embed = discord.Embed(
            title="❌ Fehler",
            description=f"Fehler: {str(e)}",
            color=0xff0000
        )
        await ctx.send(embed=error_embed)

@bot.command(name='test_voice_state')
async def test_voice_state(ctx):
    """Test Voice State Updates"""
    if ctx.author.voice:
        voice_channel = ctx.author.voice.channel
        embed = discord.Embed(
            title="🎤 Voice State Test",
            description=f"Du bist in: **{voice_channel.name}**\n"
                       f"User ID: {ctx.author.id}\n"
                       f"Bot erkennt Voice State Updates!",
            color=0x00ff00
        )
        await ctx.send(embed=embed)
        
        # Starte manuell das automatische Zuhören
        await auto_listen_on_join(ctx.author, voice_channel)
    else:
        embed = discord.Embed(
            title="❌ Nicht in Voice Channel",
            description="Tritt einem Voice Channel bei und verwende dann `!test_voice_state`",
            color=0xff0000
        )
        await ctx.send(embed=embed)

@bot.command(name='battery_help')
async def help_command(ctx):
    """Help command handler"""
    help_embed = discord.Embed(
        title="🔋 Battery Buddy Bot - Hilfe",
        color=0x0099ff
    )
    
    help_embed.add_field(
        name="📋 Commands:",
        value="`!daily` - Generiert einen täglichen Batterie-Report\n"
              "`!status` - Zeigt aktuellen Batterie-Status\n"
              "`!chart` - Erstellt Batterie-Chart\n"
              "`!listen_now` - 🎤 Push-to-Talk (Bot hört zu!)\n"
              "`!test_voice_state` - 🎤 Teste automatisches Zuhören\n"
              "`!test_elevenlabs` - ElevenLabs TTS testen\n"
              "`!battery_help` - Diese Hilfe anzeigen",
        inline=False
    )
    
    help_embed.add_field(
        name="🎤 Automatisches Zuhören:",
        value="Tritt einem Voice Channel bei → Bot hört automatisch 1 Minute zu!\n"
              "Oder verwende `!test_voice_state` zum Testen.",
        inline=False
    )
    
    await ctx.send(embed=help_embed)

async def elevenlabs_tts_api(text):
    """ElevenLabs TTS über direkte API-Anfrage - unterbrechbar"""
    global BOT_IS_SPEAKING
    
    try:
        import requests
        
        # ElevenLabs API URL
        url = "https://api.elevenlabs.io/v1/text-to-speech/21m00Tcm4TlvDq8ikWAM"
        
        # API Key
        api_key = os.environ.get('ELEVENLABS_API_KEY')
        if not api_key:
            print("❌ Kein ElevenLabs API Key")
            return
        
        # Headers
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": api_key
        }
        
        # Voice Settings
        data = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
                "style": 0.0,
                "use_speaker_boost": True
            }
        }
        
        print(f"🎤 Sende Anfrage an ElevenLabs API...")
        
        # API-Anfrage
        response = requests.post(url, json=data, headers=headers)
        
        if response.status_code == 200:
            # Speichere Audio
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as temp_file:
                temp_file.write(response.content)
                temp_file.flush()
                
                print(f"🎵 Spiele ElevenLabs Audio ab...")
                
                # Setze Bot-Sprechen Flag
                BOT_IS_SPEAKING = True
                
                try:
                    # Spiele Audio ab (macOS) - unterbrechbar
                    process = subprocess.Popen(['afplay', temp_file.name])
                    
                    # Warte bis Audio fertig oder unterbrochen
                    while process.poll() is None:
                        await asyncio.sleep(0.1)
                        # Prüfe ob User anfängt zu sprechen (wird in auto_listen_on_join gecheckt)
                        
                finally:
                    # Lösche temporäre Datei
                    os.unlink(temp_file.name)
                    BOT_IS_SPEAKING = False
                    
                    print("✅ ElevenLabs Audio abgespielt")
        else:
            print(f"❌ ElevenLabs API Fehler: {response.status_code} - {response.text}")
            
    except Exception as e:
        print(f"❌ ElevenLabs TTS Fehler: {e}")
        # Fallback zu System TTS
        print("🔄 Fallback zu System TTS...")
        BOT_IS_SPEAKING = True
        try:
            subprocess.run(['say', '-v', 'Anna', text])
        finally:
            BOT_IS_SPEAKING = False

async def get_weather_data():
    """Holt aktuelle Wetterdaten von Open-Meteo API"""
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
        print(f"🌤️ Wetterdaten geladen: {weather_info['sun_hours_today']:.1f}h Sonne heute")
        return weather_info
    except Exception as e:
        print(f"⚠️ Wetter-API Fehler: {e}, verwende Fallback")
        return {
            "sun_hours_today": 5.0,
            "sun_hours_tomorrow": 6.0,
            "max_temp_today": 20.0,
            "min_temp_today": 10.0,
            "max_temp_tomorrow": 22.0,
            "precipitation_today": 0.0,
            "precipitation_tomorrow": 0.0
        }

async def generate_voice_response(user_text):
    """Generiert AI-Antwort und spricht sie mit ElevenLabs"""
    try:
        print(f"🚀 generate_voice_response für: {user_text}")
        
        # Lade Batterie-Daten für Kontext
        df = pd.read_json("data/day1.json")
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # Erstelle Kontext
        context_data = {
            "current_soc": df['SOC_opt'].iloc[-1],
            "total_savings": df['electricity_savings_step'].sum(),
            "solar_production": df['pv_profile'].sum(),
            "current_price": df['foreign_power_costs'].iloc[-1],
            "peak_price": df['foreign_power_costs'].max()
        }
        
        # Wetterdaten holen
        weather_info = await get_weather_data()
        
        # AI-Prompt für Voice-Antwort (universell wie im Telegram Bot)
        ai_prompt = f"""
Du bist ein intelligenter Batterie-Assistent. Antworte auf die folgende Frage mit einer kurzen, gesprochenen Antwort (max. 2 Sätze).

AKTUELLE BATTERIE-DATEN:
- Ladestand: {context_data['current_soc']:.1%}
- Heutige Einsparungen: {context_data['total_savings']:.2f}€
- Solar-Produktion: {context_data['solar_production']:.1f} kWh
- Aktueller Strompreis: {context_data['current_price']:.3f}€/kWh

AKTUELLE WETTER-DATEN:
- Sonnenstunden heute: {weather_info['sun_hours_today']:.1f}h
- Sonnenstunden morgen: {weather_info['sun_hours_tomorrow']:.1f}h
- Temperatur heute: {weather_info['min_temp_today']:.1f}°C - {weather_info['max_temp_today']:.1f}°C
- Niederschlag heute: {weather_info['precipitation_today']:.1f}mm

NUTZER-FRAGE: {user_text}

Antworte freundlich, hilfreich und mit vielen Emojis. Erkläre Dinge einfach und verständlich.
Nutze die Wetterdaten um Zusammenhänge zwischen Wetter und Solar-Produktion zu erklären.
Wenn die Frage nichts mit Batterie oder Wetter zu tun hat, antworte trotzdem hilfreich.
        """
        
        print(f"🤖 Generiere AI-Antwort...")
        
        # Anthropic AI aufrufen
        api_key = os.environ.get('ANTHROPIC_API_KEY')
        if api_key:
            client = anthropic.Anthropic(api_key=api_key)
            response = client.messages.create(
                model='claude-3-5-haiku-20241022',
                max_tokens=100,
                messages=[{'role': 'user', 'content': ai_prompt}]
            )
            
            ai_response = ''.join([block.text for block in response.content if hasattr(block, 'text')])
            print(f"✅ AI-Antwort: {ai_response}")
        else:
            ai_response = f"Ladestand: {context_data['current_soc']:.1%}, Einsparungen: {context_data['total_savings']:.2f} Euro"
            print(f"⚠️ Kein API Key, verwende Fallback: {ai_response}")
        
        # Text-to-Speech mit ElevenLabs
        print(f"🔊 Starte ElevenLabs TTS...")
        await elevenlabs_tts_api(ai_response)
        print(f"✅ Voice Response abgeschlossen")
        
    except Exception as e:
        print(f"❌ Voice Response Fehler: {e}")
        import traceback
        traceback.print_exc()

# AI Chat Handler
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    # Prüfe auf Commands
    await bot.process_commands(message)
    
    # AI Chat (nur wenn keine Commands)
    if not message.content.startswith('!'):
        try:
            # Lade Batterie-Daten für Kontext
            df = pd.read_json("data/day1.json")
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            # Erstelle Kontext
            context_data = {
                "current_soc": df['SOC_opt'].iloc[-1],
                "total_savings": df['electricity_savings_step'].sum(),
                "solar_production": df['pv_profile'].sum(),
                "current_price": df['foreign_power_costs'].iloc[-1],
                "peak_price": df['foreign_power_costs'].max()
            }
            
            # Wetterdaten holen
            weather_info = await get_weather_data()
            
            # AI-Prompt
            ai_prompt = f"""
Du bist ein intelligenter Batterie-Assistent. Antworte auf die folgende Frage mit einer kurzen, hilfreichen Antwort.

AKTUELLE BATTERIE-DATEN:
- Ladestand: {context_data['current_soc']:.1%}
- Heutige Einsparungen: {context_data['total_savings']:.2f}€
- Solar-Produktion: {context_data['solar_production']:.1f} kWh
- Aktueller Strompreis: {context_data['current_price']:.3f}€/kWh

AKTUELLE WETTER-DATEN:
- Sonnenstunden heute: {weather_info['sun_hours_today']:.1f}h
- Sonnenstunden morgen: {weather_info['sun_hours_tomorrow']:.1f}h
- Temperatur heute: {weather_info['min_temp_today']:.1f}°C - {weather_info['max_temp_today']:.1f}°C
- Niederschlag heute: {weather_info['precipitation_today']:.1f}mm

NUTZER-FRAGE: {message.content}

Antworte kurz, freundlich und mit Emojis.
Nutze die Wetterdaten um Zusammenhänge zwischen Wetter und Solar-Produktion zu erklären.
            """
            
            # Anthropic AI aufrufen
            api_key = os.environ.get('ANTHROPIC_API_KEY')
            if api_key:
                client = anthropic.Anthropic(api_key=api_key)
                response = client.messages.create(
                    model='claude-3-5-haiku-20241022',
                    max_tokens=200,
                    messages=[{'role': 'user', 'content': ai_prompt}]
                )
                
                ai_response = ''.join([block.text for block in response.content if hasattr(block, 'text')])
                
                # Sende AI-Antwort
                await message.reply(ai_response)
            
        except Exception as e:
            print(f"AI Chat Fehler: {e}")

# Starte Bot
if __name__ == "__main__":
    bot.run(os.environ.get('DISCORD_TOKEN'))
