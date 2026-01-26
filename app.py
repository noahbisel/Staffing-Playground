import streamlit as st
import pandas as pd
import plotly.express as px
import os
import utils

# --- 1. APP CONFIGURATION ---
st.set_page_config(page_title="Staffing Sandbox", layout="wide", page_icon="👥")

# --- 2. INIT & LOAD (CLEAN SLATE) ---
if 'program_mrr' not in st.session_state:
    st.session_state.program_mrr = {}

if 'undo_stack' not in st.session_state:
    st.session_state.undo_stack = []

if 'df' not in st.session_state:
    st.session_state.df = pd.DataFrame()

# --- NEW: NAVIGATION STATE MANAGEMENT ---
# We need these to persist selections when switching views
if 'editor_focus' not in st.session_state:
    st.session_state.editor_focus = "People" # Default View
if 'editor_selected_people' not in st.session_state:
    st.session_state.editor_selected_people = []
if 'editor_selected_programs' not in st.session_state:
    st.session_state.editor_selected_programs = []

# Helper functions to switch views
def go_to_program(prog_name):
    st.session_state.editor_focus = "Programs"
    st.session_state.editor_selected_programs = [prog_name]
    # No rerun needed here if called inside a button callback, 
    # but strictly safe to let Streamlit handle the rerun cycle.

def go_to_person(emp_name):
    st.session_state.editor_focus = "People"
    st.session_state.editor_selected_people = [emp_name]

# --- 3. GLOBAL VARIABLES ---
df = st.session_state.df
prog_cols = []
margin_metrics = {}

if not df.empty:
    numeric_cols = df.select_dtypes(include=['number']).columns
    exclude_cols = ['Capacity', 'Current Hours to Target']
    prog_cols = [c for c in numeric_cols if c not in exclude_cols]
    margin_metrics = utils.calculate_margin(df, st.session_state.program_mrr)

def render_employee_card(name, row):
    util = row.get('Current Hours to Target', 0)
    cap = row.get('Capacity', utils.STANDARD_CAPACITY)
    role = row.get('Role', 'N/A')
    
    # Calculate Hours Breakdown
    allocated_hours = int((util / 100) * cap)
    unused_hours = int(cap - allocated_hours)
    
    color = "green"
    if util > 100: color = "red"
    elif util < 80: color = "orange"
    
    with st.container(border=True):
        c_head, c_badge = st.columns([3, 1])
        with c_head:
            st.markdown(f"**{name}**")
            st.caption(role)
            st.markdown(f"Alloc: **{allocated_hours}** | Unused: **{unused_hours}**")
        
        with c_badge:
            st.markdown(f":{color}[**{util}%**]")
        
        st.progress(min(util, 100) / 100)

