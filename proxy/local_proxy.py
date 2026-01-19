"""Local proxy server that translates Anthropic API calls to claude.ai API.

This proxy enables full OAuth functionality by:
1. Accepting standard Anthropic API requests (localhost:8765)
2. Converting them to claude.ai format
3. Using OAuth token for authentication
4. Handling Cloudflare protection
5. Returning responses in Anthropic API format

This is REVOLUTIONARY - full OAuth support with zero manual work!
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

    def __init__(self, oauth_token: str, port: int = 8765):
        """Initialize proxy server.

        Args:
            oauth_token: OAuth token or sessionKey for authentication
            port: Port to run proxy on (default 8765)
        """
        self.oauth_token = oauth_token
        self.port = port
        self.app = None
        self.server_thread = None
        self.organization_id = None
        self.conversation_uuid = None

        # Detect token type
        self.is_session_key = oauth_token.startswith("sk-ant-sid01-")

        # Initialize session with CloudScraper (bypasses Cloudflare!)
        if CLOUDSCRAPER_AVAILABLE:
            self.session = cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "windows", "desktop": True}
            )
            # Disable auto-decompression for streaming
            # CloudScraper/requests might be eating the stream
            print("⚙️  Configuring session for streaming...")
        else:
            # Fallback to requests
            import requests

            self.session = requests.Session()

        # Set headers (without Cookie - that goes in CookieJar)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "text/event-stream,application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "Content-Type": "application/json",
            "Origin": "https://claude.ai",
            "Referer": "https://claude.ai/new",
        }

        self.session.headers.update(headers)

        # Add sessionKey to CookieJar (not headers!)
        # This allows CloudScraper to manage all cookies properly
        if self.is_session_key:
            from http.cookiejar import Cookie
            import time

            # Create a cookie object for sessionKey
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
                expires=int(time.time()) + 86400,  # 24h from now
                discard=False,
                comment=None,
                comment_url=None,
                rest={},
                rfc2109=False,
            )
            self.session.cookies.set_cookie(cookie)
            print(f"✅ Using sessionKey authentication (claude.ai)")
        else:
            # OAuth token handling
            print(f"⚠️  Token doesn't look like sessionKey, trying anyway...")

        self.base_url = "https://claude.ai"

        # Pre-warm session to get Cloudflare cookies
        self._warmup_session()

    def _warmup_session(self) -> None:
        """Pre-warm session by visiting homepage to get Cloudflare cookies."""
        try:
            print("🔥 Warming up session (bypassing Cloudflare)...")
            # Visit homepage first to get Cloudflare clearance cookies
            response = self.session.get(f"{self.base_url}/chats")
            if response.status_code == 200:
                print("✅ Session warmed up - Cloudflare cookies acquired")
                # Debug: show cookies
                cookie_names = [cookie.name for cookie in self.session.cookies]
                print(f"   Cookies: {', '.join(cookie_names) if cookie_names else 'none'}")
            else:
                print(f"⚠️  Warmup got status {response.status_code} (may still work)")
        except Exception as e:
            print(f"⚠️  Session warmup failed: {e} (continuing anyway)")

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

        # Fallback
        self.organization_id = "0a3f3061-4469-49c7-b0af-80a5bf5dd9df"
        return self.organization_id

    def _create_conversation(self) -> Optional[str]:
        """Create new conversation and return UUID."""
        org_id = self._get_organization_id()
        if not org_id:
            return None

        # Retry up to 3 times (Cloudflare may need warming up)
        import time

        max_retries = 3

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    time.sleep(2**attempt)  # 2s, 4s

                response = self.session.post(
                    f"{self.base_url}/api/organizations/{org_id}/chat_conversations",
                    json={"name": "Python Session", "uuid": None},
                )

                if response.status_code == 201 or response.status_code == 200:
                    data = response.json()
                    self.conversation_uuid = data.get("uuid")
                    return self.conversation_uuid
                elif response.status_code == 403 and attempt < max_retries - 1:
                    continue

            except Exception:
                if attempt < max_retries - 1:
                    continue

        return None

    def _convert_document(self, file_content: bytes, file_name: str) -> Optional[str]:
        """Convert document/audio to text using claude.ai upload API.

        Args:
            file_content: Raw file bytes
            file_name: Original filename (for mime type detection)

        Returns:
            Extracted text content or None on failure
        """
        org_id = self._get_organization_id()
        if not org_id:
            print("❌ [Proxy] Cannot convert document - no organization ID")
            return None

        try:
            import mimetypes
            mime_type, _ = mimetypes.guess_type(file_name)
            if not mime_type:
                mime_type = "audio/wav" if file_name.endswith(".wav") else "application/octet-stream"

            # Format from st1vms/unofficial-claude-api
            files = {
                "file": (file_name, file_content, mime_type),
                "orgUuid": (None, org_id),
            }

            # Remove Content-Type header so requests sets multipart boundary
            headers = dict(self.session.headers)
            if "Content-Type" in headers:
                del headers["Content-Type"]

            print(f"📤 [Proxy] Uploading {file_name} ({len(file_content)} bytes, {mime_type})")

            response = self.session.post(
                f"{self.base_url}/api/{org_id}/upload",
                headers=headers,
                files=files,
                timeout=120
            )

            if response.status_code == 200:
                resp_data = response.json()
                print(f"✅ [Proxy] Upload success: {list(resp_data.keys())}")
                # Try various field names that claude.ai might return
                return resp_data.get("extracted_content") or resp_data.get("content") or resp_data.get("text") or str(resp_data)
            else:
                print(f"❌ [Proxy] Upload failed: {response.status_code} - {response.text[:300]}")
                return None
        except Exception as e:
            print(f"❌ [Proxy] Upload error: {e}")
            return None

    def _convert_messages_to_prompt(self, messages: list) -> str:
        """Convert Anthropic messages format to claude.ai prompt.

        Claude.ai expects just the user's message, not the full conversation format.
        """
        # Get the last user message
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")

                if isinstance(content, list):
                    # Handle structured content (including tool_result blocks)
                    text_parts = []
                    for block in content:
                        if isinstance(block, dict):
                            # Extract text from different block types
                            if block.get("type") == "text":
                                text_parts.append(block.get("text", ""))
                            elif block.get("type") == "tool_result":
                                # For tool results, use the content
                                tool_content = block.get("content", "")
                                if tool_content:
                                    text_parts.append(f"Tool result: {tool_content}")
                        else:
                            text_parts.append(str(block))

                    content = " ".join(text_parts) if text_parts else "Continue"

                return content if content else "Continue"

        # Fallback: if no user message, return "Continue" to keep conversation going
        return "Continue"

    def proxy_messages_endpoint(self, anthropic_request: dict):
        """Proxy /v1/messages request to claude.ai.

        Args:
            anthropic_request: Request in Anthropic API format

        Returns:
            Streaming response in Anthropic API format
        """
        if not FLASK_AVAILABLE:
            raise RuntimeError("Flask is not available - cannot create Response object")

        # Extract parameters
        messages = anthropic_request.get("messages", [])
        system = anthropic_request.get("system", "")  # CRITICAL: Extract system prompt!
        model = anthropic_request.get("model", "claude-sonnet-4-20250514")
        max_tokens = anthropic_request.get("max_tokens", 4096)
        stream = anthropic_request.get("stream", True)
        tools = anthropic_request.get("tools", None)  # Extract tools if provided

        # Create new conversation if needed (first request of this proxy instance)
        if not self.conversation_uuid:
            self._create_conversation()

            if not self.conversation_uuid:
                error_msg = (
                    "Could not create conversation - check OAuth token and connection to claude.ai"
                )
                return Response(
                    json.dumps({"error": error_msg}), status=500, content_type="application/json"
                )

        # Convert to claude.ai format
        user_prompt = self._convert_messages_to_prompt(messages)

        # CRITICAL: Prepend system prompt ONLY for first user message
        # Claude.ai doesn't have separate "system" field, so we add it to first prompt
        # After that, claude.ai remembers context from conversation
        user_message_count = sum(1 for m in messages if m.get("role") == "user")
        is_first_message = user_message_count == 1
        if system and is_first_message:
            prompt = f"{system}\n\n---\n\n{user_prompt}"
            print(f"📋 [Proxy] Including system prompt in first message ({len(system)} chars)")
        else:
            prompt = user_prompt

        org_id = self._get_organization_id()

        # Send to claude.ai with all required fields
        claude_request = {
            "prompt": prompt,
            "timezone": "America/New_York",
            "attachments": [],
            "files": [],
            "rendering_mode": "messages",
        }

        # DON'T send tools to claude.ai - it has its own built-in tools
        # We'll intercept tool_use blocks and execute locally with our tools
        # This is the Interceptor Pattern for tool execution
        if tools:
            print(
                f"ℹ️  [Proxy] Interceptor mode: {len(tools)} local tools available (not sending to claude.ai)"
            )

        try:
            # Use the /completion endpoint that we know works (returns 200)
            endpoint = f"{self.base_url}/api/organizations/{org_id}/chat_conversations/{self.conversation_uuid}/completion"

            # Make request with streaming
            response = self.session.post(
                endpoint,
                json=claude_request,
                headers={
                    "Accept": "text/event-stream",
                    "Accept-Encoding": "identity",  # Disable gzip
                },
                stream=True,
                timeout=60,
            )

            if response.status_code != 200:
                # Try to get error details
                error_text = ""
                try:
                    error_text = response.text[:500]
                    print(f"❌ Error response: {error_text}")
                except:
                    pass

                return Response(
                    json.dumps(
                        {
                            "error": f"claude.ai returned {response.status_code}",
                            "details": error_text,
                        }
                    ),
                    status=response.status_code,
                    content_type="application/json",
                )

            # Stream response back in Anthropic format (TRUE streaming!)
            def generate():
                try:
                    import codecs

                    text_parts = []
                    event_count = 0
                    buffer = b""

                    # Use incremental decoder to handle UTF-8 sequences split across chunks
                    decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')

                    # Read from response stream directly for real-time streaming
                    # chunk_size=64 for responsiveness without killing performance
                    for chunk in response.iter_content(chunk_size=64, decode_unicode=False):
                        if not chunk:
                            continue

                        buffer += chunk

                        # Process complete lines as they arrive
                        while b"\n" in buffer:
                            line_bytes, buffer = buffer.split(b"\n", 1)

                            if not line_bytes:
                                continue

                            # Use incremental decoder - handles incomplete UTF-8 sequences
                            # This prevents UnicodeDecodeError when Polish chars (ą,ę,ć)
                            # are split across chunk boundaries
                            try:
                                line = decoder.decode(line_bytes, final=False).strip()
                            except Exception as e:
                                # Should never happen with 'replace' errors, but just in case
                                logger.error(f"Failed to decode line: {e}")
                                continue

                            if not line:
                                continue

                            # SSE format: "data: {json}" or "event: type"
                            if line.startswith("data: "):
                                event_count += 1
                                data_str = line[6:]  # Remove "data: " prefix

                                # Check for SSE end marker
                                if data_str == "[DONE]":
                                    break

                                try:
                                    data = json.loads(data_str)

                                    # DEBUG: Log ONLY tool_use events
                                    event_type = data.get("type", "")
                                    if event_type == "content_block_start":
                                        cb = data.get("content_block", {})
                                        if cb.get("type") == "tool_use":
                                            print(
                                                f"🔍 [Proxy] tool_use detected: {cb.get('name', 'unknown')} (id: {cb.get('id', 'N/A')})"
                                            )

                                    # Claude.ai already sends Anthropic SSE format!
                                    # Just check for text_delta in content_block_delta events
                                    if data.get("type") == "content_block_delta":
                                        delta = data.get("delta", {})
                                        if delta.get("type") == "text_delta":
                                            text = delta.get("text", "")
                                            text_parts.append(text)

                                    # Filter out claude.ai-specific events that SDK doesn't understand
                                    event_type = data.get("type")
                                    if event_type == "message_limit":
                                        # Skip claude.ai specific event
                                        continue

                                    # Add usage stats to message_delta if missing (for SDK compatibility)
                                    if event_type == "message_delta":
                                        # usage should be at top level, not in delta!
                                        if "usage" not in data:
                                            data["usage"] = {
                                                "output_tokens": len(text_parts)  # Approximate
                                            }

                                    # Pass through events to client
                                    yield f"data: {json.dumps(data)}\n\n"

                                    # Check for message_stop
                                    if event_type == "message_stop":
                                        # Send [DONE] marker so oauth_anthropic_client knows stream ended
                                        yield "data: [DONE]\n\n"
                                        break

                                except json.JSONDecodeError as e:
                                    # Silently skip bad JSON
                                    continue

                            elif line.startswith("event: "):
                                # Pass through event lines too
                                yield f"{line}\n"

                    # Finalize decoder - process any remaining bytes
                    if buffer:
                        try:
                            remaining = decoder.decode(buffer, final=True).strip()
                            if remaining and remaining.startswith("data: "):
                                # Process final line if it's valid SSE
                                yield f"{remaining}\n\n"
                        except Exception as e:
                            logger.debug(f"Skipping final buffer: {e}")

                except Exception as e:
                    import traceback

                    traceback.print_exc()

            return Response(stream_with_context(generate()), content_type="text/event-stream")

        except Exception as e:
            return Response(
                json.dumps({"error": str(e)}), status=500, content_type="application/json"
            )

    def start_server(self):
        """Start Flask proxy server in background thread."""
        if not FLASK_AVAILABLE:
            print("⚠️  Flask not available - proxy cannot start")
            return False

        self.app = Flask(__name__)

        @self.app.route("/v1/messages", methods=["POST"])
        def messages_endpoint():
            """Proxy endpoint for /v1/messages."""
            try:
                data = request.get_json()
                return self.proxy_messages_endpoint(data)
            except Exception as e:
                return Response(
                    json.dumps({"error": str(e)}), status=500, content_type="application/json"
                )

        @self.app.route("/health", methods=["GET"])
        def health():
            """Health check endpoint."""
            return Response(json.dumps({"status": "ok"}), content_type="application/json")

        @self.app.route("/convert", methods=["POST"])
        def convert_endpoint():
            """Convert audio/document to text using claude.ai."""
            if 'file' not in request.files:
                return Response(json.dumps({"error": "No file part"}), status=400, content_type="application/json")

            file = request.files['file']
            if file.filename == '':
                return Response(json.dumps({"error": "No selected file"}), status=400, content_type="application/json")

            content = file.read()
            text = self._convert_document(content, file.filename)

            if text is not None:
                return Response(json.dumps({"text": text}), content_type="application/json")
            else:
                return Response(json.dumps({"error": "Conversion failed"}), status=500, content_type="application/json")

        # Run in background thread
        def run():
            self.app.run(host="127.0.0.1", port=self.port, debug=False, use_reloader=False)

        self.server_thread = threading.Thread(target=run, daemon=True)
        self.server_thread.start()

        print(f"✅ Proxy server started on http://127.0.0.1:{self.port}")
        return True


# Global proxy instance
_proxy_instance: Optional[ClaudeAIProxyServer] = None


def start_proxy_server(oauth_token: str, port: int = 8765) -> tuple[bool, int]:
    """Start proxy server in background with auto port selection.

    Args:
        oauth_token: OAuth token for authentication
        port: Preferred port to run on (will auto-increment if busy)

    Returns:
        Tuple of (success: bool, actual_port: int)
    """
    global _proxy_instance

    # DON'T reuse existing instance - each CLI session needs its own conversation
    # Try to find available port if default is busy
    if _proxy_instance:
        print("ℹ️  [Proxy] Previous proxy detected - finding free port for new CLI instance")

    # Try ports 8765, 8766, 8767... until we find one available
    original_port = port
    max_attempts = 20  # Increased from 10 to handle multiple CLI instances
    for attempt in range(max_attempts):
        try_port = port + attempt

        # Check if port is available
        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(("127.0.0.1", try_port))
            sock.close()
            # Port is available!
            port = try_port
            if attempt > 0:
                print(f"   Found available port: {port}")
            break
        except OSError:
            # Port busy, try next
            sock.close()
            continue
    else:
        print(
            f"❌ [Proxy] Could not find available port (tried {original_port}-{original_port+max_attempts-1})"
        )
        return (False, 0)

    _proxy_instance = ClaudeAIProxyServer(oauth_token, port)
    started = _proxy_instance.start_server()

    if not started:
        return (False, 0)

    # Wait for Flask to be ready (health check loop)
    import time
    import requests

    max_wait = 5  # seconds
    start_time = time.time()

    while time.time() - start_time < max_wait:
        try:
            response = requests.get(f"http://127.0.0.1:{port}/health", timeout=1)
            if response.status_code == 200:
                print(f"✅ Proxy health check passed - ready to accept requests")
                return (True, port)
        except:
            pass
        time.sleep(0.1)

    print(f"⚠️  Proxy health check timeout - may not be ready")
    return (True, port)  # Continue anyway


def get_proxy_base_url(port: int = 8765) -> str:
    """Get proxy base URL.

    Args:
        port: Proxy port

    Returns:
        Base URL for proxy
    """
    return f"http://127.0.0.1:{port}"
