"""
Terminal UI & Output Formatting for RepoLens CLI.
Provides cross-platform ANSI styling, status symbols, banners, and structured cards.
"""

import os
import sys
from typing import Any, Dict, List, Optional
import colorama
from colorama import Fore, Style

colorama.init(autoreset=True)

def _safe_symbol(sym: str, fallback: str) -> str:
    """Return symbol if stdout encoding supports it, else fallback."""
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        sym.encode(encoding)
        return sym
    except Exception:
        return fallback


# Cross-platform safe symbols
SYM_CHECK = _safe_symbol("✓", "[OK]")
SYM_CROSS = _safe_symbol("✗", "[X]")
SYM_WARN = _safe_symbol("⚠", "[!]")
SYM_INFO = _safe_symbol("ℹ", "[i]")
SYM_BULLET = _safe_symbol("●", "*")
SYM_ARROW = _safe_symbol("→", "->")
SYM_SPARKLE = _safe_symbol("✨", "*")
SYM_SEARCH = _safe_symbol("🔍", "[SEARCH]")
SYM_LOCK = _safe_symbol("🔒", "[SEC]")
SYM_GEAR = _safe_symbol("⚙", "[CONFIG]")


def bold(text: str) -> str:
    return f"{Style.BRIGHT}{text}{Style.RESET_ALL}"


def green(text: str) -> str:
    return f"{Fore.GREEN}{text}{Style.RESET_ALL}"


def red(text: str) -> str:
    return f"{Fore.RED}{text}{Style.RESET_ALL}"


def yellow(text: str) -> str:
    return f"{Fore.YELLOW}{text}{Style.RESET_ALL}"


def cyan(text: str) -> str:
    return f"{Fore.CYAN}{text}{Style.RESET_ALL}"


def magenta(text: str) -> str:
    return f"{Fore.MAGENTA}{text}{Style.RESET_ALL}"


def dim(text: str) -> str:
    return f"{Style.DIM}{text}{Style.RESET_ALL}"


def print_banner():
    """Print the RepoLens CLI header banner."""
    raw_banner = """
██████╗ ███████╗██████╗  ██████╗ ██╗     ███████╗███╗   ██╗███████╗
██╔══██╗██╔════╝██╔══██╗██╔═══██╗██║     ██╔════╝████╗  ██║██╔════╝
██████╔╝█████╗  ██████╔╝██║   ██║██║     █████╗  ██╔██╗ ██║███████╗
██╔══██╗██╔══╝  ██╔═══╝ ██║   ██║██║     ██╔══╝  ██║╚██╗██║╚════██║
██║  ██║███████╗██║     ╚██████╔╝███████╗███████╗██║ ╚████║███████║"""

    ascii_banner = """
======================================================================
                         R E P O L E N S
======================================================================"""

    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        raw_banner.encode(encoding)
        banner_art = f"{Fore.CYAN}{Style.BRIGHT}{raw_banner}{Style.RESET_ALL}"
    except Exception:
        banner_art = f"{Fore.CYAN}{Style.BRIGHT}{ascii_banner}{Style.RESET_ALL}"

    print(banner_art)
    print(f"{Style.BRIGHT}RepoLens -- Local AI Engineering Agent & Continuous Guardian{Style.RESET_ALL}")
    print(dim("AI proposes. Tools execute. Evidence verifies. Impact prioritizes. Developer controls."))


def print_header(title: str):
    """Print a section header."""
    print(f"\n{Style.BRIGHT}{Fore.CYAN}=== {title} ==={Style.RESET_ALL}")


def print_success(message: str):
    """Print a success message."""
    print(f" {Fore.GREEN}{SYM_CHECK}{Style.RESET_ALL} {message}")


def print_error(message: str):
    """Print an error message."""
    print(f" {Fore.RED}{SYM_CROSS}{Style.RESET_ALL} {Fore.RED}{message}{Style.RESET_ALL}", file=sys.stderr)


def print_warning(message: str):
    """Print a warning message."""
    print(f" {Fore.YELLOW}{SYM_WARN}{Style.RESET_ALL} {yellow(message)}")


def print_info(message: str):
    """Print an informational message."""
    print(f" {Fore.BLUE}{SYM_INFO}{Style.RESET_ALL} {message}")


def print_bullet(message: str, indent: int = 1):
    """Print an indented bullet point."""
    spaces = "  " * indent
    print(f"{spaces}{Fore.CYAN}{SYM_BULLET}{Style.RESET_ALL} {message}")


def print_table(headers: List[str], rows: List[List[str]]):
    """Print a clean formatted ASCII table."""
    if not headers and not rows:
        return

    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], len(str(val)))
            else:
                col_widths.append(len(str(val)))

    # Header line
    header_str = " | ".join(f"{headers[i]:<{col_widths[i]}}" for i in range(len(headers)))
    divider_str = "-+-".join("-" * col_widths[i] for i in range(len(headers)))

    print(f"{Style.BRIGHT}{header_str}{Style.RESET_ALL}")
    print(dim(divider_str))

    for row in rows:
        padded_cells = []
        for i, cell in enumerate(row):
            w = col_widths[i] if i < len(col_widths) else len(str(cell))
            padded_cells.append(f"{str(cell):<{w}}")
        print(" | ".join(padded_cells))


def priority_badge(priority: str) -> str:
    """Format priority code as colored badge."""
    p = (priority or "P3").upper()
    if p == "P0":
        return f"{Fore.WHITE}{colorama.Back.RED}{Style.BRIGHT} P0 CRITICAL {Style.RESET_ALL}"
    elif p == "P1":
        return f"{Fore.BLACK}{colorama.Back.YELLOW}{Style.BRIGHT} P1 HIGH {Style.RESET_ALL}"
    elif p == "P2":
        return f"{Fore.YELLOW}{Style.BRIGHT}P2 MEDIUM{Style.RESET_ALL}"
    elif p == "P3":
        return f"{Fore.BLUE}P3 LOW{Style.RESET_ALL}"
    return f"{dim('P4 INFO')}"


def truth_status_badge(truth_status: str) -> str:
    """Format truth status as colored badge."""
    ts = (truth_status or "UNVERIFIED").upper()
    if ts == "VERIFIED" or ts == "TRUE":
        return f"{Fore.GREEN}{SYM_CHECK} VERIFIED{Style.RESET_ALL}"
    elif ts == "LIKELY_TRUE" or ts == "PARTIALLY_TRUE":
        return f"{Fore.CYAN}{SYM_CHECK} LIKELY TRUE{Style.RESET_ALL}"
    elif ts == "UNCERTAIN":
        return f"{Fore.YELLOW}? UNCERTAIN{Style.RESET_ALL}"
    elif ts == "FALSE" or ts == "FALSE_POSITIVE":
        return f"{Fore.RED}{SYM_CROSS} FALSE POSITIVE{Style.RESET_ALL}"
    return f"{dim(ts)}"


def format_health_score(score: float) -> str:
    """Format health score (0-100) with color indicator."""
    if score >= 90.0:
        return f"{Fore.GREEN}{Style.BRIGHT}{score:.1f}/100 (Excellent){Style.RESET_ALL}"
    elif score >= 75.0:
        return f"{Fore.CYAN}{Style.BRIGHT}{score:.1f}/100 (Good){Style.RESET_ALL}"
    elif score >= 50.0:
        return f"{Fore.YELLOW}{Style.BRIGHT}{score:.1f}/100 (Moderate Risk){Style.RESET_ALL}"
    else:
        return f"{Fore.RED}{Style.BRIGHT}{score:.1f}/100 (Critical Attention Required){Style.RESET_ALL}"
