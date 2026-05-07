import streamlit as st
import pandas as pd
import hashlib
import json
import utils

# --- 1. APP CONFIGURATION ---
st.set_page_config(page_title="Staffing Sandbox", layout="wide", page_icon="👥")

# --- 2. INIT & LOAD ---
if 'program_mrr' not in st.session_state:
    st.session_state.program_mrr = {}
if 'undo_stack' not in st.session_state:
    st.session_state.undo_stack = []
if 'df' not in st.session_state:
    st.session_state.df = pd.DataFrame()
if 'editor_focus' not in st.session_state:
    st.session_state.editor_focus = "People"
if 'editor_selected_people' not in st.session_state:
    st.session_state.editor_selected_people = []
if 'editor_selected_programs' not in st.session_state:
    st.session_state.editor_selected_programs = []

# --- CALLBACK FUNCTIONS ---
def go_to_program(prog_name: str) -> None:
    st.session_state.nav_radio = "✏️ Staffing Editor"
    st.session_state.editor_focus = "Programs"
    st.session_state.editor_selected_programs = [prog_name]

def go_to_person(emp_name: str) -> None:
    st.session_state.nav_radio = "✏️ Staffing Editor"
    st.session_state.editor_focus = "People"
    st.session_state.editor_selected_people = [emp_name]

def go_to_settings() -> None:
    st.session_state.nav_radio = "⚙️ Settings"

# --- 3. GLOBAL VARIABLES ---
df = st.session_state.df
prog_cols: list[str] = []
margin_metrics: dict = {}

if not df.empty:
    prog_cols = utils.get_program_columns(df)
    margin_metrics = utils.calculate_margin(df, st.session_state.program_mrr)


def render_employee_card(name: str, row: pd.Series) -> None:
    util = row.get('Current Hours to Target', 0)
    cap = row.get('Capacity', utils.STANDARD_CAPACITY)
    role = row.get('Role', 'N/A')

    allocated_hours = int((util / 100) * cap)
    unused_hours = int(cap - allocated_hours)

    color = "green"
    if util > utils.UTILIZATION_OVER_THRESHOLD:
        color = "red"
    elif util < utils.UTILIZATION_WARN_THRESHOLD:
        color = "orange"

    with st.container(border=True):
        col_header, col_badge = st.columns([3, 1])
        with col_header:
            st.markdown(f"**{name}**")
            st.caption(role)
            st.markdown(f"Alloc: **{allocated_hours}** | Unused: **{unused_hours}**")
        with col_badge:
            st.markdown(f":{color}[**{util}%**]")
        st.progress(min(util, 100) / 100)


def push_to_history() -> None:
    st.session_state.undo_stack.append({
        'df': st.session_state.df.copy(),
        'mrr': st.session_state.program_mrr.copy()
    })
    if len(st.session_state.undo_stack) > utils.UNDO_STACK_LIMIT:
        st.session_state.undo_stack.pop(0)


def undo_last_change() -> None:
    if st.session_state.undo_stack:
        snapshot = st.session_state.undo_stack.pop()
        st.session_state.df = snapshot['df']
        st.session_state.program_mrr = snapshot['mrr']
        st.toast("Undid last change", icon="↩️")


# --- 4. NAVIGATION ---
st.sidebar.title("Staffing Sandbox")
page = st.sidebar.radio(
    "Navigate",
    ["📊 Dashboard", "✏️ Staffing Editor", "⚙️ Settings"],
    label_visibility="collapsed",
    key="nav_radio"
)
st.sidebar.markdown("---")

