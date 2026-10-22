"""Create a demo user with two months of realistic data, through the web forms.

Usage: python seed_demo.py BASE_URL EMAIL PASSWORD
Needs httpx and registration open on the target (ZEROBASE_ALLOW_REGISTRATION=true).
"""

import re
import sys

import httpx

BASE, EMAIL, PASSWORD = sys.argv[1:4]
CURRENT, SAVINGS = "Current account", "Savings"
INCOME = "Inflow: Ready to Assign"

ASSIGN = {
    "2026-09": {
        "Rent / Mortgage": "1150",
        "Utilities": "180",
        "Phone & Internet": "55",
        "Subscriptions": "32",
        "Insurance": "48",
        "Groceries": "420",
        "Transport": "160",
        "Health": "30",
        "Dining out": "120",
        "Entertainment": "60",
        "Clothing": "50",
        "Emergency fund": "3500",
        "Holidays": "250",
    },
    "2026-10": {
        "Rent / Mortgage": "1150",
        "Utilities": "180",
        "Phone & Internet": "55",
        "Subscriptions": "32",
        "Insurance": "48",
        "Groceries": "420",
        "Transport": "160",
        "Health": "30",
        "Dining out": "100",
        "Entertainment": "60",
        "Clothing": "50",
        "Emergency fund": "400",
        "Holidays": "250",
    },
}

# (date, account, payee, category or None, outflow, inflow)
TRANSACTIONS = [
    ("2026-08-28", CURRENT, "Starting balance", INCOME, "", "1250.00"),
    ("2026-08-28", SAVINGS, "Starting balance", INCOME, "", "1800.00"),
    ("2026-08-28", CURRENT, "Acme Ltd salary", INCOME, "", "3150.00"),
    ("2026-09-01", CURRENT, "Landlord", "Rent / Mortgage", "1150.00", ""),
    ("2026-09-03", CURRENT, "Tesco", "Groceries", "86.40", ""),
    ("2026-09-05", CURRENT, "Octopus Energy", "Utilities", "112.00", ""),
    ("2026-09-05", CURRENT, "Thames Water", "Utilities", "41.20", ""),
    ("2026-09-08", CURRENT, "BT", "Phone & Internet", "55.00", ""),
    ("2026-09-09", CURRENT, "Netflix", "Subscriptions", "10.99", ""),
    ("2026-09-10", CURRENT, "Aviva", "Insurance", "48.00", ""),
    ("2026-09-10", CURRENT, "TfL", "Transport", "42.30", ""),
    ("2026-09-12", CURRENT, "Spotify", "Subscriptions", "11.99", ""),
    ("2026-09-12", CURRENT, "Sainsbury's", "Groceries", "94.15", ""),
    ("2026-09-14", CURRENT, "Dishoom", "Dining out", "68.50", ""),
    ("2026-09-19", CURRENT, "Tesco", "Groceries", "102.60", ""),
    ("2026-09-20", CURRENT, "Odeon", "Entertainment", "24.00", ""),
    ("2026-09-21", CURRENT, "Pizza Express", "Dining out", "52.30", ""),
    ("2026-09-24", CURRENT, "Shell", "Transport", "61.80", ""),
    ("2026-09-25", CURRENT, "Acme Ltd salary", INCOME, "", "3150.00"),
    ("2026-09-26", CURRENT, "Boots", "Health", "14.99", ""),
    ("2026-09-27", CURRENT, "Côte Brasserie", "Dining out", "44.20", ""),
    ("2026-09-28", CURRENT, "Uniqlo", "Clothing", "39.90", ""),
    ("2026-09-29", CURRENT, "Tesco", "Groceries", "78.35", ""),
    ("2026-10-01", CURRENT, "Landlord", "Rent / Mortgage", "1150.00", ""),
    ("2026-10-02", CURRENT, "Tesco", "Groceries", "91.20", ""),
    ("2026-10-05", CURRENT, "Octopus Energy", "Utilities", "118.40", ""),
    ("2026-10-05", CURRENT, "Thames Water", "Utilities", "41.20", ""),
    ("2026-10-08", CURRENT, "BT", "Phone & Internet", "55.00", ""),
    ("2026-10-09", CURRENT, "Netflix", "Subscriptions", "10.99", ""),
    ("2026-10-10", CURRENT, "Aviva", "Insurance", "48.00", ""),
    ("2026-10-11", CURRENT, "TfL", "Transport", "38.60", ""),
    ("2026-10-12", CURRENT, "Spotify", "Subscriptions", "11.99", ""),
    ("2026-10-13", CURRENT, "Sainsbury's", "Groceries", "88.75", ""),
    ("2026-10-15", CURRENT, "Nando's", "Dining out", "31.40", ""),
    ("2026-10-17", CURRENT, "Tesco", "Groceries", "96.10", ""),
    ("2026-10-18", CURRENT, "Vue", "Entertainment", "18.50", ""),
    ("2026-10-19", CURRENT, "Shell", "Transport", "58.20", ""),
    ("2026-10-20", CURRENT, "Amazon", None, "23.99", ""),  # left uncategorised on purpose
]


def ok(response: httpx.Response) -> httpx.Response:
    if response.status_code >= 400:
        sys.exit(f"{response.request.method} {response.request.url} -> {response.status_code}")
    return response


with httpx.Client(base_url=BASE, follow_redirects=True, timeout=30) as client:
    ok(client.post("/register", data={"email": EMAIL, "password": PASSWORD}))

    for name, kind, on_budget, opening in [
        (CURRENT, "checking", True, ""),
        (SAVINGS, "savings", True, ""),
        ("Mortgage", "other", False, "-182450.00"),
    ]:
        data = {"name": name, "kind": kind, "opening_balance": opening}
        if on_budget:
            data["on_budget"] = "on"
        ok(client.post("/accounts", data=data))

    page = ok(client.get("/transactions")).text
    account_select = re.search(r'<select name="account_id".*?</select>', page, re.S).group(0)
    accounts = {
        n: v for v, n in re.findall(r'<option value="(\d+)"[^>]*>([^<]+)</option>', account_select)
    }
    category_select = re.search(r'<select name="category_id">.*?</select>', page, re.S).group(0)
    categories = {
        n.replace("&amp;", "&"): v
        for v, n in re.findall(r'<option value="(\d+)"[^>]*>([^<]+)</option>', category_select)
    }

    for month, amounts in ASSIGN.items():
        for name, amount in amounts.items():
            ok(
                client.post(
                    "/budget/assign",
                    data={"category_id": categories[name], "month": month, "amount": amount},
                )
            )

    for when, account, payee, category, outflow, inflow in TRANSACTIONS:
        ok(
            client.post(
                "/transactions",
                data={
                    "account_id": accounts[account],
                    "when": when,
                    "payee": payee,
                    "memo": "",
                    "category_id": categories[category] if category else "",
                    "outflow": outflow,
                    "inflow": inflow,
                },
            )
        )

    budget = ok(client.get("/budget?month=2026-10")).text
    rta = re.search(r'id="rta"[^>]*>\s*<strong>([^<]+)</strong>', budget)
    print(
        "accounts", len(accounts), "categories", len(categories), "transactions", len(TRANSACTIONS)
    )
    print("October Ready to Assign:", rta.group(1) if rta else "(not found)")
