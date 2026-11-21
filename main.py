# =====================================================================
# 🌱 우리 학교 극지식물 개체별 생육 차이 분석 대시보드 (main.py)
# - Streamlit Cloud에서 에러 없이 실행되는 코드
# - 인코딩(utf-8-sig/cp949) 자동 감지, 열 이름 표준화, 한글 폰트 적용
# =====================================================================

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import io

# ------------------------------------------------------------------------
# 한글 폰트 깨짐 방지 (Streamlit CSS)
# ------------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR&display=swap');
html, body, [class*="css"] {
   font-family: 'Noto Sans KR', 'Malgun Gothic', sans-serif;
}
</style>
""", unsafe_allow_html=True)

# 페이지 설정 (와이드 레이아웃)
st.set_page_config(page_title="극지식물 생육 차이 분석", page_icon="🌱", layout="wide")

# ------------------------------------------------------------------------
# CSV 읽기 함수: utf-8-sig → cp949 순서로 인코딩 자동 감지
# ------------------------------------------------------------------------
@st.cache_data
def read_csv(file):
    data = file.getvalue()
    for enc in ("utf-8-sig", "cp949"):
        try:
            return pd.read_csv(io.BytesIO(data), encoding=enc)
        except Exception:
            pass
    return pd.DataFrame()

# ------------------------------------------------------------------------
# 열 이름 표준화 함수 (학교마다 다른 열 이름을 표준 이름으로 변환)
# ------------------------------------------------------------------------
def std_cols(df):
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    rename = {}
    for c in df.columns:
        k = c.lower().replace(" ", "")
        if k in ("time", "categories", "시간", "날짜", "datetime", "date"):
            rename[c] = "time"
        elif k in ("temperature", "온도"):
            rename[c] = "temperature"
        elif k in ("humidity", "습도"):
            rename[c] = "humidity"
        elif k == "ph":
            rename[c] = "ph"
        elif k == "ec":
            rename[c] = "ec"
        elif "생중량" in k:
            rename[c] = "생중량"
        elif "잎" in k:
            rename[c] = "잎 수"
        elif "지상부" in k and "길이" in k:
            rename[c] = "지상부 길이"
        elif "지하부" in k and "길이" in k:
            rename[c] = "지하부 길이"
        elif "지상부" in k and ("질량" in k or "무게" in k):
            rename[c] = "지상부 질량"
        elif "지하부" in k and ("질량" in k or "무게" in k):
            rename[c] = "지하부 질량"
        elif "개체" in k:
            rename[c] = "개체번호"
    df = df.rename(columns=rename)

    # 숫자 열 정리 (단위·쉼표 제거 후 숫자로 변환)
    for c in df.columns:
        if c in ("time", "개체번호"):
            continue
        if not pd.api.types.is_numeric_dtype(df[c]):
            num = pd.to_numeric(
                df[c].astype(str).str.replace(",", "").str.extract(r"(-?\d+\.?\d*)")[0],
                errors="coerce"
            )
            if num.notna().mean() >= 0.5:
                df[c] = num

    # 생중량 열이 없으면 지상부 질량 + 지하부 질량으로 계산
    if "생중량" not in df.columns and {"지상부 질량", "지하부 질량"} <= set(df.columns):
        df["생중량"] = df["지상부 질량"] + df["지하부 질량"]

    # 시간 열 변환: '2026-07-15 06:00:00' 또는 '20260715_0'
    if "time" in df.columns:
        t = df["time"].astype(str).str.strip()
        parsed = pd.to_datetime(t, errors="coerce", format="mixed")
        bad = parsed.isna() & t.str.match(r"^\d{8}_\d{1,2}$")
        if bad.any():
            parts = t[bad].str.split("_", expand=True)
            parsed[bad] = pd.to_datetime(parts[0], format="%Y%m%d") + pd.to_timedelta(parts[1].astype(int), unit="h")
        df["time"] = parsed

    return df

# ------------------------------------------------------------------------
# 개체번호를 원래 값 그대로 표시하기 위한 보조 함수 (56.0 → 56)
# ------------------------------------------------------------------------
def fmt_id(val):
    try:
        f = float(val)
        if f.is_integer():
            return str(int(f))
    except (TypeError, ValueError):
        pass
    return str(val)

# ------------------------------------------------------------------------
# 안전한 평균 계산 (열이 없거나 값이 없으면 None)
# ------------------------------------------------------------------------
def safe_mean(df, col):
    if col not in df.columns:
        return None
    v = df[col].dropna()
    if len(v) == 0:
        return None
    return v.mean()

# ------------------------------------------------------------------------
# 사이드바 구성
# ------------------------------------------------------------------------
st.sidebar.title("📁 업로드")
env_file = st.sidebar.file_uploader("환경 데이터 CSV", type="csv")
growth_file = st.sidebar.file_uploader("생육 결과 데이터 CSV", type="csv")

st.sidebar.subheader("🌱 생육 측정 항목 선택")
growth_items = st.sidebar.multiselect(
    "개체별 비교에 사용할 항목",
    ["생중량", "잎 수", "지상부 길이", "지하부 길이"],
    default=["생중량"]
)
# 평균 생중량은 항상 표시
if "생중량" not in growth_items:
    growth_items = ["생중량"] + growth_items

# ------------------------------------------------------------------------
# 학교명 추출 (파일명 앞부분, 하드코딩 금지)
# ------------------------------------------------------------------------
school_name = ""
if env_file is not None:
    school_name = env_file.name.replace("_환경데이터.csv", "").replace(".csv", "")
elif growth_file is not None:
    school_name = growth_file.name.replace("_생육결과데이터.csv", "").replace(".csv", "")

# ------------------------------------------------------------------------
# CSV 로드 (한 번만 읽어 재사용)
# ------------------------------------------------------------------------
env_df = pd.DataFrame()
growth_df = pd.DataFrame()

if env_file is not None:
    with st.spinner("환경 데이터를 불러오는 중..."):
        env_df = read_csv(env_file)
        env_df = std_cols(env_df)

if growth_file is not None:
    with st.spinner("생육 데이터를 불러오는 중..."):
        growth_df = read_csv(growth_file)
        growth_df = std_cols(growth_df)

# =====================================================================
# 탭 구성
# =====================================================================
tab1, tab2, tab3 = st.tabs(["📖 실험 개요", "🌡️ 환경 데이터", "📊 생육 결과"])

# =====================================================================
# Tab 1: 실험 개요
# =====================================================================
with tab1:
    try:
        st.subheader("1. 연구 배경 및 목적")
        st.write("극지 식물은 낮은 온도와 짧은 생장기 등 극한 환경에서 자라기 때문에, 같은 스마트팜에서도 개체마다 생육 차이가 크게 나타날 수 있습니다. 이 대시보드는 우리 학교 극지식물 개체별 생육 차이를 한눈에 비교하여, 어떤 개체가 잘 자랐는지 탐색하는 데 도움을 줍니다.")

        st.subheader("2. 데이터 요약 표")
        rows = []
        if len(growth_df) > 0:
            rows.append(["개체 수", f"{len(growth_df)}개체"])
            t_valid = growth_df["time"].dropna()
            if len(t_valid) > 0:
                rows.append(["측정 기간", f"{t_valid.min().strftime('%Y-%m-%d')} ~ {t_valid.max().strftime('%Y-%m-%d')}"])
        else:
            rows.append(["개체 수", "0개체 (생육 데이터 미업로드)"])
        rows.append(["생육 측정 항목", "잎 수, 지상부 길이, 지하부 길이, 생중량"])
        if len(env_df) > 0:
            rows.append(["환경 측정 항목", "온도, 습도, pH, EC"])
        else:
            rows.append(["환경 측정 항목", "-"])
        rows.append(["학교명", school_name if school_name else "파일명 확인 필요"])
        summary_df = pd.DataFrame(rows, columns=["항목", "내용"])
        st.dataframe(summary_df, width="stretch")

        st.subheader("3. 주요 지표")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            if len(growth_df) > 0:
                st.metric("총 개체수", f"{len(growth_df)}개체")
            else:
                st.info("생육 데이터가 아직 없어 총 개체수를 표시할 수 없어요.")
        with c2:
            t_mean = safe_mean(env_df, "temperature")
            if t_mean is not None:
                st.metric("평균 온도", f"{t_mean:.2f} °C")
            else:
                st.info("온도 열이 없어 평균 온도를 표시할 수 없어요.")
        with c3:
            h_mean = safe_mean(env_df, "humidity")
            if h_mean is not None:
                st.metric("평균 습도", f"{h_mean:.2f} %")
            else:
                st.info("습도 열이 없어 평균 습도를 표시할 수 없어요.")
        with c4:
            g_mean = safe_mean(growth_df, "생중량")
            if g_mean is not None:
                st.metric("평균 생중량", f"{g_mean:.2f} g")
            else:
                st.info("생중량 열이 없어 평균 생중량을 표시할 수 없어요.")
    except Exception as e:
        st.warning(f"⚠️ 이 부분은 데이터 형식 때문에 표시하지 못했어요: {e}")

# =====================================================================
# Tab 2: 환경 데이터
# =====================================================================
with tab2:
    try:
        st.subheader("환경 데이터 요약 (평균·최소·최대)")
        if len(env_df) > 0:
            env_cols = [c for c in ["temperature", "humidity", "ph", "ec"] if c in env_df.columns]
            if len(env_cols) > 0:
                env_sum = env_df[env_cols].dropna().agg(["mean", "min", "max"])
                env_sum_df = env_sum.reset_index()
                env_sum_df.columns = ["항목", "평균", "최소", "최대"]
                st.dataframe(env_sum_df, width="stretch")
            else:
                st.info("환경 데이터에서 숫자 열(온도·습도·pH·EC)을 찾지 못했어요.")

            st.subheader("날짜별 시계열 (일별 평균)")
            if "time" in env_df.columns:
                t_valid = env_df["time"].dropna()
                if len(t_valid) > 0:
                    ts = env_df.dropna(subset=["time"]).copy()
                    ts["date"] = ts["time"].dt.date
                    daily_cols = [c for c in ["temperature", "humidity", "ph", "ec"] if c in ts.columns]
                    if len(daily_cols) > 0:
                        daily_avg = ts.groupby("date")[daily_cols].mean().reset_index()
                        daily_avg["time"] = pd.to_datetime(daily_avg["date"])
                        if "temperature" in daily_avg.columns:
                            fig = px.line(daily_avg, x="time", y="temperature", title="일별 평균 온도 변화")
                            fig.update_layout(xaxis_title="날짜", yaxis_title="온도 (°C)")
                            st.plotly_chart(fig, width="stretch")
                        if "humidity" in daily_avg.columns:
                            fig = px.line(daily_avg, x="time", y="humidity", title="일별 평균 습도 변화")
                            fig.update_layout(xaxis_title="날짜", yaxis_title="습도 (%)")
                            st.plotly_chart(fig, width="stretch")
                        if "ph" in daily_avg.columns:
                            fig = px.line(daily_avg, x="time", y="ph", title="일별 평균 pH 변화")
                            fig.update_layout(xaxis_title="날짜", yaxis_title="pH")
                            st.plotly_chart(fig, width="stretch")
                        if "ec" in daily_avg.columns:
                            fig = px.line(daily_avg, x="time", y="ec", title="일별 평균 EC 변화")
                            fig.update_layout(xaxis_title="날짜", yaxis_title="EC (mS/cm)")
                            st.plotly_chart(fig, width="stretch")
                    else:
                        st.info("환경 데이터에서 숫자 열을 찾지 못했어요.")
                else:
                    st.info("시간 열이 비어 있어 일별 평균을 계산할 수 없어요.")
            else:
                st.info("시간 열이 없어 일별 시계열을 그릴 수 없어요.")
        else:
            st.info("환경 데이터가 아직 업로드되지 않았어요. 사이드바에서 환경 CSV를 올려주세요.")
    except Exception as e:
        st.warning(f"⚠️ 이 부분은 데이터 형식 때문에 표시하지 못했어요: {e}")

# =====================================================================
# Tab 3: 생육 결과
# =====================================================================
with tab3:
    try:
        st.subheader("핵심 결과 카드")
        if len(growth_df) > 0:
            c1, c2, c3 = st.columns(3)
            with c1:
                g_valid = growth_df["생중량"].dropna()
                if len(g_valid) > 0:
                    st.metric("평균 생중량", f"{g_valid.mean():.2f} g")
                else:
                    st.info("생중량 열에 유효한 값이 없어요.")
            with c2:
                if "개체번호" in growth_df.columns:
                    max_idx = growth_df["생중량"].dropna().idxmax()
                    min_idx = growth_df["생중량"].dropna().idxmin()
                    st.metric("최대 생중량 개체", fmt_id(growth_df.loc[max_idx, "개체번호"]))
                    st.metric("최소 생중량 개체", fmt_id(growth_df.loc[min_idx, "개체번호"]))
                else:
                    st.info("개체번호 열이 없어 최대·최소 개체를 표시할 수 없어요.")
            with c3:
                st.metric("데이터 요약", f"생육 개체 {len(growth_df)}개")
        else:
            st.info("생육 데이터가 아직 업로드되지 않았어요. 사이드바에서 생육 CSV를 올려주세요.")

        st.subheader("개체별 생육 비교")
        if "개체번호" in growth_df.columns and len(growth_df) > 0:
            for item in growth_items:
                if item not in growth_df.columns:
                    st.info(f"'{item}' 열이 없어 비교할 수 없어요.")
                    continue
                per_ind = growth_df.groupby("개체번호", as_index=False)[item].mean()
                per_ind = per_ind.sort_values(item, ascending=False).reset_index(drop=True)
                n = len(per_ind)
                top3 = set(per_ind["개체번호"].head(3).tolist())
                bot3 = set(per_ind["개체번호"].tail(3).tolist())
                colors = []
                for _, r in per_ind.iterrows():
                    if r["개체번호"] in top3:
                        colors.append("green")
                    elif r["개체번호"] in bot3:
                        colors.append("red")
                    else:
                        colors.append("rgba(96,165,250,0.7)")
                fig = go.Figure(go.Bar(
                    x=per_ind["개체번호"].map(fmt_id),
                    y=per_ind[item],
                    marker_color=colors,
                    text=per_ind[item].round(2),
                    textposition="outside"
                ))
                unit = "g" if item == "생중량" else ("장" if item == "잎 수" else "mm")
                fig.update_layout(
                    title=f"개체별 평균 {item} ({n}개체, 상위 3개 녹색·하위 3개 빨간색)",
                    xaxis_title="개체",
                    yaxis_title=f"평균 {item} ({unit})"
                )
                st.plotly_chart(fig, width="stretch")
        else:
            st.info("개체번호 열이 없어 개체별 비교를 그릴 수 없어요.")

        st.subheader("생중량 요약 통계 (평균·표준편차·CV)")
        if "생중량" in growth_df.columns:
            g_valid = growth_df["생중량"].dropna()
            if len(g_valid) >= 1:
                stats_rows = []
                for col in ["생중량", "잎 수", "지상부 길이", "지하부 길이"]:
                    if col in growth_df.columns:
                        v = growth_df[col].dropna()
                        if len(v) >= 1:
                            cv = (v.std() / v.mean()) * 100 if v.mean() != 0 else 0
                            stats_rows.append([col, f"{v.mean():.2f}", f"{v.std():.2f}", f"{cv:.2f}"])
                if stats_rows:
                    stats_df = pd.DataFrame(stats_rows, columns=["항목", "평균", "표준편차", "CV(%)"])
                    st.dataframe(stats_df, width="stretch")
                else:
                    st.info("요약 통계를 계산할 값이 부족해요.")
            else:
                st.info("생중량 값이 없어요.")
        else:
            st.info("생중량 열이 없어요.")

        st.subheader("생중량 분포")
        if "생중량" in growth_df.columns:
            g_valid = growth_df["생중량"].dropna()
            if len(g_valid) >= 2:
                fig = px.box(growth_df, y="생중량", title="개체별 생중량 분포")
                fig.update_layout(yaxis_title="생중량 (g)")
                st.plotly_chart(fig, width="stretch")
            else:
                st.info("생중량 값이 2개 미만이라 분포를 그릴 수 없어요.")
        else:
            st.info("생중량 열이 없어 분포를 그릴 수 없어요.")

        st.subheader("상관관계 분석 (산점도 + 추세선)")
        corr_pairs = [
            ("잎 수", "생중량", "잎 수 (장)", "생중량 (g)"),
            ("지상부 길이", "생중량", "지상부 길이 (mm)", "생중량 (g)"),
        ]
        valid_pairs = []
        for x_item, y_item, x_label, y_label in corr_pairs:
            if x_item in growth_df.columns and y_item in growth_df.columns:
                valid = growth_df[[x_item, y_item]].dropna()
                if len(valid) >= 2:
                    valid_pairs.append((x_item, y_item, valid, x_label, y_label))
        if len(valid_pairs) >= 1:
            fig = make_subplots(
                rows=1, cols=len(valid_pairs),
                subplot_titles=[f"{x_item} vs {y_item}" for x_item, y_item, _, _, _ in valid_pairs]
            )
            for col, (x_item, y_item, valid, x_label, y_label) in enumerate(valid_pairs, start=1):
                x = valid[x_item].values
                y = valid[y_item].values
                slope, intercept = np.polyfit(x, y, 1)
                fig.add_trace(go.Scatter(x=x, y=y, mode="markers", name="개체", showlegend=False), row=1, col=col)
                fig.add_trace(go.Scatter(x=x, y=slope*x+intercept, mode="lines", name="추세선", showlegend=False), row=1, col=col)
                fig.update_yaxes(title_text=y_label, row=1, col=col)
                fig.update_xaxes(title_text=x_label, row=1, col=col)
            fig.update_layout(
                title="잎 수·지상부 길이와 생중량의 관계 (추세선은 np.polyfit으로 직접 계산)",
                height=450
            )
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("상관관계에 필요한 열이 없거나 값이 2개 미만이에요.")

        st.subheader("상위 25% vs 하위 25% 개체 비교")
        if "생중량" in growth_df.columns:
            g_valid = growth_df["생중량"].dropna()
            if len(g_valid) >= 4:
                q75 = g_valid.quantile(0.75)
                q25 = g_valid.quantile(0.25)
                top = growth_df.loc[g_valid[g_valid >= q75].index]
                bot = growth_df.loc[g_valid[g_valid <= q25].index]
                compare_cols = [c for c in ["잎 수", "지상부 길이", "지하부 길이", "생중량"] if c in growth_df.columns]
                rows = []
                for col in compare_cols:
                    t_val = top[col].mean()
                    b_val = bot[col].mean()
                    ratio = f"{t_val/b_val:.2f}" if b_val != 0 else "-"
                    rows.append([col, f"{t_val:.2f}", f"{b_val:.2f}", ratio])
                comp_df = pd.DataFrame(rows, columns=["항목", "상위 25% 평균", "하위 25% 평균", "비율(Top/Bottom)"])
                st.dataframe(comp_df, width="stretch")
            else:
                st.info("생중량 값이 4개 미만이라 상위·하위 25% 그룹을 나눌 수 없어요.")
        else:
            st.info("생중량 열이 없어 상위·하위 그룹 비교를 할 수 없어요.")

        st.subheader("원본 데이터")
        with st.expander("🌱 생육 데이터 원본 테이블"):
            if len(growth_df) > 0:
                st.dataframe(growth_df, width="stretch")
            else:
                st.info("생육 데이터가 아직 업로드되지 않았어요.")
        with st.expander("⬇️ 생육 데이터 CSV 다운로드"):
            if growth_file is not None:
                st.download_button(
                    label="생육 데이터 CSV 다운로드",
                    data=growth_df.to_csv(index=False).encode("utf-8-sig"),
                    file_name=growth_file.name,
                    mime="text/csv"
                )
    except Exception as e:
        st.warning(f"⚠️ 이 부분은 데이터 형식 때문에 표시하지 못했어요: {e}")

