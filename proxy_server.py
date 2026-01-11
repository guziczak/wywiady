"""Local proxy server that translates Anthropic API calls to claude.ai API.

This proxy enables full OAuth functionality by:
1. Accepting standard Anthropic API requests (localhost:8765)
2. Converting them to claude.ai format
3. Using OAuth token for authentication
4. Handling Cloudflare protection
5. Returning responses in Anthropic API format
"""

import asyncio
import json
from typing import Optional, Dict, Any
from pathlib import Path
import threading

try:
    from flask import Flask, request, Response, stream_with_context

    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

try:
    import cloudscraper

    CLOUDSCRAPER_AVAILABLE = True
except ImportError:
    CLOUDSCRAPER_AVAILABLE = False


class ClaudeAIProxyServer:
    """Local proxy server for claude.ai API with OAuth."""

    def __init__(self, oauth_token: str, port: int = 8765, conversation_uuid: str = None):
        """Initialize proxy server.

        Args:
            oauth_token: OAuth token or sessionKey for authentication
            port: Port to run proxy on (default 8765)
            conversation_uuid: Optional UUID to resume existing chat
        """
        self.oauth_token = oauth_token
        self.port = port
        self.app = None
        self.server_thread = None
        self.organization_id = None
        self.conversation_uuid = conversation_uuid

        # Detect token type
        self.is_session_key = oauth_token.startswith("sk-ant-sid01-")

        # Initialize session with CloudScraper (bypasses Cloudflare!)
        if CLOUDSCRAPER_AVAILABLE:
            self.session = cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "windows", "desktop": True}
            )
            print("⚙️  Configuring session...")
        else:
            # Fallback to requests
            import requests

            self.session = requests.Session()

        # Set headers
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "text/event-stream,application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "Content-Type": "application/json",
            "Origin": "https://claude.ai",
            "Referer": "https://claude.ai/new",
        }

        self.session.headers.update(headers)

        if self.is_session_key:
            from http.cookiejar import Cookie
            import time

            cookie = Cookie(
                version=0,
                name="sessionKey",
                value=oauth_token,
                port=None,
                port_specified=False,
                domain=".claude.ai",
                domain_specified=True,
                domain_initial_dot=True,
                path="/",
                path_specified=True,
                secure=True,
                expires=int(time.time()) + 86400,
                discard=False,
                comment=None,
                comment_url=None,
                rest={},
                rfc2109=False,
            )
            self.session.cookies.set_cookie(cookie)
            print(f"✅ Using sessionKey authentication")
        else:
            print(f"⚠️  Token doesn't look like sessionKey, trying anyway...")

        self.base_url = "https://claude.ai"
        self._warmup_session()

    def _warmup_session(self) -> None:
        """Pre-warm session by visiting homepage."""
        try:
            print("🌡️ Warming up session...")
            response = self.session.get(f"{self.base_url}/chats")
            if response.status_code == 200:
                print("✅ Session warmed up")
            else:
                print(f"⚠️  Warmup got status {response.status_code}")
        except Exception as e:
            print(f"⚠️  Session warmup failed: {e}")

    def _get_organization_id(self) -> Optional[str]:
        """Get organization ID from OAuth token."""
        if self.organization_id:
            return self.organization_id

        try:
            response = self.session.get(f"{self.base_url}/api/organizations")

            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and len(data) > 0:
                    self.organization_id = data[0].get("uuid")
                    return self.organization_id
        except Exception:
            pass

        self.organization_id = "0a3f3061-4469-49c7-b0af-80a5bf5dd9df"
        return self.organization_id

    def _create_conversation(self) -> Optional[str]:
        """Create new conversation and return UUID."""
        # If we already have a UUID (resumed), verify it exists or just use it
        if self.conversation_uuid:
            return self.conversation_uuid

        org_id = self._get_organization_id()
        if not org_id:
            return None

        import time
        max_retries = 3

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    time.sleep(2**attempt)

                response = self.session.post(
                    f"{self.base_url}/api/organizations/{org_id}/chat_conversations",
                    json={"name": "Stomatolog Session", "uuid": None},
                )

                if response.status_code == 201 or response.status_code == 200:
                    data = response.json()
                    self.conversation_uuid = data.get("uuid")
                    print(f"✅ Created conversation: {self.conversation_uuid}")
                    return self.conversation_uuid
                else:
                    print(f"❌ Create conversation failed: {response.status_code} - {response.text[:200]}")
            except Exception as e:
                print(f"❌ Create conversation error: {e}")

        return None
    
    def convert_document(self, file_content: bytes, file_name: str) -> Optional[str]:
        """Convert document/audio to text using claude.ai API."""
        org_id = self._get_organization_id()
        if not org_id:
            return None

        try:
            import mimetypes
            mime_type, _ = mimetypes.guess_type(file_name)
            if not mime_type:
                mime_type = "audio/wav" if file_name.endswith(".wav") else "application/octet-stream"

            # Exact format from st1vms/unofficial-claude-api:
            # files = {"file": (basename, fp, content_type), "orgUuid": (None, org_id)}
            files = {
                "file": (file_name, file_content, mime_type),
                "orgUuid": (None, org_id),
            }

            # Headers - remove Content-Type so requests can set boundary
            headers = self.session.headers.copy()
            if "Content-Type" in headers:
                del headers["Content-Type"]

            # Endpoint: /api/{org_id}/upload
            response = self.session.post(
                f"{self.base_url}/api/{org_id}/upload",
                headers=headers,
                files=files,
                timeout=120
            )

            if response.status_code == 200:
                resp_data = response.json()
                print(f"✅ Upload response: {json.dumps(resp_data, indent=2)[:500]}")
                # Try various field names
                return resp_data.get("extracted_content") or resp_data.get("content") or resp_data.get("text") or str(resp_data)
            else:
                print(f"❌ Conversion failed: {response.status_code} - {response.text[:500]}")
                return None
        except Exception as e:
            print(f"❌ Conversion error: {e}")
            return None

    def delete_conversation(self) -> bool:
        """Delete current conversation from claude.ai."""
        if not self.conversation_uuid:
            return False

        org_id = self._get_organization_id()
        if not org_id:
            return False

        try:
            response = self.session.delete(
                f"{self.base_url}/api/organizations/{org_id}/chat_conversations/{self.conversation_uuid}"
            )
            if response.status_code == 204:
                self.conversation_uuid = None
                return True
        except Exception:
            pass
        return False

    def _convert_messages_to_prompt(self, messages: list) -> str:
        """Convert messages to prompt."""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, list):
                    text_parts = []
                    for block in content:
                        if isinstance(block, dict):
                            if block.get("type") == "text":
                                text_parts.append(block.get("text", ""))
                        else:
                            text_parts.append(str(block))
                    return " ".join(text_parts) if text_parts else "Continue"
                return content if content else "Continue"
        return "Continue"

    def proxy_messages_endpoint(self, anthropic_request: dict):
        """Proxy /v1/messages request to claude.ai."""
        if not FLASK_AVAILABLE:
            raise RuntimeError("Flask is not available")

        messages = anthropic_request.get("messages", [])
        system = anthropic_request.get("system", "")
        
        if not self.conversation_uuid:
            self._create_conversation()
            if not self.conversation_uuid:
                return Response(json.dumps({"error": "Could not create conversation"}), status=500)

        user_prompt = self._convert_messages_to_prompt(messages)

        # Append system prompt to first message only if needed
        # (Actually simplified: just prepend if it's the first turn or if we want to reinforce it)
        prompt = f"{system}\n\n---\n\n{user_prompt}" if system else user_prompt

        org_id = self._get_organization_id()

        claude_request = {
            "prompt": prompt,
            "timezone": "America/New_York",
            "attachments": [],
            "files": [],
            "rendering_mode": "messages",
        }

        try:
            endpoint = f"{self.base_url}/api/organizations/{org_id}/chat_conversations/{self.conversation_uuid}/completion"

            response = self.session.post(
                endpoint,
                json=claude_request,
                headers={"Accept": "text/event-stream", "Accept-Encoding": "identity"},
                stream=True,
                timeout=60,
            )

            if response.status_code != 200:
                print(f"❌ Completion failed: {response.status_code} - {response.text[:300]}")
                return Response(json.dumps({"error": f"Status {response.status_code}"}), status=response.status_code)

            def generate():
                import codecs
                decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
                for chunk in response.iter_content(chunk_size=64, decode_unicode=False):
                    if not chunk: continue
                    # Simple pass-through of SSE
                    try:
                        text = decoder.decode(chunk, final=False)
                        if text: yield text
                    except: pass

            return Response(stream_with_context(generate()), content_type="text/event-stream")

        except Exception as e:
            return Response(json.dumps({"error": str(e)}), status=500)

    def start_server(self):
        """Start Flask proxy server."""
        if not FLASK_AVAILABLE:
            return False

        self.app = Flask(__name__)

        @self.app.route("/v1/messages", methods=["POST"])
        def messages_endpoint():
            try:
                data = request.get_json()
                return self.proxy_messages_endpoint(data)
            except Exception as e:
                return Response(json.dumps({"error": str(e)}), status=500)
        
        @self.app.route("/convert", methods=["POST"])
        def convert_endpoint():
            """Endpoint to convert audio/file to text."""
            if 'file' not in request.files:
                return Response(json.dumps({"error": "No file part"}), status=400)
            
            file = request.files['file']
            if file.filename == '':
                return Response(json.dumps({"error": "No selected file"}), status=400)

            content = file.read()
            text = self.convert_document(content, file.filename)
            
            if text is not None:
                return Response(json.dumps({"text": text}), content_type="application/json")
            else:
                return Response(json.dumps({"error": "Conversion failed"}), status=500)

        @self.app.route("/uuid", methods=["GET", "DELETE"])
        def uuid_endpoint():
            if request.method == "DELETE":
                success = self.delete_conversation()
                return Response(json.dumps({"success": success}), content_type="application/json")
            return Response(json.dumps({"uuid": self.conversation_uuid}), content_type="application/json")

        @self.app.route("/health", methods=["GET"])
        def health():
            return Response(json.dumps({"status": "ok"}), content_type="application/json")

        def run():
            self.app.run(host="127.0.0.1", port=self.port, debug=False, use_reloader=False)

        self.server_thread = threading.Thread(target=run, daemon=True)
        self.server_thread.start()
        print(f"✅ Proxy server started on http://127.0.0.1:{self.port}")
        return True


