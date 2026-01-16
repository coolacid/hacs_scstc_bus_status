"""Config flow for SCSTC Bus Status integration."""
from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries

from .const import DOMAIN


class MySensorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SCSTC Bus Status."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step.

        Presents a `type` option ("Cancelation" or "Bus") and an optional
        `bus_number`. Only allows one `Cancelation` entry to be created.
        """
        if user_input is None:
            # Hide Cancelation option if one already exists
            existing_types = [entry.data.get("type") for entry in self._async_current_entries()]
            options = [t for t in ("Cancelation", "Bus") if not (t == "Cancelation" and "Cancelation" in existing_types)]
            if not options:
                return self.async_abort(reason="no_options")

            schema = vol.Schema(
                {
                    vol.Required("type", default=options[0]): vol.In(options),
                    vol.Optional("bus_number"): str,
                }
            )
            return self.async_show_form(step_id="user", data_schema=schema)

        # Enforce only one Cancelation entry
        if user_input.get("type") == "Cancelation":
            for entry in self._async_current_entries():
                if entry.data.get("type") == "Cancelation":
                    return self.async_abort(reason="single_cancelation_allowed")

        # If type is Bus and no bus_number provided, ask for it explicitly
        if user_input.get("type") == "Bus" and not user_input.get("bus_number"):
            # store partial selection in flow context and ask for bus_number
            self.context["flow_user_input"] = user_input
            return await self.async_step_bus_number()

        # Build entry data and title
        if user_input.get("type") == "Cancelation":
            title = "Cancelation"
            data = {"type": "Cancelation"}
        else:
            bus_number = user_input.get("bus_number")
            title = f"Bus {bus_number}"
            data = {"type": "Bus", "bus_number": bus_number}

        return self.async_create_entry(title=title, data=data)

    async def async_step_bus_number(self, user_input=None):
        """Ask for the bus number when not provided initially."""
        if user_input is None:
            schema = vol.Schema({vol.Required("bus_number"): str})
            return self.async_show_form(step_id="bus_number", data_schema=schema)

        # Merge with previously stored flow data
        prior = self.context.get("flow_user_input", {})
        bus_number = user_input.get("bus_number")

        title = f"Bus {bus_number}"
        data = {"type": "Bus", "bus_number": bus_number}

        return self.async_create_entry(title=title, data=data)
