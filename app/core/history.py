from __future__ import annotations

import csv, json, logging, threading, time, uuid
from pathlib import Path
from typing import Any
LOG=logging.getLogger("organizepro.history")

class HistoryStore:
    def __init__(self,directory:Path,limit:int=5000,retention_days:int=30):
        self.directory=directory; self.directory.mkdir(parents=True,exist_ok=True); self.path=directory/"operations.jsonl"; self.limit=max(1,int(limit)); self.retention_days=max(1,min(int(retention_days),3650)); self._lock=threading.RLock(); self._records=[]; self._load()
    def _load(self):
        if not self.path.exists(): return
        try:
            lines=self.path.read_text(encoding="utf-8").splitlines()[-self.limit:]; loaded=[]
            for line in lines:
                if not line.strip(): continue
                try:
                    row=json.loads(line)
                    if isinstance(row,dict): loaded.append(row)
                except json.JSONDecodeError: LOG.warning("Skipping malformed operation-history row")
            self._records=list(reversed(loaded)); self._prune_locked()
        except OSError: LOG.exception("Could not read operation history"); self._records=[]
    def add(self,**values):
        with self._lock:
            record={"id":uuid.uuid4().hex,"timestamp":time.time(),"operation":"move","status":"success","filename":"","source_path":"","destination_path":"","file_size":0,"category":"","reason":"","error":None,"event_id":None}; record.update(values); self._records.insert(0,record); self._prune_locked(); self._persist_locked(); return dict(record)
    def query(self,*,limit:int=250,status:str="all",search:str=""):
        with self._lock:
            result=self._records
            if status!="all": result=[r for r in result if r.get("status")==status]
            needle=search.casefold().strip()
            if needle: result=[r for r in result if needle in " ".join(str(r.get(k,"")) for k in ("filename","source_path","destination_path","category","error")).casefold()]
            return [dict(r) for r in result[:max(1,min(limit,5000))]]
    def stats(self):
        with self._lock:
            records=self._records; moved=[r for r in records if r.get("status")=="success" and r.get("operation")=="move"]
            return {"processed":sum(1 for r in records if r.get("operation") in {"move","skip","error","dry_run"}),"organized":len(moved),"skipped":sum(1 for r in records if r.get("status")=="skipped"),"failed":sum(1 for r in records if r.get("status")=="failed"),"bytes_organized":sum(int(r.get("file_size",0) or 0) for r in moved),"last_success":next((r.get("timestamp") for r in records if r.get("status")=="success" and r.get("operation")=="move"),None),"last_success_filename":next((r.get("filename") for r in records if r.get("status")=="success" and r.get("operation")=="move"),None),"record_count":len(records)}
    def set_retention_days(self,days:int):
        with self._lock: self.retention_days=max(1,min(int(days),3650)); self._prune_locked(); self._persist_locked()
    def _prune_locked(self):
        cutoff=time.time()-self.retention_days*86400; retained=[]
        for r in self._records:
            try:
                if float(r.get("timestamp",0))>=cutoff: retained.append(r)
            except (TypeError,ValueError): pass
        self._records=retained[:self.limit]
    def clear(self):
        with self._lock: self._records.clear(); self._persist_locked()
    def export_csv(self,path:Path):
        records=self.query(limit=self.limit); fields=["id","timestamp","operation","status","filename","source_path","destination_path","file_size","category","reason","error"]
        with path.open("w",newline="",encoding="utf-8-sig") as handle:
            writer=csv.DictWriter(handle,fieldnames=fields,extrasaction="ignore"); writer.writeheader(); writer.writerows(records)
    def find(self,record_id:str):
        with self._lock:
            item=next((r for r in self._records if r.get("id")==record_id),None); return dict(item) if item else None
    def update_status(self,record_id:str,status:str,error:str|None=None):
        with self._lock:
            for r in self._records:
                if r.get("id")==record_id: r["status"]=status; r["error"]=error; self._persist_locked(); return True
            return False
    def _persist_locked(self):
        temporary=self.path.with_suffix(f".tmp-{threading.get_ident()}")
        try:
            with temporary.open("w",encoding="utf-8") as handle:
                for r in reversed(self._records): handle.write(json.dumps(r,ensure_ascii=False)+"\n")
            temporary.replace(self.path)
        except OSError:
            temporary.unlink(missing_ok=True); LOG.exception("Could not persist operation history to %s",self.path)
