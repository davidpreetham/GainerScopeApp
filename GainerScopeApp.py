"""GainerScope Explorer - a Windows desktop stock-research application.

Install once: py -m pip install --upgrade yfinance pandas lxml requests
Run:          py .\GainerScopeApp.py
"""

import math
import queue
import threading
import time
from datetime import datetime
from io import StringIO
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import pandas as pd
import requests
import yfinance as yf


WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
HISTORY_PERIOD = "6mo"
EXPLORER_LIMIT = 30
MIN_AVG_DOLLAR_VOLUME = 10_000_000
MAX_ANNUAL_VOLATILITY = 45.0


def load_sp500():
    response = requests.get(
        WIKIPEDIA_URL,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        timeout=30,
    )
    response.raise_for_status()
    tables = pd.read_html(StringIO(response.text))
    sp500 = next(
        table for table in tables if {"Symbol", "Security"}.issubset(table.columns)
    ).copy()
    sp500["Yahoo Symbol"] = sp500["Symbol"].str.replace(".", "-", regex=False)
    return sp500


def trend_label(close, sma_20, sma_50):
    if close >= sma_20 and close >= sma_50:
        return "Above 20 & 50 day"
    if close >= sma_50:
        return "Above 50 day"
    if close >= sma_20:
        return "Above 20 day"
    return "Below 20 & 50 day"


def volatility_band(value):
    if value < 25:
        return "Lower"
    if value < 40:
        return "Medium"
    return "Higher"


def company_badge(symbol):
    """Return a stable, colourful offline badge without using trademarked logos."""
    colours = ("🔵", "🟣", "🟢", "🟠", "🟡", "🔴")
    index = sum(ord(character) for character in symbol) % len(colours)
    return f"{colours[index]} {symbol}"


def scan_stocks(min_gain, min_relative_volume, events):
    """Runs in a background thread and posts progress/results to the UI queue."""
    try:
        yf.config.network.retries = 2
        sp500 = load_sp500()
        company_by_symbol = dict(zip(sp500["Yahoo Symbol"], sp500["Security"]))
        symbols = sp500["Yahoo Symbol"].tolist()
    except Exception as exc:
        events.put(("error", f"Could not load the S&P 500 list: {exc}"))
        return

    all_stocks = []
    momentum = []
    errors = 0
    started = time.perf_counter()
    events.put(("started", len(symbols)))

    for number, symbol in enumerate(symbols, start=1):
        try:
            hist = yf.Ticker(symbol).history(
                period=HISTORY_PERIOD,
                auto_adjust=False,
            ).dropna(subset=["Close", "Volume"])

            if len(hist) < 51:
                continue

            latest = hist.iloc[-1]
            previous = hist.iloc[-2]
            close = float(latest["Close"])
            previous_close = float(previous["Close"])
            volume = float(latest["Volume"])
            prior_20 = hist.iloc[-21:-1]
            average_volume = float(prior_20["Volume"].mean())

            if close <= 0 or previous_close <= 0 or volume <= 0 or average_volume <= 0:
                continue

            closes = hist["Close"]
            returns = closes.pct_change().dropna()
            daily_change = (close / previous_close - 1) * 100
            one_month_change = (close / float(closes.iloc[-22]) - 1) * 100
            relative_volume = volume / average_volume
            volatility = float(returns.tail(20).std() * math.sqrt(252) * 100)
            sma_20 = float(closes.tail(20).mean())
            sma_50 = float(closes.tail(50).mean())

            record = {
                "Symbol": symbol,
                "Company": company_by_symbol.get(symbol, "N/A"),
                "Date": hist.index[-1].strftime("%Y-%m-%d"),
                "Close": round(close, 2),
                "Day %": round(daily_change, 2),
                "1-Month %": round(one_month_change, 2),
                "Relative Volume": round(relative_volume, 2),
                "Avg Daily $ Volume": round(average_volume * close),
                "Annualized Volatility %": round(volatility, 1),
                "Volatility Band": volatility_band(volatility),
                "Trend": trend_label(close, sma_20, sma_50),
            }
            all_stocks.append(record)

            if daily_change >= min_gain and relative_volume >= min_relative_volume:
                momentum.append(record)

        except Exception:
            errors += 1

        if number % 10 == 0 or number == len(symbols):
            elapsed = time.perf_counter() - started
            rate = number / elapsed if elapsed else 0
            eta = (len(symbols) - number) / rate if rate else 0
            events.put(("progress", number, len(symbols), len(momentum), errors, elapsed, eta))

    if not all_stocks:
        events.put(("error", "No usable price data was returned. Please try again later."))
        return

    all_df = pd.DataFrame(all_stocks)
    explorer = all_df[
        (all_df["Avg Daily $ Volume"] >= MIN_AVG_DOLLAR_VOLUME)
        & (all_df["Annualized Volatility %"] <= MAX_ANNUAL_VOLATILITY)
    ].copy()
    if len(explorer) < EXPLORER_LIMIT:
        explorer = all_df.copy()

    explorer = explorer.sort_values(
        by=["Avg Daily $ Volume", "Annualized Volatility %"],
        ascending=[False, True],
    ).head(EXPLORER_LIMIT)

    momentum_df = pd.DataFrame(momentum)
    if not momentum_df.empty:
        momentum_df = momentum_df.sort_values(
            by=["Day %", "Relative Volume"], ascending=[False, False]
        )

    events.put(("complete", explorer, momentum_df, all_df, errors, time.perf_counter() - started))


