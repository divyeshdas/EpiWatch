"""
Binary min-heap — array-backed priority queue.

Used as the frontier in Dijkstra (A3) and A* (A4).  Each entry is a
(priority, item) pair where priority is a float and item is an int node ID.

Heap property: every parent's priority ≤ its children's priorities.
The root (_data[0]) always holds the minimum-priority entry.

Array layout:
  root at index 0
  parent(i)      = (i - 1) // 2
  left child(i)  = 2 * i + 1
  right child(i) = 2 * i + 2

Time complexity:
  push    O(log n)  — append then sift-up at most ⌊log₂ n⌋ levels
  pop_min O(log n)  — swap root with tail, shrink, then sift-down
  peek    O(1)      — root is always at index 0
Space complexity: O(n)
"""


class MinHeap:
    """Array-backed binary min-heap keyed by float priority."""

    __slots__ = ("_data",)

    def __init__(self) -> None:
        self._data: list[tuple[float, int]] = []

    # ── public interface ──────────────────────────────────────────────────────

    def push(self, priority: float, item: int) -> None:
        """Append (priority, item) and restore heap order upwards.  O(log n)."""
        self._data.append((priority, item))
        self._sift_up(len(self._data) - 1)

    def pop_min(self) -> tuple[float, int]:
        """Remove and return the entry with the lowest priority.  O(log n)."""
        data = self._data
        # Swap root (the global minimum) with the last element so the minimum
        # can be removed in O(1); then sift the new root down to restore order.
        data[0], data[-1] = data[-1], data[0]
        entry = data.pop()
        if data:
            self._sift_down(0)
        return entry

    def peek(self) -> tuple[float, int]:
        """Return the minimum entry without removing it.  O(1)."""
        return self._data[0]

    def __len__(self) -> int:
        return len(self._data)

    def __bool__(self) -> bool:
        return bool(self._data)

    # ── internal helpers ──────────────────────────────────────────────────────

    def _sift_up(self, i: int) -> None:
        """Bubble element at index i up until the heap property holds."""
        data = self._data
        while i > 0:
            parent = (i - 1) // 2
            if data[i] < data[parent]:
                data[i], data[parent] = data[parent], data[i]
                i = parent
            else:
                break

    def _sift_down(self, i: int) -> None:
        """Push element at index i down until the heap property holds."""
        data = self._data
        n = len(data)
        while True:
            smallest = i
            left, right = 2 * i + 1, 2 * i + 2
            if left < n and data[left] < data[smallest]:
                smallest = left
            if right < n and data[right] < data[smallest]:
                smallest = right
            if smallest == i:
                break
            data[i], data[smallest] = data[smallest], data[i]
            i = smallest
