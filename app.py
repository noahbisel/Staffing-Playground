import streamlit as st
import pandas as pd
import plotly.express as px
import os

# --- 1. APP CONFIGURATION ---
st.set_page_config(page_title="Staffing OS", layout="wide", page_icon="👥")
DATA_FILE = 'staffing_db.csv'

# --- 2. UTILITY FUNCTIONS (THE ENGINE) ---

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
        
        # 1. Clean Unwanted Columns
        mrr_col = find_column(df, ['Program MRR', 'MRR'])
        if mrr_col: df = df.drop(columns=[mrr_col])
        
        # 2. Identify Key Columns
        ct_col = find_column(df, ['CT Name', 'Employee Name', 'Employee'])
        prog_col = find_column(df, ['Program Name', 'Program', 'Client'])
        role_col = find_column(df, ['Account Role', 'Role'])
        
        # 3. Pivot if "Transactional" (Long) format
        if ct_col and prog_col:
            st.toast("Processing Data...", icon="🔄")
            hour_col = find_column(df, ['Allocated Monthly Hours', 'Allocated Hours', 'Hours'])
            # Fallback search
            if not hour_col:
                found = [c for c in df.columns if 'Allocated' in c]
                if found: hour_col = found[0]
            
            if hour_col:
                df[hour_col] = pd.to_numeric(df[hour_col], errors='coerce').fillna(0)
                pivot_df = df.pivot_table(index=ct_col, columns=prog_col, values=hour_col, aggfunc='sum').fillna(0)
                
                # Re-attach Roles
                if role_col:
                    roles = df[[ct_col, role_col]].drop_duplicates(subset=ct_col).groupby(ct_col).first()
                    final_df = roles.join(pivot_df).reset_index()
                    final_df = final_df.rename(columns={ct_col: 'Employee', role_col: 'Role'})
                else:
                    final_df = pivot_df.reset_index().rename(columns={ct_col: 'Employee'})
                
                return final_df
                
        # 4. Fallback: Rename 'CT Name' to 'Employee' if pivot wasn't needed
        if ct_col and ct_col != 'Employee':
            df = df.rename(columns={ct_col: 'Employee'})
            
        return df

    except Exception as e:
        st.error(f"Error processing file: {e}")
        return pd.DataFrame()

def save_to_disk(df):
    """Saves DataFrame to CSV, ensuring 'Employee' is a column."""
    try:
        save_df = df.copy()
        if save_df.index.name == 'Employee':
            save_df = save_df.reset_index()
        save_df.to_csv(DATA_FILE, index=False)
    except Exception as e:
        st.error(f"Save Failed: {e}")

def recalculate_utilization(df):
    """Updates the 'Current Hours to Target' column based on allocated hours."""
    if df.empty: return df
    
    # Identify Program Columns (Numeric, not Metadata)
    exclude = ['Capacity', 'Current Hours to Target']
    prog_cols = [c for c in df.select_dtypes(include=['number']).columns if c not in exclude]
    
    total_hours = df[prog_cols].sum(axis=1)
    
    # Ensure Capacity exists
    if 'Capacity' not in df.columns:
        col_idx = 1 if 'Role' in df.columns else 0
        df.insert(col_idx, 'Capacity', 152)
    
    # Calculate %
    # Safe division to avoid crashing on 0 capacity
    util = df.apply(lambda x: (total_hours[x.name] / x['Capacity'] * 100) if x['Capacity'] > 0 else 0, axis=1)
    df['Current Hours to Target'] = util.round(0).astype(int)
    
    return df

def render_employee_card(name, row):
    """Reusable UI component for displaying an employee."""
    util = row.get('Current Hours to Target', 0)
    role = row.get('Role', 'N/A')
    
    # Color Logic
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
    """Calculates Avg Util and Unused Capacity for a list of roles."""
    if 'Role' not in df.columns: return 0, 0
    
    # Filter by role (case insensitive)
    # Handle NaN roles by converting to string first
    mask = df['Role'].astype(str).str.upper().isin([r.upper() for r in role_list])
    role_df = df[mask]
    
    if role_df.empty: return 0, 0
    
    avg_util = role_df['Current Hours to Target'].mean()
    
    # Unused Cap = Total Cap - Total Allocated
    total_cap = role_df['Capacity'].sum()
    
    # Calculate allocated hours
    exclude = ['Capacity', 'Current Hours to Target']
    # Use global prog_cols logic here essentially
    p_cols = [c for c in role_df.select_dtypes(include=['number']).columns if c not in exclude]
    total_alloc = role_df[p_cols].sum().sum()
    
    unused_cap = total_cap - total_alloc
    
    return avg_util, unused_cap

