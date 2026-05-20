import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import date, timedelta

from cafe24_api import Cafe24API, process_orders as cafe24_process
from coupang_api import CoupangAPI, process_orders as coupang_process
from meta_api import MetaAdsAPI, process_meta_insights, process_meta_daily

st.set_page_config(
    page_title="보뉴랩 운영 리포트",
    page_icon="📈",
    layout="wide",
)

DOW_MAP = {0: "월", 1: "화", 2: "수", 3: "목", 4: "금", 5: "토", 6: "일"}
DOW_ORDER = ["월", "화", "수", "목", "금", "토", "일"]
CH_COLOR = {"Cafe24": "#4F86F7", "쿠팡": "#FF6B6B"}


# ── 비밀번호 ─────────────────────────────────────────────────
def check_password() -> bool:
    if st.session_state.get("auth"):
        return True
    _, col, _ = st.columns([1, 1, 1])
    with col:
        st.markdown("## 📈 보뉴랩 운영 리포트")
        pw = st.text_input("비밀번호", type="password")
        if st.button("로그인", use_container_width=True):
            if pw == st.secrets.get("dashboard_password", ""):
                st.session_state.auth = True
                st.rerun()
            else:
                st.error("비밀번호가 틀렸습니다.")
    return False


if not check_password():
    st.stop()


# ── API 클라이언트 ────────────────────────────────────────────
@st.cache_resource
def get_cafe24() -> Cafe24API:
    api = Cafe24API(
        mall_id=st.secrets["cafe24_mall_id"],
        client_id=st.secrets["cafe24_client_id"],
        client_secret=st.secrets["cafe24_client_secret"],
        refresh_token=st.secrets["cafe24_refresh_token"],
    )
    api.refresh_access_token()
    return api


@st.cache_resource
def get_coupang() -> CoupangAPI:
    return CoupangAPI(
        access_key=st.secrets["coupang_access_key"],
        secret_key=st.secrets["coupang_secret_key"],
        vendor_id=st.secrets["coupang_vendor_id"],
    )


@st.cache_resource
def get_meta():
    try:
        return MetaAdsAPI(
            access_token=st.secrets["meta_access_token"],
            ad_account_id=st.secrets["meta_ad_account_id"],
        )
    except Exception:
        return None


# ── 데이터 로드 ───────────────────────────────────────────────
def load_cafe24(start: str, end: str) -> pd.DataFrame:
    ck = f"cafe24_{start}_{end}"
    if ck in st.session_state:
        return st.session_state[ck]
    try:
        api = get_cafe24()
        orders, offset = [], 0
        while True:
            data = api._get("orders", {
                "start_date": start, "end_date": end,
                "shop_no": 1, "limit": 100, "offset": offset,
            })
            chunk = data.get("orders", [])
            orders.extend(chunk)
            if len(chunk) < 100:
                break
            offset += 100
        df = cafe24_process(orders)
        if not df.empty:
            df["channel"] = "Cafe24"
        st.session_state[ck] = df
        return df
    except Exception as e:
        st.error(f"Cafe24 API 오류: {e}")
        return pd.DataFrame()


def load_coupang(start: str, end: str) -> pd.DataFrame:
    ck = f"cpg_{start}_{end}"
    if ck in st.session_state:
        return st.session_state[ck]
    try:
        df = coupang_process(get_coupang().get_orders(start, end))
        if not df.empty:
            df["channel"] = "쿠팡"
        st.session_state[ck] = df
        return df
    except Exception as e:
        st.warning(f"쿠팡 API: {e}")
        st.session_state[ck] = pd.DataFrame()
        return pd.DataFrame()


def load_meta(start: str, end: str):
    ck = f"meta_{start}_{end}"
    if ck in st.session_state:
        return st.session_state[ck]
    api = get_meta()
    if api is None:
        result = (pd.DataFrame(), pd.DataFrame())
        st.session_state[ck] = result
        return result
    try:
        ad_insights = process_meta_insights(api.get_insights(start, end, level="ad"))
        daily = process_meta_daily(api.get_daily_insights(start, end))
        result = (ad_insights, daily)
    except Exception as e:
        st.warning(f"Meta Ads 오류: {e}")
        result = (pd.DataFrame(), pd.DataFrame())
    st.session_state[ck] = result
    return result