# ============================================================
# DASHBOARD
# ============================================================
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

        col_team, col_acp, col_cp, col_ce = st.columns(4)
        with col_team:
            with st.container(border=True):
                st.metric("Team Avg Utilization", f"{team_util:.0f}%", delta=f"{team_util-100:.0f}%" if team_util > 100 else None)
                st.caption(f"Alloc: **{int(team_alloc)}** | Unused: **{int(team_unused)}**")
        with col_acp:
            st.metric("ACP Utilization", f"{acp_util:.0f}%")
            st.metric("ACP Unused Hours", f"{int(acp_unused)}")
        with col_cp:
            st.metric("CP/SCP/LCP Utilization", f"{cp_util:.0f}%")
            st.metric("CP/SCP/LCP Unused", f"{int(cp_unused)}")
        with col_ce:
            st.metric("ACE/CE/SCE Util", f"{ce_util:.0f}%")
            st.metric("ACE/CE/SCE Unused", f"{int(ce_unused)}")

        st.divider()

        col_left, col_right = st.columns(2)

        # --- LEFT: ALLOCATIONS BY PROGRAM ---
        with col_left:
            st.subheader("Allocations by Program")

            if prog_cols:
                master_data = []
                for p in prog_cols:
                    p_hours = df[p].sum() if p in df.columns else 0
                    if p_hours > 0:
                        m_data = margin_metrics.get(p, {})
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
                    st.dataframe(
                        master_df, use_container_width=True, hide_index=True,
                        column_config={
                            "Program Name": st.column_config.TextColumn("Program Name"),
                            "Program MRR": st.column_config.TextColumn("Program MRR"),
                            "Total Hours": st.column_config.NumberColumn("Total Hours", format="%d"),
                            "Contributing Margin": st.column_config.NumberColumn("Contributing Margin", format="%.1f%%")
                        }
                    )
                else:
                    st.info("No active programs found.")

        # --- RIGHT: ALLOCATIONS BY EMPLOYEE ---
        with col_right:
            toggle_col_ri, toggle_col_csm = st.columns(2)
            include_ri = toggle_col_ri.toggle("Include R+I Roles?", value=True)
            include_csm = toggle_col_csm.toggle("Include CSM Roles?", value=True)

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

            st.dataframe(
                emp_table_df, use_container_width=True, hide_index=True,
                column_config={
                    "Employee": st.column_config.TextColumn("Employee"),
                    "Utilization": st.column_config.ProgressColumn("Utilization %", format="%d%%", min_value=0, max_value=100)
                }
            )

        st.divider()
        st.subheader("Team Overview")
        col_acp_overview, col_cp_overview, col_ce_overview = st.columns(3)

        def render_role_column(container, title: str, roles: list[str]) -> None:
            with container:
                st.markdown(f"### {title}")
                if 'Role' in df.columns:
                    mask = df['Role'].astype(str).str.upper().isin([r.upper() for r in roles])
                    group_df = df[mask].sort_values('Current Hours to Target', ascending=False)
                    if group_df.empty:
                        st.info("No employees.")
                    else:
                        for name, row in group_df.iterrows():
                            render_employee_card(name, row)
                else:
                    st.warning("No Role data.")

        render_role_column(col_acp_overview, "ACP", ['ACP'])
        render_role_column(col_cp_overview, "CP / SCP / LCP", ['CP', 'SCP', 'LCP'])
        render_role_column(col_ce_overview, "ACE / CE / SCE", ['ACE', 'CE', 'SCE'])
    else:
        st.info("Welcome to the Staffing Sandbox! To begin, please import your data.")
        st.markdown("""
        ### How to get started:
        1. Click **Settings** in the sidebar.
        2. Go to the **Data Import** tab.
        3. Upload your staffing CSV file.
        """)
        st.button("Go to Settings", type="primary", on_click=go_to_settings)

