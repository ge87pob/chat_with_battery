import numpy as np
import pandas as pd

def build_daily_summary(df, co2_intensity_kg_per_kwh=0.32, eps=1e-6, sun_hours_today=0, sun_hours_tomorrow=0):
    # --- Hygiene ---
    df = df.copy()
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    # winzige numerische Artefakte auf 0 clippen
    for c in [
        'pv_profile','pv_surplus','pv_utilized_kw_opt','pv_to_grid_kw_opt','pv_to_battery_kw_opt',
        'grid_to_battery_kw_opt','grid_to_load_kw_opt','battery_to_load_kw_opt','battery_to_grid_kw_opt',
        'grid_import_kw_opt','grid_export_kw_opt','gross_load','net_load'
    ]:
        df[c] = df[c].astype(float).where(df[c].abs() > eps, 0.0)

    # --- Totals ---
    tot = lambda c: float(df[c].sum())
    total_pv          = tot('pv_profile')
    pv_utilized       = tot('pv_utilized_kw_opt')
    pv_to_grid        = tot('pv_to_grid_kw_opt')
    pv_to_batt        = tot('pv_to_battery_kw_opt')
    grid_to_batt      = tot('grid_to_battery_kw_opt')
    batt_to_load      = tot('battery_to_load_kw_opt')
    batt_to_grid      = tot('battery_to_grid_kw_opt')
    grid_import       = tot('grid_import_kw_opt')
    grid_export       = tot('grid_export_kw_opt')
    gross_load_total  = tot('gross_load')
    net_load_total    = tot('net_load')

    # --- Preisbasierte Größen ---
    import_cost = float((df['grid_import_kw_opt'] * df['foreign_power_costs']).sum())
    export_revenue = float((df['grid_export_kw_opt'] * df['feed_in_tariff_hourly']).sum())
    weighted_import_price = float((df['grid_import_kw_opt'] * df['foreign_power_costs']).sum() /
                                  max(grid_import, eps))
    weighted_market_price_for_load = float((df['gross_load'] * df['foreign_power_costs']).sum() /
                                           max(gross_load_total, eps))

    # Savings (aus Daten)
    savings_total = float((df['electricity_savings_step'] + df['feed_in_revenue_delta_step']).sum())
    savings_arbitrage_total = float(df['electricity_savings_arbitrage_step'].sum())
    savings_pv_selfcons_total = float(df['electricity_savings_pv_self_consumption_step'].sum())
    savings_share_arbitrage = float(savings_arbitrage_total / max(savings_total, eps))
    savings_share_pv = float(savings_pv_selfcons_total / max(savings_total, eps))

    # --- Anteile & Effizienzen ---
    grid_dependence = float(grid_import / max(gross_load_total, eps))

    # direkte PV→Load vs. PV via Batterie (proportional zu Ladequellen)
    total_charge = pv_to_batt + grid_to_batt
    pv_charge_share = (pv_to_batt / total_charge) if total_charge > eps else 0.0
    pv_via_battery_to_load = float(batt_to_load * pv_charge_share)
    direct_pv_to_load = float(max(pv_utilized - pv_to_batt, 0.0))

    # Autonomie & Peak-Fenster
    autonomy_hours = int((df['grid_import_kw_opt'] <= eps).sum())
    # Peak = oberstes Preis-Quartil
    thr = df['foreign_power_costs'].quantile(0.75)
    peak_mask = df['foreign_power_costs'] >= thr
    peak_load = float(df.loc[peak_mask, 'gross_load'].sum())
    peak_covered = float((df.loc[peak_mask, 'pv_utilized_kw_opt'].sum() +
                          df.loc[peak_mask, 'battery_to_load_kw_opt'].sum()))
    peak_window_coverage = float(peak_covered / max(peak_load, eps))

    # Busiest hours
    busiest_charge_idx = (df['pv_to_battery_kw_opt'] + df['grid_to_battery_kw_opt']).idxmax()
    busiest_discharge_idx = (df['battery_to_load_kw_opt'] + df['battery_to_grid_kw_opt']).idxmax()

    # SOC & Zeiten
    soc_min = float(df['SOC_opt'].min());  soc_min_time = df.loc[df['SOC_opt'].idxmin(), 'timestamp'].strftime('%H:%M')
    soc_max = float(df['SOC_opt'].max());  soc_max_time = df.loc[df['SOC_opt'].idxmax(), 'timestamp'].strftime('%H:%M')
    soc_swing = float(round(soc_max - soc_min, 3))

    # Effektive Preisvorteile
    effective_price_delta_pct = float((weighted_market_price_for_load - weighted_import_price) /
                                      max(weighted_market_price_for_load, eps))

    # CO2 (nur grobe Abschätzung, import- und grid-avoidance-basiert)
    avoided_grid_kwh = pv_utilized + batt_to_load  # was nicht zum Netz musste
    co2_saved_kg = float(avoided_grid_kwh * co2_intensity_kg_per_kwh)

    # Netto-Cashflow heute (leicht verständliche €-Bilanz)
    net_energy_cashflow_eur = float(import_cost - export_revenue - savings_total)

    # Hilfsfunktionen für Fenster (schöne Stories)
    def _windows(series, thr_kwh=5.0):
        active = series > thr_kwh
        blocks = []
        start = None
        for i, on in enumerate(active):
            if on and start is None: start = i
            if (not on or i == len(active)-1) and start is not None:
                end = i if not on else i
                blocks.append((df['timestamp'].iloc[start].strftime('%H:%M'),
                               df['timestamp'].iloc[end].strftime('%H:%M'),
                               float(series.iloc[start:end+1].sum())))
                start = None
        return blocks

    charge_series = df['pv_to_battery_kw_opt'] + df['grid_to_battery_kw_opt']
    discharge_series = df['battery_to_load_kw_opt'] + df['battery_to_grid_kw_opt']
    charge_windows = _windows(charge_series)
    discharge_windows = _windows(discharge_series)

    summary = {
        # Basis (deine Felder, teils umbenannt für Klarheit)
        "date": str(df['timestamp'].iloc[0].date()),
        "total_solar": float(round(total_pv, 1)),
        "solar_self_consumed": float(round(pv_utilized, 1)),
        "solar_exported": float(round(pv_to_grid, 1)),
        "battery_charged": float(round(pv_to_batt + grid_to_batt, 1)),
        "battery_discharged": float(round(batt_to_load + batt_to_grid, 1)),
        "grid_import": float(round(grid_import, 1)),
        "grid_export": float(round(grid_export, 1)),
        "savings_total": float(round(savings_total, 2)),
        "peak_price_time": df.loc[df['foreign_power_costs'].idxmax(), 'timestamp'].strftime("%H:%M"),
        "peak_price": float(round(df['foreign_power_costs'].max(), 3)),
        "cheap_price_time": df.loc[df['foreign_power_costs'].idxmin(), 'timestamp'].strftime("%H:%M"),
        "cheap_price": float(round(df['foreign_power_costs'].min(), 3)),
        "sunniest_hour": df.loc[df['pv_profile'].idxmax(), 'timestamp'].strftime("%H:%M"),
        "solar_coverage_pct": float(round(pv_utilized / max(gross_load_total, eps) * 100, 1)),
        "export_ratio_pct": float(round((pv_to_grid / max(total_pv, eps)) * 100, 1)) if total_pv > eps else 0.0,
        "battery_contribution_pct": float(round((batt_to_load + batt_to_grid) / max(net_load_total, eps) * 100, 1)),
        "soc_swing": float(round(soc_swing, 2)),
        "grid_dependence_pct": float(round(grid_dependence * 100, 1)),

        # NEU – Nutzer-KPIs
        # "self_sufficiency_pct": float(round(self_sufficiency * 100, 1)),
        "autonomy_hours": autonomy_hours,
        "direct_pv_to_load": float(round(direct_pv_to_load, 1)),
        "pv_via_battery_to_load": float(round(pv_via_battery_to_load, 1)),
        "peak_window_coverage_pct": float(round(peak_window_coverage * 100, 1)),

        # NEU – Preis/Ersparnis
        "import_cost_eur": float(round(import_cost, 2)),
        "export_revenue_eur": float(round(export_revenue, 2)),
        "net_energy_cashflow_eur": float(round(net_energy_cashflow_eur, 2)),

        # NEU – Umwelt
        "co2_saved_kg": float(round(co2_saved_kg, 1)),

        # NEU – Betriebs-Events
        "busiest_charge_hour": df.loc[busiest_charge_idx, 'timestamp'].strftime('%H:%M'),
        "busiest_discharge_hour": df.loc[busiest_discharge_idx, 'timestamp'].strftime('%H:%M'),
        "soc_min": float(round(soc_min,3)), "soc_min_time": soc_min_time,
        "soc_max": float(round(soc_max,3)), "soc_max_time": soc_max_time,
        "charge_windows": charge_windows,        # [(start,end,kWh), ...]
        "discharge_windows": discharge_windows,  # [(start,end,kWh), ...]

        # Forecast
        "sun_hours_today": sun_hours_today,
        "sun_hours_tomorrow": sun_hours_tomorrow
    }
    return summary