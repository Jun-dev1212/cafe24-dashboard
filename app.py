import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import date, timedelta

from cafe24_api import Cafe24API, process_orders as cafe24_process
from coupang_api import CoupangAPI, process_orders as coupang_process

st.set_page_config(
    page_title="보뉴랩 통합 매출 대시보드",
    page_icon="📊",
    layout="wide",
)

DOW_MAP = {0: "월", 1: "화", 2: "수", 3: "목", 4: "금", 5: "토", 6: "일"}
DOW_ORDER = ["월", "화", "수", "목", "금", "토", "일"]
CH_COLOR = {"Cafe24": "#4F86F7", "쿠팡": "#FF6B6B"}


# ── 비밀번호 ──────────────────────────────────────────────
def check_password() -> bool:
    if st.session_state.get("auth"):
        return True
    _, col, _ = st.columns([1, 1, 1])
    with col:
        st.markdown("## 📊 보뉴랩 대시보드")
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


# ── API 클라이언트 ─────────────────────────────────────────
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


# ── 데이터 로드 (5분 캐시) ────────────────────────────────
def load_cafe24(start: str, end: str) -> pd.DataFrame:
    cache_key = f"cafe24_{start}_{end}"
    if cache_key in st.session_state:
        return st.session_state[cache_key]
    try:
        api = get_cafe24()
        all_orders = []
        offset = 0
        while True:
            data = api._get("orders", {
                "start_date": start,
                "end_date": end,
                "shop_no": 1,
                "limit": 100,
                "offset": offset,
            })
            chunk = data.get("orders", [])
            all_orders.extend(chunk)
            if len(chunk) < 100:
                break
            offset += 100
        df = cafe24_process(all_orders)
        if not df.empty:
            df["channel"] = "Cafe24"
        st.session_state[cache_key] = df
        return df
    except Exception as e:
        st.error(f"Cafe24 API 오류: {e}")
        return pd.DataFrame()


def load_visitor_stats(start: str, end: str) -> pd.DataFrame:
    cache_key = f"vis_{start}_{end}"
    if cache_key in st.session_state:
        return st.session_state[cache_key]
    try:
        raw = get_cafe24()._get("reports/visitorsstatistics", {"start_date": start, "end_date": end})
        rows = raw.get("visitorsstatistics", [])
    except Exception:
        rows = []
    if not rows:
        st.session_state[cache_key] = pd.DataFrame()
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
    st.session_state[cache_key] = df
    return df


@st.cache_data(ttl=300, show_spinner=False)
def load_sales_report(start: str, end: str) -> pd.DataFrame:
    rows = get_cafe24().get_sales_report(start, end)
    if not rows:
        return pd.DataFrame()
    records = []
    for r in rows:
        try:
            records.append({
                "date": pd.to_datetime(r.get("date") or r.get("sale_date", "")),
                "revenue": float(r.get("total_sales_amount") or r.get("sales_amount", 0)),
                "orders": int(r.get("order_count") or r.get("total_orders", 0)),
            })
        except Exception:
            continue
    return pd.DataFrame(records)


@st.cache_data(ttl=300, show_spinner=False)
def load_coupang(start: str, end: str) -> pd.DataFrame:
    df = coupang_process(get_coupang().get_orders(start, end))
    if not df.empty:
        df["channel"] = "쿠팡"
    return df


# ── 사이드바 ──────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ 설정")
    period = st.selectbox("기간", ["최근 7일", "최근 30일", "최근 90일", "직접 입력"], index=1)
    today = date.today()

    if period == "최근 7일":
        start, end = today - timedelta(days=7), today
    elif period == "최근 30일":
        start, end = today - timedelta(days=30), today
    elif period == "최근 90일":
        start, end = today - timedelta(days=90), today
    else:
        start = st.date_input("시작일", today - timedelta(days=30))
        end = st.date_input("종료일", today)

    if st.button("🔄 새로고침", use_container_width=True):
        for k in list(st.session_state.keys()):
            if k.startswith("cafe24_") or k.startswith("cpg_"):
                del st.session_state[k]
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.caption("Cafe24 + 쿠팡Wing\n캐시: 5분")


# ── 데이터 로드 ───────────────────────────────────────────
s, e = start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

