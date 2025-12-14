import logging  # noqa: D100, EXE002, N999

from homeassistant.helpers import entity_registry
from homeassistant.helpers import area_registry

_LOGGER = logging.getLogger(__name__)

DOMAIN = "motion_sensor_groups"


class MotionSensorGrouper:
    """Class to group motion sensors by area."""

    def __init__(self, hass) -> None:  
        """Initialize the motion sensor grouper."""
        self.hass = hass

    async def create_sensor_groups(self) -> None:
        """Create groups of motion sensors by area."""
        # Get all areas from Home Assistant

        areas = area_registry.async_get(self.hass)

        # Get entity registry to find entities
        entities = entity_registry.async_get(self.hass)

        # Loop over each area and find associated motion sensors
        for area_id, area in areas.areas.items():
            # Find all motion sensors in the area
            motion_sensors = [
                entity.entity_id
                for entity in entities.entities.values()
                if (
                    entity.original_device_class in ("motion", "occupancy", "presence")
                    or entity.entity_id.startswith("media_player.")
                )
                and entity.area_id == area_id
            ]

            # if motion_sensors:
            group_name = f"group.motion_sensors_{area.name.lower().replace(' ', '_')}"
            await self._create_group(group_name, motion_sensors)

    async def create_security_sensor_group(self) -> None:
        """Create a group of motion sensors for security alarm."""
        # Get all areas from Home Assistant

        # Get entity registry to find light entities
        entities = entity_registry.async_get(self.hass)

        motion_sensors = [
            entity.entity_id
            for entity in entities.entities.values()
            if (entity.original_device_class in ("motion", "occupancy", "presence"))
            and entity.entity_id != "binary_sensor.security_motion_sensors_group"
            and entity.entity_id != "binary_sensor.security_motion_group_sensor"
            and entity.entity_id != "group.security_motion_sensors_group"
            and entity.labels is not None
            and not self.checkforlabel(entity.labels, "notforsecuritymonitoring")
        ]

        await self._create_group("group.security_motion_sensors_group", motion_sensors)

    def checkforlabel(self, labels, value_to_check) -> bool:
        """Check whether a label is in the list of labels."""

        # Handle potential null or empty values and convert to a clean list
        parsed_labels = [label for label in labels if label] if labels else []

        _LOGGER.debug(parsed_labels)

        # Check if the value is in parsed_labels
        if value_to_check in parsed_labels:
            _LOGGER.debug(f"'{value_to_check}' is in parsed_labels.")
            return True
        _LOGGER.debug(f"'{value_to_check}' is not in parsed_labels.")
        return False

    async def _create_group(self, group_name, entity_ids) -> None:  # noqa: ANN001
        """Create a group of entities in Home Assistant."""
        service_data = {
            "object_id": group_name.split(".")[-1],
            "name": group_name.split(".")[-1].replace("_", " ").title(),
            "entities": entity_ids,
        }

        # Call Home Assistant service to create the group
        await self.hass.services.async_call("group", "set", service_data, blocking=True)
        _LOGGER.debug(f"Group {group_name} created with entities: {entity_ids}")  # noqa: G004
