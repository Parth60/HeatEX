from __future__ import annotations

from dataclasses import dataclass

FRONT_HEADS = {
    "A": "Channel and removable cover",
    "B": "Bonnet (integral cover)",
    "C": "Channel integral with tubesheet and removable cover",
    "N": "Channel integral with tubesheet and removable cover",
    "D": "Special high-pressure closure",
}

SHELL_TYPES = {
    "E": "One-pass shell",
    "F": "Two-pass shell with longitudinal baffle",
    "G": "Split-flow shell",
    "H": "Double-split-flow shell",
    "J": "Divided-flow shell",
    "K": "Kettle reboiler shell",
    "X": "Cross-flow shell",
}

REAR_HEADS = {
    "L": "Fixed tubesheet rear head similar to A",
    "M": "Fixed tubesheet rear head similar to B",
    "N": "Fixed tubesheet rear head similar to N",
    "P": "Outside-packed floating head",
    "S": "Floating head with backing device",
    "T": "Pull-through floating head",
    "U": "U-tube bundle",
    "W": "Externally sealed floating tubesheet",
}

# Screening correction factors only. Production implementation should calculate F
# from the actual thermal arrangement / temperature program rather than use this table.
SHELL_F_SCREENING = {"E": 0.95, "F": 0.87, "G": 0.90, "H": 0.88, "J": 0.91, "K": 0.93, "X": 0.96}


@dataclass(frozen=True)
class TemaConfiguration:
    front: str
    shell: str
    rear: str

    @property
    def code(self) -> str:
        return f"{self.front}{self.shell}{self.rear}"

    def validate(self) -> None:
        if self.front not in FRONT_HEADS:
            raise ValueError(f"Unknown TEMA front head {self.front}")
        if self.shell not in SHELL_TYPES:
            raise ValueError(f"Unknown TEMA shell {self.shell}")
        if self.rear not in REAR_HEADS:
            raise ValueError(f"Unknown TEMA rear head {self.rear}")

    def description(self) -> dict[str, str]:
        self.validate()
        return {
            "code": self.code,
            "front": FRONT_HEADS[self.front],
            "shell": SHELL_TYPES[self.shell],
            "rear": REAR_HEADS[self.rear],
        }
