"""Phase 5c: proof of concept dashboard.

Run from the kb_mvp folder:
    streamlit run dashboard/app.py

Reads only the tables in output/tables, exactly like a SharePoint or Power BI
page would read SharePoint lists. This is a demo and testing tool, not the
final front end.

Click a project card to open its overview right below the cards; click it
again (or Close) to hide it.
"""
import sys
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kb.publish import TABLES  # noqa: E402
from kb.report import add_request, process_requests  # noqa: E402

st.set_page_config(page_title="FE Project Knowledge Base", page_icon=":material/dashboard:", layout="wide")

# ---------------------------------------------------------------- look and feel
# Soft, airy card style: light canvas, white rounded cards, gentle shadows,
# one indigo accent and pastel status pills. Change the colors here only.
ACCENT, INK, MUTED, CANVAS = "#5B5BD6", "#1C1C3A", "#8A8AA3", "#F5F6FB"
PILL = {"On track": ("#E6F6EC", "#1F7A43"), "At risk": ("#FFF3DC", "#9A5B00"),
        "Off track": ("#FDE8E8", "#A61B1B"), "Paused": ("#EEF0F6", "#4A4F68"),
        "Unknown": ("#EEF0F6", "#4A4F68")}

st.markdown(f"""
<style>
  .stApp {{ background: {CANVAS}; }}
  .block-container {{ padding-top: 4.5rem; max-width: 1200px; }}
  h1, h2, h3 {{ color: {INK}; letter-spacing: -0.01em; }}
  .card {{ background: #fff; border-radius: 18px; padding: 20px 22px;
          box-shadow: 0 6px 24px rgba(28,28,58,0.06); border: 1px solid #ECEDF5; height: 100%; }}
  .pcard {{ min-height: 268px; transition: transform .15s ease, box-shadow .15s ease, border-color .15s ease; }}
  .pcard.selected {{ border: 2px solid {ACCENT}; box-shadow: 0 14px 34px rgba(91,91,214,.18); }}
  .open-hint {{ color: {ACCENT}; font-size: .82rem; font-weight: 600; margin-top: 14px; }}
  .kpi-label {{ color: {MUTED}; font-size: 0.78rem; text-transform: uppercase; letter-spacing: .06em; }}
  .kpi-value {{ color: {INK}; font-size: 2rem; font-weight: 700; line-height: 1.2; }}
  .kpi-value.small {{ font-size: 1.4rem; }}
  .pill {{ display: inline-block; padding: 3px 12px; border-radius: 999px; font-size: .78rem; font-weight: 600; }}
  .ptitle {{ color: {INK}; font-weight: 700; font-size: 1.05rem; margin: 10px 0 2px; }}
  .otitle {{ color: {INK}; font-weight: 700; font-size: 1.5rem; margin: 8px 0 2px; }}
  .muted {{ color: {MUTED}; font-size: .85rem; }}
  .stat {{ display: inline-block; margin-right: 16px; color: {INK}; font-size: .9rem; }}
  .stat b {{ color: {ACCENT}; }}
  .change {{ background: #fff; border-radius: 14px; padding: 12px 16px; margin-bottom: 10px;
            border: 1px solid #ECEDF5; }}
  .tag {{ font-size: .72rem; font-weight: 600; color: {ACCENT}; background: #EEEEFC;
         border-radius: 999px; padding: 2px 10px; margin-right: 8px; }}
  .tag.minor {{ color: {MUTED}; background: #F0F1F6; }}
  .tag.warn {{ color: #9A5B00; background: #FFF3DC; }}
  .src {{ color: {MUTED}; font-size: .76rem; }}
  .sec {{ color: {MUTED}; font-size: .74rem; font-weight: 700; text-transform: uppercase;
         letter-spacing: .07em; margin: 18px 0 8px; }}
  .item {{ padding: 8px 0; border-bottom: 1px solid #F0F1F6; color: {INK}; font-size: .92rem; }}
  .item:last-child {{ border-bottom: none; }}
  .flag {{ color: #A61B1B; font-size: .75rem; font-weight: 700; margin-left: 6px; }}
  .stButton button, .stDownloadButton button {{ border-radius: 12px; }}

  /* Whole project card is clickable: an invisible button is stretched over it. */
  [class*="st-key-card-"] {{ position: relative; gap: 0; }}
  [class*="st-key-card-"] [data-testid="stElementContainer"]:has(.stButton) {{
      position: absolute; inset: 0; z-index: 3; margin: 0; }}
  [class*="st-key-card-"] .stButton, [class*="st-key-card-"] .stButton button {{ width: 100%; height: 100%; }}
  [class*="st-key-card-"] .stButton button {{ opacity: 0; cursor: pointer; }}
  [class*="st-key-card-"]:hover .pcard {{ transform: translateY(-3px); box-shadow: 0 14px 34px rgba(28,28,58,.12); }}

  /* Overview panel under the cards */
  .st-key-overview {{ background: #fff; border-radius: 20px; padding: 26px 28px;
      border: 1px solid #ECEDF5; box-shadow: 0 10px 30px rgba(28,28,58,0.07); }}
  .st-key-overview .card {{ background: {CANVAS}; box-shadow: none; border: none; padding: 14px 16px; }}
</style>""", unsafe_allow_html=True)


