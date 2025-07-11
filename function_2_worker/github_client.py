import requests
import logging


class GitHubAPIClient:
    BASE_URL = "https://api.github.com"

    def __init__(self, token):
        self._headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        }

    def _make_paginated_request(self, url, params=None):
        """페이지네이션을 처리하며 모든 데이터를 가져옵니다."""
        if params is None:
            params = {}
        results = []
        while url:
            response = requests.get(url, headers=self._headers, params=params)
            response.raise_for_status()
            results.extend(response.json())
            url = response.links.get('next', {}).get('url')
            params = {}
        return results

    def get_pull_requests(self, owner, repo):
        """특정 레포지토리의 모든 PR 목록을 가져옵니다."""
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/pulls"
        return self._make_paginated_request(url, params={'state': 'all'})

    def get_pr_detail(self, pr_url):
        """PR 상세 정보를 가져옵니다."""
        response = requests.get(pr_url, headers=self._headers)
        response.raise_for_status()
        return response.json()

    def get_reviews(self, review_url):
        """특정 PR의 모든 리뷰 목록을 가져옵니다."""
        return self._make_paginated_request(review_url)

    def get_issues(self, owner, repo):
        """특정 레포지토리의 모든 이슈 목록을 가져옵니다."""
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/issues"
        return self._make_paginated_request(url, params={'state': 'all'})