FROM python:3.13-slim
WORKDIR /app
COPY forecast_core.py predict.py server.py ./
COPY static ./static
COPY data/routes.csv data/my_forecast.csv data/seasonal_forecast.csv ./data/
RUN useradd -r -u 10001 app && mkdir -p /app/state && chown app /app/state
USER app
ENV USERS_FILE=/app/state/users.json HOST=0.0.0.0 PORT=8000 PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["python", "server.py"]
