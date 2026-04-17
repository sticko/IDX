from datetime import datetime, timedelta
import threading
import sys
import webbrowser
import pandas as pd
import numpy as np
import ttkbootstrap as tb
from ttkbootstrap.constants import *
from ttkbootstrap.dialogs import Messagebox
from ttkbootstrap.widgets import ToolTip
import yfinance as yf
from pdf_parser import parse_shareholder_pdf
from idx_fetcher import fetch_idx_pdf
from helper import resource_path

# ---------- Window Setup ----------
root = tb.Window(themename="litera")
root.iconbitmap(resource_path("assets/app.ico"))
root.title("IDX Shareholder Analytics")
root.geometry("1300x950")

mode_var = tb.StringVar(value="latest")
simple_view_var = tb.BooleanVar(value=True)
table_df = pd.DataFrame()

# ---------- UI Layout ----------
top_frame = tb.Frame(root, padding=10)
top_frame.pack(fill="x")

def safe_exit():
    """Direct exit without prompt."""
    root.destroy()
    sys.exit()

def export_to_excel():
    if table_df.empty:
        Messagebox.show_warning("No data to export.", "Warning"); return
    filename = f"IDX_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    try:
        table_df.to_excel(filename, index=False)
        Messagebox.show_info(f"Saved to {filename}", "Success")
    except Exception as e: 
        Messagebox.show_error(str(e), "Error")

exit_btn = tb.Button(top_frame, text="Exit", bootstyle="danger", command=safe_exit, width=10)
exit_btn.pack(side="right", anchor="n", padx=5)

# TOOLTIP FIX: Assigned to variables
tt_exit = ToolTip(exit_btn, text="Close the application safely", bootstyle=(DANGER, INVERSE))

mode_row = tb.Frame(top_frame)
mode_row.pack(fill="x", pady=5)

radio_latest = tb.Radiobutton(mode_row, text="Latest", variable=mode_var, value="latest", 
                              bootstyle="info-toolbutton", command=lambda: date_entry.config(state=DISABLED))
radio_latest.pack(side="left", padx=5)

radio_exact = tb.Radiobutton(mode_row, text="Pick Exact Date", variable=mode_var, value="exact", 
                             bootstyle="info-toolbutton", command=lambda: date_entry.config(state=NORMAL))
radio_exact.pack(side="left", padx=5)

# TOOLTIP FIX
tt_radio = ToolTip(radio_exact, text="Search for a specific date (Weekdays only)", bootstyle=(INFO, INVERSE))

date_entry = tb.Entry(mode_row, width=15)
date_entry.pack(side="left", padx=5)
date_entry.insert(0, datetime.today().strftime("%Y-%m-%d")) 
date_entry.config(state=DISABLED)

# TOOLTIP FIX
tt_date = ToolTip(date_entry, text="Required format: YYYY-MM-DD", bootstyle=(INFO, INVERSE))

action_row = tb.Frame(top_frame)
action_row.pack(fill="x", pady=5)

fetch_button = tb.Button(action_row, text="Fetch, Price & Cost", 
                         command=lambda: threading.Thread(target=fetch_parse_thread, daemon=True).start(), 
                         bootstyle="primary")
fetch_button.pack(side="left")

simple_view_check = tb.Checkbutton(action_row, text="Simple View", variable=simple_view_var, 
                                   command=lambda: display_table(table_df), bootstyle="success-roundtoggle")
simple_view_check.pack(side="left", padx=15)

fetch_status_label = tb.Label(action_row, text="", bootstyle="info")
fetch_status_label.pack(side="left")

# ... rest of labels ...
ticker_warning_label = tb.Label(top_frame, text="", bootstyle="warning", font=("Helvetica", 9, "italic"), wraplength=1100)
ticker_warning_label.pack(fill="x", pady=(10, 0))

viewing_date_label = tb.Label(root, text="No data loaded", bootstyle="secondary", font=("Helvetica", 10, "bold"))
viewing_date_label.pack(fill="x", padx=15, pady=(15, 0))

hint_label = tb.Label(root, text="💡 Tip: Double-click row to open Chart directly (IDX:[Ticker])", 
                      font=("Helvetica", 8, "italic"), bootstyle="secondary")
