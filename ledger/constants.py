"""
Ledger constants. Add parent group names here to include their ledgers
in the "Total Op. Bal." sum on the ledger create/alter form.
"""
# Ledgers whose opening balances are summed in "Total Op. Bal."
# A ledger is included if its parent group name is in this tuple.
LEDGERS_IN_OPENING_BAL_TOTAL = (
    "Bank Accounts",
    "Cash-in-hand",
    "Capital Account",
)
