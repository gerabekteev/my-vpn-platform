import httpx
from urllib.parse import urlparse, parse_qs

class OutlineServer:
    def __init__(self, access_url: str):
        parsed = urlparse(access_url)
        self.base_url = f"{parsed.scheme}://{parsed.hostname}:{parsed.port}/access-keys"
        self.token = parse_qs(parsed.query)['token'][0]
        self.headers = {'Authorization': f'Bearer {self.token}'}

    async def create_key(self, name: str):
        async with httpx.AsyncClient() as client:
            r = await client.post(self.base_url, headers=self.headers, json={'name': name})
            r.raise_for_status()
            return r.json()