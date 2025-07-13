import requests
import logging
import time


class GitHubAPIClient:
    """GitHub API와의 통신을 담당하며, Session과 자동 재시도를 사용하는 클라이언트"""
    BASE_URL = "https://api.github.com"

    def __init__(self, token, max_retries=3, timeout=30):
        if not token:
            raise ValueError("GitHub token is required for APIClient.")

        self.max_retries = max_retries
        self.timeout = timeout

        # ✨ Session 객체 생성 및 헤더 설정
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        })
        logging.info("GitHubAPIClient initialized with Session and retry logic.")

    def _send_request_with_retry(self, url, params=None):
        """지정한 횟수만큼 재시도하며 API 요청을 보냅니다."""
        for attempt in range(self.max_retries):
            try:
                # ✨ requests.get 대신 self.session.get 사용 및 timeout 설정
                response = self.session.get(url, params=params, timeout=self.timeout)
                response.raise_for_status()
                return response
            except requests.exceptions.RequestException as e:
                logging.warning(f"Attempt {attempt + 1} failed for {url}: {e}. Retrying...")
                time.sleep(2 ** attempt)

        logging.error(f"API request failed for {url} after {self.max_retries} attempts.")
        raise ConnectionError(f"API request failed after multiple retries for url: {url}")

    def _make_paginated_request(self, url, params=None):
        """페이지네이션을 처리하며 모든 데이터를 리스트로 가져옵니다."""
        if params is None:
            params = {}
        results = []

        while url:
            response = self._send_request_with_retry(url, params=params)
            results.extend(response.json())
            url = response.links.get('next', {}).get('url')
            params = {}
        return results

    def get_pull_requests(self, owner, repo):
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/pulls"
        logging.info(f"Fetching pull requests for {owner}/{repo}")
        return self._make_paginated_request(url, params={'state': 'all', 'per_page': 100})

    def get_pr_detail(self, pr_url):
        logging.info(f"Fetching PR detail from: {pr_url}")
        response = self._send_request_with_retry(pr_url)
        return response.json()

    def get_reviews_for_pr(self, pr_url):
        reviews_url = f"{pr_url}/reviews"
        logging.info(f"Fetching reviews from: {reviews_url}")
        return self._make_paginated_request(reviews_url, params={'per_page': 100})

    def get_issues(self, owner, repo):
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/issues"
        logging.info(f"Fetching issues for {owner}/{repo}")
        return self._make_paginated_request(url, params={'state': 'all', 'per_page': 100})