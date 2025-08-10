DOMAIN = "tally_list"

CONF_USER = "user"
CONF_DRINKS = "drinks"
CONF_DRINK = "drink"
CONF_PRICE = "price"
CONF_FREE_AMOUNT = "free_amount"
CONF_EXCLUDED_USERS = "excluded_users"
CONF_OVERRIDE_USERS = "override_users"
CONF_CURRENCY = "currency"

CONF_ENABLE_FREE_MARKS = "enable_free_marks"
CONF_CASH_USER_NAME = "cash_user_name"

ATTR_USER = "user"
ATTR_DRINK = "drink"
ATTR_FREE_MARK = "free_mark"
ATTR_COMMENT = "comment"

SERVICE_ADD_DRINK = "add_drink"
SERVICE_REMOVE_DRINK = "remove_drink"
SERVICE_ADJUST_COUNT = "adjust_count"
SERVICE_RESET_COUNTERS = "reset_counters"
SERVICE_EXPORT_CSV = "export_csv"

# Dedicated user name that exposes drink prices
PRICE_LIST_USER_DE = "Preisliste"
PRICE_LIST_USER_EN = "Price list"
# Default name for backward compatibility
PRICE_LIST_USER = PRICE_LIST_USER_DE
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
