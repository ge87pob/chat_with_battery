#!/usr/bin/env python3
"""
Send a daily energy summary email with API data, Anthropic-generated message, and Puppeteer charts using Resend.

Environment variables:
- RESEND_API_KEY:            Resend API key (required)
- ANTHROPIC_API_KEY:         Anthropic API key (required for message generation)
- BATTERY_API_BASE_URL:      Base URL for energy data API (default: http://91.98.200.67)
- BATTERY_DATA_ID:           Data ID to query (default: klassiche-demo-hackathon-evo-9mflyui8)
- BATTERY_SITE_URL:          Vite dev server URL for Puppeteer (default: http://localhost:8080/)

Usage examples:
- python email_daily_summary.py --to gottliebdinh99@gmail.com
- python email_daily_summary.py --to a@b.com --to c@d.com --subject "Daily Summary"
"""

import os
import json
import base64
import argparse
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import requests

import resend
import daily_summary as ds


def load_customers_ascii_safe(path: str = "customers.json"):
    try:
        with open(path, "r", encoding="utf-8") as f:
            customers = json.load(f)
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
    except Exception:
        return []


def get_customer_context(data_id: str) -> str:
    customers = load_customers_ascii_safe()
    for c in customers:
        if c.get('data_id') == data_id:
            parts = [f"Customer: {c.get('name','Unknown')}"]
            if c.get('business_type'): parts.append(f"Business: {c['business_type']}")
            if c.get('building_type'): parts.append(f"Building: {c['building_type']}")
            if c.get('location'): parts.append(f"Location: {c['location']}")
            if c.get('capacity_info'): parts.append(f"Details: {c['capacity_info']}")
            if c.get('special_notes'): parts.append(f"Notes: {c['special_notes']}")
            return " | ".join(parts)
    return f"Customer: Unknown | ID: {data_id}"


def fetch_energy_data(api_base_url: str, data_id: str, days_back: int) -> Tuple[pd.DataFrame, dict]:
    """Fetch energy data from the API"""
    url = f"{api_base_url}/api/energy-data"
    params = {"id": data_id, "days_back": days_back}
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        api_data = response.json()
        df = pd.DataFrame(api_data['data'])
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        metadata = api_data.get('metadata', {})
        return df, metadata
    except Exception as e:
        print(f"Error fetching data from API: {e}")
        print("Falling back to local data...")
        df = pd.read_json("data/day1.json")
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        return df, {"source": "local_fallback"}


def build_summary_text(df: pd.DataFrame, data_source: str, requested_date: str, customer_context: str) -> str:
    """Generate summary text using Anthropic API with same logic as telegram bot"""
    sun_hours_today = 0
    sun_hours_tomorrow = 0
    try:
        weather_data = requests.get(
            'https://api.open-meteo.com/v1/forecast?latitude=48.1374&longitude=11.5755&daily=sunshine_duration,daylight_duration&timezone=Europe%2FBerlin&forecast_days=3',
            timeout=8
        )
        wj = weather_data.json()
        sun_hours_today = wj["daily"]["sunshine_duration"][0] / 3600
        sun_hours_tomorrow = wj["daily"]["sunshine_duration"][1] / 3600
    except Exception as e:
        print(f"Weather API failed: {e}")

    summary = ds.build_daily_summary(df, sun_hours_today=sun_hours_today, sun_hours_tomorrow=sun_hours_tomorrow)

    api_key = os.environ.get('ANTHROPIC_API_KEY', '').strip()
    print(f"Anthropic API key available: {'Yes' if api_key else 'No'}")
    
    if api_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
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
{json.dumps(summary, ensure_ascii=False)}