# API 연결 상태 테스트
with st.expander("🔧 API 연결 진단", expanded=True):
    try:
        api = get_cafe24()
        st.success(f"✅ Cafe24 토큰 갱신 성공 (access_token: {api.access_token[:10]}...)")
        import requests as _req
        _url = f"{api.base_url}/orders"
        _resp = _req.get(_url, headers=api._headers(), params={"start_date": s, "end_date": e, "shop_no": 1, "limit": 3})
        _data = _resp.json()
        _orders = _data.get("orders", [])
        if _orders:
            o = _orders[0]
            st.info(f"첫 주문 — payment_amount: {o.get('payment_amount')} | canceled: {o.get('canceled')} | shipping_status: {o.get('shipping_status')} | order_date: {o.get('order_date')}")
        else:
            st.warning(f"HTTP {_resp.status_code}: 주문 없음")

        # _get 직접 호출 (401 자동 재발급 포함)
        st.markdown("---")
        try:
            raw_resp = api._get("orders", {"start_date": s, "end_date": e, "shop_no": 1, "limit": 3})
            orders_in = raw_resp.get("orders", [])
            st.info(f"📦 _get 응답: {len(orders_in)}건 | 갱신 후 토큰: {api.access_token[:10]}...")
            st.info(f"응답 키: {list(raw_resp.keys())}")
            if orders_in:
                r0 = orders_in[0]
                st.success(f"첫 주문: payment_amount={r0.get('payment_amount')} | order_date={r0.get('order_date')}")
        except Exception as ex2:
            st.error(f"❌ _get 오류: {ex2}")
    except Exception as ex:
        st.error(f"❌ Cafe24 오류: {ex}")

with st.spinner("데이터 불러오는 중…"):
    df_c24 = load_cafe24(s, e)
    df_cpg = load_coupang(s, e)
    df_vis = load_visitor_stats(s, e)

_frames = [df for df in [df_c24, df_cpg] if not df.empty]
df_all = pd.concat(_frames, ignore_index=True) if _frames else pd.DataFrame()

period_days = max((end - start).days, 1)
ps = (start - timedelta(days=period_days)).strftime("%Y-%m-%d")
pe = (start - timedelta(days=1)).strftime("%Y-%m-%d")

with st.spinner("이전 기간 데이터 로드 중…"):
    prev_c24 = load_cafe24(ps, pe)
    prev_cpg = load_coupang(ps, pe)

_prev_frames = [df for df in [prev_c24, prev_cpg] if not df.empty]
df_prev = pd.concat(_prev_frames, ignore_index=True) if _prev_frames else pd.DataFrame()


# ── 공통 헬퍼 ─────────────────────────────────────────────
def kpi_delta(cur, prev):
    if prev and prev > 0:
        return f"{(cur - prev) / prev * 100:+.1f}%"
    return None


def render_kpi(df: pd.DataFrame, df_p: pd.DataFrame):
    rev = df["actual_price"].sum()
    n = len(df)
    aov = rev / n if n else 0
    prev_rev = df_p["actual_price"].sum() if not df_p.empty else 0
    prev_n = len(df_p) if not df_p.empty else 0
    prev_aov = prev_rev / prev_n if prev_n else 0

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("💰 총 매출", f"₩{rev:,.0f}", kpi_delta(rev, prev_rev))
    with c2:
        st.metric("📦 주문 건수", f"{n:,}건", kpi_delta(n, prev_n))
    with c3:
        st.metric("🧾 객단가", f"₩{aov:,.0f}", kpi_delta(aov, prev_aov))


def render_daily(df: pd.DataFrame, tab: str = ""):
    daily = (
        df.groupby(["order_date", "channel"])
        .agg(revenue=("actual_price", "sum"), orders=("order_id", "count"))
        .reset_index()
    )
    channels = daily["channel"].unique().tolist()
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    for ch in channels:
        d = daily[daily["channel"] == ch]
        fig.add_trace(
            go.Bar(x=d["order_date"], y=d["revenue"], name=f"{ch} 매출",
                   marker_color=CH_COLOR.get(ch, "#888"), opacity=0.8),
            secondary_y=False,
        )
        fig.add_trace(
            go.Scatter(x=d["order_date"], y=d["orders"], name=f"{ch} 주문수",
                       line=dict(color=CH_COLOR.get(ch, "#888"), width=2, dash="dot"),
                       mode="lines+markers"),
            secondary_y=True,
        )
    fig.update_layout(
        hovermode="x unified", height=300, barmode="stack",
        legend=dict(orientation="h", y=1.12),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=10, b=0),
    )
    fig.update_yaxes(title_text="매출 (원)", tickformat=",", secondary_y=False)
    fig.update_yaxes(title_text="주문 건수", secondary_y=True)
    st.plotly_chart(fig, use_container_width=True, key=f"daily_{tab}")