# ============================================================
# EDITOR
# ============================================================
elif page == "✏️ Staffing Editor":
    if df.empty:
        st.title("✏️ Staffing Editor")
        st.warning("No data loaded. Please go to Settings to import your CSV.")
    else:
        col_title, col_undo = st.columns([5, 1])
        col_title.title("✏️ Staffing Editor")
        if st.session_state.undo_stack:
            if col_undo.button("↩️ Undo", type="primary"):
                undo_last_change()
                st.rerun()
        else:
            col_undo.button("↩️ Undo", disabled=True)

        view = st.radio("View:", ["Profile View (Detail)", "Grid View (Spreadsheet)"], horizontal=True)
        st.divider()

        if view == "Profile View (Detail)":
            focus = st.radio(
                "Focus:",
                ["People", "Programs"],
                horizontal=True,
                label_visibility="collapsed",
                key="editor_focus"
            )

            # --- PEOPLE VIEW ---
            if focus == "People":
                all_emps = sorted(df.index.astype(str), key=str.casefold)
                filtered_emps = [e for e in all_emps if not str(df.loc[e, 'Role']).strip().upper().startswith("R+I")]

                sel_emps = st.multiselect(
                    "Select Employees",
                    filtered_emps,
                    default=[e for e in st.session_state.editor_selected_people if e in filtered_emps],
                    placeholder="Select people to edit...",
                    key="people_multiselect"
                )

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

                            if active:
                                st.caption("Jump to Program:")
                                nav_cols = st.columns(len(active) + 1)
                                for i, prog in enumerate(active):
                                    nav_cols[i].button(
                                        f"🔗 {prog}",
                                        key=f"btn_jump_prog_{name}_{prog}",
                                        on_click=go_to_program,
                                        args=(prog,)
                                    )

                            to_edit = st.multiselect(f"Programs for {name}", sorted(prog_cols, key=str.casefold), default=active, key=f"sel_{name}")

                            edited = st.data_editor(
                                p_df.loc[to_edit], use_container_width=True,
                                column_config={
                                    "Hours": st.column_config.NumberColumn(min_value=0, max_value=utils.MAX_HOURS_PER_PROGRAM),
                                    "Margin %": st.column_config.NumberColumn(format="%.1f%%", disabled=True)
                                }, key=f"ed_{name}"
                            )
                            if not edited['Hours'].equals(p_df.loc[to_edit, 'Hours']):
                                push_to_history()
                                for prog, r in edited.iterrows():
                                    st.session_state.df.at[name, prog] = r['Hours']
                                st.session_state.df = utils.recalculate_utilization(st.session_state.df)
                                st.rerun()
                else:
                    st.info("Select one or more employees above to view and edit allocations.")

            # --- PROGRAMS VIEW ---
            else:
                sel_progs = st.multiselect(
                    "Select Programs",
                    sorted(prog_cols, key=str.casefold),
                    default=[p for p in st.session_state.editor_selected_programs if p in prog_cols],
                    placeholder="Select programs...",
                    key="program_multiselect"
                )

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
                            col_hours, col_margin, col_mrr_edit = st.columns(3)
                            col_hours.metric("Total Hours", f"{total} hrs")
                            col_margin.metric("Contr. Margin", f"{margin_pct_disp:.1f}%", delta_color="normal")
                            new_mrr = col_mrr_edit.number_input(
                                "Edit MRR ($)",
                                min_value=0,
                                value=int(mrr),
                                step=1000,
                                key=f"mrr_edit_{prog}"
                            )
                            if new_mrr != int(mrr):
                                push_to_history()
                                st.session_state.program_mrr[prog] = new_mrr
                                st.toast(f"MRR for {prog} updated to ${new_mrr:,}", icon="💰")
                                st.rerun()

                            t_df = pd.DataFrame(df[prog])
                            t_df.columns = ['Hours']
                            if 'Role' in df.columns:
                                t_df = t_df.join(df['Role'])

                            t_df['Utilization'] = df.loc[t_df.index, 'Current Hours to Target']
                            active = t_df[t_df['Hours'] > 0].index.tolist()
                            valid_active = [p for p in active if p in df.index]

                            if valid_active:
                                st.caption("Jump to Employee:")
                                display_list = valid_active[:utils.JUMP_BUTTON_DISPLAY_LIMIT]

                                nav_cols = st.columns(min(len(display_list), utils.JUMP_BUTTON_COLUMNS))
                                for i, emp in enumerate(display_list):
                                    col_idx = i % utils.JUMP_BUTTON_COLUMNS
                                    short_name = (emp[:utils.NAME_TRUNCATION_LENGTH] + '..') if len(emp) > utils.NAME_TRUNCATION_LENGTH else emp

                                    nav_cols[col_idx].button(
                                        f"👤 {short_name}",
                                        key=f"btn_jump_emp_{prog}_{emp}",
                                        on_click=go_to_person,
                                        args=(emp,)
                                    )
                                if len(valid_active) > utils.JUMP_BUTTON_DISPLAY_LIMIT:
                                    st.caption(f"...and {len(valid_active) - utils.JUMP_BUTTON_DISPLAY_LIMIT} others.")

                            to_edit = st.multiselect(f"Team for {prog}", sorted(df.index.tolist(), key=str.casefold), default=active, key=f"psel_{prog}")

                            edited = st.data_editor(
                                t_df.loc[to_edit], use_container_width=True,
                                column_config={
                                    "Hours": st.column_config.NumberColumn(min_value=0, max_value=utils.MAX_HOURS_PER_PROGRAM),
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
                    st.info("Select one or more programs above to view and edit allocations.")
        else:
            # GRID VIEW
            col_search, _ = st.columns([2, 1])
            search = col_search.text_input("🔍 Search", placeholder="Filter by name...")
            df_view = df.copy().sort_index(key=lambda x: x.str.lower())
            if search:
                mask = df_view.index.astype(str).str.contains(search, case=False)
                df_view = df_view[mask]
            active_progs = [c for c in prog_cols if df_view[c].sum() > 0]
            sel_cols = st.multiselect("Active Programs (Add to view)", sorted(prog_cols, key=str.casefold), default=sorted(active_progs, key=str.casefold))
            cols_to_show = [c for c in df_view.columns if c not in prog_cols] + sel_cols

            grid_col_config = {
                "Current Hours to Target": st.column_config.ProgressColumn("Util %", format="%d%%", min_value=0, max_value=100),
            }
            for prog in sel_cols:
                grid_col_config[prog] = st.column_config.NumberColumn(min_value=0, max_value=utils.MAX_HOURS_PER_PROGRAM)

            edited = st.data_editor(
                df_view[cols_to_show], use_container_width=True,
                column_config=grid_col_config,
                disabled=['Current Hours to Target'], key="grid_main"
            )
            if not edited.equals(df_view[cols_to_show]):
                push_to_history()
                st.session_state.df.update(edited)
                st.session_state.df = utils.recalculate_utilization(st.session_state.df)
                st.rerun()

# ============================================================
# SETTINGS
# ============================================================
elif page == "⚙️ Settings":
    st.title("⚙️ Settings")
    st.info("Uploads and edits are temporary. They will reset if you refresh the page. Use Export or Save Session to preserve your work.")
    tab_import, tab_people, tab_programs = st.tabs(["📥 Data Import", "👤 People", "🏢 Programs"])

    with tab_import:
        st.write("Upload a CSV to work with your own data in this session.")
        up_file = st.file_uploader("Upload CSV", type=['csv'])
        if up_file:
            file_hash = hashlib.md5(up_file.getvalue()).hexdigest()
            if st.session_state.get('last_processed_hash') != file_hash:
                new_df, new_mrr = utils.process_uploaded_file(up_file)
                if not new_df.empty:
                    if 'Employee' in new_df.columns:
                        new_df = new_df.set_index('Employee')
                    new_df = utils.recalculate_utilization(new_df)
                    st.session_state.df = new_df
                    st.session_state.original_df = new_df.copy()
                    st.session_state.program_mrr.update(new_mrr)
                    st.session_state.last_processed_hash = file_hash
                    st.toast("Data loaded for this session!", icon="✅")
                    st.rerun()

        st.divider()

        if not df.empty:
            st.subheader("Export Data")
            col_export_xlsx, col_export_session = st.columns(2)

            with col_export_xlsx:
                original = st.session_state.get('original_df')
                xlsx_bytes = utils.export_to_excel(df, original, st.session_state.program_mrr)
                st.download_button(
                    "📥 Download Excel (with change highlights)",
                    xlsx_bytes,
                    "staffing_export.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                st.caption("Yellow = changed cells, Green = new rows/columns")

            with col_export_session:
                session_data = {
                    'df': df.to_json(),
                    'program_mrr': st.session_state.program_mrr,
                    'original_df': st.session_state.get('original_df', pd.DataFrame()).to_json() if st.session_state.get('original_df') is not None else None
                }
                st.download_button(
                    "💾 Save Session (JSON)",
                    json.dumps(session_data),
                    "staffing_session.json",
                    "application/json"
                )
                st.caption("Save and restore your full session later")

        st.divider()

        st.subheader("Load Session")
        session_file = st.file_uploader("Upload a saved session (.json)", type=['json'], key="session_loader")
        if session_file:
            try:
                session_data = json.loads(session_file.getvalue())
                loaded_df = pd.read_json(session_data['df'])
                st.session_state.df = loaded_df
                st.session_state.program_mrr = session_data.get('program_mrr', {})
                if session_data.get('original_df'):
                    st.session_state.original_df = pd.read_json(session_data['original_df'])
                st.toast("Session restored!", icon="✅")
                st.rerun()
            except Exception as e:
                st.error(f"Could not load session file: {e}")

        st.divider()

        if st.button("⚠️ Reset to Default (Clear Data)"):
            st.session_state['confirm_reset'] = True

        if st.session_state.get('confirm_reset'):
            st.warning("This will erase all data. Are you sure?")
            col_yes, col_no, _ = st.columns([1, 1, 4])
            if col_yes.button("Yes, Reset", type="primary"):
                st.session_state.clear()
                st.rerun()
            if col_no.button("Cancel"):
                st.session_state['confirm_reset'] = False
                st.rerun()

    with tab_people:
        if df.empty:
            st.warning("Please import data first.")
        else:
            col_add, col_delete = st.columns(2)
            with col_add:
                with st.form("new_emp"):
                    st.subheader("Add Employee")
                    new_employee_name = st.text_input("Name")
                    new_employee_role = st.selectbox("Role", list(utils.RATE_CARD.keys()))
                    if st.form_submit_button("Add"):
                        if new_employee_name and new_employee_name not in st.session_state.df.index:
                            push_to_history()
                            new_row = {c: 0 for c in st.session_state.df.columns}
                            new_row['Role'] = new_employee_role
                            new_row['Capacity'] = utils.STANDARD_CAPACITY
                            st.session_state.df.loc[new_employee_name] = pd.Series(new_row)
                            st.session_state.df = utils.recalculate_utilization(st.session_state.df)
                            st.toast(f"Added {new_employee_name}", icon="✅")
                            st.rerun()
                        elif new_employee_name in st.session_state.df.index:
                            st.warning(f"'{new_employee_name}' already exists.")
                        else:
                            st.warning("Please enter a name.")

            with col_delete:
                st.subheader("Delete Employee")
                all_emps = sorted(st.session_state.df.index.tolist(), key=str.casefold)
                del_emp = st.selectbox("Select Employee", ["Select..."] + all_emps)
                if st.button("Delete Employee", type="primary"):
                    if del_emp != "Select...":
                        st.session_state[f'confirm_del_emp_{del_emp}'] = True

                if del_emp != "Select..." and st.session_state.get(f'confirm_del_emp_{del_emp}'):
                    st.warning(f"Are you sure you want to delete **{del_emp}**?")
                    col_yes, col_no, _ = st.columns([1, 1, 4])
                    if col_yes.button("Yes, Delete", key="confirm_del_emp_yes", type="primary"):
                        push_to_history()
                        st.session_state.df = st.session_state.df.drop(index=[del_emp])
                        st.session_state.df = utils.recalculate_utilization(st.session_state.df)
                        del st.session_state[f'confirm_del_emp_{del_emp}']
                        st.toast(f"Deleted {del_emp}", icon="🗑️")
                        st.rerun()
                    if col_no.button("Cancel", key="cancel_del_emp"):
                        del st.session_state[f'confirm_del_emp_{del_emp}']
                        st.rerun()

    with tab_programs:
        if df.empty:
            st.warning("Please import data first.")
        else:
            col_add, col_delete = st.columns(2)
            with col_add:
                st.subheader("Add Program")
                new_program_name = st.text_input("New Program Name")
                mrr_input = st.number_input("Program MRR ($)", min_value=0, value=0, step=1000)
                if st.button("Add Program"):
                    if new_program_name and new_program_name not in st.session_state.df.columns:
                        push_to_history()
                        st.session_state.df[new_program_name] = 0
                        st.session_state.program_mrr[new_program_name] = mrr_input
                        st.session_state.df = utils.recalculate_utilization(st.session_state.df)
                        st.toast(f"Added program '{new_program_name}'", icon="✅")
                        st.rerun()
                    elif new_program_name in st.session_state.df.columns:
                        st.warning(f"Program '{new_program_name}' already exists.")
                    else:
                        st.warning("Please enter a program name.")

            with col_delete:
                st.subheader("Delete Program")
                del_prog = st.selectbox("Select Program", ["Select..."] + sorted(prog_cols, key=str.casefold))
                if st.button("Delete Program", type="primary"):
                    if del_prog != "Select...":
                        st.session_state[f'confirm_del_prog_{del_prog}'] = True

                if del_prog != "Select..." and st.session_state.get(f'confirm_del_prog_{del_prog}'):
                    st.warning(f"Are you sure you want to delete **{del_prog}**?")
                    col_yes, col_no, _ = st.columns([1, 1, 4])
                    if col_yes.button("Yes, Delete", key="confirm_del_prog_yes", type="primary"):
                        push_to_history()
                        st.session_state.df = st.session_state.df.drop(columns=[del_prog])
                        if del_prog in st.session_state.program_mrr:
                            del st.session_state.program_mrr[del_prog]
                        st.session_state.df = utils.recalculate_utilization(st.session_state.df)
                        del st.session_state[f'confirm_del_prog_{del_prog}']
                        st.toast(f"Deleted program '{del_prog}'", icon="🗑️")
                        st.rerun()
                    if col_no.button("Cancel", key="cancel_del_prog"):
                        del st.session_state[f'confirm_del_prog_{del_prog}']
                        st.rerun()
