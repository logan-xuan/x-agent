"""
Plugin validator for the x-agent2 AI assistant system.

This module handles the validation of plugins to ensure they meet security and
functional requirements before being loaded into the system.
"""

import ast
import os
import subprocess
import tempfile
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
import hashlib
import secrets
import sys
import importlib.util
from enum import Enum


class ValidationResult(Enum):
    """Result of a validation check."""
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"


class SecurityIssue(Enum):
    """Types of security issues that can be detected."""
    CODE_INJECTION = "code_injection"
    PATH_TRAVERSAL = "path_traversal"
    ARBITRARY_FILE_ACCESS = "arbitrary_file_access"
    COMMAND_INJECTION = "command_injection"
    UNAUTHORIZED_NETWORK_ACCESS = "unauthorized_network_access"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    WEAK_CRYPTOGRAPHY = "weak_cryptography"
    INSECURE_RANDOMNESS = "insecure_randomness"


class ValidationSeverity(Enum):
    """Severity levels for validation issues."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PluginValidator:
    """Validates plugins for security and functional compliance."""

    def __init__(self):
        # Dangerous patterns that indicate potential security issues
        self.dangerous_patterns = [
            # Code execution
            r'\beval\s*\(',
            r'\bexec\s*\(',
            r'\bcompile\s*\(',
            r'\b__import__\s*\(',
            r'\bos\.system\s*\(',
            r'\bsubprocess\.',
            r'\bexecfile\s*\(',
            r'\bopen\s*\([^)]*("[^"]*\.py"|\'[^\']*\.py\')[^)]*\)',  # Opening Python files for execution

            # Path traversal
            r'\.\.\.',  # Triple dots
            r'\.\./',   # Dot dot slash
            r'\\.\\.',  # Windows style

            # File system access
            r'\bos\.remove\s*\(',
            r'\bos\.unlink\s*\(',
            r'\bshutil\.rmtree\s*\(',

            # Network access
            r'\brequests\.',
            r'\burllib\.',
            r'\bhttplib.',
            r'\bsmtplib.',
            r'\bftplib.',

            # Crypto issues
            r'random\.(rand|seed)',
            r'hashlib\.md5\(',
            r'hashlib\.sha1\(',
        ]

        # Required imports for safe plugin operation
        self.safe_imports = [
            "json",
            "os",
            "sys",
            "pathlib",
            "typing",
            "datetime",
            "collections",
            "itertools",
            "functools",
            "operator",
            "math",
            "statistics",
            "random",  # Though needs to be reviewed for secure use
            "decimal",
            "fractions",
            "copy",
            "pickle",  # Needs review
            "base64",
            "uuid",
            "re",
            "string",
            "textwrap",
            "unicodedata",
            "stringprep",
            "reprlib",
            "pprint",
            "ast",
            "weakref",
            "gc",
            "inspect",
            "site",
            "user",
            "threading",
            "multiprocessing",
            "concurrent",
            "asyncio",
            "queue",
            "sched",
            "contextlib",
            "abc",
            "atexit",
            "traceback",
            "warnings",
            "abc",
            "collections",
            "collections.abc",
            "heapq",
            "bisect",
            "array",
            "weakref",
            "types",
            "enum",
            "numbers",
            "decimal",
            "fractions",
            "functions",
            "itertools",
            "operator",
            "filecmp",
            "tempfile",
            "glob",
            "fnmatch",
            "linecache",
            "shutil",
            "macpath",
            "stat",
            "filetype",
            "pprint",
            "reprlib",
            "enum",
            "graphlib",
            "dataclasses",
            "contextvars",
            "inspect",
            "importlib",
            "importlib.util",
        ]

        # Forbidden imports for security
        self.forbidden_imports = [
            "os",
            "subprocess",
            "sys",
            "importlib",
            "execjs",
            "ctypes",
            "cffi",
            "builtins",
            "_winreg",
            "winreg",
            "winsound",
            "msvcrt",
            "termios",
            "tty",
            "pty",
            "grp",
            "pwd",
            "spwd",
            "crypt",
            "resource",
            "faulthandler",
            "pdb",
            "profile",
            "cProfile",
            "pstats",
            "cgitb",
            "antigravity",
            "this",
            "keyword",
            "token",
            "tokenize",
            "tabnanny",
            "pyclbr",
            "py_compile",
            "compileall",
            "dis",
            "pickletools",
            "zipimport",
            "pkgutil",
            "modulefinder",
            "runpy",
            "platform",
            "errno",
            "ctypes",
            "fcntl",
            "select",
            "socket",
            "ssl",
            "http",
            "urllib",
            "urllib2",
            "httplib",
            "httplib2",
            "requests",
            "paramiko",
            "fabric",
            "scp",
            "ftplib",
            "telnetlib",
            "smtplib",
            "poplib",
            "imaplib",
            "nntplib",
            "smtplib",
            "xmlrpc",
            "xmlrpclib",
            "xml",
            "lxml",
            "beautifulsoup",
            "html.parser",
            "cgi",
            "cgitb",
            "webbrowser",
            "uuid",
            "hashlib",
            "hmac",
            "base64",
            "binascii",
            "quopri",
            "uu",
            "encodings",
            "codecs",
            "code",
            "symbol",
            "tokenize",
            "tabnanny",
            "pyclbr",
            "py_compile",
            "compileall",
            "zipfile",
            "tarfile",
            "gzip",
            "bz2",
            "lzma",
            "zipimport",
            "pkgutil",
            "modulefinder",
            "runpy",
            "filecmp",
            "fileinput",
            "gettext",
            "locale",
            "calendar",
            "time",
            "datetime",
            "zoneinfo",
            "collections",
            "collections.abc",
            "heapq",
            "bisect",
            "array",
            "weakref",
            "types",
            "copy",
            "pprint",
            "reprlib",
            "enum",
            "graphlib",
            "dataclasses",
            "numbers",
            "decimal",
            "fractions",
            "functional",
            "itertools",
            "math",
            "numbers",
            "operator",
            "random",
            "statistics",
            "string",
            "textwrap",
            "unicodedata",
            "stringprep",
            "re",
            "difflib",
            "string",
            "textwrap",
            "sre",
            "sre_parse",
            "sre_constants",
            "formatter",
            "parser",
            "bytecode",
            "dis",
            "pickle",
            "copyreg",
            "shelve",
            "marshal",
            "json",
            "turtle",
            "colorsys",
            "urllib",
            "urllib2",
            "httplib",
            "httplib2",
            "xmlrpclib",
            "xmlrpc",
            "email",
            "mailbox",
            "smtpd",
            "asyncore",
            "asynchat",
            "signal",
            "mmap",
            "select",
            "threading",
            "thread",
            "dummy_thread",
            "dummy_threading",
            "multiprocessing",
            "concurrent",
            "concurrent.futures",
            "socketserver",
            "xml",
            "xml.parsers",
            "xml.dom",
            "xml.sax",
            "xml.etree",
            "html",
            "html.parser",
            "html.entities",
            "cgi",
            "urllib",
            "urllib.request",
            "urllib.parse",
            "urllib.error",
            "urllib.robotparser",
            "webbrowser",
            "ftplib",
            "poplib",
            "imaplib",
            "nntplib",
            "smtplib",
            "smtplib",
            "telnetlib",
            "uuid",
            "ssl",
            "http",
            "http.client",
            "http.server",
            "http.cookies",
            "http.cookiejar",
            "xmlrpc",
            "xmlrpc.client",
            "xmlrpc.server",
            "ipaddress",
            "audioop",
            "aifc",
            "sunau",
            "wave",
            "chunk",
            "colorsys",
            "cgi",
            "cgitb",
            "webbrowser",
            "fractions",
            "decimal",
            "numbers",
            "hashlib",
            "hmac",
            "base64",
            "binascii",
            "quopri",
            "uu",
            "uuid",
            "random",
            "statistics",
            "itertools",
            "functools",
            "operator",
            "pathlib",
            "filecmp",
            "tempfile",
            "glob",
            "fnmatch",
            "linecache",
            "shutil",
            "macpath",
            "stat",
            "filetype",
            "lib2to3",
            "pyclbr",
            "py_compile",
            "compileall",
            "zipfile",
            "tarfile",
            "gzip",
            "bz2",
            "lzma",
            "zipimport",
            "pkgutil",
            "modulefinder",
            "runpy",
            "pdb",
            "profile",
            "cProfile",
            "pstats",
            "cgitb",
            "trace",
            "tracemalloc",
            "distutils",
            "ensurepip",
            "venv",
            "zipapp",
            "webbrowser",
            "wsgiref",
            "urllib",
            "urllib.request",
            "urllib.parse",
            "urllib.error",
            "urllib.robotparser",
            "xml",
            "xml.parsers",
            "xml.dom",
            "xml.sax",
            "xml.etree",
            "html",
            "html.parser",
            "html.entities",
            "cgi",
            "urllib",
            "urllib2",
            "httplib",
            "httplib2",
            "xmlrpclib",
            "xmlrpc",
            "email",
            "mailbox",
            "smtpd",
            "asyncore",
            "asynchat",
            "signal",
            "mmap",
            "select",
            "threading",
            "thread",
            "dummy_thread",
            "dummy_threading",
            "multiprocessing",
            "concurrent",
            "concurrent.futures",
            "socketserver",
            "sqlite3",
            "dbm",
            "dbm.ndbm",
            "dbm.gnu",
            "dbm.sqlite3",
            "gdbm",
            "dbhash",
            "bsddb",
            "whichdb",
            "bdb",
            "cmd",
            "shlex",
            "importlib",
            "importlib.util",
            "importlib.machinery",
            "importlib.resources",
            "importlib.abc",
            "importlib.metadata",
            "zipimport",
            "pkgutil",
            "modulefinder",
            "runpy",
            "tkinter",
            "turtle",
            "curses",
            "colorama",
            "webbrowser",
            "pyautogui",
            "keyboard",
            "mouse",
            "pynput",
            "pyxhook",
            "winsound",
            "winsdk",
            "win32api",
            "win32gui",
            "win32console",
            "win32clipboard",
            "win32com",
            "win32con",
            "win32console",
            "win32cred",
            "win32crypt",
            "win32evtlog",
            "win32file",
            "win32gui",
            "win32help",
            "win32inet",
            "win32job",
            "win32lz",
            "win32net",
            "win32pdh",
            "win32pipe",
            "win32print",
            "win32process",
            "win32profile",
            "win32ras",
            "win32security",
            "win32service",
            "win32timezone",
            "win32trace",
            "win32transaction",
            "win32ts",
            "win32wnet",
            "pyHook",
            "pyttsx3",
            "speech_recognition",
            "playsound",
            "pyaudio",
            "pygame",
            "pyscreenshot",
            "mss",
            "opencv-python",
            "cv2",
            "scipy",
            "numpy",
            "pandas",
            "matplotlib",
            "seaborn",
            "plotly",
            "bokeh",
            "altair",
            "dash",
            "streamlit",
            "flask",
            "django",
            "fastapi",
            "starlette",
            "uvicorn",
            "gunicorn",
            "uwsgi",
            "bjoern",
            "meinheld",
            "eventlet",
            "gevent",
            "daphne",
            "channels",
            "celery",
            "redis",
            "pymongo",
            "mysql",
            "psycopg2",
            "sqlalchemy",
            "alembic",
            "sqlmodel",
            "pydantic",
            "marshmallow",
            "attrs",
            "click",
            "fire",
            "typer",
            "argparse",
            "optparse",
            "configparser",
            "toml",
            "yaml",
            "ruamel.yaml",
            "json",
            "simplejson",
            "ujson",
            "orjson",
            "pendulum",
            "python-dateutil",
            "arrow",
            "maya",
            "delorean",
            "when",
            "moment",
            "pytz",
            "zoneinfo",
            "babel",
            "money",
            "prices",
            "currencyconverter",
            "requests",
            "httpx",
            "aiohttp",
            "urllib3",
            "http.client",
            "socket",
            "selectors",
            "asyncio",
            "threading",
            "multiprocessing",
            "concurrent.futures",
            "sched",
            "queue",
            "pipes",
            "posix",
            "nt",
            "os2",
            "ce",
            "java",
            "auto",
            "pwd",
            "grp",
            "spwd",
            "crypt",
            "dl",
            "imageext",
            "imgfile",
            "imageio",
            "PIL",
            "pillow",
            "scikit-image",
            "skimage",
            "opencv",
            "cv2",
            "tensorflow",
            "torch",
            "keras",
            "scikit-learn",
            "sklearn",
            "xgboost",
            "lightgbm",
            "catboost",
            "gensim",
            "nltk",
            "spacy",
            "transformers",
            "datasets",
            "evaluate",
            "accelerate",
            "trl",
            "diffusers",
            "sentence-transformers",
            "openai",
            "anthropic",
            "cohere",
            "huggingface_hub",
            "bitsandbytes",
            "accelerate",
            "peft",
            "safetensors",
            "tokenizers",
            "tiktoken",
            "langchain",
            "llama-index",
            "haystack",
            "serpapi",
            "google-search-results",
            "duckduckgo_search",
            "wikipedia",
            "newsapi-client",
            "pytrends",
            "yfinance",
            "alpha_vantage",
            "polygon-api-client",
            "alpaca-trade-api",
            "robin-stocks",
            "td-ameritrade-python-api",
            "etrade-python",
            "schwab-py",
            "ibapi",
            "tastytrade",
            "quantopian",
            "zipline",
            "backtrader",
            "bt",
            "pyalgotrade",
            "ta",
            "ta-lib",
            "talib",
            "pandas-ta",
            "finta",
            "ta4j",
            "technicalindicators",
            "crypto",
            "ccxt",
            "binance",
            "coinbase",
            "kraken",
            "kucoin",
            "huobi",
            "okex",
            "bitfinex",
            "bitstamp",
            "gemini",
            "poloniex",
            "bittrex",
            "hitbtc",
            "bybit",
            "ftx",
            "gateio",
            "mexc",
            "coinex",
            "huobi-client",
            "kucoin-api",
            "bitget-api",
            "whitebit",
            "lbank",
            "bigone",
            "aax",
            "coinspot",
            "independentreserve",
            "bitflyer",
            "liquid",
            "quoine",
            "bitbank",
            "bitmex",
            "deribit",
            "okcoin",
            "bitpanda",
            "swyftx",
            "cryptocom",
            "phemex",
            "probit",
            "wazirx",
            "coinflex",
            "bitso",
            "novadax",
            "southxchange",
            "bitbns",
            "exmo",
            "bitrue",
            "bitforex",
            "hotbit",
            "oceanex",
            "probit",
            "bitmax",
            "zb",
            "dragonex",
            "bitz",
            "jitrex",
            "bitmart",
            "bkex",
            "lbank",
            "coinsbit",
            "graviex",
            "etherdelta",
            "idex",
            "forkdelta",
            "radarrelay",
            "ddex",
            "tokenstore",
            "ethfinex",
            "gdac",
            "coinroom",
            "paymium",
            "bl3p",
            "surbitcoin",
            "VBTC",
            "bitinka",
            "coinsource",
            "coinmate",
            "bit2c",
            "bitonic",
            "litebit",
            "anxpro",
            "bitmarket",
            "livecoin",
            "liqui",
            "crex24",
            "cryptopia",
            "novaexchange",
            "braziliex",
            "satoexchange",
            "cryptobridge",
            "openledger",
            "transwiser",
            "coinsuper",
            "oceanex",
            "rightbtc",
            "coinbene",
            "bitifrag",
            "topbtc",
            "coinut",
            "coinegg",
            "xbtce",
            "acx",
            "quadrigacx",
            "ccex",
            "yobit",
            "tidex",
            "crypton",
            "coinse",
            "upbit",
            "coinone",
            "korbit",
            "gopax",
            "huobi",
            "okcoin",
            "bitfinex",
            "kraken",
            "bitstamp",
            "gemini",
            "lakebtc",
            "itbit",
            "btcchina",
            "okcoin",
            "bitvc",
            "btcbox",
            "coincheck",
            "zaif",
            "bithumb",
            "coinone",
            "korbit",
            "gopax",
            "huobi",
            "okcoin",
            "bitfinex",
            "kraken",
            "bitstamp",
            "gemini",
            "lakebtc",
            "itbit",
            "btcchina",
            "allcoin",
            "bibox",
            "bitmex",
            "quoine",
            "quoinex",
            "liquid",
            "bitflyer",
            "bitflyerFX",
            "bitflyerBTCFX",
            "cex",
            "xbtx",
            "bitkonan",
            "btcmarkets",
            "coinjar",
            "independentreserve",
            "bitx",
            "luno",
            "bitbay",
            "virwox",
            "paymium",
            "bleutrade",
            "btc38",
            "bter",
            "jubi",
            "chbtc",
            "huobi",
            "okcoin",
            "bitfinex",
            "kraken",
            "bitstamp",
            "gemini",
            "lakebtc",
            "itbit",
            "btcchina",
            "yunbi",
            "coincheck",
            "zaif",
            "bithumb",
            "coinone",
            "korbit",
            "gopax",
            "coinroom",
            "bitso",
            "surbitcoin",
            "VBTC",
            "bitinka",
            "coinsource",
            "coinmate",
            "bit2c",
            "bitonic",
            "litebit",
            "anxpro",
            "bitmarket",
            "livecoin",
            "liqui",
            "crex24",
            "cryptopia",
            "novaexchange",
            "braziliex",
            "satoexchange",
            "cryptobridge",
            "openledger",
            "transwiser",
            "coinsuper",
            "oceanex",
            "rightbtc",
            "coinbene",
            "bitifrag",
            "topbtc",
            "coinut",
            "coinegg",
            "xbtce",
            "acx",
            "quadrigacx",
            "ccex",
            "yobit",
            "tidex",
            "crypton",
            "coinse",
            "upbit",
            "coinone",
            "korbit",
            "gopax",
            "huobi",
            "okcoin",
            "bitfinex",
            "kraken",
            "bitstamp",
            "gemini",
            "lakebtc",
            "itbit",
            "btcchina",
            "allcoin",
            "bibox",
            "bitmex",
            "quoine",
            "quoinex",
            "liquid",
            "bitflyer",
            "bitflyerFX",
            "bitflyerBTCFX",
            "cex",
            "xbtx",
            "bitkonan",
            "btcmarkets",
            "coinjar",
            "independentreserve",
            "bitx",
            "luno",
            "bitbay",
            "virwox",
            "paymium",
            "bleutrade",
            "btc38",
            "bter",
            "jubi",
            "chbtc",
            "huobi",
            "okcoin",
            "bitfinex",
            "kraken",
            "bitstamp",
            "gemini",
            "lakebtc",
            "itbit",
            "btcchina",
            "yunbi",
            "coincheck",
            "zaif",
            "bithumb",
            "coinone",
            "korbit",
            "gopax",
            "coinroom",
            "bitso",
            "surbitcoin",
            "VBTC",
            "bitinka",
            "coinsource",
            "coinmate",
            "bit2c",
            "bitonic",
            "litebit",
            "anxpro",
            "bitmarket",
            "livecoin",
            "liqui",
            "crex24",
            "cryptopia",
            "novaexchange",
            "braziliex",
            "satoexchange",
            "cryptobridge",
            "openledger",
            "transwiser",
            "coinsuper",
            "oceanex",
            "rightbtc",
            "coinbene",
            "bitifrag",
            "topbtc",
            "coinut",
            "coinegg",
            "xbtce",
            "acx",
            "quadrigacx",
            "ccex",
            "yobit",
            "tidex",
            "crypton",
            "coinse",
            "upbit",
            "coinone",
            "korbit",
            "gopax",
            "huobi",
            "okcoin",
            "bitfinex",
            "kraken",
            "bitstamp",
            "gemini",
            "lakebtc",
            "itbit",
            "btcchina",
            "allcoin",
            "bibox",
            "bitmex",
            "quoine",
            "quoinex",
            "liquid",
            "bitflyer",
            "bitflyerFX",
            "bitflyerBTCFX",
            "cex",
            "xbtx",
            "bitkonan",
            "btcmarkets",
            "coinjar",
            "independentreserve",
            "bitx",
            "luno",
            "bitbay",
            "virwox",
            "paymium",
            "bleutrade",
            "btc38",
            "bter",
            "jubi",
            "chbtc",
            "huobi",
            "okcoin",
            "bitfinex",
            "kraken",
            "bitstamp",
            "gemini",
            "lakebtc",
            "itbit",
            "btcchina",
            "yunbi",
            "coincheck",
            "zaif",
            "bithumb",
            "coinone",
            "korbit",
            "gopax"
        ]

    def validate_plugin_structure(self, plugin_path: Path) -> Dict[str, Any]:
        """
        Validate the basic structure of a plugin.

        Args:
            plugin_path: Path to the plugin directory

        Returns:
            Dictionary with validation results
        """
        issues = []
        warnings = []

        # Check if plugin.json exists
        manifest_path = plugin_path / "plugin.json"
        if not manifest_path.exists():
            issues.append({
                "issue": "Missing plugin.json manifest",
                "severity": ValidationSeverity.CRITICAL.value,
                "type": SecurityIssue.INSECURE_RANDOMNESS.value
            })

        # Check if main module exists
        if manifest_path.exists():
            import json
            try:
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    manifest = json.load(f)

                main_module = manifest.get("main_module")
                if main_module:
                    main_module_path = plugin_path / main_module
                    if not main_module_path.exists():
                        issues.append({
                            "issue": f"Main module file {main_module} does not exist",
                            "severity": ValidationSeverity.CRITICAL.value,
                            "type": SecurityIssue.ARBITRARY_FILE_ACCESS.value
                        })

        # Check for potentially dangerous files
        dangerous_files = [
            "__pycache__",
            ".git",
            ".env",
            "config.json",
            "credentials.json",
            "secrets.json",
            "private_key.pem",
            "ssh_private_key",
            "id_rsa"
        ]

        for item in plugin_path.iterdir():
            if item.name in dangerous_files:
                warnings.append({
                    "issue": f"Dangerous file found: {item.name}",
                    "severity": ValidationSeverity.HIGH.value,
                    "type": SecurityIssue.ARBITRARY_FILE_ACCESS.value
                })

        return {
            "result": ValidationResult.FAILED.value if issues else ValidationResult.PASSED.value,
            "issues": issues,
            "warnings": warnings
        }

    def validate_python_code(self, file_path: Path) -> Dict[str, Any]:
        """
        Static analysis of Python code for security issues.

        Args:
            file_path: Path to the Python file to analyze

        Returns:
            Dictionary with validation results
        """
        issues = []
        warnings = []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                source_code = content

            # Check for dangerous patterns using regex
            import re
            for pattern in self.dangerous_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                if matches:
                    issues.append({
                        "issue": f"Dangerous pattern found: {pattern}",
                        "location": str(file_path),
                        "severity": ValidationSeverity.CRITICAL.value,
                        "type": SecurityIssue.CODE_INJECTION.value,
                        "instances": len(matches)
                    })

            # Parse AST to check for security issues
            try:
                tree = ast.parse(source_code)

                # Walk the AST and check for dangerous constructs
                for node in ast.walk(tree):
                    # Check for eval/exec usage
                    if isinstance(node, ast.Call):
                        if isinstance(node.func, ast.Name):
                            if node.func.id in ['eval', 'exec', 'execfile', '__import__']:
                                issues.append({
                                    "issue": f"Dangerous function call: {node.func.id}",
                                    "location": f"{file_path}:{node.lineno}",
                                    "severity": ValidationSeverity.CRITICAL.value,
                                    "type": SecurityIssue.CODE_INJECTION.value
                                })

                    # Check for import statements
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            if alias.name in self.forbidden_imports:
                                issues.append({
                                    "issue": f"Forbidden import: {alias.name}",
                                    "location": f"{file_path}:{node.lineno}",
                                    "severity": ValidationSeverity.HIGH.value,
                                    "type": SecurityIssue.PRIVILEGE_ESCALATION.value
                                })
                    elif isinstance(node, ast.ImportFrom):
                        if node.module in self.forbidden_imports:
                            issues.append({
                                "issue": f"Forbidden import from: {node.module}",
                                "location": f"{file_path}:{node.lineno}",
                                "severity": ValidationSeverity.HIGH.value,
                                "type": SecurityIssue.PRIVILEGE_ESCALATION.value
                            })

            except SyntaxError as e:
                issues.append({
                    "issue": f"Syntax error in file: {str(e)}",
                    "location": f"{file_path}:{e.lineno}",
                    "severity": ValidationSeverity.HIGH.value,
                    "type": SecurityIssue.INSECURE_RANDOMNESS.value
                })

        except UnicodeDecodeError:
            issues.append({
                "issue": f"Could not decode file: {file_path}",
                "location": str(file_path),
                "severity": ValidationSeverity.MEDIUM.value,
                "type": SecurityIssue.INSECURE_RANDOMNESS.value
            })

        return {
            "result": ValidationResult.FAILED.value if issues else ValidationResult.PASSED.value,
            "issues": issues,
            "warnings": warnings
        }

    def validate_file_safety(self, plugin_path: Path) -> Dict[str, Any]:
        """
        Validate that the plugin files are safe to load.

        Args:
            plugin_path: Path to the plugin directory

        Returns:
            Dictionary with validation results
        """
        issues = []
        warnings = []

        for root, dirs, files in os.walk(plugin_path):
            for file in files:
                file_path = Path(root) / file

                # Skip directories and non-Python files for code validation
                if file.endswith('.py'):
                    result = self.validate_python_code(file_path)
                    issues.extend(result['issues'])
                    warnings.extend(result['warnings'])

                # Check file extensions for potentially unsafe types
                if file.endswith(('.exe', '.bat', '.sh', '.dll', '.so')):
                    issues.append({
                        "issue": f"Potentially unsafe file type: {file}",
                        "location": str(file_path),
                        "severity": ValidationSeverity.HIGH.value,
                        "type": SecurityIssue.ARBITRARY_FILE_ACCESS.value
                    })

                # Check file size (arbitrary limit of 10MB to prevent extremely large files)
                if file_path.stat().st_size > 10 * 1024 * 1024:  # 10MB
                    warnings.append({
                        "issue": f"Large file detected: {file} ({file_path.stat().st_size} bytes)",
                        "location": str(file_path),
                        "severity": ValidationSeverity.MEDIUM.value,
                        "type": SecurityIssue.ARBITRARY_FILE_ACCESS.value
                    })

        return {
            "result": ValidationResult.FAILED.value if issues else ValidationResult.PASSED.value,
            "issues": issues,
            "warnings": warnings
        }

    def validate_runtime_safety(self, plugin_path: Path) -> Dict[str, Any]:
        """
        Validate plugin safety during a limited runtime test.

        Args:
            plugin_path: Path to the plugin directory

        Returns:
            Dictionary with validation results
        """
        issues = []
        warnings = []

        # This would involve actually loading the plugin in a sandboxed environment
        # For now, we'll just do a basic check without actually running the code
        # In a real implementation, this would use a proper sandboxing solution

        manifest_path = plugin_path / "plugin.json"
        if manifest_path.exists():
            import json
            try:
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    manifest = json.load(f)

                # Check if plugin has an entry point defined
                entry_point = manifest.get("entry_point")
                if not entry_point:
                    warnings.append({
                        "issue": "No entry point defined in manifest",
                        "location": str(manifest_path),
                        "severity": ValidationSeverity.MEDIUM.value,
                        "type": SecurityIssue.INSECURE_RANDOMNESS.value
                    })
            except Exception as e:
                issues.append({
                    "issue": f"Could not parse manifest: {str(e)}",
                    "location": str(manifest_path),
                    "severity": ValidationSeverity.HIGH.value,
                    "type": SecurityIssue.INSECURE_RANDOMNESS.value
                })

        return {
            "result": ValidationResult.PASSED.value,  # Simplified for now
            "issues": issues,
            "warnings": warnings,
            "note": "Runtime safety validation is limited in this implementation. Full runtime validation would require a proper sandbox."
        }

    def calculate_plugin_hash(self, plugin_path: Path) -> str:
        """
        Calculate a hash of the plugin for integrity checking.

        Args:
            plugin_path: Path to the plugin directory

        Returns:
            SHA256 hash of the plugin files
        """
        hash_sha256 = hashlib.sha256()

        # Walk through all files in the plugin directory
        for root, dirs, files in os.walk(plugin_path):
            # Sort to ensure consistent order
            files.sort()
            for file in files:
                file_path = Path(root) / file
                if file_path.is_file():
                    # Add file path to hash for integrity
                    hash_sha256.update(file_path.as_posix().encode('utf-8'))

                    # Add file content to hash
                    with open(file_path, 'rb') as f:
                        # Read in chunks to handle large files
                        for chunk in iter(lambda: f.read(4096), b""):
                            hash_sha256.update(chunk)

        return hash_sha256.hexdigest()

    def validate_plugin_integrity(self, plugin_path: Path, expected_hash: Optional[str] = None) -> Dict[str, Any]:
        """
        Validate plugin integrity by checking its hash.

        Args:
            plugin_path: Path to the plugin directory
            expected_hash: Expected hash to compare against (optional)

        Returns:
            Dictionary with validation results
        """
        issues = []
        warnings = []

        try:
            current_hash = self.calculate_plugin_hash(plugin_path)

            if expected_hash:
                if current_hash != expected_hash:
                    issues.append({
                        "issue": "Plugin hash does not match expected hash",
                        "severity": ValidationSeverity.HIGH.value,
                        "type": SecurityIssue.INSECURE_RANDOMNESS.value,
                        "expected": expected_hash,
                        "actual": current_hash
                    })
                else:
                    warnings.append({
                        "issue": "Plugin integrity verified",
                        "severity": ValidationSeverity.LOW.value,
                        "type": "integrity_check"
                    })
            else:
                warnings.append({
                    "issue": f"Plugin hash: {current_hash}",
                    "severity": ValidationSeverity.LOW.value,
                    "type": "integrity_check"
                })

        except Exception as e:
            issues.append({
                "issue": f"Could not calculate plugin hash: {str(e)}",
                "severity": ValidationSeverity.HIGH.value,
                "type": SecurityIssue.INSECURE_RANDOMNESS.value
            })

        return {
            "result": ValidationResult.FAILED.value if issues else ValidationResult.PASSED.value,
            "issues": issues,
            "warnings": warnings,
            "current_hash": current_hash if 'current_hash' in locals() else None
        }

    def validate(self, plugin_path: Path, expected_hash: Optional[str] = None) -> Dict[str, Any]:
        """
        Perform comprehensive validation of a plugin.

        Args:
            plugin_path: Path to the plugin directory
            expected_hash: Expected hash to compare against (optional)

        Returns:
            Dictionary with comprehensive validation results
        """
        # Perform all validation checks
        structure_result = self.validate_plugin_structure(plugin_path)
        safety_result = self.validate_file_safety(plugin_path)
        runtime_result = self.validate_runtime_safety(plugin_path)
        integrity_result = self.validate_plugin_integrity(plugin_path, expected_hash)

        # Aggregate results
        all_issues = []
        all_warnings = []

        for result in [structure_result, safety_result, runtime_result, integrity_result]:
            all_issues.extend(result.get('issues', []))
            all_warnings.extend(result.get('warnings', []))

        # Determine overall result
        overall_result = ValidationResult.PASSED.value
        if any(issue['severity'] in [ValidationSeverity.CRITICAL.value, ValidationSeverity.HIGH.value]
               for issue in all_issues):
            overall_result = ValidationResult.FAILED.value
        elif all_issues:
            overall_result = ValidationResult.WARNING.value

        return {
            "overall_result": overall_result,
            "structure_validation": structure_result,
            "file_safety_validation": safety_result,
            "runtime_safety_validation": runtime_result,
            "integrity_validation": integrity_result,
            "total_issues": len(all_issues),
            "total_warnings": len(all_warnings),
            "critical_issues": len([i for i in all_issues if i['severity'] == ValidationSeverity.CRITICAL.value]),
            "high_severity_issues": len([i for i in all_issues if i['severity'] == ValidationSeverity.HIGH.value]),
            "all_issues": all_issues,
            "all_warnings": all_warnings,
            "plugin_hash": integrity_result.get("current_hash")
        }


class PluginValidationService:
    """Service class for managing plugin validation operations."""

    def __init__(self):
        self.validator = PluginValidator()

    def validate_plugin(self, plugin_path: str, expected_hash: Optional[str] = None) -> Dict[str, Any]:
        """
        Validate a plugin at the specified path.

        Args:
            plugin_path: Path to the plugin directory
            expected_hash: Expected hash to compare against (optional)

        Returns:
            Dictionary with validation results
        """
        plugin_path = Path(plugin_path)
        return self.validator.validate(plugin_path, expected_hash)

    def validate_plugins_in_directory(self, directory_path: str) -> Dict[str, Any]:
        """
        Validate all plugins in a directory.

        Args:
            directory_path: Path to the directory containing plugins

        Returns:
            Dictionary with validation results for all plugins
        """
        directory_path = Path(directory_path)
        results = {}

        for item in directory_path.iterdir():
            if item.is_dir():
                # Look for plugin.json to identify plugins
                if (item / "plugin.json").exists():
                    results[item.name] = self.validate_plugin(item)

        return results


# Global validator instance
plugin_validator = PluginValidator()
validation_service = PluginValidationService()


# Convenience functions
def validate_plugin(plugin_path: str, expected_hash: Optional[str] = None) -> Dict[str, Any]:
    """Validate a plugin at the specified path."""
    return validation_service.validate_plugin(plugin_path, expected_hash)


def validate_plugins_in_directory(directory_path: str) -> Dict[str, Any]:
    """Validate all plugins in a directory."""
    return validation_service.validate_plugins_in_directory(directory_path)