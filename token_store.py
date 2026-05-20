"""
GitHub Gist를 refresh_token 영구 저장소로 사용.
Streamlit Cloud는 파일시스템이 휘발성이므로 외부 저장소 필요.
"""
import json
import requests

GIST_FILENAME = "cafe24_tokens.json"


class GistTokenStore:
    def __init__(self, gist_id: str, github_token: str):
        self.gist_id = gist_id
        self._headers = {
            "Authorization": f"token {github_token}",
            "Accept": "application/vnd.github.v3+json",
        }

    def read(self) -> str:
        resp = requests.get(
            f"https://api.github.com/gists/{self.gist_id}",
            headers=self._headers,
            timeout=10,
        )
        resp.raise_for_status()
        content = resp.json()["files"][GIST_FILENAME]["content"]
        return json.loads(content)["refresh_token"]

    def write(self, refresh_token: str) -> None:
        requests.patch(
            f"https://api.github.com/gists/{self.gist_id}",
            headers=self._headers,
            json={"files": {GIST_FILENAME: {"content": json.dumps({"refresh_token": refresh_token})}}},
            timeout=10,
        )


def create_gist(github_token: str, initial_refresh_token: str) -> str:
    """최초 설정 시 private Gist 생성 후 gist_id 반환."""
    resp = requests.post(
        "https://api.github.com/gists",
        headers={
            "Authorization": f"token {github_token}",
            "Accept": "application/vnd.github.v3+json",
        },
        json={
            "description": "bornewlab cafe24 token store (do not delete)",
            "public": False,
            "files": {
                GIST_FILENAME: {
                    "content": json.dumps({"refresh_token": initial_refresh_token})
                }
            },
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["id"]
