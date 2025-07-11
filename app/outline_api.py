import ssl
from urllib3.poolmanager import PoolManager
from requests.adapters import HTTPAdapter
import requests

class SSLIgnoreHostnameAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context(cafile="/root/my-vpn-platform/outline.crt")
        ctx.check_hostname = False  # Отключаем проверку имени хоста
        kwargs['ssl_context'] = ctx
        self.poolmanager = PoolManager(*args, **kwargs)

class OutlineServer:
    def __init__(self, access_url):
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(access_url)
        self.token = parse_qs(parsed.query)['token'][0]
        self.base_url = f"{parsed.scheme}://{parsed.hostname}:{parsed.port}/access-keys"
        self.headers = {'Authorization': f"Bearer {self.token}"}
        
        # Настроим сессию с кастомным SSL-адаптером
        self.session = requests.Session()
        self.session.mount("https://", SSLIgnoreHostnameAdapter())

    def create_key(self, name: str):
        r = self.session.post(
            self.base_url,
            headers=self.headers,
            json={'name': name},
            verify="/root/my-vpn-platform/outline.crt"
        )
        r.raise_for_status()
        return r.json()