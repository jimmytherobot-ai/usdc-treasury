#!/usr/bin/env python3
"""
USDC Treasury — Inter-Agent REST API Server

A lightweight HTTP server that exposes treasury operations as a REST API,
enabling agent-to-agent USDC invoicing and payment settlement.

Usage:
    # Start the server
    TREASURY_API_KEY=your-secret-key python scripts/server.py --port 8080

    # Or with defaults (port 9090, no auth in dev mode)
    python scripts/server.py

Environment Variables:
    TREASURY_API_KEY  — Bearer token for authentication (required in production)
    TREASURY_PORT     — Port to listen on (default: 9090)
"""

import sys
import os
import json
import argparse
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))

from treasury import get_all_balances, get_balance
from invoices import (
    create_invoice, pay_invoice, list_invoices,
    get_invoice, get_invoice_audit_trail, cancel_invoice,
)


# ============================================================
# Auth
# ============================================================

API_KEY = os.environ.get("TREASURY_API_KEY", "")


def check_auth(handler):
    """Verify Bearer token if TREASURY_API_KEY is set."""
    if not API_KEY:
        return True  # No auth configured (dev mode)
    auth = handler.headers.get("Authorization", "")
    if auth == f"Bearer {API_KEY}":
        return True
    handler.send_error_json(401, "Unauthorized: invalid or missing Bearer token")
    return False


# ============================================================
# Request Handler
# ============================================================

