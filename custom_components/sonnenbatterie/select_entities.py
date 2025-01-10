from dataclasses import dataclass
from enum import Enum
from typing import NamedTuple

from homeassistant.components.select import SelectEntityDescription, SelectEntity
from homeassistant.const import EntityCategory

from custom_components.sonnenbatterie import SB_OPERATING_MODES

class SelectEntry(NamedTuple):
    # the key to use for the select entity
    key: str = None
    # the section where the value is found in the coordinator
    section: str = None
    # the property name of the setting
    property: str = None
    # whether the value is writable or not
    writable: bool = None

class Tag(SelectEntry, Enum):
    def __hash__(self) -> int:
        return hash(self.key)
    def __str__(self) -> str:
        return self.key

    OPERATING_MODE = SelectEntry(
        key="operating_mode",
        section="configurations",
        property="EM_OperatingMode",
        writable=True,
    )

@dataclass(frozen=True,kw_only=True)
class SonnenbatterieSelectEntityDescription(SelectEntityDescription):
    tag: Tag = None
    section: str = None

SELECT_ENTITIES = [
    SonnenbatterieSelectEntityDescription(
        key=Tag.OPERATING_MODE.key,
        icon="mdi:solar-power",
        entity_category=EntityCategory.CONFIG,
        tag=Tag.OPERATING_MODE,
        options=["manual", "automatic", "timeofuse"],
    ),

]
