from homeassistant.components.select import SelectEntityDescription
from homeassistant.const import EntityCategory

from custom_components.sonnenbatterie import SB_OPERATING_MODES


class SonnenbatterieSelectEntityDescription(SelectEntityDescription):


SELECT_ENTITIES = [
    SonnenbatterieSelectEntityDescription(
        key="EM_Operating_Mode",
        icon="mdi:solar-power",
        entity_category=EntityCategory.CONFIG,
        options=SB_OPERATING_MODES,
    ),

]
