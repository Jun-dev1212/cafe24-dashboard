"""
Coupang Wing Open API 클라이언트.
인증: HMAC-SHA256 (OAuth 없음 — API Key 방식, 만료 없음)
"""
import hashlib
import hmac
import time
import requests
import pandas as pd
from datetime import datetime


class CoupangAPI:
    BASE_URL = "https://api-gateway.coupang.com"
    # 유효 주문 상태 (취소/반품 제외)
    PAID_STATUSES = {"ACCEPT", "INSTRUCT", "DEPARTURE", "DELIVERING",
                     "FINAL_DELIVERY", "CONFIRMED"}

    def __init__(self, access_key: str, secret_key: str, vendor_id: str):
        self.access_key = access_key
        self.secret_key = secret_key
        self.vendor_id = vendor_id

    def _sign(self, method: str, path: str, query: str = "") -> dict:
        dt_ms = str(int(time.time() * 1000))
        message = dt_ms + method.upper() + path + query
        sig = hmac.new(
            self.secret_key.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return {
            "Authorization": (
                f"CEA algorithm=HmacSHA256, access-key={self.access_key}, "
                f"signed-date={dt_ms}, signature={sig}"
            ),
            "Content-Type": "application/json;charset=UTF-8",
        }

    def _get_orders_page(self, created_from: str, created_to: str,
                         page: int, per_page: int = 50) -> list:
        path = f"/v2/providers/openapi/apis/api/v4/vendors/{self.vendor_id}/ordersheets"
        params = {
            "createdAtFrom": created_from,
            "createdAtTo": created_to,
            "maxPerPage": per_page,
            "pageIndex": page,
        }
        # 쿼리 문자열을 HMAC 메시지에 포함 (sorted key order)
        query_str = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        headers = self._sign("GET", path, query_str)
        resp = requests.get(
            self.BASE_URL + path,
            headers=headers,
            params=params,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", [])

    def get_orders(self, start_date: str, end_date: str) -> list:
        """start_date/end_date: 'YYYY-MM-DD' 형식"""
        created_from = f"{start_date}T00:00:00"
        created_to = f"{end_date}T23:59:59"
        all_sheets = []
        page = 1
        per_page = 50
        while True:
            try:
                chunk = self._get_orders_page(created_from, created_to, page, per_page)
            except Exception:
                break
            all_sheets.extend(chunk)
            if len(chunk) < per_page:
                break
            page += 1
        return all_sheets


def _parse_dt(raw: str) -> datetime:
    """쿠팡 날짜 문자열을 datetime으로 파싱 (여러 포맷 허용)."""
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    raise ValueError(f"날짜 파싱 실패: {raw}")


def process_orders(sheets: list) -> pd.DataFrame:
    if not sheets:
        return pd.DataFrame()
    rows = []
    for sheet in sheets:
        status = sheet.get("status", "")
        if status not in CoupangAPI.PAID_STATUSES:
            continue
        try:
            dt_raw = sheet.get("orderedAt") or sheet.get("paidAt", "")
            dt = _parse_dt(dt_raw)
        except Exception:
            continue

        # 주문 총액 계산 (orderItems 합산 / 또는 상위 필드)
        if "orderPrice" in sheet:
            price = float(sheet["orderPrice"] or 0)
        else:
            price = 0.0
            for item in sheet.get("orderItems", []):
                qty = int(item.get("quantity", 0))
                cancel = int(item.get("cancelCount", 0))
                unit = float(item.get("unitPrice", 0) or 0)
                price += unit * max(0, qty - cancel)

        rows.append({
            "order_id": str(sheet.get("orderId", "")),
            "order_date": dt.date(),
            "order_datetime": dt,
            "hour": dt.hour,
            "weekday": dt.weekday(),
            "actual_price": price,
            "payment_method": sheet.get("paymentMethod", ""),
            "order_status": status,
            "member_id": str(sheet.get("orderId", "")),  # 쿠팡은 구매자 ID 미노출
        })
    return pd.DataFrame(rows)
