import requests
import pandas as pd
from datetime import datetime
from typing import Optional


class Cafe24API:
    PAID_STATUSES = ["F", "M", "J", "A", "B", "C"]  # 결제완료~구매확정

    def __init__(self, mall_id, client_id, client_secret, refresh_token,
                 token_store=None):
        self.mall_id = mall_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.access_token = None
        self.token_store = token_store  # GistTokenStore 또는 None
        self.base_url = f"https://{mall_id}.cafe24api.com/api/v2/admin"

    def refresh_access_token(self):
        url = f"https://{self.mall_id}.cafe24api.com/api/v2/oauth/token"
        resp = requests.post(
            url,
            data={"grant_type": "refresh_token", "refresh_token": self.refresh_token},
            auth=(self.client_id, self.client_secret),
        )
        if resp.status_code != 200:
            raise Exception(f"토큰 갱신 실패 ({resp.status_code}): {resp.text}")
        tokens = resp.json()
        self.access_token = tokens["access_token"]
        if "refresh_token" in tokens:
            new_rt = tokens["refresh_token"]
            if new_rt != self.refresh_token:
                self.refresh_token = new_rt
                # 새 refresh_token을 Gist에 즉시 저장 (자동 갱신 핵심)
                if self.token_store:
                    self.token_store.write(self.refresh_token)

    def _headers(self):
        return {"Authorization": f"Bearer {self.access_token}"}

    def _get(self, endpoint, params=None):
        url = f"{self.base_url}/{endpoint}"
        resp = requests.get(url, headers=self._headers(), params=params)
        if resp.status_code == 401:
            self.refresh_access_token()
            resp = requests.get(url, headers=self._headers(), params=params)
        resp.raise_for_status()
        return resp.json()

    def get_orders(self, start_date: str, end_date: str) -> list:
        all_orders = []
        offset = 0
        while True:
            data = self._get("orders", {
                "start_date": start_date,
                "end_date": end_date,
                "shop_no": 1,
                "limit": 100,
                "offset": offset,
            })
            chunk = data.get("orders", [])
            all_orders.extend(chunk)
            if len(chunk) < 100:
                break
            offset += 100
        return all_orders

    def get_sales_report(self, start_date: str, end_date: str) -> list:
        """매출통계(Salesreport) — 일별 매출 집계."""
        try:
            data = self._get("reports/salesvolume", {
                "start_date": start_date,
                "end_date": end_date,
                "search_type": "daily",
            })
            return data.get("salesvolume", [])
        except Exception:
            return []

    def get_visitor_stats(self, start_date: str, end_date: str) -> list:
        """접속통계(Analytics) — 일별 방문자 + 전환율."""
        try:
            data = self._get("reports/visitorsstatistics", {
                "start_date": start_date,
                "end_date": end_date,
            })
            return data.get("visitorsstatistics", [])
        except Exception:
            return []


def process_orders(orders: list) -> pd.DataFrame:
    if not orders:
        return pd.DataFrame()
    rows = []
    for o in orders:
        if o.get("canceled") == "T":
            continue
        if float(o.get("payment_amount") or 0) <= 0:
            continue
        try:
            dt_str = o.get("order_date", "")
            dt = datetime.fromisoformat(dt_str.replace("+0900", "+09:00"))
            rows.append({
                "order_id": o.get("order_id", ""),
                "order_date": dt.date(),
                "order_datetime": dt,
                "hour": dt.hour,
                "weekday": dt.weekday(),
                "actual_price": float(o.get("payment_amount") or o.get("actual_order_amount") or 0),
                "payment_method": o.get("payment_method", ""),
                "order_status": o.get("shipping_status") or "",
                "member_id": o.get("member_id", ""),
            })
        except Exception:
            continue
    return pd.DataFrame(rows)
