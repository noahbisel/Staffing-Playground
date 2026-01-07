import streamlit as st
import pandas as pd
import plotly.express as px
import os
import utils

# --- 1. APP CONFIGURATION ---
st.set_page_config(page_title="Staffing Sandbox v2.0", layout="wide", page_icon="👥")
DEFAULT_DATA_FILE = 'staffing_db.csv'

# --- 2. INIT & LOAD ---
if 'program_mrr' not in st.session_state: st.session_state.program_mrr = {}
if 'undo_stack' not in st.session_state: st.session_state.undo_stack = []
if 'future_map' not in st.session_state: st.session_state.future_map = {} # <--- New State

if 'df' not in st.session_state:
    if os.path.exists(DEFAULT_DATA_FILE):
        try:
            df = pd.read_csv(DEFAULT_DATA_FILE)
            # Try to process with new logic if columns exist
            # Note: For default file load, we might not have date columns, so it handles gracefully
            processed_df, new_mrr, f_map = utils.process_uploaded_file(open(DEFAULT_DATA_FILE, 'r'))
            
            if not processed_df.empty:
                st.session_state.df = utils.recalculate_utilization(processed_df.set_index('Employee'))
                st.session_state.program_mrr = new_mrr
                st.session_state.future_map = f_map
            else:
                # Fallback if process fails
                st.session_state.df = pd.DataFrame()
        except: st.session_state.df = pd.DataFrame()
    else:
        # Fallback Mock Data
        cap = utils.STANDARD_CAPACITY
        data = {
            'Employee': ['Mitch Ursick', 'Noah Bisel', 'Kevin Steger', 'Nicki Williams', 'R+I I (Placeholder)'],
            'Role': ['CSM', 'CE', 'CP', 'CE', 'R+I I'],
            'Capacity': [cap, cap, cap, cap, cap],
            'Accenture': [10, 80, 20, 0, 0],
            'Google': [60, 20, 60, 15, 40]
        }
        st.session_state.program_mrr = {'Accenture': 15000, 'Google': 25000}
        df = pd.DataFrame(data).set_index('Employee')
        st.session_state.df = utils.recalculate_utilization(df)

# --- 3. GLOBAL VARIABLES ---
df = st.session_state.df
prog_cols = []
margin_metrics = {}

if not df.empty:
    numeric_cols = df.select_dtypes(include=['number']).columns
    exclude_cols = ['Capacity', 'Current Hours to Target']
    prog_cols = [c for c in numeric_cols if c not in exclude_cols]
    # Pass the future_map to margin calculation
    margin_metrics = utils.calculate_margin(df, st.session_state.program_mrr, st.session_state.future_map)

def render_employee_card(name, row):
    util = row.get('Current Hours to Target', 0)
    role = row.get('Role', 'N/A')
    color = "green"
    if util > 100: color = "red"
    elif util < 80: color = "orange"
    with st.container(border=True):
        c_head, c_badge = st.columns([3, 1])
        c_head.markdown(f"**{name}**")
        c_head.caption(role)
        c_badge.markdown(f":{color}[**{util}%**]")
        st.progress(min(util, 100) / 100)

def push_to_history():
    st.session_state.undo_stack.append(st.session_state.df.copy())
    if len(st.session_state.undo_stack) > 10: st.session_state.undo_stack.pop(0)

def undo_last_change():
    if st.session_state.undo_stack:
        prev_df = st.session_state.undo_stack.pop()
        st.session_state.df = prev_df
        st.toast("Undid last change", icon="↩️")

# --- 4. NAVIGATION ---
st.sidebar.title("Staffing Sandbox")
page = st.sidebar.radio("Navigate", ["📊 Dashboard", "✏️ Staffing Editor", "⚙️ Settings"], label_visibility="collapsed")
st.sidebar.markdown("---")