def push_to_history():
    st.session_state.undo_stack.append(st.session_state.df.copy())
    if len(st.session_state.undo_stack) > 10:
        st.session_state.undo_stack.pop(0)

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
        # --- TOP METRICS ---
        team_util, team_alloc, team_cap = utils.calculate_group_utilization(df, utils.TEAM_ROLES)
        team_unused = team_cap - team_alloc

        acp_util, acp_alloc, acp_cap = utils.calculate_group_utilization(df, ['ACP'])
        acp_unused = acp_cap - acp_alloc
        
        cp_util, cp_alloc, cp_cap = utils.calculate_group_utilization(df, ['CP', 'SCP', 'LCP'])
        cp_unused = cp_cap - cp_alloc
        
        ce_util, ce_alloc, ce_cap = utils.calculate_group_utilization(df, ['ACE', 'CE', 'SCE'])
        ce_unused = ce_cap - ce_alloc

        m1, m2, m3, m4 = st.columns(4)
        with m1:
            with st.container(border=True):
                st.metric("Team Avg Utilization", f"{team_util:.0f}%", delta=f"{team_util-100:.0f}%" if team_util > 100 else None)
                st.caption(f"Alloc: **{int(team_alloc)}** | Unused: **{int(team_unused)}**")
        with m2: 
            st.metric("ACP Utilization", f"{acp_util:.0f}%")
            st.metric("ACP Unused Hours", f"{int(acp_unused)}")
        with m3: 
            st.metric("CP/SCP/LCP Utilization", f"{cp_util:.0f}%")
            st.metric("CP/SCP/LCP Unused", f"{int(cp_unused)}")
        with m4: 
            st.metric("ACE/CE/SCE Util", f"{ce_util:.0f}%")
            st.metric("ACE/CE/SCE Unused", f"{int(ce_unused)}")

        st.divider()

        col_l, col_r = st.columns(2)
        
        # --- LEFT: ALLOCATIONS BY PROGRAM ---
        with col_l:
            st.write("")
            st.write("")
            st.write("")
            st.subheader("Allocations by Program")
            
            program_analysis_df = df.copy() 
            if prog_cols:
                dynamic_margin = utils.calculate_margin(program_analysis_df, st.session_state.program_mrr)
                master_data = []
                for p in prog_cols:
                    p_hours = program_analysis_df[p].sum() if p in program_analysis_df.columns else 0
                    if p_hours > 0:
                        m_data = dynamic_margin.get(p, {})
                        mrr_val = m_data.get('mrr', 0)
                        master_data.append({
                            "Program Name": p,
                            "Program MRR": f"${mrr_val:,.0f}", 
                            "Total Hours": int(p_hours),
                            "Contributing Margin": m_data.get('margin_pct', 0)
                        })
                master_df = pd.DataFrame(master_data)
                if not master_df.empty:
                    master_df = master_df.sort_values("Contributing Margin", ascending=False)
                    st.dataframe(master_df, use_container_width=True, hide_index=True, column_config={"Program Name": st.column_config.TextColumn("Program Name"), "Program MRR": st.column_config.TextColumn("Program MRR"), "Total Hours": st.column_config.NumberColumn("Total Hours", format="%d"), "Contributing Margin": st.column_config.NumberColumn("Contributing Margin", format="%.1f%%")})
                else: st.info("No active programs found.")

        # --- RIGHT: ALLOCATIONS BY EMPLOYEE ---
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

            emp_sorted = emp_view_df.sort_values('Current Hours to Target', ascending=False)
            emp_table_df = emp_sorted[['Current Hours to Target']].reset_index()
            emp_table_df.columns = ['Employee', 'Utilization']
            
            st.dataframe(emp_table_df, use_container_width=True, hide_index=True, column_config={"Employee": st.column_config.TextColumn("Employee"), "Utilization": st.column_config.ProgressColumn("Utilization %", format="%d%%", min_value=0, max_value=100)})
            
        st.divider()
        st.subheader("Team Overview")
        t1, t2, t3 = st.columns(3)
        def render_role_column(container, title, roles):
            with container:
                st.markdown(f"### {title}")
                if 'Role' in df.columns:
                    mask = df['Role'].astype(str).str.upper().isin([r.upper() for r in roles])
                    group_df = df[mask].sort_values('Current Hours to Target', ascending=False)
                    if group_df.empty: st.info("No employees.")
                    else:
                        for name, row in group_df.iterrows():
                            render_employee_card(name, row)
                else: st.warning("No Role data.")
        render_role_column(t1, "ACP", ['ACP'])
        render_role_column(t2, "CP / SCP / LCP", ['CP', 'SCP', 'LCP'])
        render_role_column(t3, "ACE / CE / SCE", ['ACE', 'CE', 'SCE'])
    else:
        st.info("👋 Welcome to the Staffing Sandbox! To begin, please import your data.")
        st.markdown("""
        ### How to get started:
        1. Click **⚙️ Settings** in the sidebar.
        2. Go to the **Data Import** tab.
        3. Upload your staffing CSV file.
        """)
        if st.button("Go to Settings", type="primary"):
            st.write("👈 Click 'Settings' in the left sidebar.")

