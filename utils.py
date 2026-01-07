import pandas as pd
import streamlit as st
from datetime import datetime, timedelta

# --- CONSTANTS ---
STANDARD_CAPACITY = 152

RATE_CARD = {
    "ACP": 37, "CP": 54, "SCP": 54, "LCP": 89,
    "ACE": 89, "CE": 89, "SCE": 119,
    "R+I I": 44, "R+I II": 56, "R+I III": 89, "R+I IV": 135
}

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

        # --- 1. Map & Clean Date Columns ---
        # We try to find them, and if found, convert to datetime objects
        end_date_col = find_column(df, ['Assignment End Date', 'End Date'])
        future_date_col = find_column(df, ['Future Hours Date', 'Change Date', 'Effective Date'])
        
        # Helper to clean date strings
        def clean_dates(series):
            return pd.to_datetime(series, errors='coerce')

        if end_date_col:
            df[end_date_col] = clean_dates(df[end_date_col])
        if future_date_col:
            df[future_date_col] = clean_dates(df[future_date_col])

        # --- 2. Extract MRR ---
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
        
        # --- 3. Pivot Data (But keep Date columns!) ---
        ct_col = find_column(df, ['CT Name', 'Employee Name', 'Employee'])
        prog_col = find_column(df, ['Program Name', 'Program', 'Client'])
        role_col = find_column(df, ['Account Role', 'Role'])

        if ct_col and prog_col:
            hour_col = find_column(df, ['Allocated Monthly Hours', 'Allocated Hours', 'Hours'])
            future_hours_col = find_column(df, ['Future Allocated Hours', 'Future Hours'])

            if hour_col:
                # We need to preserve the date columns during the pivot/aggregation. 
                # Strategy: We will pivot the HOURS, but we need to keep the metadata (Dates/Future Hours) 
                # attached to the (Employee, Program) pair.
                
                # First, ensure numerics
                df[hour_col] = pd.to_numeric(df[hour_col], errors='coerce').fillna(0)
                if future_hours_col:
                    df[future_hours_col] = pd.to_numeric(df[future_hours_col], errors='coerce').fillna(0)

                # Create the Pivot for Current Hours (The core structure)
                pivot_df = df.pivot_table(index=ct_col, columns=prog_col, values=hour_col, aggfunc='sum').fillna(0)
                
                # --- NEW: Process Future Logic Row-by-Row ---
                # Because Pivot tables destroy row-level metadata, we need to re-attach this logic.
                # Ideally, the CSV is 1 row per Employee-Program assignment.
                # We will create a lookup dictionary for "Future State" details.
                
                # Unique Key for Lookup: (Employee, Program)
                future_state_map = {}
                
                today = pd.Timestamp.now()

                for idx, row in df.iterrows():
                    emp = row[ct_col]
                    prog = row[prog_col]
                    key = (emp, prog)
                    
                    current_hrs = row[hour_col]
                    fut_hrs = row[future_hours_col] if future_hours_col else current_hrs
                    end_date = row[end_date_col] if end_date_col else pd.NaT
                    change_date = row[future_date_col] if future_date_col else pd.NaT
                    
                    # --- THE LOGIC HIERARCHY ---
                    final_future_hrs = current_hrs
                    status_msg = "Stable"
                    
                    # 1. Check Churn (End Date within 30 days)
                    if pd.notna(end_date) and (end_date - today).days <= 30:
                        final_future_hrs = 0
                        status_msg = f"🔴 Rolling off ({end_date.strftime('%b %d')})"
                    
                    # 2. Check Ramp/Change (Change Date within 60 days)
                    elif pd.notna(change_date) and (change_date - today).days <= 60:
                        if fut_hrs != current_hrs:
                            final_future_hrs = fut_hrs
                            direction = "Increasing" if fut_hrs > current_hrs else "Decreasing"
                            status_msg = f"🟢 {direction} to {int(fut_hrs)}h ({change_date.strftime('%b %d')})"
                    
                    future_state_map[key] = {
                        'future_hours': final_future_hrs,
                        'status': status_msg
                    }
                
                # Attach Role
                if role_col:
                    roles = df[[ct_col, role_col]].drop_duplicates(subset=ct_col).groupby(ct_col).first()
                    final_df = roles.join(pivot_df).reset_index()
                    final_df = final_df.rename(columns={ct_col: 'Employee', role_col: 'Role'})
                else:
                    final_df = pivot_df.reset_index().rename(columns={ct_col: 'Employee'})
                
                return final_df, new_mrr_map, future_state_map

        if ct_col and ct_col != 'Employee':
            df = df.rename(columns={ct_col: 'Employee'})

        return df, new_mrr_map, {}

    except Exception as e:
        st.error(f"Error processing file: {e}")
        return pd.DataFrame(), {}, {}

