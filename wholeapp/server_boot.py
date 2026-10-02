"""Protected runtime entrypoint. Not part of the agent's editable project."""
import os
from datetime import datetime

os.chdir("/home/frappe/frappe-bench/sites")
import frappe
import frappe.utils.data

fixed_time = datetime.fromisoformat("2026-10-01T12:00:00")
frappe.utils.data.now_datetime = lambda: fixed_time
frappe.utils.now_datetime = lambda: fixed_time

from gunicorn.app.base import BaseApplication
from frappe.app import application


class CandidateServer(BaseApplication):
    def load_config(self):
        self.cfg.set("bind", "0.0.0.0:8000")
        self.cfg.set("workers", 1)
        self.cfg.set("threads", 2)
        self.cfg.set("timeout", 45)
        self.cfg.set("accesslog", None)
        self.cfg.set("errorlog", "-")

    def load(self):
        return application


CandidateServer().run()