def load_visitor_stats(start: str, end: str) -> pd.DataFrame:
    ck = f"vis_{start}_{end}"
    if ck in st.session_state:
        return st.session_state[ck]
    try:
        raw = get_cafe24()._get("reports/visitorsstatistics", {"start_date": start, "end_date": end})
        rows = raw.get("visitorsstatistics", [])
    except Exception:
        rows = []
    if not rows:
        st.session_state[ck] = pd.DataFrame()
        return pd.DataFrame()
    records = []
    for r in rows:
        try:
            records.append({
                "date": pd.to_datetime(r.get("date") or r.get("visit_date", "")),
                "visitors": int(r.get("total_visitors") or r.get("visitors", 0)),
                "pageviews": int(r.get("pageviews") or r.get("page_views", 0)),
                "orders": int(r.get("total_orders") or r.get("purchase_count", 0)),
                "conversion_rate": float(r.get("conversion_rate") or 0),
            })
        except Exception:
            continue
    df = pd.DataFrame(records)
    st.session_state[ck] = df
    return df


# ── 사이드바 ──────────────────────────────────────────────────
today = date.today()

with st.sidebar:
    st.markdown("## ⚙️ 설정")

    if "date_start" not in st.session_state:
        st.session_state["date_start"] = today - timedelta(days=30)
    if "date_end" not in st.session_state:
        st.session_state["date_end"] = today

    st.markdown("**빠른 설정**")
    pa, pb, pc = st.columns(3)
    with pa:
        if st.button("7일", use_container_width=True, key="b7"):
            st.session_state["date_start"] = today - timedelta(days=7)
            st.session_state["date_end"] = today
    with pb:
        if st.button("30일", use_container_width=True, key="b30"):
            st.session_state["date_start"] = today - timedelta(days=30)
            st.session_state["date_end"] = today
    with pc:
        if st.button("90일", use_container_width=True, key="b90"):
            st.session_state["date_start"] = today - timedelta(days=90)
            st.session_state["date_end"] = today

    start = st.date_input("시작일", key="date_start")
    end = st.date_input("종료일", key="date_end")

    if end < start:
        st.error("종료일이 시작일보다 앞입니다.")

    if st.button("🔄 새로고침", use_container_width=True, key="refresh_btn"):
        for k in list(st.session_state.keys()):
            if any(k.startswith(p) for p in ("cafe24_", "cpg_", "vis_", "meta_")):
                del st.session_state[k]
        st.rerun()

    st.divider()
    st.caption(f"{start.strftime('%Y.%m.%d')} ~ {end.strftime('%Y.%m.%d')}")
    st.caption("Cafe24 + 쿠팡Wing + Meta Ads")


# ── 데이터 로드 ───────────────────────────────────────────────
s, e = start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
period_days = max((end - start).days, 1)
ps = (start - timedelta(days=period_days)).strftime("%Y-%m-%d")
pe = (start - timedelta(days=1)).strftime("%Y-%m-%d")

with st.spinner("데이터 불러오는 중…"):
    df_c24 = load_cafe24(s, e)
    df_cpg = load_coupang(s, e)
    df_vis = load_visitor_stats(s, e)
    prev_c24 = load_cafe24(ps, pe)
    prev_cpg = load_coupang(ps, pe)
    df_meta_ads, df_meta_daily = load_meta(s, e)

_frames = [df for df in [df_c24, df_cpg] if not df.empty]
df_all = pd.concat(_frames, ignore_index=True) if _frames else pd.DataFrame()

_prev_frames = [df for df in [prev_c24, prev_cpg] if not df.empty]
df_prev = pd.concat(_prev_frames, ignore_index=True) if _prev_frames else pd.DataFrame()


# ── 헬퍼 ──────────────────────────────────────────────────────
def _delta_html(cur, prev):
    if not prev or prev <= 0:
        return '<span style="color:#9ca3af;font-size:13px">-</span>'
    pct = (cur - prev) / prev * 100
    if pct > 0:
        return f'<span style="color:#22c55e;font-weight:700;font-size:14px">▲ {pct:.1f}%</span>'
    if pct < 0:
        return f'<span style="color:#ef4444;font-weight:700;font-size:14px">▼ {abs(pct):.1f}%</span>'
    return '<span style="color:#9ca3af;font-size:13px">±0.0%</span>'


_CHART_BASE = dict(
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    margin=dict(l=0, r=0, t=20, b=0),
    font=dict(size=12),
)


# ── 렌더 함수 ─────────────────────────────────────────────────

