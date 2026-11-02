import httpx

from portfolio.contexts.contacts.domain.model import OutgoingEmail

RESEND_URL = "https://api.resend.com/emails"


class ResendMailer:
    """Plain-text email through Resend's HTTP API. A non-2xx answer raises, so the
    message handler fails and the broker retries it."""

    def __init__(self, client: httpx.AsyncClient, api_key: str, sender: str) -> None:
        self._client = client
        self._api_key = api_key
        self._sender = sender

    async def send(self, email: OutgoingEmail) -> None:
        payload: dict[str, object] = {
            "from": self._sender,
            "to": [email.to],
            "subject": email.subject,
            "text": email.text,
        }
        if email.reply_to:
            payload["reply_to"] = email.reply_to
        response = await self._client.post(
            RESEND_URL,
            json=payload,
            headers={"Authorization": f"Bearer {self._api_key}"},
            timeout=15,
        )
        response.raise_for_status()