def pill(status):
    bg, fg = PILL.get(status, PILL["Unknown"])
    return f'<span class="pill" style="background:{bg};color:{fg}">{escape(status)}</span>'


@st.cache_data(ttl=5)
def load(name):
    path = TABLES / f"{name}.csv"
    return pd.read_csv(path, keep_default_na=False) if path.exists() else pd.DataFrame()


projects, facts, changes, conflicts = (load(n) for n in ("Projects", "Facts", "Changes", "Conflicts"))
if projects.empty:
    st.title("FE Project Knowledge Base")
    st.info("No data yet. In the kb_mvp folder, run:  python -m kb.run")
    st.stop()

for df, col in ((changes, "Meaningful"), (facts, "Supported"), (changes, "NeedsReview")):
    if not df.empty:
        df[col] = df[col].astype(str) == "True"

# Most urgent first: off track, at risk, then the rest; ties by most changes.
SEVERITY = {"Off track": 0, "At risk": 1, "Paused": 2, "Unknown": 3, "On track": 4}
projects = (projects.assign(_sev=projects["Status"].map(SEVERITY).fillna(3))
            .sort_values(["_sev", "MeaningfulChanges"], ascending=[True, False])
            .drop(columns="_sev").reset_index(drop=True))
order = {pid: i for i, pid in enumerate(projects["ProjectID"])}
if not changes.empty:
    changes = changes.sort_values("ProjectID", key=lambda s: s.map(order), kind="stable")
title = dict(zip(projects["ProjectID"], projects["Title"]))


def toggle(pid):
    st.session_state["selected"] = None if st.session_state.get("selected") == pid else pid


def close():
    st.session_state["selected"] = None


selected = st.session_state.get("selected")
if selected not in title:
    selected = None

# ---------------------------------------------------------------- header
snap, model = projects["Snapshot"].iloc[0], projects["Model"].iloc[0]
st.markdown("<div class='muted'>Forward Engineering · proof of concept</div>", unsafe_allow_html=True)
st.title("Project Knowledge Base")
st.markdown(f"<div class='muted'>Snapshot <b>{snap}</b> · model <b>{model}</b> · "
            f"published {projects['PublishedAt'].iloc[0].replace('T', ' ')}</div>", unsafe_allow_html=True)
st.write("")

k = st.columns(5)
kpis = [("Projects", len(projects)),
        ("At risk", int((projects["Status"].isin(["At risk", "Off track"])).sum())),
        ("Open blockers", int(projects["OpenBlockers"].sum())),
        ("Meaningful changes", int(changes["Meaningful"].sum()) if not changes.empty else 0),
        ("Conflicts", int(projects["Conflicts"].sum()))]
for col, (label, value) in zip(k, kpis):
    col.markdown(f"<div class='card'><div class='kpi-label'>{label}</div>"
                 f"<div class='kpi-value'>{value}</div></div>", unsafe_allow_html=True)
