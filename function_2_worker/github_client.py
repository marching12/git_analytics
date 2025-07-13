import requests
import logging


class GitHubAPIClient:
    """GitHub API와의 통신을 담당하는 클라이언트"""
    BASE_URL = "https://api.github.com"

    def __init__(self, token):
        if not token:
            raise ValueError("GitHub token is required for APIClient.")
        self._headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        }
        logging.info("GitHubAPIClient initialized.")

    def _make_paginated_request(self, url, params=None):
        """페이지네이션을 처리하며 모든 데이터를 리스트로 가져옵니다."""
        if params is None:
            params = {}
        results = []
        initial_params = params.copy()

        while url:
            try:
                response = requests.get(url, headers=self._headers, params=initial_params)
                response.raise_for_status()
                results.extend(response.json())
                url = response.links.get('next', {}).get('url')
                initial_params = {}
            except requests.exceptions.RequestException as e:
                logging.error(f"API request failed for url {url}: {e}")
                break
        return results

    def get_pull_requests(self, owner, repo):
        """특정 레포지토리의 모든 PR 목록을 가져옵니다."""
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/pulls"
        logging.info(f"Fetching pull requests for {owner}/{repo}")
        return self._make_paginated_request(url, params={'state': 'all', 'per_page': 100})

    def get_pr_detail(self, pr_url):
        """단일 PR의 상세 정보를 가져옵니다."""
        logging.info(f"Fetching PR detail from: {pr_url}")
        response = requests.get(pr_url, headers=self._headers)
        response.raise_for_status()
        return response.json()

    def get_reviews_for_pr(self, pr_url):
        """특정 PR의 모든 리뷰 목록을 가져옵니다."""
        reviews_url = f"{pr_url}/reviews"
        logging.info(f"Fetching reviews from: {reviews_url}")
        return self._make_paginated_request(reviews_url, params={'per_page': 100})

    def get_issues(self, owner, repo):
        """특정 레포지토리의 모든 이슈 목록을 가져옵니다."""
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/issues"
        logging.info(f"Fetching issues for {owner}/{repo}")
        return self._make_paginated_request(url, params={'state': 'all', 'per_page': 100})