class GainerScopeApp(tk.Tk):
    columns = (
        "Stock", "Company", "Close", "Day %", "1-Month %",
        "Relative Volume", "Volatility", "Trend",
    )
    numeric_columns = {
        "Close": "Close", "Day %": "Day %", "1-Month %": "1-Month %",
        "Relative Volume": "Relative Volume", "Volatility": "Annualized Volatility %",
    }

    def __init__(self):
        super().__init__()
        self.title("GainerScope Explorer")
        self.geometry("1360x860")
        self.minsize(1060, 680)
        self.configure(bg="#0B1020")

        self.events = queue.Queue()
        self.is_scanning = False
        self.explorer_df = pd.DataFrame()
        self.momentum_df = pd.DataFrame()
        self.all_df = pd.DataFrame()
        self.active_view = "explore"
        self.sort_column = "Avg Daily $ Volume"
        self.sort_descending = True
        self.metric_vars = [tk.StringVar(value="--") for _ in range(4)]
        self.metric_notes = [tk.StringVar(value="Run a scan to begin") for _ in range(4)]

        self._style()
        self._build_ui()
        self.after(100, self._read_events)

    def _style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#111827")
        style.configure("TLabel", background="#111827", foreground="#E5E7EB")
        style.configure("Title.TLabel", font=("Segoe UI", 20, "bold"), foreground="#F9FAFB")
        style.configure("Sub.TLabel", font=("Segoe UI", 10), foreground="#9CA3AF")
        style.configure("Treeview", background="#FFFFFF", foreground="#111827", rowheight=28, fieldbackground="#FFFFFF")
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"), background="#E5E7EB", foreground="#111827")
        style.map("Treeview", background=[("selected", "#BFDBFE")], foreground=[("selected", "#111827")])

    def _build_ui(self):
        self._build_dashboard_ui()
        return

        header = ttk.Frame(self, padding=(22, 18, 22, 8))
        header.pack(fill="x")
        ttk.Label(header, text="GainerScope Explorer", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Explore S&P 500 market activity. Educational research only — not investment advice.",
            style="Sub.TLabel",
        ).pack(anchor="w", pady=(3, 0))

        controls = ttk.Frame(self, padding=(22, 6))
        controls.pack(fill="x")
        ttk.Label(controls, text="Minimum daily gain %").grid(row=0, column=0, sticky="w")
        self.gain_var = tk.StringVar(value="1.0")
        ttk.Entry(controls, textvariable=self.gain_var, width=9).grid(row=0, column=1, padx=(8, 22))
        ttk.Label(controls, text="Minimum relative volume").grid(row=0, column=2, sticky="w")
        self.volume_var = tk.StringVar(value="1.0")
        ttk.Entry(controls, textvariable=self.volume_var, width=9).grid(row=0, column=3, padx=(8, 22))
        self.scan_button = ttk.Button(controls, text="Scan S&P 500", command=self.start_scan)
        self.scan_button.grid(row=0, column=4, padx=(0, 10))
        ttk.Button(controls, text="Export current view", command=self.export_view).grid(row=0, column=5)

        status_box = ttk.Frame(self, padding=(22, 6))
        status_box.pack(fill="x")
        self.status_var = tk.StringVar(value="Ready. Click ‘Scan S&P 500’ to begin.")
        ttk.Label(status_box, textvariable=self.status_var, style="Sub.TLabel").pack(side="left")
        self.progress = ttk.Progressbar(status_box, mode="determinate", length=300)
        self.progress.pack(side="right")

        views = ttk.Frame(self, padding=(22, 8))
        views.pack(fill="x")
        ttk.Label(views, text="View:").pack(side="left")
        self.view_var = tk.StringVar(value="Explore stable, liquid stocks")
        selector = ttk.Combobox(
            views,
            textvariable=self.view_var,
            state="readonly",
            width=31,
            values=("Explore stable, liquid stocks", "Momentum activity"),
        )
        selector.pack(side="left", padx=8)
        selector.bind("<<ComboboxSelected>>", lambda _event: self.populate_table())

        table_frame = ttk.Frame(self, padding=(22, 2, 22, 8))
        table_frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(table_frame, columns=self.columns, show="headings")
        widths = {"Symbol": 75, "Company": 240, "Close": 80, "Day %": 75, "1-Month %": 90, "Relative Volume": 110, "Annualized Volatility %": 150, "Trend": 165}
        for column in self.columns:
            self.tree.heading(column, text=column)
            self.tree.column(column, width=widths[column], anchor="w")
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self.show_details)

        details = ttk.Frame(self, padding=(22, 8, 22, 18))
        details.pack(fill="x")
        self.details_var = tk.StringVar(value="Select a stock to see a plain-language explanation.")
        ttk.Label(details, textvariable=self.details_var, wraplength=1200, style="Sub.TLabel").pack(anchor="w")

    def _make_card(self, parent, title, value_var, note_var, accent):
        card = tk.Frame(parent, bg="#141E33", highlightbackground="#243352", highlightthickness=1)
        card.pack(side="left", fill="both", expand=True, padx=6)
        tk.Frame(card, bg=accent, height=4).pack(fill="x")
        tk.Label(card, text=title.upper(), bg="#141E33", fg="#8EA2C8", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=16, pady=(14, 2))
        tk.Label(card, textvariable=value_var, bg="#141E33", fg="#F7FAFF", font=("Segoe UI", 22, "bold")).pack(anchor="w", padx=16)
        tk.Label(card, textvariable=note_var, bg="#141E33", fg="#8495B5", font=("Segoe UI", 9)).pack(anchor="w", padx=16, pady=(0, 14))

    def _build_dashboard_ui(self):
        style = ttk.Style(self)
        style.configure("Dark.Treeview", background="#121A2B", foreground="#E8EEF9", fieldbackground="#121A2B", rowheight=38, borderwidth=0, font=("Segoe UI", 10))
        style.configure("Dark.Treeview.Heading", background="#1A2640", foreground="#9FB3D9", font=("Segoe UI", 10, "bold"), relief="flat", padding=(12, 10))
        style.map("Dark.Treeview", background=[("selected", "#243A64")], foreground=[("selected", "#FFFFFF")])
        style.configure("Blue.Horizontal.TProgressbar", troughcolor="#1A2640", background="#5B8CFF", bordercolor="#1A2640")

        header = tk.Frame(self, bg="#0B1020")
        header.pack(fill="x", padx=28, pady=(24, 10))
        brand = tk.Frame(header, bg="#0B1020")
        brand.pack(side="left")
        tk.Label(brand, text="G", bg="#5B8CFF", fg="white", font=("Segoe UI", 18, "bold"), width=2).pack(side="left", padx=(0, 10))
        text_box = tk.Frame(brand, bg="#0B1020")
        text_box.pack(side="left")
        tk.Label(text_box, text="GainerScope", bg="#0B1020", fg="#F7FAFF", font=("Segoe UI", 22, "bold")).pack(anchor="w")
        tk.Label(text_box, text="S&P 500 market explorer", bg="#0B1020", fg="#8495B5", font=("Segoe UI", 10)).pack(anchor="w")
        tk.Label(header, text="EDUCATIONAL RESEARCH", bg="#183B32", fg="#71E0B1", font=("Segoe UI", 9, "bold"), padx=12, pady=6).pack(side="right", pady=7)

        controls = tk.Frame(self, bg="#141E33", highlightbackground="#243352", highlightthickness=1)
        controls.pack(fill="x", padx=28, pady=(4, 12))
        tk.Label(controls, text="SCANNER FILTERS", bg="#141E33", fg="#9FB3D9", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, padx=(18, 12), pady=13)
        tk.Label(controls, text="Daily gain %", bg="#141E33", fg="#8495B5", font=("Segoe UI", 9)).grid(row=0, column=1)
        self.gain_var = tk.StringVar(value="1.0")
        tk.Entry(controls, textvariable=self.gain_var, width=8, bg="#0D1526", fg="#F7FAFF", insertbackground="#F7FAFF", relief="flat", justify="center", font=("Segoe UI", 10)).grid(row=0, column=2, padx=(7, 18), ipady=6)
        tk.Label(controls, text="Relative volume", bg="#141E33", fg="#8495B5", font=("Segoe UI", 9)).grid(row=0, column=3)
        self.volume_var = tk.StringVar(value="1.0")
        tk.Entry(controls, textvariable=self.volume_var, width=8, bg="#0D1526", fg="#F7FAFF", insertbackground="#F7FAFF", relief="flat", justify="center", font=("Segoe UI", 10)).grid(row=0, column=4, padx=(7, 18), ipady=6)
        self.scan_button = tk.Button(controls, text="Scan S&P 500", command=self.start_scan, bg="#5B8CFF", fg="white", activebackground="#4779ED", activeforeground="white", relief="flat", font=("Segoe UI", 10, "bold"), padx=18, pady=8, cursor="hand2")
        self.scan_button.grid(row=0, column=5, padx=(0, 8), pady=9)
        tk.Button(controls, text="Export CSV", command=self.export_view, bg="#243352", fg="#D9E4F8", activebackground="#31476E", activeforeground="white", relief="flat", font=("Segoe UI", 10, "bold"), padx=16, pady=8, cursor="hand2").grid(row=0, column=6, padx=(0, 18))

        metrics = tk.Frame(self, bg="#0B1020")
        metrics.pack(fill="x", padx=22, pady=(0, 14))
        self._make_card(metrics, "Stocks analysed", self.metric_vars[0], self.metric_notes[0], "#5B8CFF")
        self._make_card(metrics, "Momentum matches", self.metric_vars[1], self.metric_notes[1], "#B57BFF")
        self._make_card(metrics, "Average day move", self.metric_vars[2], self.metric_notes[2], "#4FD1A5")
        self._make_card(metrics, "Highest relative volume", self.metric_vars[3], self.metric_notes[3], "#F7B955")

        content = tk.Frame(self, bg="#0B1020")
        content.pack(fill="both", expand=True, padx=28, pady=(0, 10))
        toolbar = tk.Frame(content, bg="#0B1020")
        toolbar.pack(fill="x", pady=(0, 9))
        self.explore_button = tk.Button(toolbar, text="Explore", command=lambda: self.set_view("explore"), bg="#5B8CFF", fg="white", relief="flat", font=("Segoe UI", 10, "bold"), padx=20, pady=8, cursor="hand2")
        self.explore_button.pack(side="left")
        self.momentum_button = tk.Button(toolbar, text="Momentum", command=lambda: self.set_view("momentum"), bg="#1A2640", fg="#AAB9D4", relief="flat", font=("Segoe UI", 10, "bold"), padx=20, pady=8, cursor="hand2")
        self.momentum_button.pack(side="left", padx=(4, 0))
        self.status_var = tk.StringVar(value="Ready. Click Scan S&P 500 to begin.")
        tk.Label(toolbar, textvariable=self.status_var, bg="#0B1020", fg="#8495B5", font=("Segoe UI", 9)).pack(side="right", pady=8)

        shell = tk.Frame(content, bg="#141E33", highlightbackground="#243352", highlightthickness=1)
        shell.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(shell, columns=self.columns, show="headings", style="Dark.Treeview")
        widths = {"Stock": 115, "Company": 250, "Close": 100, "Day %": 95, "1-Month %": 110, "Relative Volume": 125, "Volatility": 105, "Trend": 210}
        for column in self.columns:
            self.tree.heading(column, text=column + "  <>", command=lambda name=column: self.sort_by(name))
            self.tree.column(column, width=widths[column], anchor="w", stretch=column in {"Company", "Trend"})
        scrollbar = ttk.Scrollbar(shell, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(1, 0), pady=1)
        scrollbar.pack(side="right", fill="y", padx=(0, 1), pady=1)
        self.tree.tag_configure("gain", foreground="#72E0B4")
        self.tree.tag_configure("loss", foreground="#FF9DA6")
        self.tree.bind("<<TreeviewSelect>>", self.show_details)

        details = tk.Frame(self, bg="#141E33", highlightbackground="#243352", highlightthickness=1)
        details.pack(fill="x", padx=28, pady=(0, 12))
        self.details_var = tk.StringVar(value="Select a stock row to see a plain-language research summary.")
        tk.Label(details, text="INSIGHT", bg="#141E33", fg="#5B8CFF", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=16, pady=(10, 0))
        tk.Label(details, textvariable=self.details_var, bg="#141E33", fg="#CBD7EC", font=("Segoe UI", 10), wraplength=1260, justify="left").pack(anchor="w", padx=16, pady=(3, 11))
        self.progress = ttk.Progressbar(self, mode="determinate", style="Blue.Horizontal.TProgressbar")
        self.progress.pack(fill="x", padx=28, pady=(0, 16))

    def set_view(self, view):
        self.active_view = view
        if view == "explore":
            self.explore_button.configure(bg="#5B8CFF", fg="white")
            self.momentum_button.configure(bg="#1A2640", fg="#AAB9D4")
            self.sort_column = "Avg Daily $ Volume"
        else:
            self.momentum_button.configure(bg="#5B8CFF", fg="white")
            self.explore_button.configure(bg="#1A2640", fg="#AAB9D4")
            self.sort_column = "Day %"
        self.sort_descending = True
        self.populate_table()

    def start_scan(self):
        if self.is_scanning:
            return
        try:
            gain = float(self.gain_var.get())
            volume = float(self.volume_var.get())
            if volume <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid filters", "Enter valid numbers. Relative volume must be greater than zero.")
            return

        self.is_scanning = True
        self.scan_button.configure(state="disabled")
        self.progress.configure(value=0, maximum=503)
        self.status_var.set("Loading S&P 500 companies...")
        self.details_var.set("The scan runs in the background. The app remains usable while it works.")
        threading.Thread(target=scan_stocks, args=(gain, volume, self.events), daemon=True).start()

    def _read_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "started":
                    self.progress.configure(maximum=event[1], value=0)
                    self.status_var.set(f"Scanning {event[1]} S&P 500 companies...")
                elif kind == "progress":
                    _, done, total, matches, errors, elapsed, eta = event
                    self.progress.configure(value=done, maximum=total)
                    self.status_var.set(
                        f"{done}/{total} scanned | {matches} momentum matches | {errors} errors | "
                        f"elapsed {elapsed / 60:.1f} min | ETA {eta / 60:.1f} min"
                    )
                elif kind == "complete":
                    _, self.explorer_df, self.momentum_df, self.all_df, errors, elapsed = event
                    self.is_scanning = False
                    self.scan_button.configure(state="normal")
                    self.progress.configure(value=self.progress.cget("maximum"))
                    self.update_metrics()
                    self.populate_table()
                    self.status_var.set(
                        f"Complete: {len(self.all_df)} stocks analysed, {len(self.momentum_df)} momentum matches, "
                        f"{errors} errors, {elapsed / 60:.1f} minutes."
                    )
                elif kind == "error":
                    self.is_scanning = False
                    self.scan_button.configure(state="normal")
                    self.status_var.set("Scan could not complete.")
                    messagebox.showerror("GainerScope", event[1])
        except queue.Empty:
            pass
        self.after(100, self._read_events)

    def current_dataframe(self):
        return self.explorer_df if self.active_view == "explore" else self.momentum_df

    def update_metrics(self):
        self.metric_vars[0].set(f"{len(self.all_df):,}")
        self.metric_notes[0].set("S&P 500 companies reviewed")
        self.metric_vars[1].set(f"{len(self.momentum_df):,}")
        self.metric_notes[1].set("Met your gain + volume filters")
        self.metric_vars[2].set(f"{self.all_df['Day %'].mean():+.2f}%")
        self.metric_notes[2].set("Across all analysed stocks")
        if not self.all_df.empty:
            busiest = self.all_df.loc[self.all_df["Relative Volume"].idxmax()]
            self.metric_vars[3].set(f"{busiest['Relative Volume']:.2f}x")
            self.metric_notes[3].set(f"{busiest['Symbol']} has the busiest volume")

    def sort_by(self, display_column):
        if display_column == "Stock":
            data_column = "Symbol"
        elif display_column in {"Company", "Trend"}:
            data_column = display_column
        else:
            data_column = self.numeric_columns[display_column]
        if self.sort_column == data_column:
            self.sort_descending = not self.sort_descending
        else:
            self.sort_column = data_column
            self.sort_descending = data_column not in {"Symbol", "Company", "Trend"}
        self.populate_table()

    def populate_table(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        data = self.current_dataframe()
        if data.empty:
            self.details_var.set("No rows in this view. Try a lower gain or relative-volume filter.")
            return
        data = data.sort_values(self.sort_column, ascending=not self.sort_descending)
        for _, row in data.iterrows():
            day_change = float(row["Day %"])
            tag = "gain" if day_change >= 0 else "loss"
            values = (
                company_badge(row["Symbol"]), row["Company"], f"${row['Close']:,.2f}",
                f"{day_change:+.2f}%", f"{row['1-Month %']:+.2f}%",
                f"{row['Relative Volume']:.2f}x", f"{row['Annualized Volatility %']:.1f}%",
                row["Trend"],
            )
            self.tree.insert("", "end", values=values, tags=(tag,))

    def show_details(self, _event=None):
        selected = self.tree.selection()
        if not selected:
            return
        values = self.tree.item(selected[0], "values")
        row = dict(zip(self.columns, values))
        if "Stock" in row:
            symbol = row["Stock"].split()[-1]
            self.details_var.set(
                f"{symbol} | {row['Company']}: day change {row['Day %']}, "
                f"one-month change {row['1-Month %']}, relative volume {row['Relative Volume']}, "
                f"recent volatility {row['Volatility']}, trend: {row['Trend']}. "
                "These describe past market activity and are not a trading recommendation."
            )
            return
        self.details_var.set(
            f"{row['Symbol']} — {row['Company']}: day change {row['Day %']}%, "
            f"one-month change {row['1-Month %']}%, relative volume {row['Relative Volume']}x, "
            f"recent volatility {row['Annualized Volatility %']}%, trend: {row['Trend']}. "
            "These describe past market activity and are not a trading recommendation."
        )

    def export_view(self):
        data = self.current_dataframe()
        if data.empty:
            messagebox.showinfo("Nothing to export", "Run a scan first, then choose a view to export.")
            return
        default_name = f"gainerscope_{datetime.now():%Y-%m-%d}.csv"
        filename = filedialog.asksaveasfilename(
            title="Save GainerScope results",
            initialdir=Path.cwd(),
            initialfile=default_name,
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
        )
        if filename:
            data.to_csv(filename, index=False)
            self.status_var.set(f"Saved {len(data)} rows to {filename}")


if __name__ == "__main__":
    GainerScopeApp().mainloop()