def render_kpi_cards(df: pd.DataFrame, df_p: pd.DataFrame):
    if df.empty:
        return
    n = len(df)
    rev = df["actual_price"].sum()
    aov = rev / n if n else 0
    pn = len(df_p) if not df_p.empty else 0
    prev_rev = df_p["actual_price"].sum() if not df_p.empty else 0
    paov = prev_rev / pn if pn else 0

    items = [
        ("📦 주문건수", f"{n:,}건", _delta_html(n, pn), "#6366f1"),
        ("💰 총 매출", f"₩{rev:,.0f}", _delta_html(rev, prev_rev), "#4F86F7"),
        ("🧾 객단가", f"₩{aov:,.0f}", _delta_html(aov, paov), "#0ea5e9"),
    ]
    cols = st.columns(3)
    for col, (title, value, delta, color) in zip(cols, items):
        with col:
            st.markdown(
                f'<div style="background:#f8faff;border-radius:14px;padding:22px 16px;'
                f'text-align:center;border-top:4px solid {color};'
                f'box-shadow:0 2px 8px rgba(0,0,0,0.07)">'
                f'<div style="font-size:13px;color:#6b7280;margin-bottom:6px">{title}</div>'
                f'<div style="font-size:28px;font-weight:800;color:#111827;'
                f'letter-spacing:-0.5px;line-height:1.2">{value}</div>'
                f'<div style="margin-top:8px">{delta}'
                f'<span style="font-size:12px;color:#9ca3af"> vs 이전기간</span></div>'
                f'</div>',
                unsafe_allow_html=True,
            )


def render_daily(df: pd.DataFrame, tab: str = ""):
    if df.empty:
        return
    if "channel" not in df.columns:
        df = df.copy()
        df["channel"] = "전체"
    daily = (
        df.groupby(["order_date", "channel"])
        .agg(revenue=("actual_price", "sum"), orders=("order_id", "count"))
        .reset_index()
    )
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    for ch in daily["channel"].unique():
        d = daily[daily["channel"] == ch]
        color = CH_COLOR.get(ch, "#4F86F7")
        fig.add_trace(
            go.Bar(x=d["order_date"], y=d["revenue"], name=f"{ch} 매출",
                   marker_color=color, opacity=0.85),
            secondary_y=False,
        )
        fig.add_trace(
            go.Scatter(x=d["order_date"], y=d["orders"], name=f"{ch} 주문수",
                       line=dict(color=color, width=2, dash="dot"),
                       mode="lines+markers", marker=dict(size=5)),
            secondary_y=True,
        )
    fig.update_layout(
        hovermode="x unified", height=300, barmode="stack",
        legend=dict(orientation="h", y=1.12),
        **_CHART_BASE,
    )
    fig.update_yaxes(title_text="매출 (원)", tickformat=",", gridcolor="#f0f0f0", secondary_y=False)
    fig.update_yaxes(title_text="주문 건수", secondary_y=True)
    st.plotly_chart(fig, use_container_width=True, key=f"daily_{tab}")


def render_hourly_dow(df: pd.DataFrame, tab: str = ""):
    if df.empty:
        return
    col1, col2 = st.columns(2)
    _layout = dict(height=280, **_CHART_BASE)

    with col1:
        st.markdown("##### 시간대별 주문")
        hourly = (
            df.groupby("hour")["order_id"].count()
            .reindex(range(24), fill_value=0).reset_index()
        )
        hourly.columns = ["hour", "orders"]
        fig = go.Figure(go.Bar(
            x=hourly["hour"], y=hourly["orders"],
            marker=dict(color=hourly["orders"], colorscale="Blues", showscale=False,
                        line=dict(width=0)),
            text=hourly["orders"], textposition="outside", textfont=dict(size=10),
        ))
        fig.update_layout(
            xaxis=dict(title="시간", tickmode="linear", dtick=2),
            yaxis=dict(title="건수", gridcolor="#f0f0f0"),
            **_layout,
        )
        st.plotly_chart(fig, use_container_width=True, key=f"hourly_{tab}")

    with col2:
        st.markdown("##### 요일별 평균 주문")
        dow = (
            df.groupby(["order_date", "weekday"])["order_id"].count()
            .reset_index()
            .groupby("weekday")["order_id"].mean().reset_index()
        )
        dow["day"] = dow["weekday"].map(DOW_MAP)
        dow = dow.set_index("day").reindex(DOW_ORDER).reset_index().dropna()
        colors = ["#FF6B6B" if d in ["토", "일"] else "#4F86F7" for d in dow["day"]]
        fig = go.Figure(go.Bar(
            x=dow["day"], y=dow["order_id"].round(1),
            marker=dict(color=colors, line=dict(width=0)),
            text=dow["order_id"].round(1), textposition="outside", textfont=dict(size=11),
        ))
        fig.update_layout(
            xaxis=dict(title="요일"),
            yaxis=dict(title="평균 건수", gridcolor="#f0f0f0"),
            **_layout,
        )
        st.plotly_chart(fig, use_container_width=True, key=f"dow_{tab}")


