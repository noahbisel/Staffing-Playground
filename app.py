import streamlit as st
import pandas as pd
import plotly.express as px
import os

# --- 1. APP CONFIGURATION ---
st.set_page_config(page_title="Staffing OS", layout="wide", page_icon="👥")
DEFAULT_DATA_FILE = 'staffing_db.csv'

# --- CONSTANTS ---
RATE_CARD = {
    "ACP": 37,
    "CP": 54,
    "CE": 89,
    "SCE": 119,
    "R+I I": 44,
    "R+I II": 56,
    "R+I III": 89,
    "R+I IV": 135
}

# --- 2. UTILITY FUNCTIONS ---

def find_column(df, candidates):
    """Robustly finds a column name from a list of candidates (case-insensitive)."""
    df_cols_clean = [str(col).strip().lower() for col in df.columns]
    for c in candidates:
        c_clean = c.strip().lower()
        if c_clean in df_cols_clean:
            return df.columns[df_cols_clean.index(c_clean)]
    return None

def process_uploaded_file(file):
    """Parses, Pivots, and Normalizes incoming CSV data."""
    try:
        file.seek(0)
        df = pd.read_csv(file)
        df.columns = df.columns.str.strip()

        # 1. Capture MRR before dropping it
        mrr_col = find_column(df, ['Program MRR', 'MRR', 'Revenue'])
        prog_col_raw = find_column(df, ['Program Name', 'Program', 'Client'])
        
        new_mrr_map = {}
        if mrr_col and prog_col_raw:
            try:
                if df[mrr_col].dtype == 'object':
                    df[mrr_col] = df[mrr_col].astype(str).str.replace('$', '').str.replace(',', '')
                df[mrr_col] = pd.to_numeric(df[mrr_col], errors='coerce').fillna(0)
                temp_map = df.groupby(prog_col_raw)[mrr_col].max().to_dict()
                new_mrr_map.update(temp_map)
            except:
                pass
            df = df.drop(columns=[mrr_col])
        
        if 'program_mrr' not in st.session_state:
            st.session_state.program_mrr = {}
        st.session_state.program_mrr.update(new_mrr_map)

        ct_col = find_column(df, ['CT Name', 'Employee Name', 'Employee'])
        prog_col = find_column(df, ['Program Name', 'Program', 'Client'])
        role_col = find_column(df, ['Account Role', 'Role'])

        if ct_col and prog_col:
            st.toast("Processing Data...", icon="🔄")
            hour_col = find_column(df, ['Allocated Monthly Hours', 'Allocated Hours', 'Hours'])
            if not hour_col:
                found = [c for c in df.columns if 'Allocated' in c]
                if found: hour_col = found[0]

            if hour_col:
                df[hour_col] = pd.to_numeric(df[hour_col], errors='coerce').fillna(0)
                pivot_df = df.pivot_table(index=ct_col, columns=prog_col, values=hour_col, aggfunc='sum').fillna(0)

                if role_col:
                    roles = df[[ct_col, role_col]].drop_duplicates(subset=ct_col).groupby(ct_col).first()
                    final_df = roles.join(pivot_df).reset_index()
                    final_df = final_df.rename(columns={ct_col: 'Employee', role_col: 'Role'})
                else:
                    final_df = pivot_df.reset_index().rename(columns={ct_col: 'Employee'})

                return final_df

        if ct_col and ct_col != 'Employee':
            df = df.rename(columns={ct_col: 'Employee'})

        return df

    except Exception as e:
        st.error(f"Error processing file: {e}")
        return pd.DataFrame()

def recalculate_utilization(df):
    """Updates the 'Current Hours to Target' column based on allocated hours."""
    if df.empty: return df

    exclude = ['Capacity', 'Current Hours to Target']
    prog_cols = [c for c in df.select_dtypes(include=['number']).columns if c not in exclude]

    total_hours = df[prog_cols].sum(axis=1)

    if 'Capacity' not in df.columns:
        col_idx = 1 if 'Role' in df.columns else 0
        df.insert(col_idx, 'Capacity', 152)

    util = df.apply(lambda x: (total_hours[x.name] / x['Capacity'] * 100) if x['Capacity'] > 0 else 0, axis=1)
    df['Current Hours to Target'] = util.round(0).astype(int)

    return df

def get_rate(role_name):
    """Robust lookup for Rate Card."""
    if not role_name: return 0
    role_clean = str(role_name).strip().upper()
    if role_clean in RATE_CARD:
        return RATE_CARD[role_clean]
    for key, rate in RATE_CARD.items():
        if key in role_clean:
            return rate
    return 0

