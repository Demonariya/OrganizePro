from __future__ import annotations

import csv, io, json, logging, mimetypes, secrets, threading, urllib.parse, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

LOG=logging.getLogger("organizepro.web")


class LocalDashboardServer:
    def __init__(self,controller,host="127.0.0.1",port=0):
        self.controller=controller; self.host=host; self.port=port; self.token=secrets.token_urlsafe(32); self.httpd=None; self.thread=None; self.frontend=Path(__file__).resolve().parent/"frontend"
    @property
    def url(self): return f"http://127.0.0.1:{self.port}/"
    def start(self):
        controller=self.controller; token=self.token; frontend=self.frontend
        class Handler(BaseHTTPRequestHandler):
            server_version="OrganizeProLocal/1.0"
            def log_message(self,fmt,*args): LOG.debug("HTTP %s - %s",self.address_string(),fmt%args)
            def _send(self,status,payload,content_type="application/json; charset=utf-8"):
                if isinstance(payload,(dict,list)): body=json.dumps(payload,ensure_ascii=False).encode("utf-8")
                elif isinstance(payload,str): body=payload.encode("utf-8")
                else: body=payload
                self.send_response(status); self.send_header("Content-Type",content_type); self.send_header("Content-Length",str(len(body))); self.send_header("Cache-Control","no-store"); self.send_header("X-Content-Type-Options","nosniff"); self.send_header("X-Frame-Options","DENY"); self.send_header("Referrer-Policy","no-referrer"); self.send_header("Content-Security-Policy","default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"); self.send_header("Permissions-Policy","camera=(), microphone=(), geolocation=()"); self.end_headers(); self.wfile.write(body)
            def _trusted(self):
                if self.client_address[0] not in {"127.0.0.1","::1"}: return False
                host=self.headers.get("Host","").split(":",1)[0].strip("[]").lower()
                if host not in {"127.0.0.1","localhost"}: return False
                origin=self.headers.get("Origin")
                return not origin or origin in {f"http://127.0.0.1:{self.server.server_port}",f"http://localhost:{self.server.server_port}"}
            def _authorized(self):
                if not self._trusted(): self._send(403,{"error":"Local access only"}); return False
                if self.headers.get("X-OrganizePro-Token")!=token: self._send(403,{"error":"Invalid dashboard token"}); return False
                return True
            def _body(self):
                length=int(self.headers.get("Content-Length","0"))
                if length>1_000_000: raise ValueError("Request body is too large")
                data=json.loads((self.rfile.read(length) if length else b"{}").decode("utf-8"))
                if not isinstance(data,dict): raise ValueError("JSON body must be an object")
                return data
            def do_GET(self):
                if not self._trusted(): self._send(403,{"error":"Local access only"}); return
                parsed=urllib.parse.urlparse(self.path); route=parsed.path
                if route=="/" or route.startswith("/assets/") or route in {"/app.js","/styles.css","/favicon.png"}: self._static(route); return
                if not self._authorized(): return
                query=urllib.parse.parse_qs(parsed.query)
                try:
                    if route=="/api/status": self._send(200,controller.dashboard_status())
                    elif route=="/api/settings": self._send(200,controller.settings.snapshot())
                    elif route=="/api/categories": self._send(200,controller.category_stats())
                    elif route=="/api/sources": self._send(200,controller.source_profiles())
                    elif route=="/api/activity": self._send(200,controller.activity_records(limit=int(query.get("limit",[250])[0]),status=query.get("status",["all"])[0],search=query.get("search",[""])[0]))
                    elif route=="/api/startup":
                        from app.desktop.startup import StartupManager
                        self._send(200,StartupManager.status())
                    elif route=="/api/logs": self._send(200,controller.read_logs(limit=int(query.get("limit",[250])[0])))
                    elif route=="/api/export":
                        rows=controller.history.query(limit=5000); stream=io.StringIO(); fields=["timestamp","operation","status","filename","source_path","destination_path","file_size","category","reason","error"]; writer=csv.DictWriter(stream,fieldnames=fields,extrasaction="ignore"); writer.writeheader(); writer.writerows(rows); self._send(200,stream.getvalue(),"text/csv; charset=utf-8")
                    else: self._send(404,{"error":"Not found"})
                except Exception as exc: LOG.exception("GET API failure: %s",route); self._send(400,{"error":str(exc)})
            def do_POST(self):
                if not self._authorized(): return
                route=urllib.parse.urlparse(self.path).path
                try:
                    data=self._body()
                    if route=="/api/monitor/start": result=controller.start_monitoring()
                    elif route=="/api/monitor/pause": controller.monitor.pause(); result=controller.monitor.status()
                    elif route=="/api/monitor/resume": controller.monitor.resume(); result=controller.monitor.status()
                    elif route=="/api/monitor/restart": result=controller.monitor.restart()
                    elif route=="/api/monitor/stop": controller.monitor.stop(); result=controller.monitor.status()
                    elif route=="/api/scan/preview": result=controller.preview_existing()
                    elif route=="/api/scan/dry-run": result=controller.dry_run_existing()
                    elif route=="/api/scan/execute":
                        if data.get("confirm") is not True: raise ValueError("Explicit confirmation is required for batch organization")
                        result=controller.organize_existing(confirm_replace=bool(data.get("confirm_replace")))
                    elif route=="/api/settings":
                        from app.config.settings import validate_settings
                        old=controller.settings.snapshot(); validate_settings({**old,**data}); was_running=controller.monitor.is_running
                        if was_running: controller.monitor.stop()
                        try:
                            result=controller.settings.update(data); controller.apply_runtime_settings()
                            if was_running: controller.start_monitoring()
                        except Exception:
                            try:
                                controller.settings.update(old); controller.apply_runtime_settings()
                                if was_running and not controller.monitor.is_running: controller.start_monitoring()
                            except Exception: LOG.exception("Could not restore previous runtime configuration")
                            raise
                    elif route=="/api/categories": result=controller.update_categories(data)
                    elif route=="/api/sources": result=controller.update_sources(data)
                    elif route=="/api/open-operation-location": result=controller.open_operation_location(str(data.get("id","")),str(data.get("kind","source")))
                    elif route=="/api/undo": result=dict(zip(("success","message"),controller.organizer.undo(str(data.get("id","")))))
                    elif route=="/api/startup":
                        from app.desktop.startup import StartupManager
                        ok,message=StartupManager.set_enabled(bool(data.get("enabled")),bool(data.get("start_minimized",True))); result={"success":ok,"message":message,"status":StartupManager.status()}
                        if not ok: self._send(400,result); return
                    elif route=="/api/open-folder": result=controller.open_folder(str(data.get("kind","source")))
                    else: self._send(404,{"error":"Not found"}); return
                    self._send(200,result)
                except Exception as exc: LOG.exception("POST API failure: %s",route); self._send(400,{"error":str(exc)})
            def _static(self,route):
                names={"/":"index.html","/app.js":"app.js","/styles.css":"styles.css","/favicon.png":"favicon.png"}; rel=names.get(route)
                if route.startswith("/assets/"): rel=route.lstrip("/")
                if not rel: self._send(404,"Not found","text/plain; charset=utf-8"); return
                candidate=(frontend/rel).resolve()
                try: candidate.relative_to(frontend.resolve())
                except ValueError: self._send(403,"Forbidden","text/plain; charset=utf-8"); return
                if not candidate.is_file(): self._send(404,"Not found","text/plain; charset=utf-8"); return
                data=candidate.read_bytes(); ctype=mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
                if candidate.suffix in {".js",".css",".html",".svg"}: ctype+="; charset=utf-8"
                if candidate.name=="index.html": data=data.replace(b"__ORGANIZEPRO_TOKEN__",token.encode("ascii"))
                self._send(200,data,ctype)
        self.httpd=ThreadingHTTPServer((self.host,self.port),Handler); self.httpd.daemon_threads=True; self.port=int(self.httpd.server_address[1]); self.thread=threading.Thread(target=self.httpd.serve_forever,name="OrganizeProHTTP",daemon=True); self.thread.start(); LOG.info("Dashboard server listening on %s",self.url); return self.url
    def open(self,page=""): webbrowser.open(self.url+page.lstrip("/"))
    def stop(self):
        if self.httpd: self.httpd.shutdown(); self.httpd.server_close(); self.httpd=None
        if self.thread and self.thread.is_alive(): self.thread.join(timeout=3)
        self.thread=None