def render_hourly_dow(df: pd.DataFrame, tab: str = ""):
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("##### 시간대별 주문")
        hourly = (
            df.groupby("hour")["order_id"].count()
            .reindex(range(24), fill_value=0).reset_index()
        )
        hourly.columns = ["hour", "orders"]
        fig = go.Figure(go.Bar(
            x=hourly["hour"], y=hourly["orders"],
            marker=dict(color=hourly["orders"], colorscale="Blues", showscale=False),
            text=hourly["orders"], textposition="outside",
        ))
        fig.update_layout(
            xaxis=dict(title="시간", tickmode="linear", dtick=3),
            yaxis_title="건수", height=260,
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=0, r=0, t=10, b=0),
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
            marker_color=colors,
            text=dow["order_id"].round(1), textposition="outside",
        ))
        fig.update_layout(
            xaxis_title="요일", yaxis_title="평균 건수", height=260,
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=0, r=0, t=10, b=0),
        )
        st.plotly_chart(fig, use_container_width=True, key=f"dow_{tab}")


def render_heatmap(df: pd.DataFrame, tab: str = ""):
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
        colorscale="YlOrRd",
        text=pivot.values.astype(int),
        texttemplate="%{text}",
        showscale=True,
    ))
    fig.update_layout(
        height=250,
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=10, b=0),
    )
    st.plotly_chart(fig, use_container_width=True, key=f"heatmap_{tab}")


def render_traffic(df_vis: pd.DataFrame, tab: str = ""):
    if df_vis.empty:
        st.caption("접속통계 데이터 없음 (API 응답 대기 중)")
        return
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(x=df_vis["date"], y=df_vis["visitors"], name="방문자",
               marker_color="#A8C8F8", opacity=0.8),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(x=df_vis["date"], y=df_vis["conversion_rate"], name="구매전환율(%)",
                   line=dict(color="#FF6B6B", width=2.5), mode="lines+markers"),
        secondary_y=True,
    )
    fig.update_layout(
        hovermode="x unified", height=280, barmode="overlay",
        legend=dict(orientation="h", y=1.12),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=10, b=0),
    )
    fig.update_yaxes(title_text="방문자 수", secondary_y=False)
    fig.update_yaxes(title_text="전환율 (%)", secondary_y=True)
    st.plotly_chart(fig, use_container_width=True, key=f"traffic_{tab}")

    # 요약 지표
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("총 방문자", f"{df_vis['visitors'].sum():,}명")
    with c2:
        avg_cr = df_vis["conversion_rate"].mean()
        st.metric("평균 전환율", f"{avg_cr:.2f}%")
    with c3:
        st.metric("총 페이지뷰", f"{df_vis['pageviews'].sum():,}")


def render_prev_compare(df: pd.DataFrame, df_p: pd.DataFrame, tab: str = ""):
    if df_p.empty:
        return
    rev, n = df["actual_price"].sum(), len(df)
    prev_rev, prev_n = df_p["actual_price"].sum(), len(df_p)
    aov = rev / n if n else 0
    prev_aov = prev_rev / prev_n if prev_n else 0

    fig = make_subplots(rows=1, cols=3, subplot_titles=["총 매출 (원)", "주문 건수", "객단가 (원)"])
    for i, (cur, prv) in enumerate([(rev, prev_rev), (n, prev_n), (aov, prev_aov)], 1):
        for lbl, val, color in [("이번", cur, "#4F86F7"), ("이전", prv, "#D0D0D0")]:
            fig.add_trace(
                go.Bar(x=[lbl], y=[val], marker_color=color,
                       text=[f"{val:,.0f}"], textposition="outside",
                       showlegend=(i == 1), name=lbl),
                row=1, col=i,
            )
    fig.update_layout(
        height=260, barmode="group",
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=30, b=0),
    )
    st.plotly_chart(fig, use_container_width=True, key=f"compare_{tab}")


# ── 헤더 ──────────────────────────────────────────────────
st.markdown("# 📊 보뉴랩 통합 매출 대시보드")
st.caption(f"{start.strftime('%Y.%m.%d')} ~ {end.strftime('%Y.%m.%d')} | 전기간 대비")
st.divider()

