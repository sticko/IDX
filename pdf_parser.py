import os
import numpy as np
import pdfplumber
import pandas as pd
import re

RESULT_DIR = "results"
os.makedirs(RESULT_DIR, exist_ok=True)

def parse_shareholder_pdf(pdf_path: str, log_callback=None) -> pd.DataFrame:
    pdf_filename = os.path.basename(pdf_path)
    csv_filename = os.path.splitext(pdf_filename)[0] + ".csv"
    csv_path = os.path.join(RESULT_DIR, csv_filename)

    if os.path.exists(csv_path):
        if log_callback:
            log_callback(f"CSV already exists, loading from {csv_path}")
        return pd.read_csv(csv_path)

    all_rows = []
    final_header = None

    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        for idx, page in enumerate(pdf.pages[1:], start=2):
            if log_callback:
                log_callback(f"Processing page {idx-1} of {total_pages-1}...")
            
            table = page.extract_table()
            if not table or len(table) < 3:
                continue

            if final_header is None:
                header = table[0]
                temp_header = []
                i = 0
                while i < len(header):
                    h = (header[i] or "").strip()
                    if "kepemilikan per" in h.lower():
                        m = re.search(r"(\d{1,2}-[A-Z]{3}-\d{4})", h)
                        date_str = m.group(1) if m else "Unknown"
                        temp_header.extend([
                            f"Kepemilikan Per {date_str} - Jumlah Saham",
                            f"Kepemilikan Per {date_str} - Saham Gabungan Per Investor",
                            f"Kepemilikan Per {date_str} - Persentase Kepemilikan Per Investor (%)"
                        ])
                        i += 3
                    else:
                        temp_header.append(h if h else f"Col_{i}")
                        i += 1
                final_header = temp_header

            data = table[2:]
            for row in data:
                if len(row) == len(final_header):
                    all_rows.append(row)

    if not all_rows:
        return pd.DataFrame()

    df = pd.DataFrame(all_rows, columns=final_header)

    # Clean text: remove commas, newlines, and placeholder strings
    for col in df.columns:
        df[col] = (df[col].astype(str).str.strip()
                   .replace([r"[\n\r]", "None", "none", "nan", "NaN"], [" ", "", "", "", ""], regex=True)
                   .str.replace(",", "", regex=False))

    # Calculate Individual Share Changes
    sh_cols = [c for c in df.columns if "Jumlah Saham" in c]
    if len(sh_cols) >= 2:
        prev_sh, curr_sh = sh_cols[-2], sh_cols[-1]
        df[prev_sh] = pd.to_numeric(df[prev_sh], errors="coerce").fillna(0)
        df[curr_sh] = pd.to_numeric(df[curr_sh], errors="coerce").fillna(0)
        df["Perubahan_Shares"] = df[curr_sh] - df[prev_sh]

    # Calculate Individual Percentage Changes
    perc_cols = [c for c in df.columns if "Persentase" in c or "%" in c]
    if len(perc_cols) >= 2:
        p_prev, p_curr = perc_cols[-2], perc_cols[-1]
        df[p_prev] = pd.to_numeric(df[p_prev], errors="coerce").fillna(0)
        df[p_curr] = pd.to_numeric(df[p_curr], errors="coerce").fillna(0)
        df["Perubahan_Pct"] = df[p_curr] - df[p_prev]

    # Filter: Remove all rows where no movement occurred
    if "Perubahan_Shares" in df.columns:
        filtered_df = df[df["Perubahan_Shares"] != 0].copy()
    else:
        filtered_df = df.copy()

    # Save to CSV and return
    filtered_df.to_csv(csv_path, index=False)
    return filtered_df