def calculate_margin(df, program_mrr_dict):
    """Calculates Extended Cost and Margin % for all programs."""
    if df.empty: return {}
    
    exclude = ['Capacity', 'Current Hours to Target']
    prog_cols = [c for c in df.select_dtypes(include=['number']).columns if c not in exclude]
    
    margin_data = {} 
    
    program_costs = {p: 0.0 for p in prog_cols}
    
    for idx, row in df.iterrows():
        role = row.get('Role', '')
        rate = get_rate(role)
        for prog in prog_cols:
            hours = row.get(prog, 0)
            cost = hours * rate
            program_costs[prog] += cost
            
    for prog, cost in program_costs.items():
        mrr = program_mrr_dict.get(prog, 0)
        margin_pct = 0.0
        if mrr > 0:
            margin_pct = ((mrr - cost) / mrr) * 100
        else:
            margin_pct = -100.0 if cost > 0 else 0.0
            
        margin_data[prog] = {
            'mrr': mrr,
            'cost': cost,
            'margin_pct': margin_pct
        }
        
    return margin_data

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

def get_role_metrics(df, role_list):
    if 'Role' not in df.columns: return 0, 0
    mask = df['Role'].astype(str).str.upper().isin([r.upper() for r in role_list])
    role_df = df[mask]
    if role_df.empty: return 0, 0

    avg_util = role_df['Current Hours to Target'].mean()
    total_cap = role_df['Capacity'].sum()
    exclude = ['Capacity', 'Current Hours to Target']
    p_cols = [c for c in role_df.select_dtypes(include=['number']).columns if c not in exclude]
    total_alloc = role_df[p_cols].sum().sum()
    unused_cap = total_cap - total_alloc
    return avg_util, unused_cap

# --- 3. INIT & LOAD ---
if 'program_mrr' not in st.session_state:
    st.session_state.program_mrr = {}

if 'df' not in st.session_state:
    if os.path.exists(DEFAULT_DATA_FILE):
        try:
            df = pd.read_csv(DEFAULT_DATA_FILE)
            mrr_col = find_column(df, ['Program MRR', 'MRR'])
            prog_col = find_column(df, ['Program Name', 'Program'])
            if mrr_col and prog_col:
                try:
                    df[mrr_col] = pd.to_numeric(df[mrr_col], errors='coerce').fillna(0)
                    st.session_state.program_mrr = df.groupby(prog_col)[mrr_col].max().to_dict()
                    df = df.drop(columns=[mrr_col])
                except: pass
            
            if 'Employee' in df.columns: df = df.set_index('Employee')
            st.session_state.df = recalculate_utilization(df)
        except: st.session_state.df = pd.DataFrame()
    else:
        # Fallback Mock Data
        data = {
            'Employee': ['Mitch Ursick', 'Noah Bisel', 'Kevin Steger', 'Nicki Williams'],
            'Role': ['CSM', 'CE', 'CP', 'CE'],
            'Capacity': [152, 152, 152, 152],
            'Accenture': [10, 80, 20, 0],
            'Google': [60, 20, 60, 15]
        }
        st.session_state.program_mrr = {'Accenture': 15000, 'Google': 25000}
        df = pd.DataFrame(data).set_index('Employee')
        st.session_state.df = recalculate_utilization(df)

# --- 4. GLOBAL CALCULATIONS ---
df = st.session_state.df
prog_cols = []
margin_metrics = {}

if not df.empty:
    numeric_cols = df.select_dtypes(include=['number']).columns
    exclude_cols = ['Capacity', 'Current Hours to Target']
    prog_cols = [c for c in numeric_cols if c not in exclude_cols]
    margin_metrics = calculate_margin(df, st.session_state.program_mrr)

# --- 5. NAVIGATION ---
st.sidebar.title("Staffing OS")
page = st.sidebar.radio("Navigate", ["📊 Dashboard", "✏️ Staffing Editor", "⚙️ Settings"], label_visibility="collapsed")
st.sidebar.markdown("---")

