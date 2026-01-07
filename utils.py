import pandas as pd
import streamlit as st

# --- CONSTANTS ---
RATE_CARD = {
    "ACP": 37, 
    "CP": 54, 
    "CE": 89, 
    "SCE": 119,
    "LCP": 89,
    "R+I I": 44, 
    "R+I II": 56, 
    "R+I III": 89, 
    "R+I IV": 135
}

# Roles that contribute to the "Team Avg Utilization" metric
TEAM_ROLES = ['ACP', 'CP', 'SCP', 'LCP', 'ACE', 'CE', 'SCE']

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
            except: pass
            df = df.drop(columns=[mrr_col])
        
        ct_col = find_column(df, ['CT Name', 'Employee Name', 'Employee'])
        prog_col = find_column(df, ['Program Name', 'Program', 'Client'])
        role_col = find_column(df, ['Account Role', 'Role'])

        if ct_col and prog_col:
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

                return final_df, new_mrr_map

        if ct_col and ct_col != 'Employee':
            df = df.rename(columns={ct_col: 'Employee'})

        return df, new_mrr_map

    except Exception as e:
        st.error(f"Error processing file: {e}")
        return pd.DataFrame(), {}

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
    if not role_name: return 0
    role_clean = str(role_name).strip().upper()
    if role_clean in RATE_CARD: return RATE_CARD[role_clean]
    for key, rate in RATE_CARD.items():
        if key in role_clean: return rate
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
        margin_data[prog] = {'mrr': mrr, 'cost': cost, 'margin_pct': margin_pct}
    return margin_data

def calculate_group_utilization(df, role_list):
    """
    New Math: Total Hours / (Count of Employees * 152)
    Filters DF for the specific role list before calculating.
    """
    if 'Role' not in df.columns or df.empty:
        return 0, 0, 0 

    mask = df['Role'].astype(str).str.upper().isin([r.upper() for r in role_list])
    role_df = df[mask]
    
    if role_df.empty:
        return 0, 0, 0

    exclude = ['Capacity', 'Current Hours to Target']
    prog_cols = [c for c in role_df.select_dtypes(include=['number']).columns if c not in exclude]
    
    total_allocated_hours = role_df[prog_cols].sum().sum()
    count_employees = len(role_df)
    total_capacity = count_employees * 152
    
    utilization_pct = 0
    if total_capacity > 0:
        utilization_pct = (total_allocated_hours / total_capacity) * 100
        
    return utilization_pct, total_allocated_hours, total_capacity
