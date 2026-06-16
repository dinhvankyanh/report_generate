FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code + bundled sample data (Report_Sample/) so the agent runs headless.
COPY . .

EXPOSE 8080
CMD ["python", "main.py"]
