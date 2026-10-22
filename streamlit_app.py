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

t0, t1, t2, t3, t4, t5 = st.tabs(["締め", "概要", "夜ごと", "今夜の候補", "ストップ高", "常駐"])

with t0:
    # 毎晩 18:07 に Discord へ飛ぶ要約(evening_digest)の、細かい中身。晩を選べる
    led = read_csv("ledger/ledger_v3.csv", dtype={"code": str})
    nights = sorted(done.date.unique(), reverse=True) if len(done) else []
    if not nights:
        st.info("まだ締めた晩が無い")
    else:
        night = st.selectbox("締めた晩", nights, index=0)
        x = done[done.date == night].set_index("variant")
        L = led[led.date == night] if len(led) else led
        lo = L[L.role == "long"] if len(L) else L
        # 金利の日数(受渡日どうし・両端入れ・土日込み)は台帳の金利から割り戻す
        days = None
        if len(lo):
            q = lo[(lo.variant == "A") & lo["約定した値段"].notna()]
            amt = (q.shares * q["約定した値段"]).sum()
            days = round(q["金利"].sum() / (amt * 0.028 / 365)) if amt else None
        st.subheader(f"{night} の晩" + (f"(金利{days}日)" if days else ""))
        order = ["A", "shadow_2516", "shadow_100", "shadow_lb90", "shadow_lb250", "shadow_175", "B"]
        rows = []
        for v in [v for v in order if v in x.index] + [v for v in x.index if v not in order]:
            r = x.loc[v]
            rows.append({"版": v, "元金比%": r.net_pct_equity, "差し引き": r.net_pnl, "株": r.long_pnl, "ヘッジ": r.hedge_pnl,
                         "コスト": r.costs, "本数": r.n_traded, "寄らず": r.n_stuck})
        if {"A", "shadow_2516"} <= set(x.index):
            rows.insert(2, {"版": "半々(1321+2516)", "元金比%": (x.loc["A"].net_pct_equity + x.loc["shadow_2516"].net_pct_equity) / 2,
                            "差し引き": (x.loc["A"].net_pnl + x.loc["shadow_2516"].net_pnl) / 2,
                            "株": x.loc["A"].long_pnl, "ヘッジ": (x.loc["A"].hedge_pnl + x.loc["shadow_2516"].hedge_pnl) / 2,
                            "コスト": (x.loc["A"].costs + x.loc["shadow_2516"].costs) / 2, "本数": x.loc["A"].n_traded, "寄らず": x.loc["A"].n_stuck})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                     column_config={"元金比%": st.column_config.NumberColumn(format="%+.3f"),
                                    "差し引き": st.column_config.NumberColumn(format="%+,.0f")})
        if len(L):
            h = L[L.role == "hedge"][["variant", "code", "shares", "約定した値段", "exit_price", "pnl_yen", "貸株料"]].copy()
            h["10口の倍数"] = h.shares % 10 == 0
            st.markdown("**ヘッジ**")
            st.dataframe(h.rename(columns={"variant": "版", "code": "銘柄", "shares": "口数", "約定した値段": "売り", "exit_price": "買い戻し", "pnl_yen": "損益"}),
                         hide_index=True, width="stretch")
            if (~h["10口の倍数"]).any():
                st.warning("10口の倍数やない口数がある(10/20 の晩は単位を直す前の記帳)")
            st.markdown("**本線の建玉**")
            a_ = lo[lo.variant == "A"][["rank", "code", "shares", "想定の値段", "約定した値段", "exit_price", "pnl_yen", "status", "金利", "日々公表", "外し損ねた決算の夜"]]
            st.dataframe(a_.sort_values("rank").rename(columns={"rank": "順位", "code": "コード", "shares": "株数", "約定した値段": "買い",
                                                                "exit_price": "売り", "pnl_yen": "損益", "status": "状態"}),
                         hide_index=True, width="stretch")
        st.divider()
        st.markdown("**15:35 の板読み(建てた日)**")
        meta = read_csv("ledger/capture_meta.csv", dtype=str)
        mm = meta[meta.date.str.startswith(str(night))] if len(meta) else meta
        if len(mm):
            for r in mm.itertuples():
                sk = r.skipped_codes if isinstance(r.skipped_codes, str) else ""
                why = " ".join(s.replace(":4002001", "(東証に無い)").replace(":4002006", "(登録の上限🚨)") for s in sk.split())
                st.write(f"{r.date}: 上位{r.n_ranking}本・境目{r.boundary_pct}% → S高引け {r.n_limit_close}本 / 飛ばし {why or 'なし'}")
        else:
            st.caption("その日の板読みの控えが無い")
        rec = read_csv("ledger/capture_reconcile.csv", dtype=str)
        rr = rec[rec.date == str(night)] if len(rec) else rec
        if len(rr):
            r = rr.iloc[-1]
            st.write(f"日足との突き合わせ: 板{r.n_capture}本 / 日足の上限引け{r.n_jq_limit_close}本 / 漏れ{r.n_missed}本 {'' if str(r.missed) == 'nan' else r.missed}")
        arr = pd.DataFrame(status.get("jq_arrival", []))
        if len(arr):
            aa = arr[arr.date >= str(night)].head(2)
            for _, r in aa.iterrows():
                st.write(f"J-Quants {r['date']} の当日分: " + (f"{str(r['arrived_at'])[11:16]}({r.get('try')}回目)"
                                                                if isinstance(r.get("arrived_at"), str) else "🚨 届かず"))

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
