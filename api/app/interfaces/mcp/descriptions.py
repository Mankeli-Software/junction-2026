"""Tool descriptions the agents read. Placeholders for now: Jesse writes the real,
voice-oriented texts in #53, and this is the only file to edit for that.
"""

SEARCH_PRODUCTS = (
    "Search the catalogue by text, claims and category; returns a shortlist with price "
    "and availability."
)
GET_CUSTOMER_CONTEXT = "Get the caller's kitchen profile, exclusions and usual items."
SEARCH_RECIPES = "Search recipes by text, diet and occasion."
GET_RECIPE = "Get one recipe with its ingredients scaled to the given portions."
BUILD_QUOTE = (
    "Build a quote from all order lines at once; returns a decision, priced lines and text "
    "to speak."
)
UPDATE_QUOTE = "Answer a clarification or change the lines of a quote; returns a new quote."
REQUEST_CONFIRMATION = "Send the confirmation link for a ready quote to the account's own phone."
GET_ORDER_STATUS = "Get the status of a quote or order."
