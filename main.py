import os
import httpx
from fastapi import FastAPI, Request

app = FastAPI()

DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")


def alice_response(text: str, end_session: bool = False, version: str = "1.0", session: dict | None = None):
    resp = {
        "version": version,
        "response": {
            "text": text[:1024],
            "end_session": end_session,
        },
    }
    if session:
        resp["session"] = session
    return resp


@app.head("/")
async def head():
    return {}


@app.get("/")
async def health():
    return {"status": "ok"}


@app.post("/")
async def main(request: Request):
    try:
        body = await request.json()
    except Exception:
        return alice_response("Не удалось разобрать запрос.")

    user_text = (body.get("request", {}).get("original_utterance") or "").strip()
    version = body.get("version", "1.0")
    session = body.get("session", {})

    if not user_text:
        return alice_response(
            "Привет! Спросите меня о чём-нибудь.",
            version=version,
            session=session,
        )

    if not DEEPSEEK_API_KEY:
        return alice_response(
            "Сервис временно недоступен: не настроен ключ API.",
            version=version,
            session=session,
        )

    answer = ""
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            r = await client.post(
                DEEPSEEK_API_URL,
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": "Отвечай кратко, одной-двумя фразами."},
                        {"role": "user", "content": user_text},
                    ],
                    "max_tokens": 200,
                },
            )

        print(f"[DeepSeek] status={r.status_code}")
        print(f"[DeepSeek] body={r.text[:500]}")

        r.raise_for_status()
        data = r.json()
        answer = (data.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
        if not answer:
            answer = "Я не смог сформулировать ответ, попробуйте перефразировать."
    except httpx.TimeoutException:
        answer = "Я задумался слишком долго. Повторите вопрос, пожалуйста."
    except httpx.HTTPStatusError as e:
        print(f"[DeepSeek] HTTP error: {e.response.status_code} {e.response.text[:300]}")
        if e.response.status_code == 402:
            answer = "Закончились средства на API-ключе. Пополните баланс DeepSeek."
        elif e.response.status_code == 401:
            answer = "Неверный API-ключ DeepSeek. Проверьте настройки."
        elif e.response.status_code == 429:
            answer = "Слишком много запросов. Подождите немного."
        else:
            answer = f"Ошибка DeepSeek: {e.response.status_code}."
    except Exception as e:
        print(f"[DeepSeek] unexpected error: {type(e).__name__}: {e}")
        answer = "Произошла ошибка при обращении к нейросети."

    return alice_response(answer, version=version, session=session)
