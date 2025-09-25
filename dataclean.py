import pandas as pd
import json
import requests
import daily_summary

import os
import anthropic


# Load your JSON as DataFrame
df = pd.read_json("data/day2.json")
df['timestamp'] = pd.to_datetime(df['timestamp'])

weather_data = requests.get('https://api.open-meteo.com/v1/forecast?latitude=48.1374&longitude=11.5755&daily=sunshine_duration,daylight_duration&timezone=Europe%2FBerlin&forecast_days=3')
weather_json = weather_data.json()
sun_hours_tomorrow = weather_json["daily"]["sunshine_duration"][1] / 60/60
sun_hours_today = weather_json["daily"]["sunshine_duration"][0] / 60/60

# # Daily aggregates
# summary = {
#     "date": str(df['timestamp'].iloc[0].date()),
#     "total_solar": float(round(df['pv_profile'].sum(), 1)),
#     "solar_self_consumed": float(round(df['pv_utilized_kw_opt'].sum(), 1)),
#     "solar_exported": float(round(df['pv_to_grid_kw_opt'].sum(), 1)),
#     "battery_charged": float(round(df['pv_to_battery_kw_opt'].sum() + df['grid_to_battery_kw_opt'].sum(), 1)),
#     "battery_discharged": float(round(df['battery_to_load_kw_opt'].sum() + df['battery_to_grid_kw_opt'].sum(), 1)),
#     "grid_import": float(round(df['grid_import_kw_opt'].sum(), 1)),
#     "grid_export": float(round(df['grid_export_kw_opt'].sum(), 1)),
#     "savings": float(round(df['electricity_savings_step'].sum() + df['feed_in_revenue_delta_step'].sum(), 2)),
#     "peak_price_time": df.loc[df['foreign_power_costs'].idxmax(), 'timestamp'].strftime("%H:%M"),
#     "peak_price": float(round(df['foreign_power_costs'].max(), 2)),
#     "cheap_price_time": df.loc[df['foreign_power_costs'].idxmin(), 'timestamp'].strftime("%H:%M"),
#     "cheap_price": float(round(df['foreign_power_costs'].min(), 2)),
#     # Extra metrics
#     "sunniest_hour": df.loc[df['pv_profile'].idxmax(), 'timestamp'].strftime("%H:%M"),
#     "solar_coverage_pct": float(round(df['pv_utilized_kw_opt'].sum() / df['gross_load'].sum() * 100, 1)),
#     "export_ratio_pct": float(round(df['pv_to_grid_kw_opt'].sum() / df['pv_profile'].sum() * 100, 1)) if df['pv_profile'].sum() > 0 else 0.0,
#     "battery_contribution_pct": float(round((df['battery_to_load_kw_opt'].sum() + df['battery_to_grid_kw_opt'].sum()) / df['net_load'].sum() * 100, 1)),
#     "soc_swing": float(round(df['SOC_opt'].max() - df['SOC_opt'].min(), 2)),
#     "grid_dependence_pct": float(round(df['grid_import_kw_opt'].sum() / df['gross_load'].sum() * 100, 1)),
#     "sun_hours_tomorrow": sun_hours_tomorrow
# }

# print("Summary done")

# print(summary)

advanced_summary = daily_summary.build_daily_summary(df, sun_hours_tomorrow=sun_hours_tomorrow)
print(advanced_summary)

prompt ="""
You are an assistant that writes short, friendly and funny daily energy summaries for a solar+battery user. 
Use the provided data to highlight what was interesting about the day. Do not use all the data, just the most interesting bits.
For example:
- how sunny it was
- the sunniest hour
- when energy was cheap or expensive, and how the battery reacted smartly to that
- how the battery was used (charging/discharging and SOC swings)
- how much money was saved or earned
- how much energy was self-consumed versus exported
- grid dependence percentage
- CO2 only if asked not in initial summary

At the end include how many sun hours are expected tommorrow and how it will impact the energy consumptioin and prices.

Make the summary 1–3 sentences long, include as many emojis as possible, 
and keep it positive and easy to understand. Please use units and include quantity where possible.
Make it as fun as you can!

Here is the data:
{summary_json}

Now write a natural-language summary and just return the summary text, without any extra commentary.
"""

messages = []
user_input = prompt.format(summary_json=json.dumps(advanced_summary, ensure_ascii=False))
messages.append({'role': 'user', 'content': user_input})

def get_response(messages):
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        raise RuntimeError('Missing ANTHROPIC_API_KEY environment variable')

    client = anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model='claude-3-5-haiku-20241022',
        max_tokens=300,
        messages=messages
    )

    # Concatenate any returned text blocks
    reply_parts = []
    for block in response.content:
        # block can be a dict-like or TextBlock; handle both
        text = getattr(block, 'text', None)
        if text is None and isinstance(block, dict):
            text = block.get('text')
        if text:
            reply_parts.append(text)
    reply = ''.join(reply_parts) if reply_parts else ''

    messages.append({'role': 'assistant', 'content': reply})
    return reply


print("\n")
msg = get_response(messages)
print(msg)
print("\n")

import matplotlib.pyplot as plt
import io
import base64

plt.figure(figsize=(10,4))
plt.plot(df['timestamp'], df['pv_profile'], label='PV Produktion')
plt.plot(df['timestamp'], df['pv_utilized_kw_opt'], label='PV genutzt')
plt.fill_between(df['timestamp'], 0, df['pv_to_battery_kw_opt'], color='green', alpha=0.3, label='Batterie geladen')
plt.fill_between(df['timestamp'], 0, df['battery_to_load_kw_opt'], color='red', alpha=0.3, label='Batterie entladen')
plt.xlabel('Uhrzeit')
plt.ylabel('kW')
plt.title('Energiefluss heute')
plt.legend()
plt.tight_layout()
plt.savefig('bild.png')


import requests

WEBHOOK_URL = "https://discord.com/api/webhooks/1420562378436771870/hz5NbxRPKcVbSsnTOA0SZxV3bc_k79oOWo6fXmZYVZlV8oDmtzI6FftdgHXysLcK3fhF"

data = {
    "content": msg,
}


# response = requests.post(WEBHOOK_URL, json=data)
# if response.status_code == 204:
#     print("Nachricht erfolgreich gesendet!")
# else:
#     print(f"Fehler: {response.status_code}")

# files = {
#     "file": open("bild.png", "rb")
# }




# Loop für weitere Nachfragen
while True:
    follow_up = input("Du: ")
    if follow_up.lower() in ['exit', 'quit']:
        break
    messages.append({'role': 'user', 'content': follow_up})
    print("Bot:", get_response(messages))


