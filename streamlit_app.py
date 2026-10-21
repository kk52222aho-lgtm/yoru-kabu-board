"""yoru-kabu の盤(携帯で見る用)。このリポは公開で、表を描くコードだけ。

台帳の中身は非公開の kk52222aho-lgtm/yoru-kabu から、読み取り専用の鍵(Fine-grained token、Contents: Read-only、
yoru-kabu だけ)で取りに行く。合言葉と鍵は Streamlit の secrets:
    APP_PASSWORD = "..."
    GH_TOKEN = "github_pat_..."
"""
import hmac
import io
import json

import pandas as pd
import requests
import streamlit as st

REPO, REF = "kk52222aho-lgtm/yoru-kabu", "master"
API = f"https://api.github.com/repos/{REPO}/contents"
st.set_page_config(page_title="夜株の盤", page_icon="🌙", layout="centered")


def _h(raw=True):
    return {"Authorization": f"Bearer {st.secrets.get('GH_TOKEN', '')}",
            "Accept": "application/vnd.github.raw" if raw else "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"}


@st.cache_data(ttl=600, show_spinner=False)
def fetch(path: str):
    r = requests.get(f"{API}/{path}", params={"ref": REF}, headers=_h(), timeout=20)
    return r.text if r.status_code == 200 else None


@st.cache_data(ttl=600, show_spinner=False)
def listdir(path: str):
    r = requests.get(f"{API}/{path}", params={"ref": REF}, headers=_h(raw=False), timeout=20)
    return sorted(x["name"] for x in r.json()) if r.status_code == 200 else []


def gate() -> bool:
    if st.session_state.get("ok"):
        return True
    want = st.secrets.get("APP_PASSWORD", "")
    pw = st.text_input("合言葉", type="password")
    if pw and want and hmac.compare_digest(pw, want):
        st.session_state.ok = True
        st.rerun()
    elif pw:
        st.error("ちがう")
    return False


def read_csv(path, **kw):
    t = fetch(path)
    try:
        return pd.read_csv(io.StringIO(t), **kw) if t else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


if not gate():
    st.stop()

nightly = read_csv("ledger/nightly_v3.csv")
_s = fetch("ledger/status.json")
status = json.loads(_s) if _s else {}
if not _s and fetch("README.md") is None:
    st.error("台帳が読めん(GH_TOKEN が無いか、鍵の権限/期限を確かめる)")
done = nightly[nightly.get("complete", pd.Series(dtype=int)) == 1] if len(nightly) else nightly

st.title("🌙 夜株の盤")
st.caption(f"更新: {status.get('generated_at', '—')}(読み込みは10分おき)")

t1, t2, t3, t4, t5 = st.tabs(["概要", "夜ごと", "今夜の候補", "ストップ高", "常駐"])

with t1:
    a = done[done.variant == "A"] if len(done) else done
    n = len(a)
    c1, c2, c3 = st.columns(3)
    c1.metric("記帳した晩", f"{n} / 120")
    c2.metric("本線 1晩平均", f"{a.net_pct_equity.mean():+.3f}%" if n else "—")
    c3.metric("本線 元金", f"¥{a.equity_end.iloc[-1]:,.0f}" if n else "—")
    st.caption("合格の線は1晩+0.05%(1.5倍・コスト込み)。判定は120晩たってから。5年の推定は+0.074〜+0.158%(1倍・ヘッジあり)")
    if len(done):
        eq = done.pivot_table(index="date", columns="variant", values="equity_end")
        st.line_chart(eq)
        last = done[done.date == done.date.max()][["variant", "n_traded", "long_pnl", "hedge_pnl", "costs", "net_pnl", "net_pct_equity"]]
        st.subheader(f"直近の晩 {done.date.max()}")
        st.dataframe(last.rename(columns={"variant": "版", "n_traded": "本数", "long_pnl": "株", "hedge_pnl": "ヘッジ",
                                          "costs": "コスト", "net_pnl": "差し引き", "net_pct_equity": "元金比%"}),
                     hide_index=True, width="stretch")
    else:
        st.info("まだ記帳が無い")

with t2:
    if len(nightly):
        v = st.selectbox("版", sorted(nightly.variant.unique()), index=0)
        x = nightly[nightly.variant == v].sort_values("date", ascending=False)
        st.dataframe(x[["date", "n_traded", "n_stuck", "long_pnl", "hedge_pnl", "costs", "net_pnl", "net_pct_equity", "equity_end", "complete"]]
                     .rename(columns={"date": "晩", "n_traded": "本数", "n_stuck": "寄らず", "long_pnl": "株", "hedge_pnl": "ヘッジ",
                                      "costs": "コスト", "net_pnl": "差し引き", "net_pct_equity": "元金比%", "equity_end": "元金", "complete": "締め"}),
                     hide_index=True, width="stretch")

with t3:
    picks = [n for n in listdir("ledger/picks") if n.endswith(".csv")]
    if picks:
        p = read_csv(f"ledger/picks/{picks[-1]}", dtype={"code": str})
        st.subheader(f"{picks[-1][:-4]} の候補")
        a = p[p.budget_variant == "A"].copy()
        a["額"] = a.planned_shares * a.planned_price_1525
        st.metric("本線の本数 / 額", f"{len(a)}本 / ¥{a.額.sum():,.0f}")
        st.dataframe(a[["rank", "code", "planned_shares", "planned_price_1525", "額"]]
                     .rename(columns={"rank": "順位", "code": "コード", "planned_shares": "株数", "planned_price_1525": "想定の値段"}),
                     hide_index=True, width="stretch")

with t4:
    tk = read_csv("ledger/limit_up_tickets.csv", dtype={"code": str})
    st.subheader("候補のうちS高に触れた建玉")
    st.dataframe(tk.tail(50), hide_index=True, width="stretch") if len(tk) else st.caption("まだ無い")
    cp = read_csv("ledger/limit_close_capture.csv", dtype={"code": str})
    st.subheader("15:35 の板(全S高引け)")
    if len(cp):
        st.dataframe(cp[["date", "code", "name", "CurrentPrice", "四値同じ", "CurrentPriceChangeStatus", "BidSign", "AskSign", "captured_at"]].tail(80),
                     hide_index=True, width="stretch")
    else:
        st.caption("まだ無い")

with t5:
    st.subheader("死活の点検(最新の回)")
    hl = status.get("health", [])
    last_when = hl[-1].rsplit("(", 1)[-1] if hl else ""
    for line in [x for x in hl if x.endswith(last_when)]:
        (st.error if line.startswith("FAIL") else st.warning if line.startswith("WARN") else st.success)(line)
    with st.expander("前の回"):
        for line in [x for x in hl if not x.endswith(last_when)][-20:]:
            st.caption(line)
    st.subheader("J-Quants の当日分が届いた時刻")
    arr = pd.DataFrame(status.get("jq_arrival", []))
    st.dataframe(arr.tail(15), hide_index=True, width="stretch") if len(arr) else st.caption("まだ無い")
    st.subheader("15:35 の漏れ")
    rec = read_csv("ledger/capture_reconcile.csv")
    st.dataframe(rec.tail(15), hide_index=True, width="stretch") if len(rec) else st.caption("まだ無い")
    st.subheader("常駐の前回の結果")
    jobs = pd.DataFrame(status.get("jobs", []))
    st.dataframe(jobs, hide_index=True, width="stretch") if len(jobs) else st.caption("まだ無い")
