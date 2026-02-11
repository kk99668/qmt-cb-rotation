# QMT Auto Rebalancing - Convertible Bond Rotation Tool

> Convertible bond rotation auto rebalancing tool based on QMT. Open source for learning and research only.

## Table of Contents

- [Features](#features)
- [Project Description](#project-description)
- [Environment Compatibility](#environment-compatibility)
- [Usage Recommendations](#usage-recommendations)
- [Quick Start](#quick-start)
- [Installation Guide](#installation-guide)
- [Configuration](#configuration)
- [User Guide](#user-guide)
- [FAQ](#faq)
- [Developer Guide](#developer-guide)
- [Changelog](#changelog)
- [Risk & Disclaimer](#risk--disclaimer)
- [License](#license)

## Features

- **Factor Cat Account Login** - Supports remember password and auto-login
- **Strategy Management** - Load convertible bond strategies and backtest records from Factor Cat platform with pagination support
- **Flexible Configuration** - Supports fixed amount/balance-based allocation, limit orders/market orders
- **Auto Rebalancing** - Automatically execute buy/sell operations based on strategy
- **Take Profit & Stop Loss** - Real-time monitoring of positions with automatic execution (checks every minute)
- **Email Notifications** - Send email notifications when trading exceptions occur (not yet implemented; code exists but requires manual build and email configuration)
- **Scheduled Tasks** - Flexible scheduling configuration (daily, weekly, monthly)
- **Auto Update** - Support for checking new versions and prompting users

## Project Description

This project is an open-source personal automated trading assistant for convertible bond rotation strategies. It provides technical implementation reference only and does not constitute any investment advice.

## Environment Compatibility

- This tool has been tested only on Guojin Securities Mini QMT
- No guarantee of stable operation on other brokers or QMT versions
- Different brokers may have different interfaces, market data, and permissions, which may cause:
  - Rebalancing failures
  - Duplicate orders
  - Position anomalies
  - Execution mismatches

Do not use for live trading without thorough testing in your own environment.

## Usage Recommendations

1. **Always monitor regularly**
   Automated programs may be affected by network, market data, APIs, or program errors. Human oversight is required during operation; never run completely unattended.

2. **Beginners must test on paper trading first**
   Strongly recommended for all users, especially beginners:
   - Run a full strategy cycle on paper trading first
   - Confirm rebalancing logic, execution, and stability
   - Then consider live trading with small capital cautiously

3. **Start small and validate gradually**
   Do not deploy large capital for automated strategies from the start.

## Quick Start

### Prerequisites

1. Install [Python 3.9+](https://www.python.org/downloads/)
2. Install [MiniQMT](https://dict.thinktrader.net/nativeApps/startup.html) client
3. (Optional) Install [Edge WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/)

### Three Steps to Get Started

```bash
# 1. Clone the project
git clone <repository-url>
cd qmt-cb-rotation

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the program
python main.py
```

## Installation Guide

### System Requirements

| Component | Minimum Version | Recommended Version | Notes |
|-----------|----------------|---------------------|-------|
| Operating System | Windows 10 | Windows 11 | Windows only |
| Python | 3.9 | 3.11 | Must be added to PATH |
| MiniQMT | Latest | Latest | Requires Xuntou speed trading terminal |

### MiniQMT Installation Guide

#### 1. Get MiniQMT

- Visit [Xuntou Official Website](https://dict.thinktrader.net/nativeApps/startup.html) to download MiniQMT client
- Or contact your broker's customer manager to get the installation package

#### 2. Install MiniQMT

1. Run the downloaded installer
2. Follow the wizard to complete the installation
3. Remember the installation path, which will be needed for configuration later

#### 3. Find userdata_mini Path

Locate the `userdata_mini` folder in the MiniQMT installation directory, for example:
```
C:\迅投MiniQMT\userdata_mini
```

### Project Installation

#### 1. Clone the Project

```bash
git clone <repository-url>
cd qmt-cb-rotation
```

#### 2. Create Virtual Environment (Recommended)

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
venv\Scripts\activate
```

#### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

#### 4. Install QMT SDK

Copy the `xtquant` folder from the MiniQMT installation directory to the project root, or ensure Python can find the module.

### WebView2 Installation (Optional)

The program supports multiple browser kernels in order of priority:

1. **CEF (Chromium)** - Best compatibility, requires manual installation of `cefpython3`
2. **Edge WebView2** - Recommended, [Download Link](https://developer.microsoft.com/microsoft-edge/webview2/)
3. **System Default Browser** - May have compatibility issues

If the program prompts for missing WebView2 on startup, please download and install Edge WebView2 Runtime.

### Verify Installation

Run the following command to verify successful installation:

```bash
python main.py
```

If the program window opens normally, the installation is successful.

## Configuration

### Basic Configuration

After starting the program for the first time, you need to configure the following:

| Configuration Item | Description | Required | Example |
|--------------------|-------------|----------|---------|
| Factor Cat Account | For logging into Factor Cat platform | Yes | your_account |
| Password | Factor Cat account password | Yes | ******** |
| MiniQMT Path | userdata_mini folder path | Yes | C:\迅投MiniQMT\userdata_mini |
| Securities Account | Trading account | Yes | 12345678 |
| Buy Amount Type | Fixed amount or balance-based allocation | Yes | Fixed Amount |
| Per-Bond Amount | Amount to buy per convertible bond (CNY) | Yes | 10000 |
| Order Type | Limit order or market order | Yes | Limit Order |

### Advanced Configuration

#### Email Notification Configuration

After configuration, email notifications will be sent when trading exceptions occur:

| Configuration Item | Description | Example |
|--------------------|-------------|---------|
| SMTP Server | Email server address | smtp.example.com |
| SMTP Port | Email server port | 587 |
| Sender Email | Email for sending notifications | sender@example.com |
| Email Password | Authorization code for sender email | ******** |
| Receiver Email | Email for receiving notifications | receiver@example.com |

#### Take Profit & Stop Loss Configuration

Take profit and stop loss parameters are provided by the Factor Cat strategy. The program will automatically fetch them and execute trades when the position profit/loss reaches the set value.

#### Scheduled Task Configuration

Supports configuring the execution frequency of auto rebalancing:

| Option | Description |
|--------|-------------|
| Daily | Execute once per trading day |
| Every Monday | Execute once every Monday |
| 5th of each month | Execute on the 5th of each month |

### Configuration File

Configuration is stored in the `data/app.db` SQLite database, with passwords encrypted.

## User Guide

### Login & Strategy Selection

#### 1. Login to Factor Cat Account

1. After starting the program, enter your account and password on the login screen
2. You can check "Remember Password" for automatic login next time
3. Click the "Login" button

#### 2. Select Strategy

1. After successful login, the program will automatically load the strategy list
2. Select the strategy you want to use from the strategy list
3. Click "Load Backtest Records" to view the historical performance of the strategy

### Auto Trading Setup

#### 1. Configure Trading Parameters

Configure in the "Settings" page:
- MiniQMT path
- Securities account
- Buy amount type and amount
- Order type

#### 2. Start Auto Trading

1. After confirming the configuration is correct, click the "Start Trading" button
2. The program will automatically execute the following operations:
   - Get today's selected bond list
   - Get current positions
   - Sell positions not in the selected bond list
   - Buy new convertible bonds

#### 3. Monitor Running Status

On the main interface, you can view:
- Currently running strategy
- Position status
- Trading logs
- System status

### Take Profit & Stop Loss Monitoring

The program checks positions once per minute on each trading day:

1. Get the latest price of held convertible bonds
2. Calculate profit/loss ratio
3. Automatically sell when take profit/stop loss is reached
4. Send trading result notification

### Important Notes

- Trading Hours: Auto trading is only executed during trading hours
- Network Connection: Please ensure a stable network connection
- Account Funds: Ensure sufficient available funds in the account
- Suspended Bonds: Suspended convertible bonds will be skipped and an email notification will be sent

## FAQ

### Installation Issues

**Q: Module not found error when running the program?**

A: Make sure all dependencies are installed:
```bash
pip install -r requirements.txt
```

**Q: Prompted that WebView2 is not found?**

A: Please download and install [Edge WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/)

**Q: Program cannot start?**

A: Please check:
1. Whether Python version is 3.9 or higher
2. Whether running in a virtual environment
3. Check log files in the `logs` directory

### Configuration Issues

**Q: How to find the MiniQMT path?**

A: Find the `userdata_mini` folder in the MiniQMT installation directory and copy the full path.

**Q: Where to fill in the securities account?**

A: Fill in your broker trading account on the "Trading Configuration" page in program settings.

### Trading Issues

**Q: What to do if trading fails?**

A: Please check:
1. Whether MiniQMT client is logged in
2. Whether the account has sufficient funds
3. Whether the convertible bond is in a tradable state
4. Check trading logs for detailed error information

**Q: How does take profit and stop loss work?**

A: The system checks position profit/loss ratio every minute and automatically sells when the strategy's take profit/stop loss line is reached.

**Q: How to handle suspended convertible bonds?**

A: The system will skip suspended convertible bonds and send an email notification, requiring you to handle manually.

### Other Issues

**Q: How to view trading logs?**

A: Log files are located in the `logs` directory, named by date.

## Developer Guide

### Project Structure

```
qmt-cb-rotation/
├── main.py                      # Program entry point
├── requirements.txt             # Python dependencies
├── build.spec                   # PyInstaller packaging config
├── build_debug.py               # Debug packaging script
│
├── assets/                      # Frontend static resources
│   └── index.html               # Web interface (HTML/CSS/JS)
│
├── src/                         # Source code directory
│   ├── api/
│   │   └── api.py               # PyWebView API interface layer
│   │
│   ├── services/                # Business logic services
│   │   ├── factorcat_service.py    # Factor Cat API integration
│   │   ├── qmt_service.py          # QMT trading integration
│   │   ├── scheduler_service.py    # Scheduled task management
│   │   ├── auto_trade_service.py   # Auto trading core logic
│   │   ├── notification_service.py # Email notifications
│   │   └── update_service.py       # Update checking
│   │
│   ├── models/                  # Data models
│   │   ├── database.py          # SQLite database operations
│   │   └── schemas.py           # Pydantic data models
│   │
│   └── utils/                   # Utility classes
│       ├── crypto.py            # Password encryption tools
│       ├── logger.py            # Logging configuration
│       ├── token_utils.py       # Token management tools
│       └── webview2_checker.py  # WebView2 installation check
│
├── data/                        # Local data (SQLite database)
├── logs/                        # Log file directory
│
├── hooks/                       # PyInstaller custom hooks
└── dist/                        # Package output directory
```

### Tech Stack

| Category | Technology | Description |
|----------|-----------|-------------|
| Desktop Framework | PyWebView | Lightweight desktop application framework |
| Backend Language | Python 3.9+ | Main development language |
| Frontend | HTML + CSS + JavaScript | User interface |
| Database | SQLite | Local data storage |
| ORM | SQLAlchemy | Database operations |
| Data Validation | Pydantic | Data model validation |
| Scheduled Tasks | APScheduler | Task scheduling |
| Logging | Loguru | Logging system |
| HTTP Requests | Requests | API calls |
| Encryption | Cryptography | Password encryption |
| Data Processing | Pandas | Data analysis |
| Market Data | AkShare | Market data retrieval |

### Local Development

#### 1. Clone the Project

```bash
git clone <repository-url>
cd qmt-cb-rotation
```

#### 2. Create Virtual Environment

```bash
python -m venv venv
venv\Scripts\activate
```

#### 3. Install Development Dependencies

```bash
pip install -r requirements.txt
```

#### 4. Run Development Server

```bash
python main.py
```

#### 5. Code Style

The project follows PEP 8 code style guidelines. Recommended tools:

```bash
# Code formatting
pip install black
black .

# Code checking
pip install flake8
flake8 .
```

### Packaging & Release

#### Package with PyInstaller

```bash
# Run packaging script
build.bat

# Or manually package
pyinstaller build.spec
```

After packaging, the executable file is located in the `dist\因子猫QMT自动调仓\` directory.

#### Packaging Notes

1. Ensure `build.spec` includes all necessary resource files
2. Check if `hooks` directory contains custom PyInstaller hooks
3. Test whether the packaged program runs normally

### API Interface

The program exposes interfaces to the frontend through PyWebView's `js_api`. Main interfaces are in `src/api/api.py`.

For details, please refer to [API接口文档.md](docs/API接口文档.md).

### Adding New Features

1. Create a new service class in `src/services/`
2. Add corresponding API methods in `src/api/api.py`
3. Add frontend call code in `assets/index.html`
4. Update database models (if needed)

## Changelog

### v1.0.0 (2024-01-01)

- Initial release
- Factor Cat account login support
- Auto rebalancing support
- Take profit & stop loss monitoring
- Email notification support

## Risk & Disclaimer

1. This tool is an open-source learning project; it is unofficial and non-commercial.

2. The author assumes no responsibility for any profits, losses, trading anomalies, or capital losses arising from the use of this tool.

3. Convertible bond trading and rotation strategies involve risks such as market volatility, liquidity, and rule changes.

4. By using this tool, you acknowledge that you have fully understood the risks and assume all responsibility for your operations and risks.

5. Investment involves risks; trade with caution.

## License

Private - All Rights Reserved

## Contact

- Issue Reporting: Please submit an Issue

## Acknowledgments

- [PyWebView](https://pywebview.flowrl.com/) - Lightweight desktop application framework
- [MiniQMT](https://dict.thinktrader.net/) - Xuntou speed trading interface
- [Factor Cat](https://yinzimao.com) - Convertible bond backtesting platform
