"""Расчёт прогноза продаж по файлу прогноза спроса (my_forecast.csv / seasonal_forecast.csv).

Формула из условия кейса:
    желают = <q>_base_demand − price_sensitivity × (цена − base_price)
    купят  = min(seats, max(0, желают))
"""
import csv
import os
from datetime import date

QUANTILES = ["0.1", "0.2", "0.3", "0.4", "0.5", "0.6", "0.7", "0.8", "0.9"]
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# Коды аэропортов/городов -> названия (совпадают с частями поля name в routes.csv)
CITY_CODES = {
    "MOW": "Москва",
    "AER": "Сочи",
    "LED": "Санкт-Петербург",
    "KGD": "Калининград",
    "OVB": "Новосибирск",
    "MRV": "Минеральные Воды",
}
ALIASES = {"спб": "LED", "питер": "LED", "петербург": "LED", "мск": "MOW", "минводы": "MRV"}


class ForecastError(ValueError):
    """Ошибка ввода, которую можно показать пользователю."""


def default_forecast_path():
    """Свой прогноз из ML-части, если он есть, иначе файл-заглушка."""
    for name in ("my_forecast.csv", "seasonal_forecast.csv"):
        path = os.path.join(DATA_DIR, name)
        if os.path.exists(path):
            return path
    raise FileNotFoundError("В папке data нет my_forecast.csv или seasonal_forecast.csv")


class Forecaster:
    def __init__(self, forecast_path=None, routes_path=None):
        self.forecast_path = forecast_path or default_forecast_path()
        routes_path = routes_path or os.path.join(DATA_DIR, "routes.csv")
        with open(routes_path, encoding="utf-8") as f:
            self.routes = {r["route"]: r for r in csv.DictReader(f)}
        self.rows = {}
        with open(self.forecast_path, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                self.rows[(r["route"], r["date"])] = r
        self.dates = sorted({d for _, d in self.rows})

    # --- разбор ввода -------------------------------------------------------
    @staticmethod
    def city_code(text):
        t = (text or "").strip()
        if not t:
            raise ForecastError("Укажите пункт отправления и пункт назначения")
        up = t.upper()
        if up in CITY_CODES:
            return up
        low = t.lower().replace("ё", "е")
        if low in ALIASES:
            return ALIASES[low]
        for code, name in CITY_CODES.items():
            if name.lower().replace("ё", "е") == low:
                return code
        raise ForecastError(f"Неизвестный город: «{t}»")

    def route_code(self, origin, destination):
        o, d = self.city_code(origin), self.city_code(destination)
        if o == d:
            raise ForecastError("Пункты отправления и назначения совпадают")
        code = f"{o}-{d}"
        if code not in self.routes:
            available = ", ".join(self.routes[c]["name"] for c in sorted(self.routes))
            raise ForecastError(f"Маршрута {CITY_CODES[o]} → {CITY_CODES[d]} нет в прогнозе. Доступны: {available}")
        return code

    def parse_date(self, text):
        try:
            day = date.fromisoformat((text or "").strip()).isoformat()
        except ValueError:
            raise ForecastError("Дата должна быть в формате ГГГГ-ММ-ДД, например 2026-06-12") from None
        if day not in self.dates:
            raise ForecastError(f"Прогноз есть только на даты с {self.dates[0]} по {self.dates[-1]}")
        return day

    @staticmethod
    def parse_price(value):
        try:
            price = float(str(value).replace(",", ".").replace(" ", ""))
        except ValueError:
            raise ForecastError("Цена должна быть числом, например 9000") from None
        if price != price or price <= 0 or price > 10_000_000:
            raise ForecastError("Цена должна быть положительным числом")
        return price

    # --- расчёт -------------------------------------------------------------
    def forecast(self, origin, destination, day, price):
        route = self.route_code(origin, destination)
        day = self.parse_date(day)
        price = self.parse_price(price)
        info = self.routes[route]
        row = self.rows.get((route, day))
        if row is None:
            raise ForecastError(f"В прогнозе нет рейса {route} на {day}")

        seats = int(float(row["seats"]))
        base_price = float(info["base_price"])
        sens = float(info["price_sensitivity"])

        scenarios = []
        for q in QUANTILES:
            base_demand = float(row[f"{q}_base_demand"])
            want = base_demand - sens * (price - base_price)
            buy = min(seats, max(0.0, want))
            scenarios.append({
                "quantile": float(q),
                "base_demand": base_demand,
                "want": want,
                "buy": buy,
                "capped": want > seats,
                "optimal_price": float(row[f"{q}_price"]) if f"{q}_price" in row else None,
            })
        median = scenarios[QUANTILES.index("0.5")]
        sold_out = sum(s["capped"] for s in scenarios)
        return {
            "route": route,
            "route_name": info["name"],
            "date": day,
            "price": price,
            "base_price": base_price,
            "price_sensitivity": sens,
            "seats": seats,
            "want": median["want"],
            "buy": median["buy"],
            "free_seats": max(0.0, seats - median["buy"]),
            "optimal_price_median": median["optimal_price"],
            "sold_out_scenarios": sold_out,
            "scenarios": scenarios,
            "source": os.path.basename(self.forecast_path),
        }

    def route_list(self):
        return [{"route": c, "name": r["name"], "origin": c.split("-")[0], "destination": c.split("-")[1],
                 "base_price": float(r["base_price"])} for c, r in sorted(self.routes.items())]
