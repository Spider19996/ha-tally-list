DOMAIN = "tally_list"

CONF_USER = "user"
CONF_DRINKS = "drinks"
CONF_DRINK = "drink"
CONF_PRICE = "price"
CONF_ICON = "icon"
CONF_ICONS = "icons"
CONF_FREE_AMOUNT = "free_amount"
CONF_EXCLUDED_USERS = "excluded_users"
CONF_OVERRIDE_USERS = "override_users"
CONF_PUBLIC_DEVICES = "public_devices"
CONF_USER_PIN = "user_pin"
CONF_USER_PINS = "user_pins"
CONF_CURRENCY = "currency"

CONF_ENABLE_FREE_DRINKS = "enable_free_drinks"
CONF_CASH_USER_NAME = "cash_user_name"
CONF_ENABLE_LOGGING = "enable_logging"
CONF_LOG_DRINKS = "log_drinks"
CONF_LOG_PRICE_CHANGES = "log_price_changes"
CONF_LOG_FREE_DRINKS = "log_free_drinks"

ATTR_USER = "user"
ATTR_DRINK = "drink"
ATTR_FREE_DRINK = "free_drink"
ATTR_COMMENT = "comment"
ATTR_PIN = "pin"
ATTR_AMOUNT = "amount"

SERVICE_ADD_DRINK = "add_drink"
SERVICE_REMOVE_DRINK = "remove_drink"
SERVICE_SET_DRINK = "set_drink"
SERVICE_RESET_COUNTERS = "reset_counters"
SERVICE_EXPORT_CSV = "export_csv"
SERVICE_SET_PIN = "set_pin"
SERVICE_ADD_CREDIT = "add_credit"
SERVICE_REMOVE_CREDIT = "remove_credit"
SERVICE_SET_CREDIT = "set_credit"

# Dedicated user name that exposes drink prices
PRICE_LIST_USER_DE = "Preisliste"
PRICE_LIST_USER_EN = "Price list"
PRICE_LIST_USERS = {PRICE_LIST_USER_DE, PRICE_LIST_USER_EN}

CASH_USER_DE = "Freigetränke"
CASH_USER_EN = "Free Drinks"
CASH_USER_SLUG = "free_drinks"


def get_cash_user_name(language: str | None) -> str:
    """Return localized cash user name."""
    if language and language.lower().startswith("de"):
        return CASH_USER_DE
    return CASH_USER_EN


def get_price_list_user(language: str | None) -> str:
    """Return localized price list user name."""
    if language and language.lower().startswith("de"):
        return PRICE_LIST_USER_DE
    return PRICE_LIST_USER_EN