# --- PAGE: DASHBOARD ---
if page == "📊 Dashboard":
    st.title("📊 Executive Dashboard")

    if not df.empty:
        avg_util = df['Current Hours to Target'].mean()
        total_cap = df['Capacity'].sum()
        total_alloc = df[prog_cols].sum().sum()

        acp_util, acp_unused = get_role_metrics(df, ['ACP'])
        cp_util, cp_unused = get_role_metrics(df, ['CP', 'SCP'])
        ce_util, ce_unused = get_role_metrics(df, ['ACE', 'CE', 'SCE'])

        m1, m2, m3, m4 = st.columns(4)
        with m1:
            with st.container(border=True):
                st.metric("Team Avg Utilization", f"{avg_util:.0f}%", delta=f"{avg_util-100:.0f}%" if avg_util > 100 else None)
                st.caption(f"**Allocated:** {total_alloc} hrs  \n**Capacity:** {total_cap} hrs")
        with m2:
            st.metric("ACP Utilization", f"{acp_util:.0f}%")
            st.metric("ACP Unused Cap", f"{acp_unused:.0f} hrs")
        with m3:
            st.metric("CP/SCP Utilization", f"{cp_util:.0f}%")
            st.metric("CP/SCP Unused Cap", f"{cp_unused:.0f} hrs")
        with m4:
            st.metric("ACE/CE/SCE Util", f"{ce_util:.0f}%")
            st.metric("ACE/CE/SCE Unused", f"{ce_unused:.0f} hrs")

        st.divider()

        col_l, col_r = st.columns(2)
        
        # --- ALLOCATIONS BY PROGRAM (TABLE) ---
        with col_l:
            st.subheader("Allocations by Program")
            if prog_cols:
                # Sum and Sort Descending (Highest to Lowest)
                prog_sums = df[prog_cols].sum().sort_values(ascending=False)
                prog_sums = prog_sums[prog_sums > 0]
                
                # Convert to DataFrame for Table Display
                prog_table_df = prog_sums.reset_index()
                prog_table_df.columns = ['Program', 'Hours']
                
                st.dataframe(
                    prog_table_df,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Program": st.column_config.TextColumn("Program"),
                        "Hours": st.column_config.NumberColumn("Total Hours", format="%d")
                    }
                )
            else:
                st.info("No program data available.")

        # --- ALLOCATIONS BY EMPLOYEE (TABLE) ---
        with col_r:
            st.subheader("Allocations by Employee")
            
            # Filter out R+I Roles
            human_df = df.copy()
            if 'Role' in human_df.columns:
                mask = ~human_df['Role'].astype(str).str.upper().str.startswith("R+I")
                human_df = human_df[mask]

            # Sort Descending (Highest to Lowest)
            emp_sorted = human_df.sort_values('Current Hours to Target', ascending=False)
            
            # Prepare Table
            emp_table_df = emp_sorted[['Current Hours to Target']].reset_index()
            emp_table_df.columns = ['Employee', 'Utilization']
            
            st.dataframe(
                emp_table_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Employee": st.column_config.TextColumn("Employee"),
                    "Utilization": st.column_config.ProgressColumn(
                        "Utilization %", 
                        format="%d%%", 
                        min_value=0, 
                        max_value=100
                    )
                }
            )
            
        st.divider()
        st.subheader("Contributing Margin by Program")
        
        if margin_metrics:
            # Create Table DF
            table_data = []
            for prog, data in margin_metrics.items():
                table_data.append({
                    "Program": prog,
                    "Program MRR": f"${data['mrr']:,.0f}", 
                    "Contributing Margin": data['margin_pct']
                })
            
            margin_df = pd.DataFrame(table_data)
            margin_df = margin_df.sort_values(by="Contributing Margin", ascending=False)
            
            st.dataframe(
                margin_df, 
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Program": st.column_config.TextColumn("Program"),
                    "Program MRR": st.column_config.TextColumn("Program MRR"),
                    "Contributing Margin": st.column_config.NumberColumn("Contributing Margin", format="%.1f%%")
                }
            )
            
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
        render_role_column(t2, "CP / SCP", ['CP', 'SCP'])
        render_role_column(t3, "ACE / CE / SCE", ['ACE', 'CE', 'SCE'])

