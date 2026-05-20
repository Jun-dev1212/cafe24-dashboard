"""
보뉴랩 대시보드 최초 인증 설정 스크립트
실행: python3 auth_setup.py
결과: .streamlit/secrets.toml 자동 생성
"""
import webbrowser
import requests
import os
from urllib.parse import urlencode

SCOPE = "mall.read_order,mall.read_analytics,mall.read_salesreport"


def main():
    print("\n===== 보뉴랩 대시보드 최초 인증 설정 =====\n")

    dashboard_pw = input("대시보드 비밀번호 (팀 공유용): ").strip()

    # ── [1/2] Cafe24 ─────────────────────────────────────
    print("\n[1/2] Cafe24 API 설정")
    mall_id       = input("  Mall ID (예: nowenergy): ").strip()
    client_id     = input("  Client ID: ").strip()
    client_secret = input("  Client Secret: ").strip()
    redirect_uri  = f"https://{mall_id}.cafe24.com"

    auth_url = (
        f"https://{mall_id}.cafe24api.com/api/v2/oauth/authorize?"
        + urlencode({
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": SCOPE,
        })
    )
    print("\n  브라우저에서 Cafe24 로그인 후 권한 허용을 클릭하세요:")
    print(f"\n  {auth_url}\n")
    webbrowser.open(auth_url)

    print("  ▶ 권한 허용 후 주소창이 아래처럼 바뀝니다:")
    print(f"    https://{mall_id}.cafe24.com?code=XXXXXX&...")
    print("  ▶ code= 뒤의 값(& 앞까지)을 복사해서 붙여넣으세요.\n")
    code = input("  code 값: ").strip()
    if not code:
        print("❌ code를 입력하지 않았습니다.")
        return

    print("  토큰 교환 중...")
    resp = requests.post(
        f"https://{mall_id}.cafe24api.com/api/v2/oauth/token",
        data={"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri},
        auth=(client_id, client_secret),
    )
    if resp.status_code != 200:
        print(f"❌ 토큰 교환 실패: {resp.text}")
        return
    cafe24_refresh_token = resp.json()["refresh_token"]
    print("  ✅ Cafe24 토큰 발급 완료")

    # ── [2/2] 쿠팡Wing ────────────────────────────────────
    print("\n[2/2] 쿠팡Wing API 설정")
    print("  (아직 없으면 그냥 엔터 — 나중에 추가 가능)")
    print("  wing.coupang.com → 판매지원도구 → Open API → API Key 발급")
    cpg_access_key = input("  Access Key (없으면 엔터): ").strip()
    cpg_secret_key = input("  Secret Key (없으면 엔터): ").strip()
    cpg_vendor_id  = input("  Vendor ID  (없으면 엔터): ").strip()

    # ── secrets.toml 생성 ─────────────────────────────────
    secrets = (
        f'# Cafe24\n'
        f'cafe24_mall_id = "{mall_id}"\n'
        f'cafe24_client_id = "{client_id}"\n'
        f'cafe24_client_secret = "{client_secret}"\n'
        f'cafe24_refresh_token = "{cafe24_refresh_token}"\n'
        f'\n'
        f'# 쿠팡Wing\n'
        f'coupang_access_key = "{cpg_access_key}"\n'
        f'coupang_secret_key = "{cpg_secret_key}"\n'
        f'coupang_vendor_id = "{cpg_vendor_id}"\n'
        f'\n'
        f'# 대시보드\n'
        f'dashboard_password = "{dashboard_pw}"\n'
    )

    os.makedirs(".streamlit", exist_ok=True)
    with open(".streamlit/secrets.toml", "w") as f:
        f.write(secrets)

    print("\n✅ 설정 완료!")
    print("📁 .streamlit/secrets.toml 저장됨\n")
    print("⚠️  refresh_token은 14일마다 만료됩니다.")
    print("   만료 전에 python3 auth_setup.py 를 다시 실행해서 갱신하세요.\n")
    print("=" * 60)
    print("Streamlit Cloud > App settings > Secrets 에 붙여넣으세요:\n")
    print(secrets)
    print("=" * 60)


if __name__ == "__main__":
    main()