# --- PAGE: EDITOR ---
elif page == "✏️ Staffing Editor":
    if df.empty:
        st.title("✏️ Staffing Editor")
        st.warning("⚠️ No data loaded. Please go to Settings to import your CSV.")
    else:
        c_title, c_undo = st.columns([5, 1])
        c_title.title("✏️ Staffing Editor")
        if st.session_state.undo_stack:
            if c_undo.button("↩️ Undo", type="primary"):
                undo_last_change()
                st.rerun()
        else:
            c_undo.button("↩️ Undo", disabled=True)

        view = st.radio("View:", ["Profile View (Detail)", "Grid View (Spreadsheet)"], horizontal=True)
        st.divider()

        if view == "Profile View (Detail)":
            # --- VIEW TOGGLE LOGIC ---
            # We bind the Radio selection to our session state variable so programmatic changes update the UI
            focus = st.radio(
                "Focus:", 
                ["People", "Programs"], 
                horizontal=True, 
                label_visibility="collapsed",
                key="editor_focus" # Binds this widget to st.session_state.editor_focus
            )
            
            # --- PEOPLE VIEW ---
            if focus == "People":
                all_emps = sorted(df.index.astype(str), key=str.casefold)
                filtered_emps = [e for e in all_emps if not str(df.loc[e, 'Role']).strip().upper().startswith("R+I")]
                
                # Use session state for the multiselect default
                sel_emps = st.multiselect(
                    "Select Employees", 
                    filtered_emps, 
                    default=[e for e in st.session_state.editor_selected_people if e in filtered_emps],
                    placeholder="Select people to edit...",
                    key="people_multiselect"
                )
                
                # Sync selection back to state (if user manually changes it)
                if sel_emps != st.session_state.editor_selected_people:
                    st.session_state.editor_selected_people = sel_emps

                if sel_emps:
                    for name in sel_emps:
                        if name in df.index:
                            render_employee_card(name, df.loc[name])
                            row = df.loc[name]
                            p_df = pd.DataFrame(row[prog_cols])
                            p_df.columns = ['Hours']
                            p_df['Margin %'] = p_df.index.map(lambda x: margin_metrics.get(x, {}).get('margin_pct', 0.0))
                            
                            active = p_df[p_df['Hours'] > 0].index.tolist()
                            
                            # --- NAVIGATION BUTTONS ---
                            if active:
                                st.caption("Jump to Program:")
                                cols = st.columns(len(active) + 1) # +1 buffer
                                for i, prog in enumerate(active):
                                    # Create a unique key for every button
                                    if cols[i].button(f"🔗 {prog}", key=f"btn_jump_prog_{name}_{prog}"):
                                        go_to_program(prog)
                                        st.rerun()
                            
                            to_edit = st.multiselect(f"Programs for {name}", sorted(prog_cols, key=str.casefold), default=active, key=f"sel_{name}")
                            
                            edited = st.data_editor(
                                p_df.loc[to_edit], use_container_width=True, 
                                column_config={
                                    "Hours": st.column_config.NumberColumn(min_value=0),
                                    "Margin %": st.column_config.NumberColumn(format="%.1f%%", disabled=True)
                                }, key=f"ed_{name}"
                            )
                            if not edited['Hours'].equals(p_df.loc[to_edit, 'Hours']):
                                push_to_history()
                                for prog, r in edited.iterrows():
                                    st.session_state.df.at[name, prog] = r['Hours']
                                st.session_state.df = utils.recalculate_utilization(st.session_state.df)
                                st.rerun()

            # --- PROGRAMS VIEW ---
            else:
                # Use session state for the multiselect default
                sel_progs = st.multiselect(
                    "Select Programs", 
                    sorted(prog_cols, key=str.casefold), 
                    default=[p for p in st.session_state.editor_selected_programs if p in prog_cols],
                    placeholder="Select programs...",
                    key="program_multiselect"
                )
                
                # Sync selection back to state
                if sel_progs != st.session_state.editor_selected_programs:
                    st.session_state.editor_selected_programs = sel_progs

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
                            
                            # Add Utilization Column
                            t_df['Utilization'] = df.loc[t_df.index, 'Current Hours to Target']
                            active = t_df[t_df['Hours'] > 0].index.tolist()

                            # --- NAVIGATION BUTTONS ---
                            # Filter active list to exclude R+I or generic roles if you want, 
                            # or keep all. Here we keep all valid employees in index.
                            valid_active = [p for p in active if p in df.index]
                            
                            if valid_active:
                                st.caption("Jump to Employee:")
                                # Limit the number of buttons shown to avoid clutter if team is huge
                                display_limit = 10 
                                display_list = valid_active[:display_limit]
                                
                                cols = st.columns(min(len(display_list), 5)) # split into max 5 cols
                                for i, emp in enumerate(display_list):
                                    col_idx = i % 5
                                    # Truncate long names for buttons
                                    short_name = (emp[:12] + '..') if len(emp) > 12 else emp
                                    if cols[col_idx].button(f"👤 {short_name}", key=f"btn_jump_emp_{prog}_{emp}"):
                                        go_to_person(emp)
                                        st.rerun()
                                if len(valid_active) > display_limit:
                                    st.caption(f"...and {len(valid_active) - display_limit} others.")

                            to_edit = st.multiselect(f"Team for {prog}", sorted(df.index.tolist(), key=str.casefold), default=active, key=f"psel_{prog}")
                            
                            edited = st.data_editor(
                                t_df.loc[to_edit], use_container_width=True, 
                                column_config={
                                    "Hours": st.column_config.NumberColumn(min_value=0), 
                                    "Role": st.column_config.TextColumn(disabled=True),
                                    "Utilization": st.column_config.ProgressColumn(
                                        "Utilization %", 
                                        format="%d%%", 
                                        min_value=0, 
                                        max_value=100
                                    )
                                }, 
                                disabled=["Utilization"], 
                                key=f"ped_{prog}"
                            )
                            
                            edited_hours = edited[['Hours']]
                            original_hours = t_df.loc[to_edit, ['Hours']]
                            
                            if not edited_hours['Hours'].equals(original_hours['Hours']):
                                push_to_history()
                                for emp, r in edited.iterrows():
                                    st.session_state.df.at[emp, prog] = r['Hours']
                                st.session_state.df = utils.recalculate_utilization(st.session_state.df)
                                st.rerun()
        else:
            # GRID VIEW
            c1, c2 = st.columns([2, 1])
            search = c1.text_input("🔍 Search", placeholder="Filter by name...")
            df_view = df.copy().sort_index(key=lambda x: x.str.lower())
            if search:
                mask = df_view.index.astype(str).str.contains(search, case=False)
                df_view = df_view[mask]
            active_progs = [c for c in prog_cols if df_view[c].sum() > 0]
            sel_cols = st.multiselect("Active Programs (Add to view)", sorted(prog_cols, key=str.casefold), default=sorted(active_progs, key=str.casefold))
            cols_to_show = [c for c in df_view.columns if c not in prog_cols] + sel_cols
            
            edited = st.data_editor(
                df_view[cols_to_show], use_container_width=True, 
                column_config={"Current Hours to Target": st.column_config.ProgressColumn("Util %", format="%d%%", min_value=0, max_value=100)}, 
                disabled=['Current Hours to Target'], key="grid_main"
            )
            if not edited.equals(df_view[cols_to_show]):
                push_to_history()
                st.session_state.df.update(edited)
                st.session_state.df = utils.recalculate_utilization(st.session_state.df)
                st.rerun()