class TreasuryHandler(BaseHTTPRequestHandler):
    """HTTP handler for treasury API endpoints."""

    def log_message(self, format, *args):
        """Override to use structured logging."""
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        sys.stderr.write(f"[{ts}] {args[0]}\n")

    def send_json(self, data, status=200):
        """Send a JSON response."""
        body = json.dumps(data, indent=2, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, status, message):
        """Send a JSON error response."""
        self.send_json({"error": message, "status": status}, status)

    def read_body(self):
        """Read and parse JSON request body."""
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw)

    def route(self, method):
        """Route requests to handlers."""
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        qs = parse_qs(parsed.query)

        routes = {
            "GET": {
                "/health": self.handle_health,
                "/balance": self.handle_balance,
                "/invoices": self.handle_list_invoices,
            },
            "POST": {
                "/invoices": self.handle_create_invoice,
            },
        }

        # Exact match
        handler = routes.get(method, {}).get(path)
        if handler:
            return handler(qs)

        # Parameterized routes: /invoices/<number> and /invoices/<number>/pay
        parts = path.split("/")
        if len(parts) == 3 and parts[1] == "invoices":
            inv_number = parts[2]
            if method == "GET":
                return self.handle_get_invoice(inv_number)
            elif method == "POST":
                return self.handle_create_invoice(qs)
        elif len(parts) == 4 and parts[1] == "invoices" and parts[3] == "pay":
            inv_number = parts[2]
            if method == "POST":
                return self.handle_pay_invoice(inv_number)
        elif len(parts) == 4 and parts[1] == "invoices" and parts[3] == "audit":
            inv_number = parts[2]
            if method == "GET":
                return self.handle_audit_invoice(inv_number)

        self.send_error_json(404, f"Not found: {method} {path}")

    # --- Handlers ---

    def handle_health(self, qs=None):
        self.send_json({
            "status": "ok",
            "service": "usdc-treasury",
            "version": "2.1.0",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def handle_balance(self, qs=None):
        chain = (qs or {}).get("chain", [None])[0]
        try:
            if chain:
                result = get_balance(chain)
            else:
                result = get_all_balances()
            self.send_json(result)
        except Exception as e:
            self.send_error_json(500, str(e))

    def handle_list_invoices(self, qs=None):
        qs = qs or {}
        try:
            result = list_invoices(
                status=qs.get("status", [None])[0],
                counterparty=qs.get("counterparty", [None])[0],
                chain_key=qs.get("chain", [None])[0],
                invoice_type=qs.get("type", [None])[0],
            )
            self.send_json(result)
        except Exception as e:
            self.send_error_json(500, str(e))

    def handle_get_invoice(self, invoice_number):
        try:
            inv = get_invoice(invoice_number=invoice_number)
            if not inv:
                return self.send_error_json(404, f"Invoice {invoice_number} not found")
            self.send_json(inv)
        except Exception as e:
            self.send_error_json(500, str(e))

    def handle_audit_invoice(self, invoice_number):
        try:
            trail = get_invoice_audit_trail(invoice_number)
            self.send_json(trail)
        except ValueError as e:
            self.send_error_json(404, str(e))
        except Exception as e:
            self.send_error_json(500, str(e))

    def handle_create_invoice(self, qs=None):
        """
        Accept an invoice from another agent.
        
        POST /invoices
        {
            "counterparty_name": "Agent B",
            "counterparty_address": "0x...",
            "items": [{"description": "API calls", "quantity": 100, "unit_price": 0.01}],
            "chain": "base_sepolia",
            "due_days": 30,
            "memo": "January API usage",
            "category": "services"
        }
        """
        try:
            body = self.read_body()
            required = ["counterparty_name", "counterparty_address", "items"]
            missing = [f for f in required if f not in body]
            if missing:
                return self.send_error_json(400, f"Missing required fields: {missing}")

            inv = create_invoice(
                counterparty_name=body["counterparty_name"],
                counterparty_address=body["counterparty_address"],
                line_items=body["items"],
                chain_key=body.get("chain", "base_sepolia"),
                due_days=body.get("due_days", 30),
                memo=body.get("memo", ""),
                category=body.get("category", "services"),
                invoice_type=body.get("type", "payable"),
            )
            self.send_json(inv, 201)
        except ValueError as e:
            self.send_error_json(400, str(e))
        except Exception as e:
            self.send_error_json(500, str(e))

    def handle_pay_invoice(self, invoice_number):
        """
        Pay an invoice on-chain.
        
        POST /invoices/INV-0001/pay
        {"amount": 50.00}  # optional — defaults to full remaining
        """
        try:
            body = self.read_body()
            result = pay_invoice(
                invoice_number=invoice_number,
                amount_usdc=body.get("amount"),
                chain_key=body.get("chain"),
            )
            self.send_json(result)
        except ValueError as e:
            self.send_error_json(400, str(e))
        except Exception as e:
            self.send_error_json(500, str(e))

    # --- HTTP method dispatchers ---

    def do_GET(self):
        if not check_auth(self):
            return
        self.route("GET")

    def do_POST(self):
        if not check_auth(self):
            return
        self.route("POST")

    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.end_headers()


# ============================================================
# Server
# ============================================================

def run_server(port=None, host="0.0.0.0"):
    """Start the treasury API server."""
    port = port or int(os.environ.get("TREASURY_PORT", 9090))
    server = HTTPServer((host, port), TreasuryHandler)
    
    auth_mode = "Bearer token" if API_KEY else "OPEN (no auth — set TREASURY_API_KEY for production)"
    print(f"🏦 USDC Treasury API Server v2.1.0")
    print(f"   Listening on {host}:{port}")
    print(f"   Auth: {auth_mode}")
    print(f"   Endpoints:")
    print(f"     GET  /health                — Health check")
    print(f"     GET  /balance               — Treasury balances")
    print(f"     GET  /invoices              — List invoices")
    print(f"     GET  /invoices/<num>        — Get invoice details")
    print(f"     GET  /invoices/<num>/audit  — Full audit trail")
    print(f"     POST /invoices              — Create/receive invoice")
    print(f"     POST /invoices/<num>/pay    — Pay an invoice")
    print()
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n⏹  Server stopped.")
        server.server_close()


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="USDC Treasury API Server")
    parser.add_argument("--port", type=int, default=None, help="Port (default: 9090 or TREASURY_PORT)")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    args = parser.parse_args()
    run_server(port=args.port, host=args.host)


if __name__ == "__main__":
    main()
