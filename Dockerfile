# 1단계: 보호자 화면(TypeScript)을 컴파일한다.
FROM node:22-slim AS web
WORKDIR /build
COPY package.json package-lock.json tsconfig.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY web ./web
RUN npx tsc -p tsconfig.json

# 2단계: API·워커·가짜 모델 서버가 같은 이미지를 쓰고 실행 명령만 다르다(compose.yaml).
FROM python:3.12-slim
WORKDIR /app
COPY service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY fallback.py service/*.py ./
COPY contracts ./contracts
COPY web/index.html ./web/index.html
COPY --from=web /build/web/dist/app.js ./web/app.js
USER 10001
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