# --- 3. INIT & LOAD ---
if 'df' not in st.session_state:
    if os.path.exists(DATA_FILE):
        try:
            df = pd.read_csv(DATA_FILE)
            if 'Employee' in df.columns: df = df.set_index('Employee')
            st.session_state.df = recalculate_utilization(df)
        except: st.session_state.df = pd.DataFrame()
    else:
        # Initial Mock Data
        data = {
            'Employee': ['Mitch Ursick', 'Noah Bisel', 'Kevin Steger', 'Nicki Williams'],
            'Role': ['CSM', 'CE', 'CP', 'CE'],
            'Capacity': [152, 152, 152, 152],
            'Accenture': [10, 80, 20, 0],
            'Google': [60, 20, 60, 15]
        }
        df = pd.DataFrame(data).set_index('Employee')
        st.session_state.df = recalculate_utilization(df)
        save_to_disk(st.session_state.df)

# --- 4. GLOBAL CALCULATIONS (Must run before Pages) ---
# This ensures 'prog_cols' is available to ALL pages, fixing the NameError
df = st.session_state.df
prog_cols = []
if not df.empty:
    numeric_cols = df.select_dtypes(include=['number']).columns
    exclude_cols = ['Capacity', 'Current Hours to Target']
    prog_cols = [c for c in numeric_cols if c not in exclude_cols]

# --- 5. NAVIGATION ---
st.sidebar.title("Staffing OS")
page = st.sidebar.radio("Navigate", ["📊 Dashboard", "✏️ Staffing Editor", "⚙️ Settings"], label_visibility="collapsed")
st.sidebar.markdown("---")

# --- PAGE: DASHBOARD ---
if page == "📊 Dashboard":
    st.title("📊 Executive Dashboard")
    
    if not df.empty:
        # --- TOP METRICS ROW ---
        # 1. Total Team Stats (The "North Star" Metric)
        avg_util = df['Current Hours to Target'].mean()
        total_cap = df['Capacity'].sum()
        total_alloc = df[prog_cols].sum().sum()
        
        # 2. Role Specific Stats
        acp_util, acp_unused = get_role_metrics(df, ['ACP'])
        cp_util, cp_unused = get_role_metrics(df, ['CP', 'SCP'])
        ce_util, ce_unused = get_role_metrics(df, ['ACE', 'CE', 'SCE'])
        
        # Layout: 4 Columns
        m1, m2, m3, m4 = st.columns(4)
        
        # Col 1: Team Overview (Grouped)
        with m1:
            with st.container(border=True):
                st.metric("Team Avg Utilization", f"{avg_util:.0f}%", delta=f"{avg_util-100:.0f}%" if avg_util > 100 else None)
                st.caption(f"**Allocated:** {total_alloc} hrs  \n**Capacity:** {total_cap} hrs")

        # Col 2: ACP
        with m2:
            st.metric("ACP Utilization", f"{acp_util:.0f}%")
            st.metric("ACP Unused Cap", f"{acp_unused:.0f} hrs")
            
        # Col 3: CP/SCP
        with m3:
            st.metric("CP/SCP Utilization", f"{cp_util:.0f}%")
            st.metric("CP/SCP Unused Cap", f"{cp_unused:.0f} hrs")

        # Col 4: ACE/CE/SCE
        with m4:
            st.metric("ACE/CE/SCE Util", f"{ce_util:.0f}%")
            st.metric("ACE/CE/SCE Unused", f"{ce_unused:.0f} hrs")
        
        st.divider()
        
        # --- CHARTS ROW ---
        col_l, col_r = st.columns(2)
        
        with col_l:
            st.subheader("Allocations by Program")
            if prog_cols:
                prog_sums = df[prog_cols].sum().sort_values(ascending=True)
                # Filter out 0 programs for cleaner chart
                prog_sums = prog_sums[prog_sums > 0]
                
                fig = px.bar(prog_sums, orientation='h', labels={'index':'Program', 'value':'Hours'})
                # Update X-Axis to tick by 25
                fig.update_xaxes(dtick=25)
                fig.update_layout(showlegend=False, margin=dict(l=0,r=0,t=0,b=0), height=350)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No program data available.")
            
        with col_r:
            st.subheader("Allocations by Employee")
            # Sort employees by utilization
            emp_sorted = df.sort_values('Current Hours to Target', ascending=True)
            
            fig = px.bar(
                emp_sorted, 
                x='Current Hours to Target', 
                y=emp_sorted.index, 
                orientation='h',
                labels={'Current Hours to Target': 'Utilization %', 'Employee': ''},
                text='Current Hours to Target'
            )
            fig.update_traces(texttemplate='%{text}%', textposition='outside')
            fig.add_vline(x=100, line_dash="dash", line_color="red", annotation_text="100%")
            fig.update_layout(showlegend=False, margin=dict(l=0,r=0,t=0,b=0), height=350)
            st.plotly_chart(fig, use_container_width=True)
            
        st.divider()
        
        # --- TEAM OVERVIEW COLUMNS ---
        st.subheader("Team Overview")
        
        t1, t2, t3 = st.columns(3)
        
        # Helper to render sorted cards for a role group
        def render_role_column(container, title, roles):
            with container:
                st.markdown(f"### {title}")
                if 'Role' in df.columns:
                    # Filter
                    mask = df['Role'].astype(str).str.upper().isin([r.upper() for r in roles])
                    group_df = df[mask].sort_values('Current Hours to Target', ascending=False)
                    
                    if group_df.empty:
                        st.info("No employees.")
                    else:
                        for name, row in group_df.iterrows():
                            render_employee_card(name, row)
                else:
                    st.warning("No Role data.")

        # Column 1: ACP
        render_role_column(t1, "ACP", ['ACP'])
        
        # Column 2: CP / SCP
        render_role_column(t2, "CP / SCP", ['CP', 'SCP'])
        
        # Column 3: ACE / CE / SCE
        render_role_column(t3, "ACE / CE / SCE", ['ACE', 'CE', 'SCE'])