_proxy_instance: Optional[ClaudeAIProxyServer] = None


def start_proxy_server(oauth_token: str, port: int = 8765, conversation_uuid: str = None) -> tuple[bool, int]:
    global _proxy_instance

    # Check if token changed - if so, need to recreate proxy
    if _proxy_instance:
        if _proxy_instance.oauth_token != oauth_token:
            print(f"🔄 Token changed, recreating proxy...")
            _proxy_instance = None  # Force recreation
        else:
            # Same token, just update UUID if needed
            if conversation_uuid and not _proxy_instance.conversation_uuid:
                _proxy_instance.conversation_uuid = conversation_uuid
            return (True, _proxy_instance.port)

    # Find port
    original_port = port
    for attempt in range(20):
        try_port = port + attempt
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(("127.0.0.1", try_port))
            sock.close()
            port = try_port
            break
        except OSError:
            sock.close()
            continue
    
    _proxy_instance = ClaudeAIProxyServer(oauth_token, port, conversation_uuid)
    started = _proxy_instance.start_server()
    
    # Wait for health
    import time, requests
    start_time = time.time()
    while time.time() - start_time < 5:
        try:
            if requests.get(f"http://127.0.0.1:{port}/health", timeout=1).status_code == 200:
                return (True, port)
        except:
            pass
        time.sleep(0.1)

    return (started, port)

def get_proxy_base_url(port: int = 8765) -> str:
    return f"http://127.0.0.1:{port}"