"""Enumy używane w modelach."""

from enum import Enum


class VisitStatus(str, Enum):
    """Status wizyty."""
    DRAFT = "draft"
    COMPLETED = "completed"

    def __str__(self) -> str:
        return self.value

    @property
    def display_name(self) -> str:
        """Nazwa do wyświetlenia w UI."""
        return {
            VisitStatus.DRAFT: "Szkic",
            VisitStatus.COMPLETED: "Zakończona"
        }.get(self, self.value)
