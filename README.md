# ⛺ Weather Camp Chatbot

一個用 Flask + Gemini API 打造的台灣天氣露營小幫手！  
---

## ✨ 專案特色

- 📡 串接中央氣象局 API 拿到一週天氣資料
- 🤖 使用 Gemini 串接當LLM 主體 (Google Generative AI)
- 🌤️ 判讀未來幾天是否適合露營
- Flask 搭建 UI
- 🐳 Docker 容器化
- ☁️ 部署到 Google Cloud Run
- 💬 簡單對話式輸入，隨時問天氣！

---

## 🛠️ 技術棧

- Python 3.11
- Flask 2.3.3
- Google Generative AI (Gemini)
- Gunicorn
- Docker
- Google Cloud Platform (Artifact Registry + Cloud Run)

---

## 📦 如何本地啟動

安裝必要套件：

```
pip install -r requirements.txt
```
啟動 Flask App：

```
python app.py
```
本地訪問網址：http://localhost:8080

🐳 如何用 Docker 運行
Build Docker Image：
```
docker build -t weather-camp-chatbot .
```
本地 Run 起來：
```
docker run -p 8080:8080 weather-camp-chatbot
```
打開瀏覽器訪問：http://localhost:8080

☁️ 如何部署到 Google Cloud Run
登入 GCP 帳號，設定 gcloud cli

建立 Artifact Registry 儲存庫

認證 docker：
```
gcloud auth configure-docker asia-east1-docker.pkg.dev
```
Build & Push image：

```
docker build -t weather-camp-chatbot .
docker tag weather-camp-chatbot asia-east1-docker.pkg.dev/[你的專案ID]/[你的儲存庫名稱]/weather-camp-chatbot
docker push asia-east1-docker.pkg.dev/[你的專案ID]/[你的儲存庫名稱]/weather-camp-chatbot
```