def render_heatmap(df: pd.DataFrame, tab: str = ""):
    if df.empty:
        return
    hm = df.groupby(["weekday", "hour"])["order_id"].count().reset_index()
    pivot = hm.pivot(index="weekday", columns="hour", values="order_id").fillna(0)
    for h in range(24):
        if h not in pivot.columns:
            pivot[h] = 0
    pivot = pivot[sorted(pivot.columns)]
    pivot.index = [DOW_MAP[i] for i in pivot.index if i in DOW_MAP]
    pivot = pivot.reindex([d for d in DOW_ORDER if d in pivot.index])
    fig = go.Figure(go.Heatmap(
        z=pivot.values,
        x=[f"{h}시" for h in range(24)],
        y=pivot.index.tolist(),
        colorscale="Blues",
        text=pivot.values.astype(int),
        texttemplate="%{text}",
        showscale=True,
        hoverongaps=False,
    ))
    fig.update_layout(height=240, xaxis=dict(side="top"), **_CHART_BASE)
    st.plotly_chart(fig, use_container_width=True, key=f"heatmap_{tab}")


def render_funnel(df_c24: pd.DataFrame, df_vis: pd.DataFrame, tab: str = ""):
    if df_c24.empty:
        st.caption("퍼널 데이터 없음")
        return
    n_paid = len(df_c24)
    n_confirmed = len(df_c24[df_c24["order_status"].isin(["D", "E", "F"])])

    stages, values = [], []
    if not df_vis.empty and df_vis["visitors"].sum() > 0:
        stages.append("방문자")
        values.append(int(df_vis["visitors"].sum()))
        vis_orders = int(df_vis["orders"].sum()) if "orders" in df_vis.columns else 0
        if vis_orders > 0:
            stages.append("주문 시도")
            values.append(vis_orders)
    stages += ["결제 완료", "구매 확정"]
    values += [n_paid, n_confirmed]

    palette = ["#dbeafe", "#93c5fd", "#3b82f6", "#1e40af"]
    fig = go.Figure(go.Funnel(
        y=stages, x=values,
        textposition="inside", textinfo="value+percent initial",
        marker=dict(color=palette[-len(stages):], line=dict(width=2, color="white")),
        connector=dict(line=dict(color="rgba(0,0,0,0.08)", width=1)),
    ))
    fig.update_layout(**{**_CHART_BASE, "height": 300, "margin": dict(l=0, r=60, t=20, b=0)})
    st.plotly_chart(fig, use_container_width=True, key=f"funnel_{tab}")

    if len(values) >= 2:
        cvr_cols = st.columns(min(len(values) - 1, 3))
        for c, s1, s2, v1, v2 in zip(cvr_cols, stages, stages[1:], values, values[1:]):
            with c:
                st.metric(f"{s1}→{s2}", f"{v2/v1*100:.1f}%" if v1 > 0 else "-")


def render_traffic(df_vis: pd.DataFrame, tab: str = ""):
    if df_vis.empty:
        st.caption("접속통계 데이터 없음 (Cafe24 스탠다드 이상 요금제 필요)")
        return
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(x=df_vis["date"], y=df_vis["visitors"], name="방문자",
               marker_color="#A8C8F8", opacity=0.85), secondary_y=False)
    fig.add_trace(
        go.Scatter(x=df_vis["date"], y=df_vis["conversion_rate"], name="전환율(%)",
                   line=dict(color="#FF6B6B", width=2.5), mode="lines+markers",
                   marker=dict(size=6)), secondary_y=True)
    fig.update_layout(hovermode="x unified", height=280,
                      legend=dict(orientation="h", y=1.12), **_CHART_BASE)
    fig.update_yaxes(title_text="방문자 수", gridcolor="#f0f0f0", secondary_y=False)
    fig.update_yaxes(title_text="전환율 (%)", secondary_y=True)
    st.plotly_chart(fig, use_container_width=True, key=f"traffic_{tab}")
    c1, c2, c3 = st.columns(3)
    c1.metric("총 방문자", f"{df_vis['visitors'].sum():,}명")
    c2.metric("평균 전환율", f"{df_vis['conversion_rate'].mean():.2f}%")
    c3.metric("총 페이지뷰", f"{df_vis['pageviews'].sum():,}")


