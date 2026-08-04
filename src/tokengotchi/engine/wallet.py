"""Currency wallet — tracks BITS and ECHOES balances."""

from __future__ import annotations


class Wallet:
    """Holds the player's BITS and ECHOES balances.

    Balances are non-negative integers. All spend operations return False
    (no-op) if the balance would go negative.
    """

    def __init__(self, bits: int = 0, echoes: int = 0) -> None:
        self.bits: int = max(0, int(bits))
        self.echoes: int = max(0, int(echoes))

    # ------------------------------------------------------------------
    # Earning
    # ------------------------------------------------------------------

    def add_bits(self, n: int) -> None:
        """Credit n BITS.  Called by the integration layer on token events."""
        if n < 0:
            raise ValueError(f"add_bits requires a non-negative value, got {n}")
        self.bits += n

    def add_echoes(self, n: int) -> None:
        """Credit n ECHOES.  Called by the integration layer on token events."""
        if n < 0:
            raise ValueError(f"add_echoes requires a non-negative value, got {n}")
        self.echoes += n

    # ------------------------------------------------------------------
    # Spending
    # ------------------------------------------------------------------

    def spend_bits(self, n: int) -> bool:
        """Deduct n BITS.

        Returns True on success, False if balance is insufficient (balance
        is left unchanged on failure).
        """
        if n < 0:
            raise ValueError(f"spend_bits requires a non-negative value, got {n}")
        if self.bits < n:
            return False
        self.bits -= n
        return True

    def spend_echoes(self, n: int) -> bool:
        """Deduct n ECHOES.

        Returns True on success, False if balance is insufficient (balance
        is left unchanged on failure).
        """
        if n < 0:
            raise ValueError(f"spend_echoes requires a non-negative value, got {n}")
        if self.echoes < n:
            return False
        self.echoes -= n
        return True

    def __repr__(self) -> str:
        return f"Wallet(bits={self.bits}, echoes={self.echoes})"
