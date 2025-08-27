import re
import time
import aiohttp
from typing import Dict, List, Optional, Type
from urllib.parse import urljoin

from maubot import MessageEvent, Plugin
from maubot.handlers import command, event
from mautrix.types import EventType, MessageType
from mautrix.util.config import BaseProxyConfig, ConfigUpdateHelper


class Config(BaseProxyConfig):
    def do_update(self, helper: ConfigUpdateHelper) -> None:
        helper.copy("jira_url")
        helper.copy("rest_api_suffix")
        helper.copy("ignored_users")
        helper.copy("issue_cooldown")
        helper.copy("max_issues_per_message")
        helper.copy("include_url")
        helper.copy("respond_to_urls")


class JiraPlugin(Plugin):
    """
    JIRA issue lookup plugin for maubot

    Automatically detects JIRA issue keys (like PROJECT-123) in messages
    and responds with the issue title and URL.

    Features:
    - Automatic issue detection in messages
    - Cooldown to prevent spam
    - Manual project list updates
    - Configurable ignored users

    Commands:
    - !jira update - Update the list of JIRA projects
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._projects: List[str] = []
        self._recent_issues: Dict[str, int] = {}

        jar = aiohttp.DummyCookieJar()
        self.nocookie = aiohttp.ClientSession(loop=self.loop, cookie_jar=jar)

    async def start(self) -> None:
        await super().start()
        self.config.load_and_update()
        await self._load_projects()

    @classmethod
    def get_config_class(cls) -> Type[BaseProxyConfig]:
        return Config

    def on_external_config_update(self) -> None:
        self.config.load_and_update()

    @event.on(EventType.ROOM_MESSAGE)
    async def on_message(self, evt: MessageEvent) -> None:
        """Handle incoming messages and look for JIRA issue keys"""
        if evt.content.msgtype != MessageType.TEXT:
            return

        # Skip if sender is in ignored list
        if self._is_ignored_user(evt.sender):
            return

        # Skip if this is our own message
        if evt.sender == self.client.mxid:
            return

        await self._process_message_for_issues(evt)

    async def _process_message_for_issues(self, evt: MessageEvent) -> None:
        """Process a message and respond with JIRA issue information if found"""
        message_body = evt.content.body

        # Find all potential JIRA issue keys (PROJECT-123 format)
        issue_matches = re.findall(r"\b([A-Z]+-\d+)\b", message_body)

        if not issue_matches:
            return

        # Check if issues are mentioned in URLs and skip if configured to do so
        if not self.config["respond_to_urls"]:
            if re.search(r"https?://\S*", message_body):
                # Check if any issue is part of a URL
                for issue in issue_matches:
                    if re.search(rf"https?://\S*{re.escape(issue)}\b", message_body):
                        issue_matches.remove(issue)

        if not issue_matches:
            return

        # Remove duplicates while preserving order
        unique_issues = list(dict.fromkeys(issue_matches))

        # Limit the number of issues to process
        max_issues = self.config["max_issues_per_message"]
        if len(unique_issues) > max_issues:
            unique_issues = unique_issues[:max_issues]

        responses = []

        for issue_key in unique_issues:
            project_key = issue_key.split("-")[0]

            # Check if this is a valid project
            if project_key not in self._projects:
                continue

            # Check cooldown
            if self._is_issue_on_cooldown(issue_key):
                continue

            # Fetch issue information
            issue_info = await self._fetch_issue_info(issue_key)
            if issue_info:
                responses.append(issue_info)

        if responses:
            # Check if the original message started with [off]
            if message_body.lower().startswith("[off]"):
                formatted_responses = ["[off] " + response for response in responses]
            else:
                formatted_responses = responses

            response_text = "\n".join(formatted_responses)
            await evt.respond(response_text)

    async def _fetch_issue_info(self, issue_key: str) -> Optional[str]:
        """Fetch information for a specific JIRA issue"""
        try:
            api_base = urljoin(self.config["jira_url"], self.config["rest_api_suffix"])
            issue_url = urljoin(api_base + "/", f"issue/{issue_key}")

            response = await self.nocookie.get(issue_url)

            if response.status == 200:
                data = await response.json()
                title = data["fields"]["summary"]

                if self.config["include_url"]:
                    browse_url = urljoin(self.config["jira_url"], f"browse/{issue_key}")
                    return f"[{issue_key}]({browse_url}): {title}"
                else:
                    return f"{issue_key}: {title}"
            else:
                self.log.debug(
                    f"Failed to fetch issue {issue_key}: HTTP {response.status}"
                )
                return None

        except Exception as e:
            self.log.error(f"Error fetching issue {issue_key}: {e}")
            return None

    @command.new(name="jira", help="JIRA plugin commands", require_subcommand=True)
    async def jira_command(self, evt: MessageEvent) -> None:
        """Base command for JIRA plugin"""
        pass

    @jira_command.subcommand("update", help="Update the list of JIRA projects")
    async def update_projects(self, evt: MessageEvent) -> None:
        """Update the list of available JIRA projects"""
        success = await self._update_projects()
        if success:
            await evt.respond(
                f"Successfully updated projects list. Found {len(self._projects)} projects."
            )
        else:
            await evt.respond(
                "Failed to update projects list. Check logs for details."
            )

    async def _update_projects(self) -> bool:
        """Fetch and update the list of JIRA projects"""
        try:
            api_base = urljoin(self.config["jira_url"], self.config["rest_api_suffix"])
            projects_url = urljoin(api_base + "/", "project")

            response = await self.nocookie.get(projects_url)

            if response.status == 200:
                projects_data = await response.json()
                self._projects = [project["key"] for project in projects_data]
                self.log.info(
                    f"Updated projects list: {len(self._projects)} projects found"
                )
                return True
            else:
                self.log.error(f"Failed to fetch projects: HTTP {response.status}")
                self.log.error(f"{response}")
                return False

        except Exception as e:
            self.log.error(f"Error updating projects: {e}")
            return False

    async def _load_projects(self) -> None:
        """Load projects on startup"""
        if not self._projects:
            await self._update_projects()

    def _is_ignored_user(self, user_id: str) -> bool:
        """Check if a user should be ignored"""
        ignored_users = self.config.get("ignored_users", "")
        if not ignored_users:
            return False

        ignored_list = [nick.strip() for nick in ignored_users]

        # Extract displayname/localpart from Matrix ID for comparison
        username = user_id.split(":")[0].lstrip("@")

        return username in ignored_list

    def _is_issue_on_cooldown(self, issue_key: str) -> bool:
        """Check if an issue is on cooldown and update the cooldown list"""
        now = int(time.time())
        cooldown_seconds = self.config["issue_cooldown"]

        # Clean up old entries
        expired_issues = [
            key
            for key, timestamp in self._recent_issues.items()
            if (now - timestamp) > cooldown_seconds
        ]
        for key in expired_issues:
            del self._recent_issues[key]

        # Check if issue is on cooldown
        if issue_key in self._recent_issues:
            return True

        # Add issue to recent list
        self._recent_issues[issue_key] = now
        return False