# --- DASHBOARD ---
if page == "📊 Dashboard":
    st.title("📊 Executive Dashboard")

    if not df.empty:
        # Metrics
        team_util, team_alloc, team_cap = utils.calculate_group_utilization(df, utils.TEAM_ROLES)
        acp_util, acp_alloc, acp_cap = utils.calculate_group_utilization(df, ['ACP'])
        cp_util, cp_alloc, cp_cap = utils.calculate_group_utilization(df, ['CP', 'SCP', 'LCP'])
        ce_util, ce_alloc, ce_cap = utils.calculate_group_utilization(df, ['ACE', 'CE', 'SCE'])

        m1, m2, m3, m4 = st.columns(4)
        with m1:
            with st.container(border=True):
                st.metric("Team Avg Utilization", f"{team_util:.0f}%", delta=f"{team_util-100:.0f}%" if team_util > 100 else None)
                st.caption(f"**Allocated:** {int(team_alloc)} hrs  \n**Capacity:** {int(team_cap)} hrs")
        with m2: st.metric("ACP Utilization", f"{acp_util:.0f}%")
        with m3: st.metric("CP/SCP/LCP Utilization", f"{cp_util:.0f}%")
        with m4: st.metric("ACE/CE/SCE Util", f"{ce_util:.0f}%")

        st.divider()
        col_l, col_r = st.columns(2)
        
        # --- LEFT: PROGRAMS (Projected Margin) ---
        with col_l:
            st.write("")
            st.write("")
            st.write("")
            st.subheader("Allocations by Program")
            
            program_analysis_df = df.copy() 
            if prog_cols:
                # Re-run calc on full data
                dynamic_margin = utils.calculate_margin(program_analysis_df, st.session_state.program_mrr, st.session_state.future_map)
                
                master_data = []
                for p in prog_cols:
                    p_hours = program_analysis_df[p].sum() if p in program_analysis_df.columns else 0
                    if p_hours > 0:
                        m_data = dynamic_margin.get(p, {})
                        mrr_val = m_data.get('mrr', 0)
                        cur_marg = m_data.get('margin_pct', 0)
                        fut_marg = m_data.get('margin_fut', 0)
                        delta = m_data.get('delta', 0)
                        
                        # Formatting Trend
                        arrow = "→"
                        if delta > 1: arrow = "↗"
                        elif delta < -1: arrow = "↘"
                        
                        master_data.append({
                            "Program Name": p,
                            "Program MRR": f"${mrr_val:,.0f}", 
                            "Total Hours": int(p_hours),
                            "Contributing Margin": cur_marg,
                            "Proj. Margin": f"{fut_marg:.1f}% {arrow}" # <--- NEW VISUAL
                        })
                
                master_df = pd.DataFrame(master_data)
                if not master_df.empty:
                    master_df = master_df.sort_values("Contributing Margin", ascending=False)
                    st.dataframe(
                        master_df,
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "Program Name": st.column_config.TextColumn("Program Name"),
                            "Program MRR": st.column_config.TextColumn("Program MRR"),
                            "Total Hours": st.column_config.NumberColumn("Total Hours", format="%d"),
                            "Contributing Margin": st.column_config.NumberColumn("Contributing Margin", format="%.1f%%"),
                            "Proj. Margin": st.column_config.TextColumn("Proj. Margin (30d)")
                        }
                    )
                else: st.info("No active programs found.")

        # --- RIGHT: EMPLOYEES (Status Flags) ---
        with col_r:
            tg1, tg2 = st.columns(2)
            include_ri = tg1.toggle("Include R+I Roles?", value=True)
            include_csm = tg2.toggle("Include CSM Roles?", value=True)
            
            st.subheader("Allocations by Employee")
            
            emp_view_df = df.copy()
            if 'Role' in emp_view_df.columns:
                if not include_ri:
                    mask = ~emp_view_df['Role'].astype(str).str.upper().str.startswith("R+I")
                    emp_view_df = emp_view_df[mask]
                if not include_csm:
                    mask = emp_view_df['Role'].astype(str).str.upper() != "CSM"
                    emp_view_df = emp_view_df[mask]

            # Build Table with Status
            table_rows = []
            for emp, row in emp_view_df.iterrows():
                util = row['Current Hours to Target']
                
                # Check status across all programs for this emp
                # We aggregate status messages. If ANY program has a "Rolling off" status, we flag it.
                status_list = []
                for p in prog_cols:
                    f_data = st.session_state.future_map.get((emp, p))
                    if f_data and f_data['status'] != "Stable":
                        status_list.append(f_data['status'])
                
                display_status = "Stable"
                if status_list:
                    # Just show the first one for brevity in table, or "Multiple"
                    display_status = status_list[0]
                    if len(status_list) > 1: display_status += " (+)"

                table_rows.append({
                    "Employee": emp,
                    "Utilization": util,
                    "Status / Changes": display_status
                })
            
            emp_table_df = pd.DataFrame(table_rows).sort_values('Utilization', ascending=False)
            
            st.dataframe(
                emp_table_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Employee": st.column_config.TextColumn("Employee"),
                    "Utilization": st.column_config.ProgressColumn("Utilization %", format="%d%%", min_value=0, max_value=100),
                    "Status / Changes": st.column_config.TextColumn("Status / Changes")
                }
            )

