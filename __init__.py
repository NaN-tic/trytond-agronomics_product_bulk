# This file is part product_bulk module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from trytond.pool import Pool
from . import product
from . import stock
from . import production

module = 'agronomics_product_bulk'

def register():
    Pool.register(
        product.Product,
        product.ProductProductPackaging,
        product.Template,
        production.ProductionTemplate,
        stock.StockMove,
        module=module, type_='model')
