# GainerScopeApp
GainerScope Explorer — A Python Windows desktop app for educational S&amp;P 500 market data exploration, volume analysis, and momentum research.
# GainerScope Explorer

A Windows desktop application for exploring **S&P 500 market activity** using historical price data, volume analysis, volatility metrics, and simple momentum indicators.

GainerScope helps users study market movements by scanning S&P 500 companies and presenting:

* Daily price changes
* One-month performance
* Relative volume activity
* Average daily dollar volume
* Annualized volatility estimates
* Simple trend indicators based on moving averages
* Momentum candidates based on user-defined filters

The application provides a visual dashboard for **learning and researching market behaviour**.

## Features

✅ Windows desktop GUI application

✅ S&P 500 company scanner

✅ Background scanning (UI remains responsive)

✅ Daily gain filtering

✅ Relative volume filtering

✅ Momentum view

✅ Stock activity explorer

✅ CSV export capability

✅ Simple educational market metrics dashboard


## Screenshots

<img width="2532" height="1338" alt="image" src="https://github.com/user-attachments/assets/c3cd4cb8-9586-4fa3-859b-9c5101ef6584" />


## Prerequisites

### Operating System

* Windows 10 or Windows 11

### Software Requirements

* Python 3.10 or later
* Internet connection (required to download market data)

Verify Python installation:

```powershell
python --version
```

## Installation

Clone the repository:

```powershell
git clone https://github.com/<your-user>/GainerScopeExplorer.git
cd GainerScopeExplorer
```

Install required Python packages:

```powershell
python -m pip install --upgrade yfinance pandas lxml requests
```

## Running the Application

Start the Windows application:

```powershell
python .\GainerScopeApp.py
```

The application will open a desktop dashboard where you can scan S&P 500 companies and explore market activity.

## How It Works

GainerScope collects publicly available market information and calculates:

* Price movement percentage
* Relative trading volume
* Moving average trends
* Recent volatility
* Liquidity estimates

The application uses these metrics to organize stocks for easier research.

## Data Sources

Market data is retrieved using:

* Yahoo Finance API through the `yfinance` Python library
* Public S&P 500 company listings

Internet access is required while running scans.

## Educational Purpose Only

⚠️ **Disclaimer**

This project is created for **educational and research purposes only**.

It is intended to demonstrate:

* Desktop application development
* Financial data analysis
* Python programming
* Market data visualization concepts

This application:

* ❌ Does not provide investment advice
* ❌ Does not recommend buying or selling any security
* ❌ Does not predict future stock prices
* ❌ Does not guarantee trading results

All displayed information represents historical market activity only. Users should perform their own research and consult qualified financial professionals before making investment decisions.

## Technology Stack

* Python
* Tkinter (Windows GUI)
* Pandas
* yfinance
* Requests
* Threading
* CSV export

## Project Structure

```
GainerScopeExplorer/
│
├── GainerScopeApp.py      # Main Windows desktop application
├── README.md              # Project documentation
└── requirements.txt       # Python dependencies
```

## License

MIT License, This project is provided as-is for educational purposes.

Use at your own risk.
