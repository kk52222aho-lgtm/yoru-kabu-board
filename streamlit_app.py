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


def review(night, x, L, done, nm, days) -> str:
    """その晩の総評を、帳簿の数字から決まった言い回しで組む(人の判断や予想は入れん)。"""
    out = []
    if "A" not in x.index:
        return "本線の記帳が無い"
    A = x.loc["A"]
    lo = L[(L.role == "long") & (L.variant == "A") & L.exit_price.notna()].copy() if len(L) else L
    hd = L[(L.role == "hedge") & (L.variant == "A")] if len(L) else L
    if len(hd) and hd["約定した値段"].notna().all() and hd.exit_price.notna().all():
        m = (hd.exit_price.iloc[0] / hd["約定した値段"].iloc[0] - 1) * 100
        out.append(f"- **日経(1321)の夜は {m:+.2f}%**。" + ("相場は上げた夜" if m > 0.3 else "相場は下げた夜" if m < -0.3 else "相場はほぼ横ばいの夜")
                   + f"で、ヘッジの売りは ¥{A.hedge_pnl:+,.0f}。")
    if len(lo):
        lo["r"] = (lo.exit_price / lo["約定した値段"] - 1) * 100
        up, dn = int((lo.r > 0).sum()), int((lo.r < 0).sum())
        out.append(f"- **買った{len(lo)}本は 上げ{up}本・下げ{dn}本・変わらず{len(lo) - up - dn}本**、夜の動きの中央値 {lo.r.median():+.2f}%・平均 {lo.r.mean():+.2f}%。株の損益 ¥{A.long_pnl:+,.0f}。")
        b_ = lo.loc[lo.pnl_yen.idxmax()]; w_ = lo.loc[lo.pnl_yen.idxmin()]
        share = b_.pnl_yen / A.long_pnl * 100 if A.long_pnl > 0 else None
        out.append(f"- 稼ぎ頭は **{b_.code} {nm.get(str(b_.code)[:4], '')}**({b_.r:+.1f}%・¥{b_.pnl_yen:+,.0f}"
                   + (f"、株の儲けの{share:.0f}%" if share and share > 0 else "") + ")。"
                   + f"一番の負けは {w_.code} {nm.get(str(w_.code)[:4], '')}({w_.r:+.1f}%・¥{w_.pnl_yen:+,.0f})。")
        if share and share >= 50:
            out.append("- ⚠ **1本の大当たりで決まった晩**。同じ形で逆向きの晩も来る。")
    out.append(f"- コスト ¥{A.costs:,.0f}" + (f"(金利{days}日分" + ("。水曜は受渡が週末をまたいで4日" if days == 4 else "") + ")" if days else "") + "。")
    out.append(f"- **差し引き ¥{A.net_pnl:+,.0f}(元金比 {A.net_pct_equity:+.3f}%)**。合格の線 +0.05% の"
               + ("上" if A.net_pct_equity >= 0.05 else "下") + "。")
    if "shadow_2516" in x.index:
        s = x.loc["shadow_2516"]
        out.append(f"- ヘッジの比べ: 1321 {A.net_pct_equity:+.3f}% / 2516 {s.net_pct_equity:+.3f}% / 半々 {(A.net_pct_equity + s.net_pct_equity) / 2:+.3f}%。")
    notes = []
    if A.n_stuck and A.n_stuck > 0:
        notes.append(f"寄らずの建玉 {int(A.n_stuck)}本")
    if len(lo) and "外し損ねた決算の夜" in lo and (lo["外し損ねた決算の夜"] == 1).any():
        notes.append("外し損ねた決算の夜あり")
    if len(lo) and "日々公表" in lo and (lo["日々公表"] == 1).any():
        notes.append("日々公表の銘柄あり")
    if len(lo) and "その夜のTDnet開示の有無" in lo and (lo["その夜のTDnet開示の有無"] == 1).any():
        notes.append("引け後に開示があった銘柄あり")
    if notes:
        out.append("- 気をつける点: " + " / ".join(notes) + "。")
    a = done[(done.variant == "A") & (done.date <= night)]
    out.append(f"- 累計: {len(a)}/120晩・1晩平均 {a.net_pct_equity.mean():+.3f}%・元金 ¥{a.equity_end.iloc[-1]:,.0f}。"
               + ("数晩では何も言えん。120晩まで振り回されん。" if len(a) < 30 else ""))
    return chr(10).join(out)


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
        lv = read_csv("ledger/live_nightly.csv", dtype={"date": str})
        if len(lv):
            st.markdown("#### 💴 本番(実弾)")
            st.dataframe(lv.sort_values("date", ascending=False), hide_index=True, width="stretch",
                         column_config={"元金比%": st.column_config.NumberColumn(format="%+.3f"), "紙の半々%": st.column_config.NumberColumn(format="%+.3f"),
                                        "取りこぼし%": st.column_config.NumberColumn(format="%+.3f"), "差し引き": st.column_config.NumberColumn(format="%+,.0f"),
                                        "元金": st.column_config.NumberColumn(format="%,.0f")})
            st.caption("取りこぼし = 本番 − 紙の半々(本線 A と 2516 の影の平均)。株の約定のずれ = 本番の約定値と、紙の値段(引け・翌朝の寄り)の差")
        pb = read_csv("ledger/limitup_probe.csv", dtype={"code": str})
        if len(pb):
            st.markdown("#### 🧪 S高の試し")
            st.dataframe(pb.sort_values("date", ascending=False), hide_index=True, width="stretch")
        st.divider()
        night = st.selectbox("締めた晩(紙)", nights, index=0)
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
        names = read_csv("ledger/names.csv", dtype=str)
        nm = dict(zip(names.code, names.name)) if len(names) else {}
        st.markdown("#### 総評")
        st.markdown(review(night, x, L, done, nm, days))
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
            st.markdown("**本線の売買(買い=前の日の引け・売り=翌朝の寄り)**")
            a_ = lo[lo.variant == "A"].copy().sort_values("rank")
            a_["銘柄"] = a_.code.str[:4].map(nm).fillna("")
            a_["買った額"] = a_.shares * a_["約定した値段"]
            a_["売った額"] = a_.shares * a_.exit_price
            a_["損益%"] = (a_.exit_price / a_["約定した値段"] - 1) * 100
            show = a_[["rank", "code", "銘柄", "shares", "約定した値段", "exit_price", "買った額", "売った額", "損益%", "pnl_yen", "金利", "status"]]
            st.dataframe(show.rename(columns={"rank": "順位", "code": "コード", "shares": "株数", "約定した値段": "買値", "exit_price": "売値",
                                              "pnl_yen": "損益(円)", "status": "状態"}),
                         hide_index=True, width="stretch",
                         column_config={"買った額": st.column_config.NumberColumn(format="%,.0f"),
                                        "売った額": st.column_config.NumberColumn(format="%,.0f"),
                                        "損益%": st.column_config.NumberColumn(format="%+.2f"),
                                        "損益(円)": st.column_config.NumberColumn(format="%+,.0f"),
                                        "金利": st.column_config.NumberColumn(format="%.0f")})
            st.caption(f"合計: 買い ¥{a_['買った額'].sum():,.0f} → 売り ¥{a_['売った額'].sum():,.0f} / 株の損益 ¥{(a_['売った額'] - a_['買った額']).sum():+,.0f}"
                       f"(金利・手数料を引く前)。損益(円)は金利を引いた後")
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
