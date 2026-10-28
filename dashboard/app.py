"""Phase 5c: proof of concept dashboard.

Run from the kb_mvp folder:
    streamlit run dashboard/app.py

Reads only the tables in output/tables, exactly like a SharePoint or Power BI
page would read SharePoint lists. This is a demo and testing tool, not the
final front end.
"""
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from kb.publish import TABLES  # noqa: E402
from kb.report import add_request, build_report, process_requests  # noqa: E402

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
  .pcard {{ min-height: 230px; }}
  h1, h2, h3 {{ color: {INK}; letter-spacing: -0.01em; }}
  .card {{ background: #fff; border-radius: 18px; padding: 20px 22px;
          box-shadow: 0 6px 24px rgba(28,28,58,0.06); border: 1px solid #ECEDF5; height: 100%; }}
  .kpi-label {{ color: {MUTED}; font-size: 0.8rem; text-transform: uppercase; letter-spacing: .06em; }}
  .kpi-value {{ color: {INK}; font-size: 2rem; font-weight: 700; line-height: 1.2; }}
  .pill {{ display: inline-block; padding: 3px 12px; border-radius: 999px; font-size: .78rem; font-weight: 600; }}
  .ptitle {{ color: {INK}; font-weight: 700; font-size: 1.05rem; margin: 10px 0 2px; }}
  .muted {{ color: {MUTED}; font-size: .85rem; }}
  .stat {{ display: inline-block; margin-right: 16px; color: {INK}; font-size: .9rem; }}
  .stat b {{ color: {ACCENT}; }}
  .change {{ background: #fff; border-radius: 14px; padding: 12px 16px; margin-bottom: 10px;
            border: 1px solid #ECEDF5; }}
  .tag {{ font-size: .72rem; font-weight: 600; color: {ACCENT}; background: #EEEEFC;
         border-radius: 999px; padding: 2px 10px; margin-right: 8px; }}
  .tag.minor {{ color: {MUTED}; background: #F0F1F6; }}
  .src {{ color: {MUTED}; font-size: .78rem; }}
  .stButton button, .stDownloadButton button {{ border-radius: 12px; }}
</style>""", unsafe_allow_html=True)


def pill(status):
    bg, fg = PILL.get(status, PILL["Unknown"])
    return f'<span class="pill" style="background:{bg};color:{fg}">{status}</span>'


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

# ---------------------------------------------------------------- header
snap, model = projects["Snapshot"].iloc[0], projects["Model"].iloc[0]
st.markdown(f"<div class='muted'>Forward Engineering · proof of concept</div>", unsafe_allow_html=True)
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
    col.markdown(f"""<div class='card pcard'>{pill(p['Status'])}
      <div class='ptitle'>{p['Title']}</div>
      <div class='muted'>{p['Purpose'] or '&nbsp;'}</div><br>
      <span class='stat'>Go live <b>{p['GoLive'] or 'n/a'}</b></span><br>
      <span class='stat'>Blockers <b>{p['OpenBlockers']}</b></span>
      <span class='stat'>Changes <b>{p['MeaningfulChanges']}</b></span>
      <span class='stat'>Conflicts <b>{p['Conflicts']}</b></span>
    </div>""", unsafe_allow_html=True)
st.write("")

# ---------------------------------------------------------------- what changed
left, right = st.columns([3, 2], gap="large")
with left:
    st.subheader("What changed")
    show_minor = st.toggle("Show minor edits", value=False)
    feed = changes if show_minor else changes[changes["Meaningful"]]
    title = dict(zip(projects["ProjectID"], projects["Title"]))
    if feed.empty:
        st.caption("No changes in this period.")
    for _, c in feed.iterrows():
        tag = "<span class='tag'>Meaningful</span>" if c["Meaningful"] else "<span class='tag minor'>Minor</span>"
        st.markdown(f"<div class='change'>{tag}<b>{title.get(c['ProjectID'], c['ProjectID'])}</b><br>"
                    f"{c['Summary']}<br><span class='src'>{c['SourceFile']}, {c['SourceLocation']}</span></div>",
                    unsafe_allow_html=True)

with right:
    st.subheader("Conflicts to resolve")
    if conflicts.empty:
        st.caption("No conflicts between documents.")
    for _, c in conflicts.iterrows():
        st.markdown(f"<div class='change'><span class='tag' style='color:#9A5B00;background:#FFF3DC'>Conflict</span>"
                    f"<b>{title.get(c['ProjectID'], c['ProjectID'])}</b><br>{c['Text']}</div>",
                    unsafe_allow_html=True)

st.divider()

# ---------------------------------------------------------------- project detail
st.subheader("Project detail")
pid = st.selectbox("Project", projects["ProjectID"], format_func=lambda x: title[x], label_visibility="collapsed")
p = projects[projects["ProjectID"] == pid].iloc[0]
st.markdown(f"{pill(p['Status'])} &nbsp; <span class='muted'>Go live {p['GoLive'] or 'n/a'} · "
            f"{p['UnsupportedClaims']} unsupported claims</span>", unsafe_allow_html=True)

tab_facts, tab_changes, tab_report = st.tabs(["Facts and sources", "Changes", "Status report"])
with tab_facts:
    pf = facts[facts["ProjectID"] == pid]
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
with tab_changes:
    pc = changes[changes["ProjectID"] == pid]
    if pc.empty:
        st.caption("No changes for this project.")
    for _, c in pc.iterrows():
        with st.expander(("Meaningful: " if c["Meaningful"] else "Minor: ") + c["Summary"]):
            st.markdown(f"**Before:** {c['OldText'] or '(did not exist)'}")
            st.markdown(f"**After:** {c['NewText'] or '(removed)'}")
            st.caption(f"{c['SourceFile']}, {c['SourceLocation']}")
with tab_report:
    st.caption("Builds a draft Word report with numbered sources. A person must review it before sharing.")
    who = st.text_input("Requested by", value="")
    if st.button("Generate report", type="primary"):
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
    if not requests.empty:
        st.markdown("**Report requests**")
        st.dataframe(requests[["RequestID", "ProjectID", "RequestedBy", "RequestedAt", "Status"]],
                     hide_index=True, width="stretch")
