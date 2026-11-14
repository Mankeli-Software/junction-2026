"""Tool descriptions the agents read, one per agent tool (#53).

Every model client reads these: Gemini in the phone relay, the webshop chat, WebMCP browser
agents and Claude or ChatGPT connectors. They must agree with the S.I.MO system prompt
(`app.agent.prompt`), and also make sense to an outside agent that has no S.I.MO prompt.
Keep them short and in plain English. Never mention SMS or email: the demo link lands in
the phone inbox, and a real text message goes only to allowlisted numbers.
"""

SEARCH_PRODUCTS = (
    "Search the Valio Aimo catalogue by product words, optionally filtered by claims and a "
    "needed-by date; returns a shortlist with product_id, name, sales unit, gross price, stock "
    "status and the earliest available date. Optional: build_quote finds the products itself, "
    "so use this when the buyer asks what is available or what something costs, then order "
    "with build_quote."
)
GET_CUSTOMER_CONTEXT = (
    "Get the signed-in buyer's company name, kitchen exclusions, usual items (with product_id "
    "and usual quantity), account language and the masked phone number the confirmation link "
    "goes to. Call it at the start if you don't already have them. The engine applies the "
    "exclusions to every line by itself."
)
SEARCH_RECIPES = (
    "Search the 2,091 Valio Aimo recipes by a dish, an ingredient or a free description, in "
    "Finnish or English, by meaning and by words. Optional filters: diet tags, all required "
    '(Finnish such as "laktoositon", "gluteeniton", "maidoton", "vegaaninen", or '
    '"lactose_free", "gluten_free", "milk_free", "vegan"), and an occasion (such as '
    '"lounasruoka", "buffet", "joulu" or "lunch"). Diet words in q filter too, and portion '
    "counts in q are ignored. Returns recipe_ids, Finnish names, default portions and diet "
    "tags. Use it when the buyer orders for a dish or a menu, then get_recipe."
)
GET_RECIPE = (
    "Get one recipe scaled to the given number of portions: its ingredients (in Finnish) with "
    "amounts, and a product_id where an ingredient is linked to a product. To order it, send "
    "build_quote one line with recipe_ref {recipe_id, portions} and no ingredient_index, "
    "quantity the portions, unit piece and group the recipe name: the linked ingredients are "
    "ordered and the others are listed in not_ordered. The engine applies the kitchen's "
    "exclusions."
)
BUILD_QUOTE = (
    "Price the whole order. Call it once, with every line the buyer wants, only after they "
    'say the order is complete ("that\'s all") or ask for the price or a summary; never '
    "while they are still adding lines, and not after each line. In each line, text keeps "
    'the product words and any pack size the buyer said ("kevytmaito 1 l"), and product_id '
    "is only an id a tool returned for that product (a get_customer_context usual item, a "
    "search_products result or a recipe ingredient), never invented. A whole recipe is one "
    "line with recipe_ref (see get_recipe). Returns a decision (ready, needs_clarification or "
    "rejected), priced lines, flags, a clarification question or rejections, not_ordered "
    "(recipe ingredients the buyer gets elsewhere), and speak, a short summary in Finnish "
    "and English."
)
UPDATE_QUOTE = (
    "Answer the engine's clarification or change a quote's lines; returns a new quote that "
    "replaces the old one. Send the quote_id and the full line list with the same line_ids: "
    "for a clarification, the asked line gets the chosen option's product_id and the other "
    "lines stay as they were. Answer the clarification with this call, not by searching for "
    "products yourself."
)
REQUEST_CONFIRMATION = (
    "Send the confirmation link for a ready quote to the buyer's own phone, the number on the "
    "account; no recipient can be given. Call it only after the buyer clearly says yes to "
    "getting the link. Nothing is ordered until the buyer confirms through the link, so never "
    "say the order is placed."
)
GET_ORDER_STATUS = (
    "Get the status of one of the buyer's quotes or orders by quote_id: ready, "
    "pending_confirmation, confirmed (with the order number), cancelled, expired, or void "
    "(with the quote that replaced it)."
)
