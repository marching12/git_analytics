import os
import requests
import json
import random
from datetime import datetime
from dotenv import load_dotenv

# .env 파일에서 환경 변수를 로드합니다.
load_dotenv()

# --- 설정 ---
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
ORG_NAME = "BCSDLab"
REPO_LIST = [
    "KOIN_ANDROID",
    "KOIN_ORDER_WEBVIEW",
    "KOIN_WEB_RECODE",
    "KOIN_API_V2",
    "KOIN_iOS"
]

LABEL_TEAM_MAP = {
    'user': 1, '👤 User': 1, 'Team User': 1,
    'campus': 2, '🎓 Campus': 2, 'Team Campus': 2,
    'business': 3, '💼 Business': 3, 'Team Business': 3
}
COMMON_TEAM_ID = 4

HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
}


def make_request(url, params=None):
    """GitHub API 요청을 처리하는 헬퍼 함수"""
    if params is None:
        params = {}
    response = requests.get(url, headers=HEADERS, params=params)
    response.raise_for_status()
    return response.json()


def get_team_id_from_labels(labels):
    """PR의 레이블 목록을 기반으로 팀 ID를 결정하는 함수"""
    for label in labels:
        label_name = label['name']
        if label_name in LABEL_TEAM_MAP:
            return LABEL_TEAM_MAP[label_name]
    return COMMON_TEAM_ID


def collect_activities_for_repo(org, repo_name):
    """하나의 레포지토리에서 PR, 이슈, 리뷰 데이터를 수집합니다."""
    print(f"📄 레포지토리 [{repo_name}]의 활동 데이터 수집 시작...")

    repo_prs = []
    repo_issues = []
    repo_reviews = []

    # 1. Pull Requests 목록 수집 및 샘플링
    prs_url = f"https://api.github.com/repos/{org}/{repo_name}/pulls"
    pr_list_full = make_request(prs_url, params={"state": "all", "per_page": 100})

    if len(pr_list_full) > 10:
        print(f"  -> 총 {len(pr_list_full)}개의 PR 중 10개를 랜덤 샘플링합니다.")
        pr_list = random.sample(pr_list_full, 10)
    else:
        pr_list = pr_list_full

    total_pr_count = len(pr_list)
    if total_pr_count == 0:
        print("  -> 처리할 PR이 없습니다.")
    else:
        print(f"  -> 총 {total_pr_count}개의 PR에 대한 상세 정보 수집을 시작합니다.")

    for i, pr_summary in enumerate(pr_list, 1):
        print(f"    - [{repo_name}] PR #{pr_summary['number']} 처리 중... ({i}/{total_pr_count})")

        pr_detail_url = pr_summary['url']
        pr = make_request(pr_detail_url)
        team_id = get_team_id_from_labels(pr['labels'])

        repo_prs.append({
            'pr_id': pr['id'],
            'repo_id': pr['head']['repo']['id'],
            'team_id': team_id,
            'pr_number': pr['number'],
            'title': pr['title'],
            'state': pr['state'],
            'author_id': pr['user']['id'] if pr.get('user') else None,
            'created_at': pr['created_at'],
            'updated_at': pr['updated_at'],
            'merged_at': pr['merged_at'],
            'closed_at': pr['closed_at'],
            'additions': pr['additions'],
            'deletions': pr['deletions'],
            'commit_count': pr['commits'],
        })

        reviews_url = f"{pr['url']}/reviews"
        reviews = make_request(reviews_url, params={"per_page": 100})
        for review in reviews:
            repo_reviews.append({
                'review_id': review['id'],
                'pr_id': pr['id'],
                'reviewer_id': review['user']['id'] if review.get('user') else None,
                'state': review['state'],
                'submitted_at': review['submitted_at'],
            })

    # ✨ 변경된 부분: 최근 5개의 이슈만 가져오도록 수정
    print(f"    - [{repo_name}] 최근 이슈 5개 수집 중...")
    issues_url = f"https://api.github.com/repos/{org}/{repo_name}/issues"
    # per_page=5 : 한 페이지에 5개씩 가져옴 (최신순이 기본 정렬)
    issues_list = make_request(issues_url, params={"state": "all", "per_page": 5})

    for issue in issues_list:
        if 'pull_request' not in issue:
            repo_issues.append({
                'issue_id': issue['id'],
                'repo_id': issue['repository']['id'] if issue.get('repository') else None,
                'issue_number': issue['number'],
                'title': issue['title'],
                'state': issue['state'],
                'author_id': issue['user']['id'] if issue.get('user') else None,
                'created_at': issue['created_at'],
                'updated_at': issue['updated_at'],
                'closed_at': issue['closed_at'],
            })

    print(f"  -> PR: {len(repo_prs)}개, 이슈: {len(repo_issues)}개, 리뷰: {len(repo_reviews)}개 수집 완료.")
    return repo_prs, repo_issues, repo_reviews


if __name__ == "__main__":
    all_pull_requests = []
    all_issues = []
    all_reviews = []

    for repo in REPO_LIST:
        prs, issues, reviews = collect_activities_for_repo(ORG_NAME, repo)
        all_pull_requests.extend(prs)
        all_issues.extend(issues)
        all_reviews.extend(reviews)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    with open(f"pull_requests_{timestamp}.json", "w", encoding='utf-8') as f:
        json.dump(all_pull_requests, f, indent=2, ensure_ascii=False)

    with open(f"issues_{timestamp}.json", "w", encoding='utf-8') as f:
        json.dump(all_issues, f, indent=2, ensure_ascii=False)

    with open(f"reviews_{timestamp}.json", "w", encoding='utf-8') as f:
        json.dump(all_reviews, f, indent=2, ensure_ascii=False)

    print(f"\n✅ 모든 데이터 수집 완료! {timestamp} 날짜의 JSON 파일들을 확인하세요.")