st.write("")

# ---------------------------------------------------------------- project cards
st.subheader("Projects")
cols = st.columns(len(projects))
for col, (_, p) in zip(cols, projects.iterrows()):
    pid = p["ProjectID"]
    is_open = pid == selected
    with col, st.container(key=f"card-{pid}"):
        st.markdown(f"""<div class='card pcard{' selected' if is_open else ''}'>{pill(p['Status'])}
          <div class='ptitle'>{escape(p['Title'])}</div>
          <div class='muted'>{escape(p['Purpose']) or '&nbsp;'}</div><br>
          <span class='stat'>Go live <b>{escape(p['GoLive']) or 'n/a'}</b></span><br>
          <span class='stat'>Blockers <b>{p['OpenBlockers']}</b></span>
          <span class='stat'>Changes <b>{p['MeaningfulChanges']}</b></span>
          <span class='stat'>Conflicts <b>{p['Conflicts']}</b></span>
          <div class='open-hint'>{'Hide overview ↑' if is_open else 'View overview →'}</div>
        </div>""", unsafe_allow_html=True)
        st.button(f"Open {p['Title']}", key=f"open_{pid}", on_click=toggle, args=(pid,))
st.write("")


# ---------------------------------------------------------------- overview panel
def item_rows(rows, empty="None recorded."):
    if rows.empty:
        return f"<div class='item muted'>{empty}</div>"
    out = []
    for _, f in rows.iterrows():
        flag = "" if f["Supported"] else "<span class='flag'>NEEDS REVIEW</span>"
        out.append(f"<div class='item'>{escape(f['Text'])}{flag}<br>"
                   f"<span class='src'>{escape(f['SourceFile'])}, {escape(f['SourceLocation'])}</span></div>")
    return "".join(out)