hint_label.pack(fill="x", padx=15)

table_frame = tb.Frame(root, padding=10)
table_frame.pack(fill="both", expand=True)

# ---------- Functions ----------

def validate_date_format(event=None):
    text = date_entry.get().strip()
    if not text:
        date_entry.configure(bootstyle="default")
        return
    try:
        dt = datetime.strptime(text, "%Y-%m-%d")
        today = datetime.now()
        day_name = dt.strftime('%A')
        if dt > today:
            date_entry.configure(bootstyle="danger")
            log_to_label(f"⚠️ Future date: {text}")
        elif dt.weekday() >= 5:
            date_entry.configure(bootstyle="danger")
            log_to_label(f"⚠️ Market closed on {day_name}.")
        else:
            date_entry.configure(bootstyle="default")
            log_to_label(f"Selected: {day_name}")
    except ValueError:
        date_entry.configure(bootstyle="danger")
        log_to_label("⚠️ Use YYYY-MM-DD")

date_entry.bind("<KeyRelease>", validate_date_format)

def display_table(df: pd.DataFrame):
    for w in table_frame.winfo_children(): w.destroy()
    if df.empty: return

    # Ensure we only display rows with non-zero changes in the UI
    if "Perubahan_Shares" in df.columns:
        df = df[df["Perubahan_Shares"] != 0].copy()

    visible_cols = ["Kode Efek", "Nama Pemegang Rekening Efek", "Nama Rekening Efek", "Harga Terakhir", "Perubahan_Shares", "Total Cost", "Kode Efek"] if simple_view_var.get() else list(df.columns)
    
    tree = tb.Treeview(table_frame, columns=visible_cols, show="headings", bootstyle="info")
    tree.pack(side="left", fill="both", expand=True)
    tree.bind("<Double-1>", open_tradingview)

    # Dual scrollbars for performance
   # v_sc = tb.Scrollbar(container, orient="vertical", command=tree.yview)
    #h_sc = tb.Scrollbar(container, orient="horizontal", command=tree.xview)
    #tree.configure(yscrollcommand=v_sc.set, xscrollcommand=h_sc.set)

   # v_sc.pack(side="right", fill="y")
    ##h_sc.pack(side="bottom", fill="x")
    #tree.pack(side="left", fill="both", expand=True)
    
    

    # Define which columns should be right-aligned
    right_cols = ["Harga Terakhir", "Perubahan_Shares", "Total Cost"]
    center_cols = ["Kode Efek", "Domisili", "Status (Lokal/Asing)"]
    
    # Alignment: Center everything
    for col in visible_cols:
        # 1. Always center the Headings (Titles)
        tree.heading(col, text=col, anchor=CENTER)
    
        # 2. Apply specific alignment to the data rows
        if col in right_cols:
            # 'E' stands for East, which aligns text to the Right
            tree.column(col, width=180, anchor=E)
        elif col in center_cols:
            tree.column(col, width=180, anchor=CENTER)
        else:
            # Standard Center alignment for names and tickers
            tree.column(col, width=180, anchor=W)

    tree.tag_configure("pos", foreground="green")
    tree.tag_configure("neg", foreground="red")

## green pos, red neg, black not prominent changes
    for _, row in df.iterrows():
        vals = []
        for col in visible_cols:
            val = row.get(col, "")
            # Format numeric columns for readability
            if any(key in col for key in ["Saham", "Harga", "Cost", "Perubahan_Shares"]):
                try:
                    num = float(str(val).replace(",", ""))
                    if "Harga" in col or "Cost" in col:
                        prefix = "Rp " if col == "Harga Terakhir" else ""
                        val = f"{prefix}{num:,.0f}" if num != 0 else ""
                    else:
                        val = f"{num:,.0f}" if num != 0 else "0"
                except:
                    val = str(val)
            vals.append(val)

        # --- COST-BASED COLOR LOGIC ---
        try:
            cost_val = float(row.get("Total Cost", 0))
        except:
            cost_val = 0

        # Apply tag based on your thresholds
        if cost_val > 100000000:
            tag = "pos"  # Green
        elif cost_val < -100000000:
            tag = "neg"  # Red
        else:
            tag = "default" # Black

        tree.insert("", "end", values=vals, tags=(tag,))
    

