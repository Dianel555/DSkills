"""Web UI for interactive prompt enhancement."""

import json
import os
import queue
import socket
import sys
import threading
import time
import uuid
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional, TYPE_CHECKING
from urllib.parse import parse_qs, urlparse

if TYPE_CHECKING:
    try:
        from .client import AceToolClient
    except ImportError:
        from client import AceToolClient

_SESSIONS: dict = {}
_RESULT_QUEUE: Optional[queue.Queue] = None

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Prompt Enhancer - ACE Tool</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f5f5f5;min-height:100vh;padding:20px;display:flex;align-items:center;justify-content:center}
.container{background:#fff;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,0.1);border:1px solid #e0e0e0;max-width:1000px;width:100%;overflow:hidden}
.header{background:#fff;color:#333;padding:30px;text-align:center;border-bottom:1px solid #e0e0e0}
.header h1{font-size:24px;font-weight:600;margin-bottom:8px;display:flex;align-items:center;justify-content:center;gap:10px}
.header p{font-size:14px;color:#666}
.countdown{margin-top:12px;padding:8px 16px;background:#f0f0f0;border-radius:6px;display:inline-block;font-size:13px;font-weight:500;color:#555}
.countdown.warning{background:#fff3cd;color:#856404}
.countdown.danger{background:#f8d7da;color:#721c24;animation:pulse 1s ease-in-out infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.7}}
.content{padding:30px}
.section{margin-bottom:25px}
.section-title{font-size:14px;font-weight:600;color:#333;margin-bottom:10px;text-transform:uppercase;letter-spacing:0.5px}
.editor-wrapper{position:relative}
textarea{width:100%;min-height:350px;padding:16px;border:2px solid #e0e0e0;border-radius:8px;font-family:'SF Mono',Monaco,Menlo,Consolas,monospace;font-size:14px;line-height:1.6;resize:vertical;background:#fafafa}
textarea:focus{outline:none;border-color:#333;background:#fff}
.char-count{position:absolute;bottom:12px;right:12px;background:rgba(255,255,255,0.9);padding:4px 10px;border-radius:12px;font-size:12px;color:#666;pointer-events:none;box-shadow:0 2px 8px rgba(0,0,0,0.1)}
.info-box{background:#f9f9f9;border-left:4px solid #333;padding:15px;border-radius:4px;margin-bottom:20px}
.info-box p{font-size:14px;color:#555;line-height:1.6}
.buttons{display:flex;gap:12px;justify-content:flex-end;margin-top:25px;flex-wrap:wrap}
button{padding:12px 28px;border:none;border-radius:8px;font-size:15px;font-weight:600;cursor:pointer;transition:all 0.3s;display:flex;align-items:center;gap:8px}
.send-btn{background:#333;color:#fff}
.send-btn:hover:not(:disabled){background:#000}
.send-btn:disabled{background:#ccc;cursor:not-allowed}
.cancel-btn{background:#fff;color:#666;border:2px solid #e0e0e0}
.cancel-btn:hover{background:#f5f5f5;border-color:#ccc}
.re-enhance-btn{background:#fff;color:#333;border:2px solid #333}
.re-enhance-btn:hover:not(:disabled){background:#f5f5f5}
.re-enhance-btn:disabled{background:#f5f5f5;color:#ccc;border-color:#e0e0e0;cursor:not-allowed}
.status{margin-top:20px;padding:15px;border-radius:8px;display:none;animation:slideIn 0.3s ease}
@keyframes slideIn{from{opacity:0;transform:translateY(-10px)}to{opacity:1;transform:translateY(0)}}
.status.success{background:#d4edda;color:#155724;border-left:4px solid #28a745;display:block}
.status.error{background:#f8d7da;color:#721c24;border-left:4px solid #dc3545;display:block}
.loading{display:none;text-align:center;padding:40px}
.loading.active{display:block}
.spinner{border:3px solid #f3f3f3;border-top:3px solid #333;border-radius:50%;width:40px;height:40px;animation:spin 1s linear infinite;margin:0 auto 15px}
@keyframes spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}
.keyboard-hint{font-size:12px;color:#999;text-align:center;margin-top:15px}
.keyboard-hint kbd{background:#f5f5f5;border:1px solid #ddd;border-radius:4px;padding:2px 6px;font-family:monospace;font-size:11px}
</style>
</head>
<body>
<div class="container">
<div class="header">
<h1><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>Prompt Enhancer</h1>
<p>Review and refine your enhanced prompt</p>
<div class="countdown" id="countdown">Loading...</div>
</div>
<div class="content">
<div class="loading" id="loading"><div class="spinner"></div><p>Loading your enhanced prompt...</p></div>
<div id="mainContent" style="display:none">
<div class="info-box"><p><strong>Tip:</strong> AI has enhanced your prompt. You can edit it below, then click "Send Enhanced" to continue. Use "Regenerate" to get a completely new enhancement, or "Refine" to improve the current version while keeping your edits.</p></div>
<div class="section">
<div class="section-title">Enhanced Prompt</div>
<div class="editor-wrapper">
<textarea id="promptText" placeholder="Your enhanced prompt will appear here..." spellcheck="false"></textarea>
<div class="char-count" id="charCount">0 chars</div>
</div>
</div>
<div class="buttons">
<button class="cancel-btn" onclick="endConversation()">Cancel</button>
<button class="re-enhance-btn" id="regenerateBtn" onclick="regenerate()" title="Discard current and generate a new enhancement from scratch">Regenerate</button>
<button class="re-enhance-btn" id="refineBtn" onclick="refine()" title="Further improve current version while preserving your edits">Refine</button>
<button class="cancel-btn" onclick="useOriginal()">Use Original</button>
<button class="send-btn" id="sendBtn" onclick="sendPrompt()">Send Enhanced</button>
</div>
<div class="keyboard-hint">Shortcuts: <kbd>Ctrl</kbd>+<kbd>Enter</kbd> Send | <kbd>Esc</kbd> Cancel</div>
<div id="status" class="status"></div>
</div>
</div>
</div>
<script>
const urlParams=new URLSearchParams(window.location.search);
const sessionId=urlParams.get('session');
const promptText=document.getElementById('promptText');
const charCount=document.getElementById('charCount');
const loading=document.getElementById('loading');
const mainContent=document.getElementById('mainContent');
const countdownEl=document.getElementById('countdown');
let countdownInterval=null,sessionCreatedAt=null,sessionTimeoutMs=null;

function updateCharCount(){charCount.textContent=promptText.value.length+' chars'}
promptText.addEventListener('input',updateCharCount);

function formatTime(ms){const s=Math.floor(ms/1000),m=Math.floor(s/60);return m+':'+(s%60).toString().padStart(2,'0')}
function updateCountdown(){
if(!sessionCreatedAt||!sessionTimeoutMs)return;
const remaining=sessionTimeoutMs-(Date.now()-sessionCreatedAt);
if(remaining<=0){countdownEl.textContent='Timed out';countdownEl.className='countdown danger';clearInterval(countdownInterval);return}
countdownEl.className='countdown'+(remaining<60000?' danger':remaining<180000?' warning':'');
countdownEl.textContent='Remaining: '+formatTime(remaining);
}
function startCountdown(createdAt,timeoutMs){sessionCreatedAt=createdAt;sessionTimeoutMs=timeoutMs;updateCountdown();countdownInterval=setInterval(updateCountdown,1000)}

document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key==='Enter'){e.preventDefault();sendPrompt()}else if(e.key==='Escape'){e.preventDefault();endConversation()}});

if(!sessionId){loading.style.display='none';mainContent.style.display='block';showStatus('Error: No session ID','error')}
else{loading.classList.add('active');
fetch('/api/session?session='+encodeURIComponent(sessionId)).then(r=>r.json()).then(data=>{
if(data.error)throw new Error(data.error);
promptText.value=data.enhancedPrompt;updateCharCount();
loading.classList.remove('active');mainContent.style.display='block';promptText.focus();
if(data.createdAt&&data.timeoutMs)startCountdown(data.createdAt,data.timeoutMs);
}).catch(err=>{loading.classList.remove('active');mainContent.style.display='block';showStatus('Load failed: '+err.message,'error')})}

function regenerate(){
const btn=document.getElementById('regenerateBtn'),refineBtn=document.getElementById('refineBtn'),sendBtn=document.getElementById('sendBtn');
btn.disabled=refineBtn.disabled=sendBtn.disabled=true;btn.innerHTML='<div class="spinner" style="width:16px;height:16px;border-width:2px;margin:0"></div> Regenerating...';
fetch('/api/regenerate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sessionId})})
.then(r=>r.json()).then(data=>{if(data.error)throw new Error(data.error);promptText.value=data.enhancedPrompt;updateCharCount();showStatus('Regenerated!','success');btn.disabled=refineBtn.disabled=sendBtn.disabled=false;btn.innerHTML='Regenerate'})
.catch(err=>{showStatus('Failed: '+err.message,'error');btn.disabled=refineBtn.disabled=sendBtn.disabled=false;btn.innerHTML='Regenerate'})}

function refine(){
const content=promptText.value.trim();if(!content){showStatus('Please enter content','error');return}
const btn=document.getElementById('refineBtn'),regenerateBtn=document.getElementById('regenerateBtn'),sendBtn=document.getElementById('sendBtn');
btn.disabled=regenerateBtn.disabled=sendBtn.disabled=true;btn.innerHTML='<div class="spinner" style="width:16px;height:16px;border-width:2px;margin:0"></div> Refining...';
fetch('/api/refine',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sessionId,currentPrompt:content})})
.then(r=>r.json()).then(data=>{if(data.error)throw new Error(data.error);promptText.value=data.enhancedPrompt;updateCharCount();showStatus('Refined!','success');btn.disabled=regenerateBtn.disabled=sendBtn.disabled=false;btn.innerHTML='Refine'})
.catch(err=>{showStatus('Failed: '+err.message,'error');btn.disabled=regenerateBtn.disabled=sendBtn.disabled=false;btn.innerHTML='Refine'})}

function sendPrompt(){
const content=promptText.value.trim();if(!content){showStatus('Please enter content','error');return}
const btn=document.getElementById('sendBtn'),regenerateBtn=document.getElementById('regenerateBtn'),refineBtn=document.getElementById('refineBtn');
btn.disabled=regenerateBtn.disabled=refineBtn.disabled=true;btn.innerHTML='<div class="spinner" style="width:16px;height:16px;border-width:2px;margin:0"></div> Sending...';
fetch('/api/submit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sessionId,content,action:'send'})})
.then(r=>r.json()).then(data=>{if(data.error)throw new Error(data.error);showStatus('Sent! Closing...','success');setTimeout(()=>window.close(),1500)})
.catch(err=>{showStatus('Failed: '+err.message,'error');btn.disabled=regenerateBtn.disabled=refineBtn.disabled=false;btn.innerHTML='Send Enhanced'})}

function useOriginal(){if(confirm('Use original prompt?')){
fetch('/api/submit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sessionId,content:'',action:'use_original'})})
.then(r=>r.json()).then(data=>{if(data.error)throw new Error(data.error);showStatus('Using original...','success');setTimeout(()=>window.close(),1000)})
.catch(err=>showStatus('Failed: '+err.message,'error'))}}

function endConversation(){if(confirm('Cancel enhancement?')){
fetch('/api/submit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sessionId,content:'',action:'cancel'})})
.then(r=>r.json()).then(data=>{if(data.error)throw new Error(data.error);showStatus('Cancelled','success');setTimeout(()=>window.close(),1000)})
.catch(err=>showStatus('Failed: '+err.message,'error'))}}

function showStatus(msg,type){const s=document.getElementById('status');s.textContent=msg;s.className='status '+type}
</script>
</body>
</html>"""


class EnhanceRequestHandler(BaseHTTPRequestHandler):
    client: "AceToolClient" = None
    original_prompt: str = ""
    conversation_history: str = ""

    def log_message(self, format, *args):
        pass

    def handle(self):
        try:
            super().handle()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/enhance":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode("utf-8"))
        elif parsed.path == "/api/session":
            self._handle_get_session(parsed.query)
        else:
            self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")

        if parsed.path == "/api/submit":
            self._handle_submit(body)
        elif parsed.path == "/api/regenerate":
            self._handle_regenerate(body)
        elif parsed.path == "/api/refine":
            self._handle_refine(body)
        else:
            self.send_error(404)

    def _send_json(self, data: dict, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def _handle_get_session(self, query: str):
        params = parse_qs(query)
        session_id = params.get("session", [None])[0]
        if not session_id or session_id not in _SESSIONS:
            self._send_json({"error": "Session not found"}, 404)
            return
        session = _SESSIONS[session_id]
        self._send_json({
            "enhancedPrompt": session["enhanced"],
            "status": session["status"],
            "createdAt": session["created_at"],
            "timeoutMs": session["timeout_ms"],
        })

    def _handle_submit(self, body: str):
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._send_json({"error": "Invalid JSON"}, 400)
            return

        session_id = data.get("sessionId")
        action = data.get("action", "send")
        content = data.get("content", "")

        if not session_id or session_id not in _SESSIONS:
            self._send_json({"error": "Session not found"}, 404)
            return

        session = _SESSIONS[session_id]
        if session["status"] != "pending":
            self._send_json({"error": "Session already completed"}, 400)
            return

        session["status"] = "completed"

        if action == "cancel":
            result = None
        elif action == "use_original":
            result = session["original"]
        else:
            result = content if content else session["enhanced"]

        if _RESULT_QUEUE:
            _RESULT_QUEUE.put(result)

        self._send_json({"success": True})

    def _handle_regenerate(self, body: str):
        """Regenerate: discard current and generate new enhancement from original prompt."""
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._send_json({"error": "Invalid JSON"}, 400)
            return

        session_id = data.get("sessionId")
        if not session_id or session_id not in _SESSIONS:
            self._send_json({"error": "Session not found"}, 404)
            return

        session = _SESSIONS[session_id]
        try:
            result = self.client.enhance_prompt(
                session["original"],
                self.conversation_history,
            )
            new_enhanced = result.get("enhanced_prompt", session["original"])
            session["previous_enhanced"] = session["enhanced"]
            session["enhanced"] = new_enhanced
            session["regenerate_count"] = session.get("regenerate_count", 0) + 1
            self._send_json({
                "enhancedPrompt": new_enhanced,
                "regenerateCount": session["regenerate_count"],
            })
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _handle_refine(self, body: str):
        """Refine: iteratively improve current version while preserving user edits."""
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._send_json({"error": "Invalid JSON"}, 400)
            return

        session_id = data.get("sessionId")
        current_prompt = data.get("currentPrompt", "")

        if not session_id or session_id not in _SESSIONS:
            self._send_json({"error": "Session not found"}, 404)
            return

        session = _SESSIONS[session_id]
        try:
            previous_enhanced = session.get("previous_enhanced") or session["enhanced"]
            result = self.client.iterative_enhance(
                original_prompt=session["original"],
                previous_enhanced=previous_enhanced,
                current_prompt=current_prompt,
                conversation_history=self.conversation_history,
            )
            new_enhanced = result.get("enhanced_prompt", current_prompt)
            session["previous_enhanced"] = session["enhanced"]
            session["enhanced"] = new_enhanced
            session["refine_count"] = session.get("refine_count", 0) + 1
            self._send_json({
                "enhancedPrompt": new_enhanced,
                "refineCount": session["refine_count"],
            })
        except Exception as e:
            self._send_json({"error": str(e)}, 500)


def run_interactive_enhance(
    client: "AceToolClient", prompt: str, history: str, port: int = 8765,
    auto_open_browser: bool = True
) -> Optional[str]:
    """Run interactive web-based prompt enhancement."""
    global _RESULT_QUEUE

    print("Enhancing prompt...", file=sys.stderr)
    result = client.enhance_prompt(prompt, history)
    enhanced = result.get("enhanced_prompt", prompt)

    session_id = str(uuid.uuid4())
    created_at = int(time.time() * 1000)
    timeout_ms = 5 * 60 * 1000

    _SESSIONS[session_id] = {
        "original": prompt,
        "enhanced": enhanced,
        "previous_enhanced": None,
        "regenerate_count": 0,
        "refine_count": 0,
        "status": "pending",
        "created_at": created_at,
        "timeout_ms": timeout_ms,
    }

    _RESULT_QUEUE = queue.Queue()

    EnhanceRequestHandler.client = client
    EnhanceRequestHandler.original_prompt = prompt
    EnhanceRequestHandler.conversation_history = history

    for p in range(port, port + 100):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", p))
                port = p
                break
        except OSError:
            continue

    server = HTTPServer(("127.0.0.1", port), EnhanceRequestHandler)
    server.timeout = 0.5

    shutdown_flag = threading.Event()
    server_ready = threading.Event()

    def serve():
        server_ready.set()
        while not shutdown_flag.is_set():
            server.handle_request()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    server_ready.wait(timeout=2)

    url = f"http://127.0.0.1:{port}/enhance?session={session_id}"
    print(f"Opening browser: {url}", file=sys.stderr)

    def open_browser():
        import subprocess
        if sys.platform == "win32":
            # Try multiple methods on Windows
            methods = [
                lambda: os.startfile(url),
                lambda: subprocess.run(["cmd", "/c", "start", "", url], check=True, shell=False),
                lambda: subprocess.run(["powershell", "-Command", f"Start-Process '{url}'"], check=True),
                lambda: webbrowser.open(url),
            ]
        elif sys.platform == "darwin":
            methods = [
                lambda: subprocess.run(["open", url], check=True),
                lambda: webbrowser.open(url),
            ]
        else:
            methods = [
                lambda: subprocess.run(["xdg-open", url], check=True),
                lambda: webbrowser.open(url),
            ]

        for method in methods:
            try:
                method()
                return True
            except Exception as e:
                print(f"Browser open method failed: {e}", file=sys.stderr)
                continue
        return False

    if auto_open_browser:
        if not open_browser():
            print(f"Could not open browser. Please open manually: {url}", file=sys.stderr)
    else:
        print(f"Browser auto-open disabled. Please open: {url}", file=sys.stderr)

    print("Waiting for user action...", file=sys.stderr)

    try:
        result = _RESULT_QUEUE.get(timeout=timeout_ms / 1000)
    except queue.Empty:
        result = None
        print("Timeout waiting for user action", file=sys.stderr)

    shutdown_flag.set()
    thread.join(timeout=1)
    server.server_close()
    del _SESSIONS[session_id]
    _RESULT_QUEUE = None

    return result
