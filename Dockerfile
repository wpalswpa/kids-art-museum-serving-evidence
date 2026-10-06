# API·워커·가짜 모델 서버가 같은 이미지를 쓰고 실행 명령만 다르다(compose.yaml).
FROM python:3.12-slim
WORKDIR /app
COPY service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY fallback.py service/*.py ./
COPY contracts ./contracts
USER 10001
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