def open_tradingview(event):
    tree = event.widget
    item_id = tree.identify_row(event.y)
    if item_id:
        row_values = tree.item(item_id, 'values')
        ticker = row_values[0] if simple_view_var.get() else row_values[1]
        if ticker and ticker != "nan":
            url = f"https://www.tradingview.com/chart/?symbol=IDX%3A{ticker}"
            webbrowser.open(url)

def get_price(t, target_date=None):
    for symbol in [f"{t}.JK", t]:
        try:
            ticker = yf.Ticker(symbol)
            if target_date:
                start_dt = datetime.strptime(target_date, "%Y-%m-%d")
                end_dt = start_dt + timedelta(days=1)
                hist = ticker.history(start=start_dt.strftime('%Y-%m-%d'), end=end_dt.strftime('%Y-%m-%d'))
            else:
                hist = ticker.history(period="1d")
            if not hist.empty: return hist["Close"].iloc[-1], symbol
        except: continue
    return 0, None

def set_ui_state(state):
    fetch_button.config(state=state); radio_latest.config(state=state); radio_exact.config(state=state)

def log_to_label(text):
    root.after(0, lambda: fetch_status_label.config(text=text))

def fetch_parse_thread():
    current_mode = mode_var.get()
    input_date = date_entry.get().strip()
    
    # 1. Validation Logic for "Pick Exact Date" mode
    if current_mode == "exact":
        try:
            dt = datetime.strptime(input_date, "%Y-%m-%d")
            today = datetime.now()
            
            # Check if date is in the future
            if dt > today:
                root.after(0, lambda: Messagebox.show_error(
                    f"The date {input_date} has not occurred yet.", "Future Date Error"
                ))
                return
            
            # Check if it is a weekend (Market is closed)
            # 5 = Saturday, 6 = Sunday
            if dt.weekday() >= 5:
                day_name = dt.strftime('%A')
                root.after(0, lambda: Messagebox.show_error(
                    f"The market was closed on {input_date} ({day_name}).\nPlease pick a weekday.", "Market Closed"
                ))
                return
                
        except ValueError:
            root.after(0, lambda: Messagebox.show_error(
                "Invalid date format. Please use YYYY-MM-DD.", "Format Error"
            ))
            return

    set_ui_state(DISABLED); log_to_label("Fetching...")
    try:
        e_date = datetime.strptime(input_date, "%Y-%m-%d").strftime("%Y%m%d") if current_mode == "exact" else None
        res = fetch_idx_pdf(exact_date=e_date)
        df = parse_shareholder_pdf(res["savedPath"])
        
        # UI Double Check: Skip Perubahan = 0 rows
        if not df.empty and "Perubahan_Shares" in df.columns:
            df = df[df["Perubahan_Shares"] != 0].copy()

        if not df.empty:
            log_to_label("Pricing & Calculating Net...")
            p_map = {}
            for t in df["Kode Efek"].unique():
                price, _ = get_price(str(t), target_date=input_date)
                p_map[t] = price
            
            # 1. Map Price to rows
            df["Harga Terakhir"] = df["Kode Efek"].map(p_map)
            
            # 2. Calculate individual Total Cost for each row
            df["Total Cost"] = df["Perubahan_Shares"] * df["Harga Terakhir"]

            # 3. THE CHANGE: Calculate Net Change Ticker based on the SUM of Total Costs
            # This identifies the total monetary flow (IDR) for the entire emiten
            #df['Net_Change_Ticker'] = df.groupby('Kode Efek')['Total Cost'].transform('sum')

            actual_dt = res.get('date', input_date if input_date else "Latest")
            root.after(0, lambda: viewing_date_label.config(text=f"📊 Viewing Data for: {actual_dt}", bootstyle="info"))

        global table_df; table_df = df
        root.after(0, lambda: display_table(df))
    except Exception as e:
        root.after(0, lambda err=e: viewing_date_label.config(text=f"Error: {err}", bootstyle="danger"))
    finally:
        set_ui_state(NORMAL); log_to_label("")

root.mainloop()