# --- PAGE: EDITOR ---
elif page == "✏️ Staffing Editor":
    st.title("✏️ Staffing Editor")
    
    # View Toggle (Profile First)
    view = st.radio("View:", ["Profile View (Detail)", "Grid View (Spreadsheet)"], horizontal=True)
    st.divider()
    
    if view == "Profile View (Detail)":
        focus = st.radio("Focus:", ["People", "Programs"], horizontal=True, label_visibility="collapsed")
        
        if focus == "People":
            sel_emps = st.multiselect("Select Employees", sorted(df.index.astype(str)), placeholder="Select people to edit...")
            if sel_emps:
                for name in sel_emps:
                    if name in df.index:
                        # Use Reusable Card for Header
                        render_employee_card(name, df.loc[name])
                        
                        # Detail Editor
                        row = df.loc[name]
                        # Create mini DF for editing
                        p_df = pd.DataFrame(row[prog_cols])
                        p_df.columns = ['Hours']
                        active = p_df[p_df['Hours'] > 0].index.tolist()
                        
                        # Selector
                        to_edit = st.multiselect(f"Programs for {name}", prog_cols, default=active, key=f"sel_{name}")
                        
                        # Editor
                        edited = st.data_editor(
                            p_df.loc[to_edit], 
                            use_container_width=True,
                            column_config={"Hours": st.column_config.NumberColumn(min_value=0)},
                            key=f"ed_{name}"
                        )
                        
                        # Save
                        if not edited.equals(p_df.loc[to_edit]):
                            for prog, r in edited.iterrows():
                                st.session_state.df.at[name, prog] = r['Hours']
                            st.session_state.df = recalculate_utilization(st.session_state.df)
                            save_to_disk(st.session_state.df)
                            st.rerun()
                            
        else: # Focus: Programs
            sel_progs = st.multiselect("Select Programs", sorted(prog_cols), placeholder="Select programs...")
            if sel_progs:
                for prog in sel_progs:
                    total = df[prog].sum()
                    with st.container(border=True):
                        st.subheader(prog)
                        st.metric("Total Hours", f"{total} hrs")
                        
                        # Team Editor
                        t_df = pd.DataFrame(df[prog])
                        t_df.columns = ['Hours']
                        if 'Role' in df.columns: t_df = t_df.join(df['Role'])
                        
                        active = t_df[t_df['Hours'] > 0].index.tolist()
                        to_edit = st.multiselect(f"Team for {prog}", df.index.tolist(), default=active, key=f"psel_{prog}")
                        
                        edited = st.data_editor(
                            t_df.loc[to_edit],
                            use_container_width=True,
                            column_config={
                                "Hours": st.column_config.NumberColumn(min_value=0),
                                "Role": st.column_config.TextColumn(disabled=True)
                            },
                            key=f"ped_{prog}"
                        )
                        
                        if not edited.equals(t_df.loc[to_edit]):
                            for emp, r in edited.iterrows():
                                st.session_state.df.at[emp, prog] = r['Hours']
                            st.session_state.df = recalculate_utilization(st.session_state.df)
                            save_to_disk(st.session_state.df)
                            st.rerun()

    else: # Grid View
        c1, c2 = st.columns([2, 1])
        search = c1.text_input("🔍 Search", placeholder="Filter by name...")
        
        # Smart Filters
        df_view = df.copy()
        if search:
            mask = df_view.index.astype(str).str.contains(search, case=False)
            df_view = df_view[mask]
        
        # Hide Empty Columns
        active_progs = [c for c in prog_cols if df_view[c].sum() > 0]
        sel_cols = st.multiselect("Active Programs (Add to view)", prog_cols, default=active_progs)
        
        cols_to_show = [c for c in df_view.columns if c not in prog_cols] + sel_cols
        
        edited = st.data_editor(
            df_view[cols_to_show],
            use_container_width=True,
            column_config={"Current Hours to Target": st.column_config.ProgressColumn("Util %", format="%d%%", min_value=0, max_value=100)},
            disabled=['Current Hours to Target'],
            key="grid_main"
        )
        
        if not edited.equals(df_view[cols_to_show]):
            st.session_state.df.update(edited)
            st.session_state.df = recalculate_utilization(st.session_state.df)
            save_to_disk(st.session_state.df)
            st.rerun()

