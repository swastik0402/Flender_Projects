import streamlit as st
import pandas as pd
import re
import io
import os
from mistral_server import query_mistral  # type: ignore

# --------------------- Page Settings ---------------------
st.set_page_config(page_title="Breakdown Chatbot", layout="centered")
st.title("Breakdown Chatbot")

# --------------------- Theme Styling ---------------------
bg_color = "#f9f9f9"
text_color = "#1c1c1c"
border_color = "#005A9C"
button_bg = "#005A9C"
button_text = "#ffffff"
hover_color = "#003f6f"

st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap');
    html, body, [class*="st-"] {{
        font-family: 'Inter', sans-serif;
    }}
    .stApp {{
        background-color: {bg_color};
        color: {text_color};
    }}
    header[data-testid="stHeader"] {{
        background-color: white !important;
        color: black !important;
        border-bottom: 1px solid #ddd;
    }}
    div, p, span, label, h1, h2, h3, h4, h5, h6 {{
        color: {text_color} !important;
    }}
    button[kind="secondary"] {{
        background-color: {button_bg} !important;
        color: {button_text} !important;
        border: none !important;
        border-radius: 6px;
        padding: 0.6rem 1.2rem;
        font-weight: 600;
    }}
    button[kind="secondary"]:hover {{
        background-color: {hover_color} !important;
    }}
    </style>
""", unsafe_allow_html=True)

# --------------------- Load Excel File ---------------------
EXCEL_PATH = "BK Dwn May'25.xlsx"
if not os.path.exists(EXCEL_PATH):
    st.error("❌ Excel file not found in the app directory.")
    st.stop()

try:
    df = pd.read_excel(EXCEL_PATH, engine='openpyxl')
    df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    df.columns = df.columns.str.strip()
    st.success("✅ Data loaded from backend Excel file.")
except Exception as e:
    st.error(f"❗ Error reading Excel file: {e}")
    st.stop()

# --------------------- Normalize Function ---------------------
def normalize(text):
    return re.sub(r'[^a-zA-Z0-9]', '', str(text).lower())

# --------------------- Session State Setup ---------------------
if "query" not in st.session_state:
    st.session_state.query = ""
if "last_query" not in st.session_state:
    st.session_state.last_query = ""

# --------------------- Query Input & Suggestions ---------------------
query_input = st.text_input(
    "🔍 Type your query (Machine Name or Problem):",
    value=st.session_state.get("query", "")
)

# Sync input
if query_input != st.session_state.get("last_query", ""):
    st.session_state.query = query_input
    st.session_state.last_query = query_input

# Build suggestions: show unique Machine Names AND unique (Problem + Machine Name) pairs
all_suggestions = []

# Add Machine Name suggestions
machine_names = df['Machine Name'].dropna().astype(str).unique()
all_suggestions.extend(machine_names)

# Add Problem by Machine Name suggestions
problem_rows = df[['Problem', 'Machine Name']].dropna()
problem_rows = problem_rows.astype(str).drop_duplicates()
problem_suggestions = [
    f"{row['Problem']} by {row['Machine Name']}" for _, row in problem_rows.iterrows()
]
all_suggestions.extend(problem_suggestions)

matches = []
if st.session_state.query:
    norm_query = normalize(st.session_state.query)
    matches = [s for s in all_suggestions if norm_query in normalize(s)]

if matches:
    st.markdown("### 💡 Suggestions (click to auto-fill):")
    for match in matches[:10]:
        if st.button(f"➡️ {match}"):
            st.session_state['query'] = match
            st.session_state['last_query'] = match
            st.rerun()

# --------------------- Search & Mistral Explanation ---------------------
if st.session_state.query:
    norm_final = normalize(st.session_state.query)
    matched_rows = []

    for _, row in df.iterrows():
        machine_norm = normalize(str(row.get('Machine Name', '')))
        problem_norm = normalize(str(row.get('Problem', '')))
        combined_norm = normalize(f"{row.get('Problem', '')} by {row.get('Machine Name', '')}")

        if norm_final in machine_norm or norm_final in problem_norm or norm_final in combined_norm:
            matched_rows.append(row)

    if matched_rows:
        df_result = pd.DataFrame(matched_rows).reset_index(drop=True)
        st.markdown(f"### 🔍 Matching Results ({len(df_result)} found):")
        st.dataframe(df_result)

        if len(df_result) == 1:
            user_prompt = (
                f"Here is the data for query: '{st.session_state.query}'. "
                f"Explain the details and any insights.\n\n{df_result.to_string(index=False)}"
            )
        else:
            problem_counts = df_result['Problem'].value_counts().reset_index()
            problem_counts.columns = ['Problem', 'Count']
            summary = problem_counts.to_string(index=False)

            user_prompt = (
                f"The query '{st.session_state.query}' matches {len(df_result)} rows. "
                f"Analyze the problems, starting with the most common one. "
                f"Provide possible causes, suggestions, and order them by frequency.\n\n"
                f"Problem summary:\n{summary}\n\n"
                f"Details of matches:\n{df_result.to_string(index=False)}"
            )

        response = query_mistral(user_prompt)
        st.markdown("### 🧠 Explanation & Suggestions:")
        st.info(response)
    else:
        st.warning("❌ No matches found.")

# --------------------- Manual Entry Section ---------------------
st.markdown("---")
st.subheader("✍️ Manually Add New Data Entry (Real-time)")

if "manual_inputs" not in st.session_state:
    st.session_state.manual_inputs = {col: "" for col in df.columns}
if "confirm_add" not in st.session_state:
    st.session_state.confirm_add = False
if "form_cleared" not in st.session_state:
    st.session_state.form_cleared = False

with st.form("manual_entry_form"):
    for col in df.columns:
        key = f"input_{col.replace(' ', '_')}"
        if key not in st.session_state or st.session_state.form_cleared:
            st.session_state[key] = ""
        st.session_state.manual_inputs[col] = st.text_input(
            f"Enter value for **{col}**",
            value=st.session_state[key],
            key=key
        )
    st.session_state.form_cleared = False
    confirm = st.form_submit_button("➕ Add Row")

if confirm:
    st.session_state.confirm_add = True

if st.session_state.confirm_add:
    st.warning("Are you sure you want to add this row?")
    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("✅ Yes, Add"):
            df = pd.concat([df, pd.DataFrame([st.session_state.manual_inputs])], ignore_index=True)
            df.to_excel(EXCEL_PATH, index=False, engine='openpyxl')
            st.success("✅ Row added successfully!")
            st.markdown("### 📌 Updated Data (last 5 rows):")
            st.dataframe(df.tail(5))

            buffer = io.BytesIO()
            df.to_excel(buffer, index=False, engine='openpyxl')
            buffer.seek(0)
            st.download_button(
                label="📥 Download Updated Excel",
                data=buffer,
                file_name="updated_data.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

            for col in df.columns:
                key = f"input_{col.replace(' ', '_')}"
                if key in st.session_state:
                    del st.session_state[key]
            st.session_state.manual_inputs = {col: "" for col in df.columns}
            st.session_state.confirm_add = False

    with col2:
        if st.button("❌ Cancel"):
            st.session_state.confirm_add = False

if st.button("🧹 Clear Form"):
    for col in df.columns:
        key = f"input_{col.replace(' ', '_')}"
        if key in st.session_state:
            del st.session_state[key]
    st.session_state.manual_inputs = {col: "" for col in df.columns}
    st.session_state.form_cleared = True
    st.rerun()
