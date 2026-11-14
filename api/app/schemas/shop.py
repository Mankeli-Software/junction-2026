"""The webshop's public catalogue (#118): the category tree and each leaf's top products.

Public, with no login. Nothing here carries a price or stock: those come only through the
agent tools (#56). Every product listed has a Valio image (#108).
"""

from .common import Localized, StrictModel


class ShopCategory(StrictModel):
    """A leaf category: one of the product file's categories."""

    id: str
    name: Localized
    # How many products the shop lists for it: those with an image, at most 20.
    product_count: int


class ShopGroup(StrictModel):
    """The second level of the shop tree, for example Fresh products > Cheese."""

    name: Localized
    categories: list[ShopCategory]


class ShopSection(StrictModel):
    """The top level of the shop tree, for example Fresh products."""

    name: Localized
    groups: list[ShopGroup]


class ShopCatalogue(StrictModel):
    """Every section that has at least one product to show, in the shop's order."""

    sections: list[ShopSection]


class ShopProduct(StrictModel):
    product_id: str
    name: Localized
    brand: str | None
    # From the product name, for example "1 l" or "1,5 kg"; null when the name has none.
    pack_size: str | None
    sales_unit: str
    # Base units in one sales unit: above 1, the product is sold by the case.
    units_per_sales_unit: int
    image_url: str


class ShopProducts(StrictModel):
    """A leaf category's top products, best first (#118)."""

    section: Localized
    group: Localized
    category: ShopCategory
    products: list[ShopProduct]