def render_channel_utm(df: pd.DataFrame, tab: str = ""):
    if df.empty:
        st.caption("데이터 없음")
        return
    has_ch = "channel_type" in df.columns and df["channel_type"].astype(str).str.strip().ne("").any()
    has_fp = "from_place" in df.columns and df["from_place"].astype(str).str.strip().ne("").any()
    if not has_ch and not has_fp:
        st.info("채널/유입경로 데이터가 없습니다.")
        return

    col1, col2 = st.columns(2)
    _l = dict(height=300, **_CHART_BASE)

    with col1:
        st.markdown("##### 채널 유형별 매출")
        if has_ch:
            cdf = df[df["channel_type"].astype(str).str.strip() != ""]
            cd = cdf.groupby("channel_type").agg(
                revenue=("actual_price", "sum")).sort_values("revenue", ascending=False).reset_index()
            fig = go.Figure(go.Bar(
                x=cd["channel_type"], y=cd["revenue"],
                marker=dict(color="#4F86F7", line=dict(width=0)),
                text=cd["revenue"].apply(lambda x: f"₩{x/10000:.0f}만"),
                textposition="outside",
            ))
            fig.update_layout(yaxis=dict(title="매출(원)", gridcolor="#f0f0f0"), **_l)
            st.plotly_chart(fig, use_container_width=True, key=f"ch_type_{tab}")
        else:
            st.caption("채널 유형 데이터 없음")

    with col2:
        st.markdown("##### 유입경로별 매출 (Top 10)")
        if has_fp:
            fdf = df[df["from_place"].astype(str).str.strip() != ""]
            fd = fdf.groupby("from_place").agg(
                revenue=("actual_price", "sum")).sort_values("revenue", ascending=False).head(10).reset_index()
            fig = go.Figure(go.Bar(
                x=fd["revenue"], y=fd["from_place"], orientation="h",
                marker=dict(color="#6366f1", line=dict(width=0)),
                text=fd["revenue"].apply(lambda x: f"₩{x/10000:.0f}만"),
                textposition="outside",
            ))
            fig.update_layout(
                height=300, xaxis=dict(gridcolor="#f0f0f0"), yaxis=dict(autorange="reversed"),
                **{k: v for k, v in _CHART_BASE.items() if k != "margin"},
                margin=dict(l=90, r=60, t=20, b=0),
            )
            st.plotly_chart(fig, use_container_width=True, key=f"from_place_{tab}")
        else:
            st.caption("유입경로 데이터 없음")

    grp_col = "channel_type" if has_ch else "from_place"
    label = "채널유형" if has_ch else "유입경로"
    tbl_df = df[df[grp_col].astype(str).str.strip() != ""]
    tbl = (tbl_df.groupby(grp_col)
           .agg(주문건수=("order_id", "count"), 총매출=("actual_price", "sum"),
                객단가=("actual_price", "mean"))
           .sort_values("총매출", ascending=False).reset_index()
           .rename(columns={grp_col: label}))
    tbl["총매출"] = tbl["총매출"].map(lambda x: f"₩{x:,.0f}")
    tbl["객단가"] = tbl["객단가"].map(lambda x: f"₩{x:,.0f}")
    st.markdown("##### 채널별 상세")
    st.dataframe(tbl, use_container_width=True, hide_index=True)


def _kpi_card(title, value, color):
    return (
        f'<div style="background:#f8faff;border-radius:12px;padding:14px 10px;'
        f'text-align:center;border-top:4px solid {color};'
        f'box-shadow:0 2px 8px rgba(0,0,0,0.07)">'
        f'<div style="font-size:12px;color:#6b7280;margin-bottom:4px">{title}</div>'
        f'<div style="font-size:20px;font-weight:800;color:#111827">{value}</div>'
        f'</div>'
    )


