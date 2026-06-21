FROM python:3.11-slim

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Рабочая директория
WORKDIR /bot

# Копируем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY . .

# Логи
RUN mkdir -p logs

# Пользователь
RUN useradd --create-home --shell /bin/bash bot_user && \
    chown -R bot_user:bot_user /bot
USER bot_user

# Переменные окружения
ENV PYTHONPATH=/bot
ENV PYTHONUNBUFFERED=1

# Жестко задаем точку входа, чтобы не наследовать чужие ENTRYPOINT
ENTRYPOINT ["python", "main.py"]