def render_overview(pid):
    p = projects[projects["ProjectID"] == pid].iloc[0]
    pf = facts[facts["ProjectID"] == pid]
    pc = changes[changes["ProjectID"] == pid] if not changes.empty else changes
    pk = conflicts[conflicts["ProjectID"] == pid] if not conflicts.empty else conflicts

    with st.container(key="overview"):
        head, btn = st.columns([6, 1])
        head.markdown(f"{pill(p['Status'])}<div class='otitle'>{escape(p['Title'])}</div>"
                      f"<div class='muted'>{escape(p['Purpose'])}</div>", unsafe_allow_html=True)
        btn.button("Close", key="close_overview", on_click=close, width="stretch")

        m = st.columns(4)
        for c, (label, value) in zip(m, [("Go live", p["GoLive"] or "n/a"), ("Open blockers", p["OpenBlockers"]),
                                         ("Changes this period", p["MeaningfulChanges"]),
                                         ("Unsupported claims", p["UnsupportedClaims"])]):
            c.markdown(f"<div class='card'><div class='kpi-label'>{label}</div>"
                       f"<div class='kpi-value small'>{escape(str(value))}</div></div>", unsafe_allow_html=True)

        t_over, t_facts, t_changes, t_report = st.tabs(["Overview", "Facts and sources", "Changes", "Status report"])

        with t_over:
            left, right = st.columns([3, 2], gap="large")
            with left:
                for heading, cat in [("Decisions", "Decision"), ("Blockers", "Blocker"),
                                     ("Next steps", "Next step"), ("Risks", "Risk")]:
                    st.markdown(f"<div class='sec'>{heading}</div>{item_rows(pf[pf['Category'] == cat])}",
                                unsafe_allow_html=True)
            with right:
                st.markdown("<div class='sec'>What changed</div>", unsafe_allow_html=True)
                mc = pc[pc["Meaningful"]] if not pc.empty else pc
                if mc.empty:
                    st.caption("No meaningful changes this period.")
                for _, c in mc.iterrows():
                    st.markdown(f"<div class='change'><span class='tag'>{escape(c['Kind'].title())}</span>"
                                f"{escape(c['Summary'])}<br><span class='src'>{escape(c['SourceFile'])}, "
                                f"{escape(c['SourceLocation'])}</span></div>", unsafe_allow_html=True)
                st.markdown("<div class='sec'>Conflicts to resolve</div>", unsafe_allow_html=True)
                if pk.empty:
                    st.caption("No conflicts between documents.")
                for _, c in pk.iterrows():
                    st.markdown(f"<div class='change'><span class='tag warn'>Conflict</span>{escape(c['Text'])}"
                                f"<br><span class='src'>{escape(c['SourceFiles'])}</span></div>",
                                unsafe_allow_html=True)

        with t_facts:
            for cat in ["Decision", "Blocker", "Next step", "Risk"]:
                rows = pf[pf["Category"] == cat]
                st.markdown(f"**{cat}s**" if cat != "Next step" else "**Next steps**")
                if rows.empty:
                    st.caption("None recorded.")
                for _, f in rows.iterrows():
                    label = f["Text"] + ("" if f["Supported"] else "  ·  needs review")
                    with st.expander(label):
                        st.markdown(f"**Source:** {f['SourceFile']}, {f['SourceLocation']}")
                        st.markdown(f"> {f['Evidence']}")
                        if f["Issues"]:
                            st.error(f["Issues"])

        with t_changes:
            if pc.empty:
                st.caption("No changes for this project.")
            for _, c in pc.iterrows():
                with st.expander(("Meaningful: " if c["Meaningful"] else "Minor: ") + c["Summary"]):
                    st.markdown(f"**Before:** {c['OldText'] or '(did not exist)'}")
                    st.markdown(f"**After:** {c['NewText'] or '(removed)'}")
                    st.caption(f"{c['SourceFile']}, {c['SourceLocation']}")

        with t_report:
            st.caption("Builds a draft Word report with numbered sources. A person must review it before sharing.")
            who = st.text_input("Requested by", value="", key="requested_by")
            if st.button("Generate report", type="primary", key="gen_report"):
                add_request(pid, who)
                done = process_requests()
                st.session_state["last_report"] = next((r for r in done if r["ProjectID"] == pid), None)
            r = st.session_state.get("last_report")
            if r and r["ProjectID"] == pid and r["Status"] == "Ready":
                path = ROOT / r["ReportFile"]
                st.success(f"Draft ready: {path.name}")
                st.download_button("Download draft (.docx)", path.read_bytes(), file_name=path.name,
                                   mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            requests = load("ReportRequests")
            mine = requests[requests["ProjectID"] == pid] if not requests.empty else requests
            if not mine.empty:
                st.markdown("**Report requests for this project**")
                st.dataframe(mine[["RequestID", "RequestedBy", "RequestedAt", "Status"]],
                             hide_index=True, width="stretch")


if selected:
    render_overview(selected)
else:
    st.caption("Click a project card to open its overview here.")
st.write("")

# ---------------------------------------------------------------- what changed, all projects
left, right = st.columns([3, 2], gap="large")
with left:
    st.subheader("What changed")
    show_minor = st.toggle("Show minor edits", value=False)
    feed = changes if show_minor else changes[changes["Meaningful"]]
    if feed.empty:
        st.caption("No changes in this period.")
    for _, c in feed.iterrows():
        tag = "<span class='tag'>Meaningful</span>" if c["Meaningful"] else "<span class='tag minor'>Minor</span>"
        st.markdown(f"<div class='change'>{tag}<b>{escape(title.get(c['ProjectID'], c['ProjectID']))}</b><br>"
                    f"{escape(c['Summary'])}<br><span class='src'>{escape(c['SourceFile'])}, "
                    f"{escape(c['SourceLocation'])}</span></div>", unsafe_allow_html=True)

with right:
    st.subheader("Conflicts to resolve")
    if conflicts.empty:
        st.caption("No conflicts between documents.")
    for _, c in conflicts.iterrows():
        st.markdown(f"<div class='change'><span class='tag warn'>Conflict</span>"
                    f"<b>{escape(title.get(c['ProjectID'], c['ProjectID']))}</b><br>{escape(c['Text'])}</div>",
                    unsafe_allow_html=True)
