# ------------------------------------------------------------------
# JiuEat 後端服務映像檔
# 安裝 Microsoft ODBC Driver 18 for SQL Server（Debian 12 / bookworm）
# ------------------------------------------------------------------
FROM python:3.12-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ACCEPT_EULA=Y

# 加入 Microsoft 的套件來源並安裝 ODBC Driver 18
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        gnupg2 \
        apt-transport-https \
        ca-certificates \
    && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && curl -fsSL https://packages.microsoft.com/config/debian/12/prod.list > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 unixodbc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先複製相依檔以善用快取
COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt

# 複製後端與前端程式碼
COPY backend ./backend
COPY frontend ./frontend
COPY ml ./ml

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]