# --- PAGE: SETTINGS ---
elif page == "⚙️ Settings":
    st.title("⚙️ Settings")
    t1, t2, t3 = st.tabs(["📥 Data Import", "👤 People", "🏢 Programs"])
    
    with t1:
        st.info("Upload a CSV to overwrite the database.")
        up_file = st.file_uploader("Upload CSV", type=['csv'])
        if up_file:
             if 'last_processed' not in st.session_state or st.session_state.last_processed != up_file.name:
                new_df = process_uploaded_file(up_file)
                if not new_df.empty:
                    # STRICT INDEX ENFORCEMENT
                    if 'Employee' in new_df.columns: new_df = new_df.set_index('Employee')
                    new_df = recalculate_utilization(new_df)
                    
                    st.session_state.df = new_df
                    st.session_state.last_processed = up_file.name
                    save_to_disk(new_df)
                    st.success("Database Updated!")
                    st.rerun()
                    
        if st.button("⚠️ Factory Reset", type="primary"):
            if os.path.exists(DATA_FILE): os.remove(DATA_FILE)
            st.session_state.clear()
            st.rerun()

    with t2:
        with st.form("new_emp"):
            st.subheader("Add Employee")
            n = st.text_input("Name")
            r = st.text_input("Role")
            if st.form_submit_button("Add"):
                if n and n not in st.session_state.df.index:
                    new_row = {c:0 for c in st.session_state.df.columns}
                    new_row['Role'] = r
                    new_row['Capacity'] = 152
                    # Append logic for Index-based DF
                    st.session_state.df.loc[n] = pd.Series(new_row)
                    save_to_disk(st.session_state.df)
                    st.rerun()
                    
    with t3:
        c1, c2 = st.columns(2)
        with c1:
            n_prog = st.text_input("New Program Name")
            if st.button("Add Program"):
                if n_prog and n_prog not in st.session_state.df.columns:
                    st.session_state.df[n_prog] = 0
                    save_to_disk(st.session_state.df)
                    st.rerun()
        with c2:
            del_prog = st.selectbox("Delete Program", ["Select..."] + sorted(prog_cols))
            if st.button("Delete"):
                if del_prog != "Select...":
                    st.session_state.df = st.session_state.df.drop(columns=[del_prog])
                    save_to_disk(st.session_state.df)
                    st.rerun()