def render_meta_ads(df_ads: pd.DataFrame, df_daily: pd.DataFrame):
    if df_ads.empty:
        st.info("Meta Ads 데이터가 없습니다. 선택 기간에 집행된 광고가 없거나 API 오류입니다.")
        return

    # ── KPI 6종: 소진 / 노출 / 도달 / CTR / CPC / ROAS ──────
    total_spend = df_ads["spend"].sum()
    total_impr = df_ads["impressions"].sum()
    total_reach = df_ads["reach"].sum() if "reach" in df_ads.columns else 0
    total_clicks = df_ads["clicks"].sum()
    total_purchases = df_ads["purchases"].sum()
    total_revenue = df_ads["purchase_value"].sum()
    avg_ctr = total_clicks / total_impr * 100 if total_impr > 0 else 0
    avg_cpc = total_spend / total_clicks if total_clicks > 0 else 0
    avg_cpm = total_spend / total_impr * 1000 if total_impr > 0 else 0
    roas = total_revenue / total_spend if total_spend > 0 else 0

    kpi_items = [
        ("💸 광고 소진", f"₩{total_spend:,.0f}", "#f97316"),
        ("👁 노출", f"{total_impr:,}", "#6366f1"),
        ("👤 도달", f"{total_reach:,}", "#8b5cf6"),
        ("📊 CTR", f"{avg_ctr:.2f}%", "#4F86F7"),
        ("💵 CPC", f"₩{avg_cpc:,.0f}", "#0ea5e9"),
        ("🎯 ROAS", f"{roas:.2f}x", "#22c55e" if roas >= 1 else "#ef4444"),
    ]
    cols = st.columns(6)
    for col, (title, value, color) in zip(cols, kpi_items):
        with col:
            st.markdown(_kpi_card(title, value, color), unsafe_allow_html=True)

    st.markdown("")

    # ── 일별 지출 & 전환 추이 ──────────────────────────────────
    if not df_daily.empty:
        st.markdown("### 일별 광고 지출 & 구매 전환")
        daily_agg = df_daily.groupby("date").agg(
            spend=("spend", "sum"), purchases=("purchases", "sum")).reset_index()
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(
            go.Bar(x=daily_agg["date"], y=daily_agg["spend"], name="지출(원)",
                   marker_color="#f97316", opacity=0.8), secondary_y=False)
        fig.add_trace(
            go.Scatter(x=daily_agg["date"], y=daily_agg["purchases"], name="구매 전환",
                       line=dict(color="#6366f1", width=2.5), mode="lines+markers",
                       marker=dict(size=6)), secondary_y=True)
        fig.update_layout(hovermode="x unified", height=280,
                          legend=dict(orientation="h", y=1.12), **_CHART_BASE)
        fig.update_yaxes(title_text="지출 (원)", tickformat=",", gridcolor="#f0f0f0", secondary_y=False)
        fig.update_yaxes(title_text="구매 전환 수", secondary_y=True)
        st.plotly_chart(fig, use_container_width=True, key="meta_daily")

    st.divider()

    # ── 캠페인별 성과 테이블 ───────────────────────────────────
    st.markdown("### 캠페인별 성과")
    agg_cols = {c: "sum" for c in ["impressions", "reach", "clicks", "cpm", "spend", "purchases", "purchase_value"] if c in df_ads.columns}
    camp = df_ads.groupby("campaign").agg(agg_cols).reset_index()
    camp["CTR(%)"] = (camp["clicks"] / camp["impressions"] * 100).round(2)
    camp["ROAS"] = (camp["purchase_value"] / camp["spend"]).round(2)
    camp = camp.sort_values("spend", ascending=False)
    disp = camp.copy()
    for c in ["spend", "purchase_value"]:
        if c in disp.columns:
            disp[c] = disp[c].map(lambda x: f"₩{x:,.0f}")
    for c in ["impressions", "reach"]:
        if c in disp.columns:
            disp[c] = disp[c].map(lambda x: f"{x:,}")
    disp = disp.rename(columns={
        "campaign": "캠페인", "impressions": "노출", "reach": "도달",
        "clicks": "클릭", "cpm": "CPM(원)", "spend": "소진",
        "purchases": "구매", "purchase_value": "전환매출", "ROAS": "ROAS",
    })
    st.dataframe(disp, use_container_width=True, hide_index=True)

    st.divider()

    # ── 소재별 성과 — 주요(ROAS≥1) / 일반 분류 ───────────────
    st.markdown("### 소재별 성과")
    ad_df = df_ads[df_ads.get("ad", pd.Series(dtype=str)).ne("") if "ad" in df_ads.columns else df_ads.index.isin([])].copy() if "ad" in df_ads.columns else pd.DataFrame()
    if "ad" in df_ads.columns:
        ad_df = df_ads[df_ads["ad"].astype(str).str.strip() != ""].copy()
    if ad_df.empty:
        st.caption("소재 레벨 데이터 없음")
        return

    ad_df = ad_df.sort_values("roas", ascending=False)
    key_ads = ad_df[ad_df["roas"] >= 1]
    other_ads = ad_df[ad_df["roas"] < 1]

    # 주요 소재 배너
    c_key, c_other = st.columns(2)
    with c_key:
        st.markdown(
            f'<div style="background:#f0fdf4;border-radius:10px;padding:10px 16px;'
            f'border-left:4px solid #22c55e">'
            f'<strong style="color:#15803d">⭐ 주요 소재 (ROAS ≥ 1)</strong> — {len(key_ads)}개</div>',
            unsafe_allow_html=True)
    with c_other:
        st.markdown(
            f'<div style="background:#fef2f2;border-radius:10px;padding:10px 16px;'
            f'border-left:4px solid #ef4444">'
            f'<strong style="color:#991b1b">일반 소재 (ROAS &lt; 1)</strong> — {len(other_ads)}개</div>',
            unsafe_allow_html=True)

    st.markdown("")

    # 주요 소재 차트
    if not key_ads.empty:
        col1, col2 = st.columns(2)
        with col1:
            fig = go.Figure(go.Bar(
                y=key_ads["ad"].str[:22], x=key_ads["roas"], orientation="h",
                marker=dict(color="#22c55e", line=dict(width=0)),
                text=key_ads["roas"].apply(lambda x: f"{x:.2f}x"), textposition="outside",
            ))
            fig.update_layout(
                title="ROAS (주요 소재)", height=max(200, len(key_ads) * 40),
                yaxis=dict(autorange="reversed"), xaxis=dict(gridcolor="#f0f0f0"),
                **{k: v for k, v in _CHART_BASE.items() if k != "margin"},
                margin=dict(l=160, r=60, t=40, b=0),
            )
            st.plotly_chart(fig, use_container_width=True, key="meta_key_roas")
        with col2:
            fig = go.Figure(go.Bar(
                y=key_ads["ad"].str[:22], x=key_ads["ctr"], orientation="h",
                marker=dict(color="#4F86F7", line=dict(width=0)),
                text=key_ads["ctr"].apply(lambda x: f"{x:.2f}%"), textposition="outside",
            ))
            fig.update_layout(
                title="CTR (주요 소재)", height=max(200, len(key_ads) * 40),
                yaxis=dict(autorange="reversed"), xaxis=dict(gridcolor="#f0f0f0"),
                **{k: v for k, v in _CHART_BASE.items() if k != "margin"},
                margin=dict(l=160, r=60, t=40, b=0),
            )
            st.plotly_chart(fig, use_container_width=True, key="meta_key_ctr")

    # 소재 전체 테이블
    st.markdown("##### 소재별 전체 테이블")
    tbl_cols = [c for c in ["campaign", "ad", "impressions", "reach", "clicks", "ctr", "cpc", "cpm", "spend", "purchases", "purchase_value", "roas"] if c in ad_df.columns]
    tbl = ad_df[tbl_cols].copy()
    tbl["등급"] = tbl["roas"].apply(lambda x: "⭐ 주요" if x >= 1 else "일반")
    tbl = tbl.sort_values("roas", ascending=False)
    for c in ["spend", "purchase_value"]:
        if c in tbl.columns:
            tbl[c] = tbl[c].map(lambda x: f"₩{x:,.0f}")
    for c in ["impressions", "reach"]:
        if c in tbl.columns:
            tbl[c] = tbl[c].map(lambda x: f"{x:,}")
    tbl = tbl.rename(columns={
        "campaign": "캠페인", "ad": "소재명", "impressions": "노출", "reach": "도달",
        "clicks": "클릭", "ctr": "CTR(%)", "cpc": "CPC(원)", "cpm": "CPM(원)",
        "spend": "소진(원)", "purchases": "구매", "purchase_value": "전환매출(원)", "roas": "ROAS",
    })
    st.dataframe(tbl, use_container_width=True, hide_index=True)


