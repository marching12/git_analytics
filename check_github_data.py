import os
import requests
from dotenv import load_dotenv

# .env 파일에서 환경 변수를 로드합니다.
load_dotenv()

# ----------------------------------------------------
# ✅ .env 파일에서 GITHUB_TOKEN을 자동으로 불러옵니다.
# ✅ 아래의 조직 이름과 레포지토리 목록을 확인하세요.
# ----------------------------------------------------
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# 1. 정보를 조회할 GitHub 조직(Organization) 이름
ORG_NAME = "BCSDLab"

# 2. 정보를 확인할 레포지토리 이름 목록
REPO_LIST = [
    "KOIN_ANDROID",
    "KOIN_ORDER_WEBVIEW",
    "KOIN_WEB_RECODE",
    "KOIN_API_V2",
    "KOIN_iOS"
]
# ----------------------------------------------------


# 토큰이 없는 경우 오류 메시지 출력 후 종료
if not GITHUB_TOKEN:
    raise ValueError(".env 파일에 GITHUB_TOKEN이 설정되지 않았습니다.")

# API 요청을 위한 공통 헤더
headers = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}


def get_org_members(org):
    """조직의 멤버 정보를 가져옵니다."""
    print("=============================================")
    print(f"👥 {org} 조직 멤버 정보 (for developers table)")
    print("=============================================")

    url = f"https://api.github.com/orgs/{org}/members"
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        members = response.json()
        print(f"{'developer_id':<15} {'login_name'}")
        print("---------------------------------------------")
        for member in members:
            print(f"{member['id']:<15} {member['login']}")
    else:
        print(f"오류 발생: {response.status_code} - {response.text}")
    print("\n")


def get_repo_and_labels_info(org, repo_name):
    """레포지토리의 기본 정보와 레이블 목록을 가져옵니다."""
    print("=============================================")
    print(f"📄 레포지토리: {repo_name} 정보 조회")
    print("=============================================")

    # 레포지토리 정보 (for repositories table)
    print("\n--- [Repository Info] ---")
    repo_url = f"https://api.github.com/repos/{org}/{repo_name}"
    repo_response = requests.get(repo_url, headers=headers)

    if repo_response.status_code == 200:
        repo_data = repo_response.json()
        print(f"{'repo_id':<15} {'repo_name'}")
        print("---------------------------------------------")
        print(f"{repo_data['id']:<15} {repo_data['full_name']}")
    else:
        print(f"레포 정보 조회 오류: {repo_response.status_code} - {repo_response.text}")
        return

    # 레이블 정보 (for label_team_mapping table)
    print("\n--- [Available Labels] ---")
    labels_url = f"https://api.github.com/repos/{org}/{repo_name}/labels"
    labels_response = requests.get(labels_url, headers=headers)

    if labels_response.status_code == 200:
        labels = labels_response.json()
        if not labels:
            print("이 레포지토리에는 레이블이 없습니다.")
            print("\n")
            return

        print("label_name")
        print("---------------------------------------------")
        for label in labels:
            print(label['name'])
    else:
        print(f"레이블 조회 오류: {labels_response.status_code} - {labels_response.text}")
    print("\n")


if __name__ == "__main__":
    # 1. 조직 멤버 정보를 가져옵니다. (1회 실행)
    get_org_members(ORG_NAME)

    # 2. 지정된 각 레포지토리의 상세 정보를 조회합니다.
    for repo in REPO_LIST:
        get_repo_and_labels_info(ORG_NAME, repo)