# --- PAGE: EDITOR ---
elif page == "✏️ Staffing Editor":
    st.title("✏️ Staffing Editor")
    view = st.radio("View:", ["Profile View (Detail)", "Grid View (Spreadsheet)"], horizontal=True)
    st.divider()

    if view == "Profile View (Detail)":
        focus = st.radio("Focus:", ["People", "Programs"], horizontal=True, label_visibility="collapsed")
        
        if focus == "People":
            all_emps = sorted(df.index.astype(str), key=str.casefold)
            
            # --- FILTER LOGIC: EXCLUDE IF ROLE STARTS WITH "R+I" ---
            filtered_emps = [
                e for e in all_emps 
                if not str(df.loc[e, 'Role']).strip().upper().startswith("R+I")
            ]
            
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
                        
                        edited = st.data_editor(
                            p_df.loc[to_edit], 
                            use_container_width=True, 
                            column_config={
                                "Hours": st.column_config.NumberColumn(min_value=0),
                                "Margin %": st.column_config.NumberColumn(format="%.1f%%", disabled=True)
                            }, 
                            key=f"ed_{name}"
                        )

                        if not edited['Hours'].equals(p_df.loc[to_edit, 'Hours']):
                            for prog, r in edited.iterrows():
                                st.session_state.df.at[name, prog] = r['Hours']
                            st.session_state.df = recalculate_utilization(st.session_state.df)
                            st.rerun()
        else:
            sel_progs = st.multiselect("Select Programs", sorted(prog_cols, key=str.casefold), placeholder="Select programs...")
            if sel_progs:
                for prog in sel_progs:
                    total = df[prog].sum()
                    
                    m_data = margin_metrics.get(prog, {})
                    margin_pct_disp = m_data.get('margin_pct', 0)
                    cost = m_data.get('cost', 0)
                    mrr = m_data.get('mrr', 0)
                    
                    with st.container(border=True):
                        st.subheader(f"{prog} (MRR: ${mrr:,.0f})")
                        c1, c2, c3 = st.columns(3)
                        c1.metric("Total Hours", f"{total} hrs")
                        c2.metric("Extended Cost", f"${cost:,.0f}")
                        c3.metric("Contr. Margin", f"{margin_pct_disp:.1f}%", delta_color="normal")
                        
                        t_df = pd.DataFrame(df[prog])
                        t_df.columns = ['Hours']
                        if 'Role' in df.columns: t_df = t_df.join(df['Role'])
                        active = t_df[t_df['Hours'] > 0].index.tolist()
                        
                        to_edit = st.multiselect(f"Team for {prog}", sorted(df.index.tolist(), key=str.casefold), default=active, key=f"psel_{prog}")
                        
                        edited = st.data_editor(t_df.loc[to_edit], use_container_width=True, column_config={"Hours": st.column_config.NumberColumn(min_value=0), "Role": st.column_config.TextColumn(disabled=True)}, key=f"ped_{prog}")

                        if not edited.equals(t_df.loc[to_edit]):
                            for emp, r in edited.iterrows():
                                st.session_state.df.at[emp, prog] = r['Hours']
                            st.session_state.df = recalculate_utilization(st.session_state.df)
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
            st.session_state.df.update(edited)
            st.session_state.df = recalculate_utilization(st.session_state.df)
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
                new_df = process_uploaded_file(up_file)
                if not new_df.empty:
                    if 'Employee' in new_df.columns: new_df = new_df.set_index('Employee')
                    new_df = recalculate_utilization(new_df)
                    st.session_state.df = new_df
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
                r = st.selectbox("Role", list(RATE_CARD.keys()))
                if st.form_submit_button("Add"):
                    if n and n not in st.session_state.df.index:
                        new_row = {c:0 for c in st.session_state.df.columns}
                        new_row['Role'] = r
                        new_row['Capacity'] = 152
                        st.session_state.df.loc[n] = pd.Series(new_row)
                        st.session_state.df = recalculate_utilization(st.session_state.df)
                        st.rerun()
        with c2:
            st.subheader("Delete Employee")
            all_emps = sorted(st.session_state.df.index.tolist(), key=str.casefold)
            del_emp = st.selectbox("Select Employee", ["Select..."] + all_emps)
            if st.button("Delete Employee", type="primary"):
                if del_emp != "Select...":
                    st.session_state.df = st.session_state.df.drop(index=[del_emp])
                    st.session_state.df = recalculate_utilization(st.session_state.df)
                    st.rerun()
                    
    with t3:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Add Program")
            n_prog = st.text_input("New Program Name")
            mrr_input = st.number_input("Program MRR ($)", min_value=0, value=0, step=1000)
            
            if st.button("Add Program"):
                if n_prog and n_prog not in st.session_state.df.columns:
                    st.session_state.df[n_prog] = 0
                    st.session_state.program_mrr[n_prog] = mrr_input
                    st.session_state.df = recalculate_utilization(st.session_state.df)
                    st.rerun()
        with c2:
            st.subheader("Delete Program")
            del_prog = st.selectbox("Select Program", ["Select..."] + sorted(prog_cols, key=str.casefold))
            if st.button("Delete Program", type="primary"):
                if del_prog != "Select...":
                    st.session_state.df = st.session_state.df.drop(columns=[del_prog])
                    if del_prog in st.session_state.program_mrr:
                        del st.session_state.program_mrr[del_prog]
                    st.session_state.df = recalculate_utilization(st.session_state.df)
                    st.rerun()