Now write a natural-language summary and just return the summary text, without any extra commentary."""
            print("Calling Anthropic API...")
            resp = client.messages.create(
                model='claude-3-5-haiku-20241022',
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )
            parts = []
            for block in resp.content:
                text = getattr(block, 'text', None)
                if text is None and isinstance(block, dict):
                    text = block.get('text')
                if text:
                    parts.append(text)
            out = ''.join(parts).strip()
            if out:
                print("✅ Anthropic summary generated successfully")
                return out
        except Exception as e:
            print(f"❌ Anthropic API failed: {e}")

    # Fallback concise summary
    print("⚠️ Using fallback summary (no Anthropic)")
    return (
        f"🔆 Solar: {summary['total_solar']:.1f} kWh, genutzt: {summary['solar_self_consumed']:.1f} kWh, Export: {summary['solar_exported']:.1f} kWh. "
        f"🔋 Batterie geladen: {summary['battery_charged']:.1f} kWh, entladen: {summary['battery_discharged']:.1f} kWh. "
        f"⚡ Netzimport: {summary['grid_import']:.1f} kWh, Ersparnis: {summary['savings_total']:.2f} €. "
        f"☀️ Morgen: {summary['sun_hours_tomorrow']:.1f} Sonnenstunden."
    )


def wait_for_http(url: str, timeout_seconds: int = 30) -> bool:
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


def generate_charts_with_battery_graphics(df: pd.DataFrame) -> List[str]:
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
        if not wait_for_http(vite_url, timeout_seconds=2):
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
            if not wait_for_http(vite_url, timeout_seconds=30):
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


def generate_matplotlib_charts(df: pd.DataFrame) -> List[str]:
    """Generate the same charts as telegram bot fallback"""
    out_paths: List[str] = []

    # Chart 1: Energy flow (exact same as telegram bot fallback)
    try:
        plt.figure(figsize=(10, 4))
        plt.plot(df['timestamp'], df['pv_profile'], label='PV production')
        plt.plot(df['timestamp'], df['pv_utilized_kw_opt'], label='PV used')
        plt.fill_between(df['timestamp'], 0, df['pv_to_battery_kw_opt'], color='green', alpha=0.3, label='Battery charging')
        plt.fill_between(df['timestamp'], 0, df['battery_to_load_kw_opt'], color='red', alpha=0.3, label='Battery discharging')
        plt.xlabel('Time')
        plt.ylabel('kW')
        plt.title('Energy flow today')
        plt.legend()
        plt.tight_layout()
        p1 = 'email_chart_energy.png'
        plt.savefig(p1)
        plt.close()
        out_paths.append(str(Path(p1).resolve()))
        print(f"✅ Generated energy chart: {p1}")
    except Exception as e:
        print(f"❌ Energy chart failed: {e}")

    return out_paths


def generate_charts(df: pd.DataFrame) -> List[str]:
    """Generate charts using the same logic as telegram bot: battery_graphics first, matplotlib fallback"""
    print("🎨 Starting chart generation...")
    
    # Try battery_graphics (Puppeteer) first, same as telegram bot
    try:
        print("🔄 Trying battery_graphics (Puppeteer) charts...")
        chart_paths = generate_charts_with_battery_graphics(df)
        if chart_paths:
            print(f"✅ Puppeteer charts generated: {chart_paths}")
            return chart_paths
        else:
            print("⚠️ No Puppeteer charts generated")
    except Exception as e:
        print(f"❌ battery_graphics capture failed: {e}")

    # Fallback to matplotlib if Puppeteer flow fails (same as telegram bot)
    try:
        print("🔄 Falling back to matplotlib charts...")
        chart_paths = generate_matplotlib_charts(df)
        if chart_paths:
            print(f"✅ Matplotlib charts generated: {chart_paths}")
            return chart_paths
        else:
            print("⚠️ No matplotlib charts generated")
    except Exception as e:
        print(f"❌ Matplotlib fallback failed: {e}")
    
    print("❌ No charts could be generated")
    return []


def encode_file_b64(path: str) -> str:
    with open(path, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')


def guess_content_type(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext in {'.png'}:
        return 'image/png'
    if ext in {'.jpg', '.jpeg'}:
        return 'image/jpeg'
    if ext in {'.gif'}:
        return 'image/gif'
    return 'application/octet-stream'


def send_email_via_resend(to_list: List[str], subject: str, html_body: str, attachment_paths: List[str]):
    api_key = os.environ.get('RESEND_API_KEY', '').strip()
    if not api_key:
        raise RuntimeError('RESEND_API_KEY is not set')
    resend.api_key = api_key

    attachments = []
    for p in attachment_paths or []:
        try:
            attachments.append({
                'filename': Path(p).name,
                'content': encode_file_b64(p),
                'content_type': guess_content_type(p),
            })
            print(f"✅ Added attachment: {Path(p).name}")
        except Exception as e:
            print(f"❌ Failed to add attachment {p}: {e}")

    # Use Battery Buddy as sender name (using verified resend.dev domain)
    from_addr = "Battery Buddy <battery-buddy@resend.dev>"
    payload = {
        'from': from_addr,
        'to': to_list,
        'subject': subject,
        'html': html_body,
    }
    if attachments:
        payload['attachments'] = attachments

    return resend.Emails.send(payload)


def main():
    parser = argparse.ArgumentParser(description='Send daily energy summary email with API data, Anthropic message, and Puppeteer charts')
    parser.add_argument('--to', action='append', required=True, help='Recipient email (can be provided multiple times)')
    parser.add_argument('--subject', default='Daily Energy Summary from Battery Buddy', help='Email subject')
    parser.add_argument('--days-back', type=int, default=17, help='Days back for dataset selection')
    args = parser.parse_args()

    # API Configuration
    api_base_url = os.environ.get('BATTERY_API_BASE_URL', 'http://91.98.200.67')
    data_id = os.environ.get('BATTERY_DATA_ID', 'klassiche-demo-hackathon-evo-9mflyui8')

    print("🔄 Fetching energy data from API...")
    df, metadata = fetch_energy_data(api_base_url, data_id, args.days_back)
    df = df.copy()
    df['timestamp'] = pd.to_datetime(df['timestamp'])

    data_source = metadata.get('source', 'api')
    requested_date = metadata.get('requested_date', 'recent')
    customer_context = get_customer_context(data_id)

    print("🤖 Generating summary text with Anthropic...")
    summary_text = build_summary_text(df, data_source, requested_date, customer_context)

    print("🎨 Generating charts...")
    chart_paths = generate_charts(df)

    date_str = df['timestamp'].dt.date.iloc[0].isoformat() if len(df) else datetime.now().date().isoformat()

    # HTML body with Battery Buddy branding
    html = f"""
    <div style="font-family: system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="text-align: center; margin-bottom: 30px;">
            <h1 style="color: #2E7D32; margin: 0;">🔋 Battery Buddy</h1>
            <p style="color: #666; margin: 5px 0 0 0; font-size: 14px;">Your Daily Energy Report - {date_str}</p>
        </div>
        
        <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
            <p style="margin: 0; font-size: 16px; line-height: 1.6;">{summary_text}</p>
        </div>
        
        <div style="text-align: center; margin-top: 30px;">
            <p style="color: #666; font-size: 12px; margin: 0;">
                Powered by Battery Buddy • TUM Energy Management System
            </p>
        </div>
    </div>
    """

    print(f"📧 Sending email to: {', '.join(args.to)}")
    print(f"📎 Attachments: {len(chart_paths)} charts")
    
    resp = send_email_via_resend(args.to, args.subject, html, chart_paths)
    print('✅ Email sent:', resp)


if __name__ == '__main__':
    main()
