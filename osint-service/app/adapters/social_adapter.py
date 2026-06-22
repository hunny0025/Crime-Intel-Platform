"""Social platform adapter — fetches public profile/connection data.

HARD REQUIREMENT: If credentials are not configured for a platform,
the adapter MUST return a clear "unavailable — credentials not configured"
result. This is enforced in code, not just documentation.
"""

import logging
import httpx
from typing import Optional
from app.adapters.base import BaseOSINTAdapter, OSINTResult
from app.config import settings

logger = logging.getLogger(__name__)


class SocialAdapter(BaseOSINTAdapter):
    """Generic social platform adapter — platform-specific subclasses below."""
    source_type = "social"

    def __init__(self, platform: str = "generic"):
        self.platform = platform

    def is_available(self) -> bool:
        # Check platform-specific credentials
        creds = {
            "twitter": settings.TWITTER_BEARER_TOKEN,
            "github": settings.GITHUB_TOKEN,
        }
        return bool(creds.get(self.platform, ""))

    def execute(self, query: str) -> OSINTResult:
        if not self.is_available():
            return self.unavailable_result(query)

        if self.platform == "github":
            return self._github_lookup(query)
        elif self.platform == "twitter":
            return self._twitter_lookup(query)
        else:
            return self.unavailable_result(query)

    def _github_lookup(self, username: str) -> OSINTResult:
        """Fetch GitHub public profile and follower data."""
        try:
            headers = {"Authorization": f"token {settings.GITHUB_TOKEN}"}
            with httpx.Client(timeout=30.0) as client:
                # Profile
                resp = client.get(
                    f"https://api.github.com/users/{username}",
                    headers=headers,
                )
                resp.raise_for_status()
                profile = resp.json()

                entities = []
                if profile.get("email"):
                    entities.append({
                        "entity_type": "email",
                        "value": profile["email"],
                        "confidence": 0.5,
                    })
                if profile.get("company"):
                    entities.append({
                        "entity_type": "organization",
                        "value": profile["company"].strip("@"),
                        "confidence": 0.3,
                    })
                if profile.get("blog"):
                    entities.append({
                        "entity_type": "related_domain",
                        "value": profile["blog"],
                        "confidence": 0.4,
                    })

                return OSINTResult(
                    source_type=f"social_github",
                    query=username,
                    raw_result={
                        "login": profile.get("login"),
                        "name": profile.get("name"),
                        "bio": profile.get("bio"),
                        "created_at": profile.get("created_at"),
                        "followers": profile.get("followers"),
                        "following": profile.get("following"),
                        "public_repos": profile.get("public_repos"),
                    },
                    extracted_entities=entities,
                )
        except Exception as e:
            logger.warning("GitHub lookup failed for %s: %s", username, e)
            return OSINTResult(
                source_type="social_github", query=username,
                raw_result={}, extracted_entities=[], error=str(e),
            )

    def _twitter_lookup(self, username: str) -> OSINTResult:
        """Fetch Twitter/X public profile via API v2."""
        try:
            headers = {"Authorization": f"Bearer {settings.TWITTER_BEARER_TOKEN}"}
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(
                    f"https://api.twitter.com/2/users/by/username/{username}",
                    headers=headers,
                    params={"user.fields": "created_at,description,public_metrics"},
                )
                resp.raise_for_status()
                data = resp.json().get("data", {})

                return OSINTResult(
                    source_type="social_twitter",
                    query=username,
                    raw_result=data,
                    extracted_entities=[],  # Twitter rarely reveals linkable identifiers
                )
        except Exception as e:
            logger.warning("Twitter lookup failed for %s: %s", username, e)
            return OSINTResult(
                source_type="social_twitter", query=username,
                raw_result={}, extracted_entities=[], error=str(e),
            )

    def expand_connections(self, username: str, max_connections: int = 100) -> OSINTResult:
        """Fetch public connections (followers/following) up to max_connections."""
        if not self.is_available():
            return self.unavailable_result(username)

        if self.platform == "github":
            return self._github_connections(username, max_connections)
        return self.unavailable_result(username)

    def _github_connections(self, username: str, max_connections: int) -> OSINTResult:
        """Fetch GitHub following list (public, API-permitted)."""
        try:
            headers = {"Authorization": f"token {settings.GITHUB_TOKEN}"}
            connections = []
            page = 1
            per_page = min(100, max_connections)

            with httpx.Client(timeout=30.0) as client:
                while len(connections) < max_connections:
                    resp = client.get(
                        f"https://api.github.com/users/{username}/following",
                        headers=headers,
                        params={"per_page": per_page, "page": page},
                    )
                    resp.raise_for_status()
                    batch = resp.json()
                    if not batch:
                        break
                    connections.extend(batch[:max_connections - len(connections)])
                    page += 1

            entities = [
                {"entity_type": "social_handle", "value": c["login"], "confidence": 0.5}
                for c in connections
            ]

            return OSINTResult(
                source_type="social_github_connections",
                query=username,
                raw_result={"connections": [c["login"] for c in connections]},
                extracted_entities=entities,
            )
        except Exception as e:
            return OSINTResult(
                source_type="social_github_connections", query=username,
                raw_result={}, extracted_entities=[], error=str(e),
            )