# --- EDITOR & SETTINGS (Simplified for brevity, same as before) ---
elif page == "✏️ Staffing Editor":
    # [Use previous Editor code here - no changes needed for Dashboard logic]
    # For completeness in the v2 file, paste the previous Editor block here.
    c_title, c_undo = st.columns([5, 1])
    c_title.title("✏️ Staffing Editor")
    if st.session_state.undo_stack:
        if c_undo.button("↩️ Undo", type="primary"):
            undo_last_change()
            st.rerun()
    else: c_undo.button("↩️ Undo", disabled=True)

    view = st.radio("View:", ["Profile View (Detail)", "Grid View (Spreadsheet)"], horizontal=True)
    st.divider()

    if view == "Profile View (Detail)":
        focus = st.radio("Focus:", ["People", "Programs"], horizontal=True, label_visibility="collapsed")
        if focus == "People":
            all_emps = sorted(df.index.astype(str), key=str.casefold)
            filtered_emps = [e for e in all_emps if not str(df.loc[e, 'Role']).strip().upper().startswith("R+I")]
            sel_emps = st.multiselect("Select Employees", filtered_emps, placeholder="Select people to edit...")
            if sel_emps:
                for name in sel_emps:
                    if name in df.index:
                        render_employee_card(name, df.loc[name])
                        row = df.loc[name]
                        p_df = pd.DataFrame(row[prog_cols])
                        p_df.columns = ['Hours']
                        p_df['Margin %'] = p_df.index.map(lambda x: margin_metrics.get(x, {}).get('margin_pct', 0.0))
                        active = p_df[p_df['Hours'] > 0].index.tolist()
                        to_edit = st.multiselect(f"Programs for {name}", sorted(prog_cols, key=str.casefold), default=active, key=f"sel_{name}")
                        edited = st.data_editor(p_df.loc[to_edit], use_container_width=True, column_config={"Hours": st.column_config.NumberColumn(min_value=0), "Margin %": st.column_config.NumberColumn(format="%.1f%%", disabled=True)}, key=f"ed_{name}")
                        if not edited['Hours'].equals(p_df.loc[to_edit, 'Hours']):
                            push_to_history()
                            for prog, r in edited.iterrows(): st.session_state.df.at[name, prog] = r['Hours']
                            st.session_state.df = utils.recalculate_utilization(st.session_state.df)
                            st.rerun()
        else:
            sel_progs = st.multiselect("Select Programs", sorted(prog_cols, key=str.casefold), placeholder="Select programs...")
            if sel_progs:
                for prog in sel_progs:
                    total = df[prog].sum()
                    m_data = margin_metrics.get(prog, {})
                    margin_pct_disp = m_data.get('margin_pct', 0)
                    mrr = m_data.get('mrr', 0)
                    with st.container(border=True):
                        st.subheader(f"{prog} (MRR: ${mrr:,.0f})")
                        c1, c2 = st.columns(2)
                        c1.metric("Total Hours", f"{total} hrs")
                        c2.metric("Contr. Margin", f"{margin_pct_disp:.1f}%", delta_color="normal")
                        t_df = pd.DataFrame(df[prog])
                        t_df.columns = ['Hours']
                        if 'Role' in df.columns: t_df = t_df.join(df['Role'])
                        active = t_df[t_df['Hours'] > 0].index.tolist()
                        to_edit = st.multiselect(f"Team for {prog}", sorted(df.index.tolist(), key=str.casefold), default=active, key=f"psel_{prog}")
                        edited = st.data_editor(t_df.loc[to_edit], use_container_width=True, column_config={"Hours": st.column_config.NumberColumn(min_value=0), "Role": st.column_config.TextColumn(disabled=True)}, key=f"ped_{prog}")
                        if not edited.equals(t_df.loc[to_edit]):
                            push_to_history()
                            for emp, r in edited.iterrows(): st.session_state.df.at[emp, prog] = r['Hours']
                            st.session_state.df = utils.recalculate_utilization(st.session_state.df)
                            st.rerun()
    else:
        c1, c2 = st.columns([2, 1])
        search = c1.text_input("🔍 Search", placeholder="Filter by name...")
        df_view = df.copy().sort_index(key=lambda x: x.str.lower())
        if search:
            mask = df_view.index.astype(str).str.contains(search, case=False)
            df_view = df_view[mask]
        active_progs = [c for c in prog_cols if df_view[c].sum() > 0]
        sel_cols = st.multiselect("Active Programs (Add to view)", sorted(prog_cols, key=str.casefold), default=sorted(active_progs, key=str.casefold))
        cols_to_show = [c for c in df_view.columns if c not in prog_cols] + sel_cols
        edited = st.data_editor(df_view[cols_to_show], use_container_width=True, column_config={"Current Hours to Target": st.column_config.ProgressColumn("Util %", format="%d%%", min_value=0, max_value=100)}, disabled=['Current Hours to Target'], key="grid_main")
        if not edited.equals(df_view[cols_to_show]):
            push_to_history()
            st.session_state.df.update(edited)
            st.session_state.df = utils.recalculate_utilization(st.session_state.df)
            st.rerun()