# --- PAGE: SETTINGS ---
elif page == "⚙️ Settings":
    st.title("⚙️ Settings")
    st.info("💡 Note: In this Cloud Mode, uploads and edits are temporary. They will reset if you refresh the page.")
    t1, t2, t3 = st.tabs(["📥 Data Import", "👤 People", "🏢 Programs"])
    
    with t1:
        st.write("Upload a CSV to work with your own data in this session.")
        up_file = st.file_uploader("Upload CSV", type=['csv'])
        if up_file:
             if 'last_processed' not in st.session_state or st.session_state.last_processed != up_file.name:
                new_df, new_mrr = utils.process_uploaded_file(up_file)
                if not new_df.empty:
                    if 'Employee' in new_df.columns: new_df = new_df.set_index('Employee')
                    new_df = utils.recalculate_utilization(new_df)
                    st.session_state.df = new_df
                    st.session_state.program_mrr.update(new_mrr)
                    st.session_state.last_processed = up_file.name
                    st.success("Data loaded for this session!")
                    st.rerun()
        if st.button("⚠️ Reset to Default (Clear Data)", type="primary"):
            st.session_state.clear()
            st.rerun()

    with t2:
        if df.empty:
            st.warning("Please import data first.")
        else:
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
        if df.empty:
            st.warning("Please import data first.")
        else:
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
