"""Intentionally defective teaching seed; not shipped application code."""


def can_fit(capacity, occupied, incoming):
    """Return bool: the resulting occupancy may equal, but not exceed, capacity.

    Inputs are nonnegative plain integers with occupied <= capacity.
    Validation outside this domain and allocation side effects are out of scope.
    """
    return occupied + incoming < capacity
