#!/usr/bin/env python3
"""Вариант A: простое прогнозирование из командной строки.

Пример:
    python3 predict.py Москва Сочи 2026-06-12 9000
    python3 predict.py MOW AER 2026-06-12 9000 --chart chart.png   (график, нужен matplotlib)
"""
import argparse
import sys

from forecast_core import ForecastError, Forecaster


def main(argv=None):
    ap = argparse.ArgumentParser(description="Прогноз продаж авиабилетов по прогнозу спроса")
    ap.add_argument("origin", help="пункт отправления (код или город, например MOW / Москва)")
    ap.add_argument("destination", help="пункт назначения (например AER / Сочи)")
    ap.add_argument("date", help="дата вылета ГГГГ-ММ-ДД")
    ap.add_argument("price", help="цена билета, ₽")
    ap.add_argument("--forecast", help="путь к файлу прогноза (по умолчанию data/my_forecast.csv или seasonal_forecast.csv)")
    ap.add_argument("--chart", help="сохранить график распределения спроса в PNG")
    args = ap.parse_args(argv)

    try:
        fc = Forecaster(args.forecast)
        r = fc.forecast(args.origin, args.destination, args.date, args.price)
    except ForecastError as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        return 2

    print(f"Рейс: {r['route_name']} ({r['route']}), {r['date']}, цена {r['price']:.0f} ₽")
    print(f"Мест в самолётах: {r['seats']}")
    print(f"Желают купить (медиана): {r['want']:.0f}")
    print(f"Прогноз продаж: {r['buy']:.0f}   свободно мест: {r['free_seats']:.0f}")
    print(f"Источник прогноза: {r['source']}")
    print("\nСценарии спроса при этой цене:")
    print(" квантиль   желают   купят")
    for s in r["scenarios"]:
        mark = "  ← упираемся в места" if s["capped"] else ""
        print(f"   {s['quantile']:.1f}    {s['want']:7.0f} {s['buy']:7.0f}{mark}")

    if args.chart:
        save_chart(r, args.chart)
        print(f"\nГрафик сохранён: {args.chart}")
    return 0


def save_chart(r, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    qs = [s["quantile"] for s in r["scenarios"]]
    want = [s["want"] for s in r["scenarios"]]
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar([f"{q:.1f}" for q in qs], want, color=["#d9822b" if s["capped"] else "#2f6fb0" for s in r["scenarios"]])
    ax.axhline(r["seats"], color="#c0392b", ls="--", label=f"мест: {r['seats']}")
    ax.set_xlabel("квантиль (сценарий спроса)")
    ax.set_ylabel("желают купить")
    ax.set_title(f"{r['route_name']}, {r['date']}, цена {r['price']:.0f} ₽")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=120)


if __name__ == "__main__":
    sys.exit(main())
