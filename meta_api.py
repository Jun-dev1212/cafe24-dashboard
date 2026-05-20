import requests
import pandas as pd


class MetaAdsAPI:
    BASE = "https://graph.facebook.com/v19.0"

    def __init__(self, access_token: str, ad_account_id: str):
        self.access_token = access_token
        self.ad_account_id = ad_account_id  # act_XXXXXXXXXX

    def _get(self, endpoint: str, params: dict = None) -> dict:
        url = f"{self.BASE}/{endpoint}"
        p = {"access_token": self.access_token}
        if params:
            p.update(params)
        resp = requests.get(url, params=p, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _paginate(self, endpoint: str, params: dict) -> list:
        data = self._get(endpoint, params)
        results = list(data.get("data", []))
        while True:
            nxt = data.get("paging", {}).get("next")
            if not nxt:
                break
            data = requests.get(nxt, timeout=30).json()
            results.extend(data.get("data", []))
        return results

    def get_insights(self, start_date: str, end_date: str, level: str = "ad") -> list:
        """level: campaign / adset / ad"""
        return self._paginate(f"{self.ad_account_id}/insights", {
            "fields": (
                "campaign_name,adset_name,ad_name,"
                "impressions,reach,clicks,ctr,cpc,cpm,spend,"
                "actions,action_values"
            ),
            "time_range": f'{{"since":"{start_date}","until":"{end_date}"}}',
            "level": level,
            "limit": 100,
        })

    def get_daily_insights(self, start_date: str, end_date: str) -> list:
        """캠페인 레벨 일별 성과"""
        return self._paginate(f"{self.ad_account_id}/insights", {
            "fields": "campaign_name,impressions,reach,clicks,ctr,cpm,spend,actions,action_values",
            "time_range": f'{{"since":"{start_date}","until":"{end_date}"}}',
            "time_increment": 1,
            "level": "campaign",
            "limit": 100,
        })

    def get_campaign_budgets(self) -> dict:
        """캠페인별 예산 조회 → {campaign_id: daily_budget}"""
        data = self._get(f"{self.ad_account_id}/campaigns", {
            "fields": "name,daily_budget,lifetime_budget,status",
            "limit": 100,
        })
        result = {}
        for c in data.get("data", []):
            budget = int(c.get("daily_budget") or c.get("lifetime_budget") or 0)
            result[c["name"]] = budget // 100  # 센트 → 원
        return result


def _extract_action(items: list, action_type: str, default=0):
    for a in items:
        if a.get("action_type") == action_type:
            return float(a.get("value", 0))
    return float(default)


def process_meta_insights(insights: list) -> pd.DataFrame:
    if not insights:
        return pd.DataFrame()
    rows = []
    for item in insights:
        actions = item.get("actions", [])
        action_values = item.get("action_values", [])
        spend = float(item.get("spend", 0))
        purchase_value = _extract_action(action_values, "purchase")
        roas = round(purchase_value / spend, 2) if spend > 0 else 0.0
        rows.append({
            "campaign": item.get("campaign_name", ""),
            "adset": item.get("adset_name", ""),
            "ad": item.get("ad_name", ""),
            "impressions": int(item.get("impressions", 0)),
            "reach": int(item.get("reach", 0)),
            "clicks": int(item.get("clicks", 0)),
            "ctr": round(float(item.get("ctr", 0)), 2),
            "cpc": round(float(item.get("cpc", 0)), 0),
            "cpm": round(float(item.get("cpm", 0)), 0),
            "spend": round(spend, 0),
            "purchases": int(_extract_action(actions, "purchase")),
            "purchase_value": round(purchase_value, 0),
            "roas": roas,
        })
    return pd.DataFrame(rows)


def process_meta_daily(insights: list) -> pd.DataFrame:
    if not insights:
        return pd.DataFrame()
    rows = []
    for item in insights:
        actions = item.get("actions", [])
        action_values = item.get("action_values", [])
        spend = float(item.get("spend", 0))
        purchase_value = _extract_action(action_values, "purchase")
        rows.append({
            "date": pd.to_datetime(item.get("date_start", "")),
            "campaign": item.get("campaign_name", ""),
            "impressions": int(item.get("impressions", 0)),
            "clicks": int(item.get("clicks", 0)),
            "ctr": round(float(item.get("ctr", 0)), 2),
            "spend": round(spend, 0),
            "purchases": int(_extract_action(actions, "purchase")),
            "purchase_value": round(purchase_value, 0),
        })
    return pd.DataFrame(rows)
