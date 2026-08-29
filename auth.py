import os
import requests
from dotenv import load_dotenv

load_dotenv()

APP_KEY = os.getenv("NH_APP_KEY")
APP_SECRET = os.getenv("NH_APP_SECRET")

TOKEN_URL = "https://api.nhplug.com:8443/oauth2/token"


def get_access_token():
    if not APP_KEY or not APP_SECRET:
        raise RuntimeError(
            "NH_APP_KEY와 NH_APP_SECRET을 .env에 설정해주세요."
        )

    data = {
        "appkey": APP_KEY,
        "appsecretkey": APP_SECRET,
        "grant_type": "client_credentials",
        "scope": "oob",
    }

    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }

    response = requests.post(
        TOKEN_URL,
        data=data,
        headers=headers,
        timeout=10,
    )

    response.raise_for_status()
    return response.json()


if __name__ == "__main__":
    result = get_access_token()

    print("Namuh PLUG 인증 성공")
    print("token_type:", result.get("token_type"))
    print("expires_in:", result.get("expires_in"))

    # 실제 토큰 전체는 화면에 출력하지 않습니다.
    token = result.get("access_token")

    if token:
        print("access_token:", token[:8] + "...")