elif page == "⚙️ Settings":
    st.title("⚙️ Settings")
    st.info("💡 Note: In this Cloud Mode, uploads and edits are temporary. They will reset if you refresh the page.")
    t1, t2, t3 = st.tabs(["📥 Data Import", "👤 People", "🏢 Programs"])
    
    with t1:
        st.write("Upload a CSV to work with your own data in this session.")
        up_file = st.file_uploader("Upload CSV", type=['csv'])
        if up_file:
             if 'last_processed' not in st.session_state or st.session_state.last_processed != up_file.name:
                new_df, new_mrr, f_map = utils.process_uploaded_file(up_file)
                if not new_df.empty:
                    if 'Employee' in new_df.columns: new_df = new_df.set_index('Employee')
                    new_df = utils.recalculate_utilization(new_df)
                    st.session_state.df = new_df
                    st.session_state.program_mrr.update(new_mrr)
                    st.session_state.future_map = f_map # Store map
                    st.session_state.last_processed = up_file.name
                    st.success("Data loaded for this session!")
                    st.rerun()
        if st.button("⚠️ Reset to Default", type="primary"):
            st.session_state.clear()
            st.rerun()
    with t2:
        c1, c2 = st.columns(2)
        with c1:
            with st.form("new_emp"):
                st.subheader("Add Employee")
                n = st.text_input("Name")
                r = st.selectbox("Role", list(utils.RATE_CARD.keys()))
                if st.form_submit_button("Add"):
                    if n and n not in st.session_state.df.index:
                        push_to_history()
                        new_row = {c:0 for c in st.session_state.df.columns}
                        new_row['Role'] = r
                        new_row['Capacity'] = utils.STANDARD_CAPACITY
                        st.session_state.df.loc[n] = pd.Series(new_row)
                        st.session_state.df = utils.recalculate_utilization(st.session_state.df)
                        st.rerun()
        with c2:
            st.subheader("Delete Employee")
            all_emps = sorted(st.session_state.df.index.tolist(), key=str.casefold)
            del_emp = st.selectbox("Select Employee", ["Select..."] + all_emps)
            if st.button("Delete Employee", type="primary"):
                if del_emp != "Select...":
                    push_to_history()
                    st.session_state.df = st.session_state.df.drop(index=[del_emp])
                    st.session_state.df = utils.recalculate_utilization(st.session_state.df)
                    st.rerun()
    with t3:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Add Program")
            n_prog = st.text_input("New Program Name")
            mrr_input = st.number_input("Program MRR ($)", min_value=0, value=0, step=1000)
            if st.button("Add Program"):
                if n_prog and n_prog not in st.session_state.df.columns:
                    push_to_history()
                    st.session_state.df[n_prog] = 0
                    st.session_state.program_mrr[n_prog] = mrr_input
                    st.session_state.df = utils.recalculate_utilization(st.session_state.df)
                    st.rerun()
        with c2:
            st.subheader("Delete Program")
            del_prog = st.selectbox("Select Program", ["Select..."] + sorted(prog_cols, key=str.casefold))
            if st.button("Delete Program", type="primary"):
                if del_prog != "Select...":
                    push_to_history()
                    st.session_state.df = st.session_state.df.drop(columns=[del_prog])
                    if del_prog in st.session_state.program_mrr:
                        del st.session_state.program_mrr[del_prog]
                    st.session_state.df = utils.recalculate_utilization(st.session_state.df)
                    st.rerun()