def recalculate_utilization(df):
    """Updates the 'Current Hours to Target' column."""
    if df.empty: return df
    exclude = ['Capacity', 'Current Hours to Target']
    prog_cols = [c for c in df.select_dtypes(include=['number']).columns if c not in exclude]
    total_hours = df[prog_cols].sum(axis=1)
    if 'Capacity' not in df.columns:
        col_idx = 1 if 'Role' in df.columns else 0
        df.insert(col_idx, 'Capacity', STANDARD_CAPACITY)
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

def calculate_margin(df, program_mrr_dict, future_map=None):
    """
    Calculates Current AND Projected Margin.
    future_map: dict {(Employee, Program): {'future_hours': x, 'status': y}}
    """
    if df.empty: return {}
    exclude = ['Capacity', 'Current Hours to Target']
    prog_cols = [c for c in df.select_dtypes(include=['number']).columns if c not in exclude]
    
    margin_data = {} 
    
    # Init trackers
    prog_cost_current = {p: 0.0 for p in prog_cols}
    prog_cost_future = {p: 0.0 for p in prog_cols}
    
    for idx, row in df.iterrows():
        emp_name = row.get('Employee') # Should be index or column depending on context
        # If Employee is index, use row.name
        if 'Employee' not in row: emp_name = row.name 
        
        role = row.get('Role', '')
        rate = get_rate(role)
        
        for prog in prog_cols:
            curr_hours = row.get(prog, 0)
            
            # Look up future hours if map exists
            fut_hours = curr_hours
            if future_map:
                f_data = future_map.get((emp_name, prog))
                if f_data:
                    fut_hours = f_data['future_hours']

            # Cost Math
            prog_cost_current[prog] += (curr_hours * rate)
            prog_cost_future[prog] += (fut_hours * rate)
            
    for prog in prog_cols:
        mrr = program_mrr_dict.get(prog, 0)
        
        # Calc Current Margin
        margin_curr = 0.0
        if mrr > 0: margin_curr = ((mrr - prog_cost_current[prog]) / mrr) * 100
        else: margin_curr = -100.0 if prog_cost_current[prog] > 0 else 0.0
        
        # Calc Future Margin
        margin_fut = 0.0
        if mrr > 0: margin_fut = ((mrr - prog_cost_future[prog]) / mrr) * 100
        else: margin_fut = -100.0 if prog_cost_future[prog] > 0 else 0.0

        margin_data[prog] = {
            'mrr': mrr,
            'margin_pct': margin_curr,
            'margin_fut': margin_fut,
            'delta': margin_fut - margin_curr
        }
    return margin_data

def calculate_group_utilization(df, role_list):
    if 'Role' not in df.columns or df.empty: return 0, 0, 0 
    mask = df['Role'].astype(str).str.upper().isin([r.upper() for r in role_list])
    role_df = df[mask]
    if role_df.empty: return 0, 0, 0
    exclude = ['Capacity', 'Current Hours to Target']
    prog_cols = [c for c in role_df.select_dtypes(include=['number']).columns if c not in exclude]
    total_allocated_hours = role_df[prog_cols].sum().sum()
    count_employees = len(role_df)
    total_capacity = count_employees * STANDARD_CAPACITY
    utilization_pct = 0
    if total_capacity > 0: utilization_pct = (total_allocated_hours / total_capacity) * 100
    return utilization_pct, total_allocated_hours, total_capacity
