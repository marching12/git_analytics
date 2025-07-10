import os
import requests
import json

from dotenv import load_dotenv
load_dotenv()

# 설정: 고정된 GitHub 사용자/조직 이름
GITHUB_OWNER = "BCSDLab"

# 환경 변수에서 GitHub 토큰 불러오기 (또는 직접 입력 가능)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")  # or "ghp_..."
if not GITHUB_TOKEN:
    raise Exception("GITHUB_TOKEN 환경변수가 설정되어 있지 않습니다.")

# GitHub API 호출 URL
url = f"https://api.github.com/orgs/{GITHUB_OWNER}/repos"

# 요청 헤더 설정
headers = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

params = {
    "per_page": 100,  # 최대 100개
    "type": "all",    # public + private
    "sort": "full_name"
}

repo_names = []

print(f"📦 {GITHUB_OWNER} 조직의 GitHub 저장소 목록을 가져오는 중...")

page = 1
while True:
    params["page"] = page
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    data = response.json()
    if not data:
        break
    repo_names += [repo["name"] for repo in data]
    page += 1

# 결과 저장
with open("function_1_collector/repos.json", "w") as f:
    json.dump(repo_names, f, indent=2)

print(f"✅ {len(repo_names)}개의 저장소 이름이 repos.json 파일에 저장되었습니다.")
