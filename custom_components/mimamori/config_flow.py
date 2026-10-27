"""Setup in the UI: the address of mimamori and a read-only API token."""
from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_API_TOKEN, CONF_URL, CONF_VERIFY_SSL
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from yarl import URL

from .api import (
    CannotConnect,
    InvalidAuth,
    MimamoriClient,
    NotMimamori,
    RateLimited,
    Redirected,
    normalize_url,
)
from .const import (
    CONF_SCAN_SECONDS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_SECONDS,
    MIN_SCAN_SECONDS,
    TOKEN_RE,
)

_LOGGER = logging.getLogger(__name__)

URL_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.URL))
TOKEN_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


def _schema(url: str = "", verify_ssl: bool = True) -> vol.Schema:
    return vol.Schema({
        vol.Required(CONF_URL, default=url): URL_SELECTOR,
        vol.Required(CONF_API_TOKEN): TOKEN_SELECTOR,
        vol.Required(CONF_VERIFY_SSL, default=verify_ssl): bool,
    })


class MimamoriConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _check(self, url: str, token: str, verify_ssl: bool) -> dict[str, str]:
        """Asks mimamori with these values; errors for the form, {} when they work."""
        if not TOKEN_RE.match(token):
            return {CONF_API_TOKEN: "invalid_token_format"}
        session = async_get_clientsession(self.hass, verify_ssl=verify_ssl)
        try:
            await MimamoriClient(session, url, token).summary()
        except InvalidAuth:
            return {"base": "invalid_auth"}
        except RateLimited:
            return {"base": "rate_limited"}
        except Redirected:
            return {CONF_URL: "redirected"}
        except NotMimamori:
            return {"base": "not_mimamori"}
        except CannotConnect:
            return {"base": "cannot_connect"}
        except Exception:  # noqa: BLE001 - shown as "unexpected error", details in the log
            _LOGGER.exception("Unexpected error while connecting to mimamori")
            return {"base": "unknown"}
        return {}

    def _read(self, user_input: dict[str, Any]) -> tuple[str, str, dict[str, str]]:
        token = user_input[CONF_API_TOKEN].strip()
        try:
            url = normalize_url(user_input[CONF_URL])
        except ValueError:
            return "", token, {CONF_URL: "invalid_url"}
        return url, token, {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None
                              ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            url, token, errors = self._read(user_input)
            if not errors:
                await self.async_set_unique_id(url.lower())
                self._abort_if_unique_id_configured()
                errors = await self._check(url, token, user_input[CONF_VERIFY_SSL])
            if not errors:
                return self.async_create_entry(
                    title=URL(url).host or "mimamori",
                    data={CONF_URL: url, CONF_API_TOKEN: token,
                          CONF_VERIFY_SSL: user_input[CONF_VERIFY_SSL]})
        return self.async_show_form(
            step_id="user", errors=errors,
            data_schema=self.add_suggested_values_to_schema(
                _schema(), {k: v for k, v in (user_input or {}).items() if k != CONF_API_TOKEN}))

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None
                                        ) -> ConfigFlowResult:
        """The token was revoked or replaced: ask for a new one."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            token = user_input[CONF_API_TOKEN].strip()
            errors = await self._check(entry.data[CONF_URL], token,
                                       entry.data.get(CONF_VERIFY_SSL, True))
            if not errors:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_API_TOKEN: token})
        return self.async_show_form(
            step_id="reauth_confirm", errors=errors,
            data_schema=vol.Schema({vol.Required(CONF_API_TOKEN): TOKEN_SELECTOR}),
            description_placeholders={"url": entry.data[CONF_URL]})

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None
                                     ) -> ConfigFlowResult:
        """A new address (e.g. now over HTTPS) or a new token."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            url, token, errors = self._read(user_input)
            if not errors:
                errors = await self._check(url, token, user_input[CONF_VERIFY_SSL])
            if not errors:
                return self.async_update_reload_and_abort(
                    entry, unique_id=url.lower(), title=URL(url).host or entry.title,
                    data_updates={CONF_URL: url, CONF_API_TOKEN: token,
                                  CONF_VERIFY_SSL: user_input[CONF_VERIFY_SSL]})
        return self.async_show_form(
            step_id="reconfigure", errors=errors,
            data_schema=_schema(entry.data[CONF_URL], entry.data.get(CONF_VERIFY_SSL, True)))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> MimamoriOptionsFlow:
        return MimamoriOptionsFlow()


class MimamoriOptionsFlow(OptionsFlow):
    """How often Home Assistant asks mimamori."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None
                              ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                data={CONF_SCAN_SECONDS: int(user_input[CONF_SCAN_SECONDS])})
        current = self.config_entry.options.get(
            CONF_SCAN_SECONDS, int(DEFAULT_SCAN_INTERVAL.total_seconds()))
        return self.async_show_form(step_id="init", data_schema=vol.Schema({
            vol.Required(CONF_SCAN_SECONDS, default=current): NumberSelector(
                NumberSelectorConfig(min=MIN_SCAN_SECONDS, max=MAX_SCAN_SECONDS, step=1,
                                     unit_of_measurement="s", mode=NumberSelectorMode.BOX)),
        }))