# ── 헤더 ──────────────────────────────────────────────────────
st.markdown("# 📈 보뉴랩 운영 리포트")
st.caption(f"{start.strftime('%Y.%m.%d')} ~ {end.strftime('%Y.%m.%d')} | 이전 {period_days}일 대비")
st.divider()

if df_all.empty:
    st.warning("데이터가 없습니다. API 연결 상태를 확인하거나 날짜 범위를 조정하세요.")
    st.stop()


# ── 탭 ─────────────────────────────────────────────────────────
tab_summary, tab_pattern, tab_channel, tab_ads, tab_c24, tab_cpg = st.tabs([
    "📊 운영요약", "⏱ 패턴분석", "📡 채널·UTM", "📣 광고성과", "🛒 Cafe24", "🟡 쿠팡Wing",
])


# ── 운영요약 ───────────────────────────────────────────────────
with tab_summary:
    render_kpi_cards(df_all, df_prev)
    st.divider()

    col_left, col_right = st.columns([2, 1])
    with col_left:
        st.markdown("### 일별 매출 추이")
        render_daily(df_all, tab="sum")
    with col_right:
        st.markdown("### 결제 퍼널")
        render_funnel(df_c24, df_vis, tab="sum")

    st.divider()
    st.markdown("### 채널 현황")
    cpc1, cpc2 = st.columns([1, 2])
    with cpc1:
        ch_rev = df_all.groupby("channel")["actual_price"].sum().reset_index()
        fig_pie = go.Figure(go.Pie(
            labels=ch_rev["channel"], values=ch_rev["actual_price"],
            marker_colors=[CH_COLOR.get(c, "#888") for c in ch_rev["channel"]],
            hole=0.5, textinfo="label+percent",
        ))
        fig_pie.update_layout(height=220, margin=dict(l=0, r=0, t=0, b=0),
                               paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_pie, use_container_width=True, key="pie_summary")
    with cpc2:
        for ch, color in CH_COLOR.items():
            d = df_all[df_all["channel"] == ch]
            if d.empty:
                continue
            r = d["actual_price"].sum()
            n = len(d)
            a = r / n if n else 0
            st.markdown(
                f'<div style="border-left:4px solid {color};padding:10px 14px;margin-bottom:10px;'
                f'background:#fafafa;border-radius:0 8px 8px 0">'
                f'<strong>{ch}</strong>&nbsp;&nbsp;'
                f'매출 <strong>₩{r:,.0f}</strong>&nbsp;|&nbsp;'
                f'주문 <strong>{n:,}건</strong>&nbsp;|&nbsp;'
                f'객단가 <strong>₩{a:,.0f}</strong>'
                f'</div>',
                unsafe_allow_html=True,
            )