if df_all.empty:
    st.warning("데이터가 없습니다. API 연결 상태를 확인하세요.")
    st.stop()


# ── 탭 ────────────────────────────────────────────────────
tab_all, tab_c24, tab_cpg = st.tabs(["🏠 전체 통합", "🛒 Cafe24", "🟡 쿠팡Wing"])


# ── [전체] 탭 ─────────────────────────────────────────────
with tab_all:
    render_kpi(df_all, df_prev)
    st.divider()

    # 채널 매출 비중 파이 + 채널별 KPI 나란히
    st.markdown("### 채널 비중")
    pc1, pc2 = st.columns([1, 2])
    with pc1:
        ch_rev = df_all.groupby("channel")["actual_price"].sum().reset_index()
        fig_pie = go.Figure(go.Pie(
            labels=ch_rev["channel"], values=ch_rev["actual_price"],
            marker_colors=[CH_COLOR.get(c, "#888") for c in ch_rev["channel"]],
            hole=0.45, textinfo="label+percent",
        ))
        fig_pie.update_layout(
            height=240, margin=dict(l=0, r=0, t=0, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig_pie, use_container_width=True, key="pie_all")

    with pc2:
        for ch, color in CH_COLOR.items():
            d = df_all[df_all["channel"] == ch]
            if d.empty:
                continue
            rev = d["actual_price"].sum()
            n = len(d)
            aov = rev / n if n else 0
            st.markdown(
                f"<div style='border-left:4px solid {color};padding:6px 12px;margin-bottom:8px'>"
                f"<b>{ch}</b> &nbsp; 매출 ₩{rev:,.0f} &nbsp;|&nbsp; 주문 {n:,}건 &nbsp;|&nbsp; 객단가 ₩{aov:,.0f}"
                f"</div>",
                unsafe_allow_html=True,
            )

    st.divider()
    st.markdown("### 일별 매출 추이 (채널 누적)")
    render_daily(df_all, tab="all")

    st.markdown("### 구매 집중 시간대")
    render_heatmap(df_all, tab="all")
    render_hourly_dow(df_all, tab="all")

    st.markdown("### 전기간 대비")
    render_prev_compare(df_all, df_prev, tab="all")

    st.divider()
    st.markdown("### 트래픽 & 구매전환율 (Cafe24 기준)")
    render_traffic(df_vis, tab="all")


# ── [Cafe24] 탭 ───────────────────────────────────────────
with tab_c24:
    if df_c24.empty:
        st.warning("Cafe24 데이터가 없습니다.")
    else:
        render_kpi(df_c24, prev_c24)
        st.divider()
        st.markdown("### 일별 매출")
        render_daily(df_c24, tab="c24")
        st.markdown("### 구매 집중 시간대")
        render_heatmap(df_c24, tab="c24")
        render_hourly_dow(df_c24, tab="c24")
        st.markdown("### 전기간 대비")
        render_prev_compare(df_c24, prev_c24, tab="c24")

        if "payment_method" in df_c24.columns:
            st.markdown("### 결제수단 비중")
            pm = df_c24["payment_method"].value_counts().reset_index()
            pm.columns = ["method", "count"]
            fig_pm = go.Figure(go.Pie(
                labels=pm["method"], values=pm["count"],
                hole=0.4, textinfo="label+percent",
            ))
            fig_pm.update_layout(height=280, paper_bgcolor="rgba(0,0,0,0)",
                                 margin=dict(l=0, r=0, t=0, b=0))
            _, cm, _ = st.columns([1, 2, 1])
            with cm:
                st.plotly_chart(fig_pm, use_container_width=True, key="pie_c24")


# ── [쿠팡Wing] 탭 ─────────────────────────────────────────
with tab_cpg:
    if df_cpg.empty:
        st.warning("쿠팡Wing 데이터가 없습니다.")
    else:
        render_kpi(df_cpg, prev_cpg)
        st.divider()
        st.markdown("### 일별 매출")
        render_daily(df_cpg, tab="cpg")
        st.markdown("### 구매 집중 시간대")
        render_heatmap(df_cpg, tab="cpg")
        render_hourly_dow(df_cpg, tab="cpg")
        st.markdown("### 전기간 대비")
        render_prev_compare(df_cpg, prev_cpg, tab="cpg")

        st.markdown("### 트래픽 & 구매전환율")
        render_traffic(df_vis, tab="cpg")