# ── 패턴분석 ───────────────────────────────────────────────────
with tab_pattern:
    st.markdown("### 주문 히트맵 (요일 × 시간대)")
    render_heatmap(df_all, tab="pat")
    st.markdown("### 시간대 · 요일 분석")
    render_hourly_dow(df_all, tab="pat")
    st.divider()
    st.markdown("### 트래픽 & 구매전환율 (Cafe24)")
    render_traffic(df_vis, tab="pat")


# ── 채널·UTM ───────────────────────────────────────────────────
with tab_channel:
    st.markdown("### UTM · 채널별 분석")
    st.caption("Cafe24 주문 데이터의 channel_type · from_place 기준")
    render_channel_utm(df_c24, tab="ch")


# ── 광고성과 ───────────────────────────────────────────────────
with tab_ads:
    render_meta_ads(df_meta_ads, df_meta_daily)


# ── Cafe24 ─────────────────────────────────────────────────────
with tab_c24:
    if df_c24.empty:
        st.warning("Cafe24 데이터가 없습니다.")
    else:
        render_kpi_cards(df_c24, prev_c24)
        st.divider()
        st.markdown("### 일별 매출")
        render_daily(df_c24, tab="c24")
        st.markdown("### 구매 집중 시간대")
        render_heatmap(df_c24, tab="c24")
        render_hourly_dow(df_c24, tab="c24")

        if "payment_method" in df_c24.columns:
            st.markdown("### 결제수단 비중")
            pm = df_c24["payment_method"].value_counts().reset_index()
            pm.columns = ["method", "count"]
            fig_pm = go.Figure(go.Pie(
                labels=pm["method"], values=pm["count"], hole=0.4, textinfo="label+percent"))
            fig_pm.update_layout(height=280, paper_bgcolor="rgba(0,0,0,0)",
                                  margin=dict(l=0, r=0, t=0, b=0))
            _, cm, _ = st.columns([1, 2, 1])
            with cm:
                st.plotly_chart(fig_pm, use_container_width=True, key="pie_c24")


# ── 쿠팡Wing ───────────────────────────────────────────────────
with tab_cpg:
    if df_cpg.empty:
        st.warning("쿠팡Wing 데이터가 없습니다.")
    else:
        render_kpi_cards(df_cpg, prev_cpg)
        st.divider()
        st.markdown("### 일별 매출")
        render_daily(df_cpg, tab="cpg")
        st.markdown("### 구매 집중 시간대")
        render_heatmap(df_cpg, tab="cpg")
        render_hourly_dow(df_cpg, tab="cpg")
        st.markdown("### 트래픽 & 구매전환율")
        render_traffic(df_vis, tab="cpg")
